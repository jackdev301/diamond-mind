"""Phase 3: verify ORM models register and round-trip through SQLite."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

import app.models  # noqa: F401 — registers models on Base.metadata
from app.database import Base
from app.models import (
    BetEvaluationRow,
    BullpenFatigueRow,
    Game,
    ModelRun,
    OddsSnapshotRow,
    PitcherGameLog,
    Player,
    PlayerGameLog,
    RelieverUsageRow,
    Team,
    TeamFormWindowRow,
    TeamGameLog,
)


EXPECTED_TABLES = {
    "teams",
    "players",
    "games",
    "team_game_logs",
    "player_game_logs",
    "pitcher_game_logs",
    "team_form_windows",
    "player_form_windows",
    "pitcher_form_windows",
    "reliever_form_windows",
    "reliever_usage",
    "bullpen_fatigue",
    "odds_snapshots",
    "weather_snapshots",
    "model_runs",
    "bet_evaluations",
    "obsidian_exports",
}


@pytest.fixture
def memory_engine():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


def test_all_expected_tables_registered():
    actual = set(Base.metadata.tables.keys())
    assert EXPECTED_TABLES <= actual, f"Missing tables: {EXPECTED_TABLES - actual}"


def test_create_and_query_round_trip(memory_engine):
    with Session(memory_engine) as session:
        team = Team(id=143, abbr="PHI", name="Philadelphia Phillies", league="NL", division="NL East")
        opp = Team(id=121, abbr="NYM", name="New York Mets", league="NL", division="NL East")
        pitcher = Player(id=605400, full_name="Zack Wheeler", primary_position="P", throws="R")
        session.add_all([team, opp, pitcher])
        session.flush()

        game = Game(
            id=778001,
            game_date=date(2026, 5, 15),
            home_team_id=143,
            away_team_id=121,
            venue="Citizens Bank Park",
            status="scheduled",
        )
        session.add(game)
        session.flush()

        session.add(
            PitcherGameLog(
                game_id=778001,
                pitcher_id=605400,
                team_id=143,
                game_date=date(2026, 5, 14),
                role="starter",
                started=True,
                innings_pitched=7.0,
                pitches=98,
                strikeouts=9,
                walks=1,
                earned_runs=2,
            )
        )
        session.commit()

        fetched = session.scalar(select(Team).where(Team.abbr == "PHI"))
        assert fetched is not None
        assert fetched.name == "Philadelphia Phillies"

        logs = session.scalars(select(PitcherGameLog)).all()
        assert len(logs) == 1
        assert logs[0].innings_pitched == 7.0


def test_form_window_unique_index(memory_engine):
    with Session(memory_engine) as session:
        session.add(Team(id=143, abbr="PHI", name="Phillies"))
        session.flush()
        session.add(
            TeamFormWindowRow(
                team_id=143,
                window="l10",
                as_of_date=date(2026, 5, 15),
                games=10,
                runs_per_game=4.8,
                runs_allowed_per_game=3.9,
                team_ops=0.742,
                record_wins=6,
                record_losses=4,
                trend_label="heating_up",
            )
        )
        session.commit()

        # Duplicate (team_id, window, as_of_date) must fail.
        session.add(
            TeamFormWindowRow(
                team_id=143,
                window="l10",
                as_of_date=date(2026, 5, 15),
                games=10,
                runs_per_game=4.8,
                runs_allowed_per_game=3.9,
                team_ops=0.742,
                record_wins=6,
                record_losses=4,
                trend_label="heating_up",
            )
        )
        with pytest.raises(Exception):
            session.commit()


def test_unrelated_models_coexist(memory_engine):
    """Sanity check that bullpen, odds, and reports tables also build."""
    with Session(memory_engine) as session:
        session.add(Team(id=143, abbr="PHI", name="Phillies"))
        session.add(Player(id=1, full_name="Test Reliever"))
        session.add(Game(id=1, game_date=date(2026, 5, 15), home_team_id=143, away_team_id=143))
        session.flush()

        run = ModelRun(run_type="daily", started_at=datetime.now(timezone.utc), status="ok")
        session.add(run)
        session.add(
            RelieverUsageRow(
                pitcher_id=1, team_id=143, game_id=1, game_date=date(2026, 5, 14),
                role="closer", pitches=18, innings=1.0,
            )
        )
        session.add(
            BullpenFatigueRow(team_id=143, as_of_date=date(2026, 5, 15), fatigue_score=42.0)
        )
        session.add(
            OddsSnapshotRow(
                game_id=1, bookmaker="draftkings", market="moneyline",
                selection="home", american_odds=-130,
                captured_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        assert session.scalar(select(BullpenFatigueRow)).fatigue_score == 42.0
