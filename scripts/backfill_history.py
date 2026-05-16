"""Backfill historical MLB game data from the Stats API.

Iterates a date range, fetches the schedule for each date, and ingests
completed box scores. Safe to re-run — all upserts are idempotent.

Usage:
    python scripts/backfill_history.py --start 2026-04-01 --end 2026-05-14
    python scripts/backfill_history.py --start 2026-04-01  # ends yesterday
    python scripts/backfill_history.py --days 30           # last N days
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, timedelta

from sqlalchemy import select

from app.database import SessionLocal
from app.features.recent_form import (
    WindowKey,
    build_team_form_window,
    upsert_team_form_window,
)
from app.ingestion.mlb_stats_api import (
    MLBStatsClient,
    ingest_boxscore,
    ingest_schedule,
)
from app.models.entities import Team
from app.models.games import Game

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("backfill_history")

# Polite rate limit: sleep this many seconds between date fetches.
_DATE_PAUSE = 0.5


def _date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def backfill(
    start: date,
    end: date,
    recompute_form: bool = False,
    pause: float = _DATE_PAUSE,
) -> None:
    log.info("Backfill %s → %s (%d days)", start, end, (end - start).days + 1)

    with MLBStatsClient() as client:
        with SessionLocal() as session:
            for game_date in _date_range(start, end):
                try:
                    pks = ingest_schedule(session, client, game_date)
                    session.flush()

                    # Only ingest box scores for Final games on this date.
                    completed = session.execute(
                        select(Game.id).where(
                            Game.status.in_(["Final", "Game Over", "Completed Early"]),
                            Game.game_date == game_date,
                        )
                    ).scalars().all()

                    for pk in completed:
                        try:
                            ingest_boxscore(session, client, pk, game_date)
                        except Exception as exc:
                            log.warning("Box score failed game=%d date=%s: %s", pk, game_date, exc)

                    session.commit()
                    log.info("%s: %d scheduled, %d completed", game_date, len(pks), len(completed))

                except Exception as exc:
                    log.error("Failed date %s: %s", game_date, exc)
                    session.rollback()

                time.sleep(pause)

            if recompute_form:
                _recompute_team_form(session, as_of=end)


def _recompute_team_form(session, *, as_of: date) -> None:
    log.info("Recomputing team form windows as of %s", as_of)
    team_ids = list(session.execute(select(Team.id)).scalars())
    for tid in team_ids:
        for window in (WindowKey.SEASON, WindowKey.L20, WindowKey.L10, WindowKey.L5):
            w = build_team_form_window(session, team_id=tid, window=window, as_of_date=as_of)
            if w is not None:
                upsert_team_form_window(session, w)
    session.commit()
    log.info("Form windows committed for %d teams.", len(team_ids))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--days", type=int, help="Backfill the last N days.")
    group.add_argument("--start", help="Start date YYYY-MM-DD (requires --end or defaults end to yesterday).")
    parser.add_argument("--end", help="End date YYYY-MM-DD. Defaults to yesterday.")
    parser.add_argument(
        "--recompute-form", action="store_true",
        help="After ingestion, recompute team form windows as of --end date.",
    )
    parser.add_argument(
        "--pause", type=float, default=_DATE_PAUSE,
        help="Seconds to sleep between dates (default 0.5).",
    )
    args = parser.parse_args()

    yesterday = date.today() - timedelta(days=1)

    if args.days:
        end = yesterday
        start = end - timedelta(days=args.days - 1)
    elif args.start:
        try:
            start = date.fromisoformat(args.start)
        except ValueError:
            print(f"Invalid --start: {args.start}", file=sys.stderr)
            sys.exit(1)
        end = date.fromisoformat(args.end) if args.end else yesterday
    else:
        parser.print_help()
        sys.exit(1)

    if start > end:
        print(f"--start {start} is after --end {end}", file=sys.stderr)
        sys.exit(1)

    backfill(start, end, recompute_form=args.recompute_form, pause=args.pause)


if __name__ == "__main__":
    main()
