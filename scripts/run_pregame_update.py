"""Daily pregame update.

Fetches today's schedule, ingests any completed-game box scores from
yesterday, and recomputes team/player/bullpen form windows for all
active teams. Designed to be run once per day before the first pitch.

Usage:
    python scripts/run_pregame_update.py [--date 2026-05-15] [--dry-run]
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date, timedelta

from sqlalchemy import select

from app.config import get_settings
from app.database import SessionLocal
from app.features.recent_form import (
    WindowKey,
    build_bullpen_state,
    build_hitter_form_window,
    build_starter_form_window,
    build_team_form_window,
    upsert_hitter_form_window,
    upsert_team_form_window,
)
from app.ingestion.mlb_stats_api import (
    MLBStatsClient,
    ingest_boxscore,
    ingest_schedule,
)
from app.models.entities import Player, Team
from app.models.games import Game

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("run_pregame_update")


def _active_team_ids(session) -> list[int]:
    return list(session.execute(select(Team.id)).scalars())


def _compute_team_windows(session, team_id: int, as_of: date) -> None:
    for window in (WindowKey.SEASON, WindowKey.L20, WindowKey.L10, WindowKey.L5):
        w = build_team_form_window(session, team_id=team_id, window=window, as_of_date=as_of)
        if w is not None:
            upsert_team_form_window(session, w)


def _compute_player_windows(session, as_of: date) -> None:
    player_ids = list(
        session.execute(
            select(Player.id).where(Player.primary_position != "P")
        ).scalars()
    )
    for pid in player_ids:
        for window in (WindowKey.SEASON, WindowKey.L20, WindowKey.L10, WindowKey.L5):
            w = build_hitter_form_window(session, player_id=pid, window=window, as_of_date=as_of)
            if w is not None:
                upsert_hitter_form_window(session, w)


def _compute_starter_windows(session, as_of: date) -> None:
    pitcher_ids = list(
        session.execute(
            select(Player.id).where(Player.primary_position == "P")
        ).scalars()
    )
    for pid in pitcher_ids:
        for window in (WindowKey.SEASON, WindowKey.LAST_10_STARTS, WindowKey.LAST_5_STARTS):
            w = build_starter_form_window(
                session, pitcher_id=pid, window=window, as_of_date=as_of
            )
            if w is not None:
                _upsert_starter(session, w)


def _upsert_starter(session, w) -> None:
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert

    from app.models.players import PitcherFormWindowRow
    stmt = sqlite_insert(PitcherFormWindowRow).values(
        pitcher_id=w.pitcher_id,
        window=w.window.value,
        as_of_date=w.as_of_date,
        starts=w.starts,
        innings_pitched=w.innings_pitched,
        era=w.era,
        whip=w.whip,
        k_per_9=w.k_per_9,
        bb_per_9=w.bb_per_9,
        hr_per_9=w.hr_per_9,
        avg_innings_per_start=w.avg_innings_per_start,
        avg_pitches_per_start=w.avg_pitches_per_start,
        trend_label=w.trend_label.value,
        insufficient_sample=w.insufficient_sample,
    ).on_conflict_do_update(
        index_elements=["pitcher_id", "window", "as_of_date"],
        set_=dict(
            starts=w.starts,
            innings_pitched=w.innings_pitched,
            era=w.era,
            whip=w.whip,
            trend_label=w.trend_label.value,
        ),
    )
    session.execute(stmt)


def _ingest_completed_games(session, client: MLBStatsClient, yesterday: date) -> int:
    pks = ingest_schedule(session, client, yesterday)
    session.flush()

    completed = session.execute(
        select(Game.id, Game.game_date).where(
            Game.status.in_(["Final", "Game Over", "Completed Early"]),
            Game.game_date == yesterday,
        )
    ).all()

    ingested = 0
    for (pk, gdate) in completed:
        try:
            ingest_boxscore(session, client, pk, gdate)
            ingested += 1
        except Exception as exc:
            log.warning("Failed to ingest box score game=%d: %s", pk, exc)
    return ingested


def run(as_of: date, dry_run: bool = False) -> None:
    settings = get_settings()
    yesterday = as_of - timedelta(days=1)

    log.info("Pregame update for %s (yesterday=%s, dry_run=%s)", as_of, yesterday, dry_run)

    with MLBStatsClient() as client:
        with SessionLocal() as session:
            # 1. Fetch today's schedule so probable pitchers are populated.
            today_pks = ingest_schedule(session, client, as_of)
            log.info("Fetched %d games for %s", len(today_pks), as_of)

            # 2. Ingest completed games from yesterday.
            if not dry_run:
                ingested = _ingest_completed_games(session, client, yesterday)
                log.info("Ingested %d completed box scores from %s", ingested, yesterday)

            # 3. Recompute form windows for all teams.
            team_ids = _active_team_ids(session)
            log.info("Recomputing form windows for %d teams", len(team_ids))
            if not dry_run:
                for tid in team_ids:
                    _compute_team_windows(session, tid, as_of)
                log.info("Team form windows done.")

                # 4. Recompute player (hitter) form windows.
                _compute_player_windows(session, as_of)
                log.info("Hitter form windows done.")

                # 5. Recompute starter form windows.
                _compute_starter_windows(session, as_of)
                log.info("Starter form windows done.")

                # 6. Build BullpenState snapshots for each team.
                bullpen_count = 0
                for tid in team_ids:
                    bs = build_bullpen_state(session, team_id=tid, as_of_date=as_of)
                    if bs is not None:
                        bullpen_count += 1
                log.info("BullpenState built for %d teams.", bullpen_count)

                session.commit()
                log.info("All changes committed.")
            else:
                log.info("[dry-run] skipping DB writes.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        default=date.today().isoformat(),
        help="Run as if today is this date (YYYY-MM-DD). Defaults to today.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch schedule only; skip DB writes.",
    )
    args = parser.parse_args()

    try:
        run_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"Invalid date: {args.date}", file=sys.stderr)
        sys.exit(1)

    run(run_date, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
