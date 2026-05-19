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
import os
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
    ingest_roster,
    ingest_schedule,
    ingest_teams,
)
from app.ingestion.odds_api import fetch_events, fetch_odds, match_event_id, is_available as odds_available
from app.ingestion.venue_coords import get_coords
from app.ingestion.weather_api import fetch_weather
from app.models.entities import Player, Team
from app.models.games import Game, TeamGameLog
from app.models.odds import OddsSnapshotRow, WeatherSnapshotRow

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("run_pregame_update")

DEFAULT_HISTORY_DAYS = int(os.environ.get("PREGAME_HISTORY_DAYS", "60"))


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
    total = len(player_ids)
    log.info("Computing hitter windows for %d players…", total)
    for i, pid in enumerate(player_ids, 1):
        for window in (WindowKey.SEASON, WindowKey.L20, WindowKey.L10, WindowKey.L5):
            w = build_hitter_form_window(session, player_id=pid, window=window, as_of_date=as_of)
            if w is not None:
                upsert_hitter_form_window(session, w)
        if i % 50 == 0 or i == total:
            log.info("  Hitters: %d/%d done (%.0f%%)", i, total, 100 * i / total)


def _compute_starter_windows(session, as_of: date) -> None:
    pitcher_ids = list(
        session.execute(
            select(Player.id).where(Player.primary_position == "P")
        ).scalars()
    )
    total = len(pitcher_ids)
    log.info("Computing starter windows for %d pitchers…", total)
    for i, pid in enumerate(pitcher_ids, 1):
        for window in (WindowKey.SEASON, WindowKey.LAST_10_STARTS, WindowKey.LAST_5_STARTS):
            w = build_starter_form_window(
                session, pitcher_id=pid, window=window, as_of_date=as_of
            )
            if w is not None:
                _upsert_starter(session, w)
        if i % 25 == 0 or i == total:
            log.info("  Starters: %d/%d done (%.0f%%)", i, total, 100 * i / total)


def _upsert_starter(session, w) -> None:
    from app.models.players import PitcherFormWindowRow

    existing = session.scalar(
        select(PitcherFormWindowRow).where(
            PitcherFormWindowRow.pitcher_id == w.pitcher_id,
            PitcherFormWindowRow.window == w.window.value,
            PitcherFormWindowRow.as_of_date == w.as_of_date,
        )
    )
    fields = dict(
        starts=w.starts,
        innings_pitched=w.innings_pitched,
        era=w.era,
        fip=w.fip,
        babip=w.babip,
        whip=w.whip,
        k_per_9=w.k_per_9,
        bb_per_9=w.bb_per_9,
        hr_per_9=w.hr_per_9,
        avg_innings_per_start=w.avg_innings_per_start,
        avg_pitches_per_start=w.avg_pitches_per_start,
        trend_label=w.trend_label.value,
        insufficient_sample=w.insufficient_sample,
    )
    if existing is None:
        session.add(PitcherFormWindowRow(
            pitcher_id=w.pitcher_id,
            window=w.window.value,
            as_of_date=w.as_of_date,
            **fields,
        ))
    else:
        for k, v in fields.items():
            setattr(existing, k, v)


def _ingest_odds_and_weather(session, today_games: list, as_of: date) -> None:
    """Fetch odds and weather for today's games and persist snapshots."""
    from datetime import datetime, timezone
    has_odds = odds_available()
    if not has_odds:
        log.info("ODDS_API_KEY not set — skipping odds fetch.")

    for game in today_games:
        game_id = game.id
        venue = game.venue or ""
        game_time = game.game_time_utc or datetime(as_of.year, as_of.month, as_of.day, 19, 5, tzinfo=timezone.utc)

        # Weather
        coords = get_coords(venue)
        lat, lon = (coords if coords else (None, None))
        weather = fetch_weather(game_id, venue, game_time, lat=lat, lon=lon)
        if weather:
            session.add(WeatherSnapshotRow(
                game_id=game_id,
                temperature_f=weather.temperature_f,
                wind_speed_mph=weather.wind_speed_mph,
                wind_direction_deg=weather.wind_direction_deg,
                precipitation_chance=weather.precipitation_chance,
                humidity_pct=weather.humidity_pct,
                is_dome=weather.is_dome,
                captured_at=weather.captured_at,
            ))

        # Odds — resolve event_id via Odds API events list, then fetch
        if has_odds and game.odds_event_id:
            snapshots = fetch_odds(game_id, game.odds_event_id)
            for snap in snapshots:
                session.add(OddsSnapshotRow(
                    game_id=game_id,
                    bookmaker=snap.bookmaker,
                    market=snap.market,
                    selection=snap.selection,
                    american_odds=snap.american_odds,
                    line=snap.line,
                    captured_at=snap.captured_at,
                ))
            if snapshots:
                log.info("Saved %d odds snapshots for game %d.", len(snapshots), game_id)

    session.flush()
    log.info("Weather snapshots saved for %d games.", len(today_games))


def _map_odds_event_ids(session, as_of: date) -> None:
    """Fetch Odds API events for today and store event_ids on Game rows."""
    events = fetch_events(as_of)
    if not events:
        log.info("No Odds API events returned for %s.", as_of)
        return
    games = session.execute(
        select(Game).where(Game.game_date == as_of)
    ).scalars().all()
    mapped = 0
    for game in games:
        if game.odds_event_id:
            continue
        home_team = session.get(Team, game.home_team_id)
        away_team = session.get(Team, game.away_team_id)
        if not home_team or not away_team:
            continue
        event_id = match_event_id(events, home_team.abbr, away_team.abbr)
        if event_id:
            game.odds_event_id = event_id
            mapped += 1
    session.flush()
    log.info("Mapped odds event_ids for %d/%d games.", mapped, len(games))


def _date_range(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _ingest_completed_games(
    session,
    client: MLBStatsClient,
    game_date: date,
    game_type: str | None = "R",
    force: bool = False,
) -> int:
    pks = ingest_schedule(session, client, game_date, game_type=game_type)
    session.flush()

    completed = session.execute(
        select(Game.id, Game.game_date).where(
            Game.status.in_(["Final", "Game Over", "Completed Early"]),
            Game.game_date == game_date,
        )
    ).all()

    # Find which game_ids already have box score data so we can skip them.
    # A game has a box score iff it has at least one TeamGameLog row.
    if not force and completed:
        completed_ids = {pk for (pk, _) in completed}
        already_done = set(
            session.execute(
                select(TeamGameLog.game_id).where(
                    TeamGameLog.game_id.in_(completed_ids)
                ).distinct()
            ).scalars()
        )
    else:
        already_done = set()

    ingested = 0
    skipped = 0
    for (pk, gdate) in completed:
        if pk in already_done:
            skipped += 1
            continue
        try:
            ingest_boxscore(session, client, pk, gdate)
            ingested += 1
        except Exception as exc:
            log.warning("Failed to ingest box score game=%d: %s", pk, exc)

    if skipped:
        log.debug("Skipped %d already-ingested box scores for %s.", skipped, game_date)
    return ingested


def _ingest_completed_history(
    session,
    client: MLBStatsClient,
    *,
    start: date,
    end: date,
    force: bool = False,
) -> int:
    """Ingest completed games over a date range before form windows are built.

    Games whose box scores are already in the DB are skipped unless `force=True`.
    On a warm DB this means only genuinely new completions hit the network —
    typically 0 games for dates older than yesterday.
    """
    if start > end:
        return 0

    total = 0
    days = (end - start).days + 1
    log.info("Checking completed games %s → %s (%d days, force=%s)", start, end, days, force)
    for i, game_date in enumerate(_date_range(start, end), 1):
        ingested = _ingest_completed_games(session, client, game_date, force=force)
        total += ingested
        if ingested or i % 10 == 0:
            log.info("  History: %s (%d/%d) ingested %d new box scores", game_date, i, days, ingested)
    return total


def _auto_track_picks(session, as_of: date) -> None:
    """Log all non-PASS picks for the date with Kelly-derived units (idempotent)."""
    import httpx as _httpx
    import os as _os

    port = _os.environ.get("PORT", "8000")
    url = f"http://localhost:{port}/tracker/auto-track?game_date={as_of.isoformat()}"
    try:
        resp = _httpx.post(url, timeout=60)
        if resp.is_success:
            data = resp.json()
            log.info(
                "Auto-track: +%d new picks logged, %d already tracked.",
                data.get("created", 0), data.get("skipped", 0),
            )
        else:
            log.warning("Auto-track call returned %s: %s", resp.status_code, resp.text[:200])
    except Exception as exc:
        log.warning("Auto-track skipped (backend not running?): %s", exc)


def run(as_of: date, dry_run: bool = False, history_days: int = DEFAULT_HISTORY_DAYS, force_reingest: bool = False) -> None:
    settings = get_settings()
    yesterday = as_of - timedelta(days=1)

    log.info(
        "Pregame update for %s (yesterday=%s, dry_run=%s, history_days=%d, force_reingest=%s)",
        as_of,
        yesterday,
        dry_run,
        history_days,
        force_reingest,
    )

    with MLBStatsClient() as client:
        with SessionLocal() as session:
            # 0. Ensure teams and rosters are seeded (idempotent upserts).
            ingest_teams(session, client)
            team_ids_for_roster = _active_team_ids(session)
            for tid in team_ids_for_roster:
                ingest_roster(session, client, tid)
            session.flush()
            log.info("Rosters seeded for %d teams.", len(team_ids_for_roster))

            # 1. Fetch today's schedule so probable pitchers are populated.
            today_pks = ingest_schedule(session, client, as_of, game_type="R")
            log.info("Fetched %d games for %s", len(today_pks), as_of)

            # 1b. Map Odds API event_ids to today's games (requires key).
            if odds_available():
                _map_odds_event_ids(session, as_of)

            # 2. Ingest completed games over a rolling history window.
            # A fresh Render/Postgres DB otherwise has only yesterday's games,
            # which makes "season", L20, L10, and starter windows nonsense.
            if not dry_run:
                history_start = max(date(as_of.year, 3, 1), as_of - timedelta(days=max(1, history_days) - 1))
                ingested = _ingest_completed_history(
                    session,
                    client,
                    start=history_start,
                    end=yesterday,
                    force=force_reingest,
                )
                log.info("Ingested %d completed box scores from %s through %s", ingested, history_start, yesterday)

            # 3. Recompute form windows for all teams.
            team_ids = _active_team_ids(session)
            log.info("Recomputing form windows for %d teams", len(team_ids))
            if not dry_run:
                for i, tid in enumerate(team_ids, 1):
                    _compute_team_windows(session, tid, as_of)
                    log.info("  Teams: %d/%d done", i, len(team_ids))
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

                # 7. Fetch weather (and odds if key present) for today's games.
                today_games = session.execute(
                    select(Game).where(Game.game_date == as_of)
                ).scalars().all()
                _ingest_odds_and_weather(session, today_games, as_of)

                session.commit()
                log.info("All changes committed.")

                # 8. Auto-track all non-PASS picks for today.
                _auto_track_picks(session, as_of)
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
    parser.add_argument(
        "--history-days",
        type=int,
        default=DEFAULT_HISTORY_DAYS,
        help=f"Rolling history window to check for missing box scores (default: {DEFAULT_HISTORY_DAYS}). "
             "On a warm DB, already-ingested games are skipped automatically.",
    )
    parser.add_argument(
        "--force-reingest",
        action="store_true",
        help="Re-fetch and upsert box scores even for games already in the DB. "
             "Use when you suspect bad data was ingested.",
    )
    args = parser.parse_args()

    try:
        run_date = date.fromisoformat(args.date)
    except ValueError:
        print(f"Invalid date: {args.date}", file=sys.stderr)
        sys.exit(1)

    run(run_date, dry_run=args.dry_run, history_days=args.history_days, force_reingest=args.force_reingest)


if __name__ == "__main__":
    main()
