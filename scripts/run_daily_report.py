"""Generate today's daily markdown report and save to obsidian_vault."""
from __future__ import annotations

import logging
import sys
from datetime import date

from sqlalchemy import select

from app.database import SessionLocal
from app.features.bullpen_vulnerability import score_bullpen
from app.features.recent_form import build_bullpen_state, build_starter_form_window
from app.models.entities import Team
from app.models.games import Game
from datetime import datetime

from app.contracts import (
    GameContext,
    WindowKey,
)
from app.features.recent_form import build_team_form_window
from app.reports.daily_report import GameBundle, generate_daily_report
from app.obsidian.vault_writer import export_all

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s — %(message)s")
log = logging.getLogger("run_daily_report")


def _build_bundle(db, game: Game, report_date: date):
    home_team = db.get(Team, game.home_team_id)
    away_team = db.get(Team, game.away_team_id)

    def _form(team_id, window):
        return build_team_form_window(db, team_id=team_id, window=window, as_of_date=report_date)

    def _starter(pitcher_id):
        if pitcher_id is None:
            return None
        return build_starter_form_window(
            db, pitcher_id=pitcher_id,
            window=WindowKey.LAST_5_STARTS, as_of_date=report_date,
        )

    def _bullpen(team_id):
        state = build_bullpen_state(db, team_id=team_id, as_of_date=report_date)
        return score_bullpen(state) if state else None

    ctx = GameContext(
        game_id=game.id,
        game_date=report_date,
        game_time_utc=game.game_time_utc if hasattr(game, "game_time_utc") and game.game_time_utc else datetime.utcnow(),
        home_team_id=game.home_team_id,
        away_team_id=game.away_team_id,
        home_team_abbr=home_team.abbr if home_team else "UNK",
        away_team_abbr=away_team.abbr if away_team else "UNK",
        venue=game.venue or "",
        is_doubleheader=game.is_doubleheader if hasattr(game, "is_doubleheader") else False,
        game_number=game.game_number if hasattr(game, "game_number") else 1,
        home_probable_starter_id=game.home_probable_starter_id,
        away_probable_starter_id=game.away_probable_starter_id,
    )

    return GameBundle(
        context=ctx,
        home_bullpen=_bullpen(game.home_team_id),
        away_bullpen=_bullpen(game.away_team_id),
        home_starter=_starter(game.home_probable_starter_id),
        away_starter=_starter(game.away_probable_starter_id),
        home_form=_form(game.home_team_id, WindowKey.L10),
        away_form=_form(game.away_team_id, WindowKey.L10),
        odds=[],
        weather=None,
    )


def main():
    report_date = date.today()
    log.info(f"Generating report for {report_date}")

    with SessionLocal() as db:
        games = db.execute(
            select(Game).where(Game.game_date == report_date)
        ).scalars().all()

    if not games:
        log.warning(f"No games found for {report_date}")
        sys.exit(0)

    log.info(f"Building bundles for {len(games)} games")
    with SessionLocal() as db:
        bundles = [_build_bundle(db, g, report_date) for g in games]

    markdown = generate_daily_report(report_date, bundles)
    paths = export_all(report_date, bundles)

    log.info(f"Report written: {paths.get('daily_report')}")
    log.info(f"Game notes: {len(paths.get('game_notes', []))}")
    log.info(f"Bullpen notes: {len(paths.get('bullpen_notes', []))}")


if __name__ == "__main__":
    main()
