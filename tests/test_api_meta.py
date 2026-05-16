"""Tests for meta/admin endpoints — health, cache, model constants, slate, context."""

from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import _get_db, _ANALYSIS_CACHE, app
from app.database import Base
from app.models.entities import Player, Team
from app.models.games import Game, PitcherGameLog, PlayerGameLog, TeamGameLog


@pytest.fixture
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as session:
        session.add(Team(id=110, abbr="BAL", name="Orioles", league="AL", division="East"))
        session.add(Team(id=111, abbr="BOS", name="Red Sox", league="AL", division="East"))
        session.add(
            Player(
                id=500,
                full_name="Test Pitcher",
                primary_position="P",
                bats="R",
                throws="R",
                current_team_id=110,
            )
        )
        session.add(
            Game(
                id=10,
                game_date=date(2026, 5, 15),
                game_time_utc=datetime(2026, 5, 15, 23, 5),
                home_team_id=110,
                away_team_id=111,
                venue="Oriole Park at Camden Yards",
                status="Preview",
                home_score=None,
                away_score=None,
                is_doubleheader=False,
                game_number=1,
                home_probable_starter_id=500,
                away_probable_starter_id=None,
                odds_event_id=None,
            )
        )
        session.add(
            TeamGameLog(
                game_id=10,
                team_id=110,
                game_date=date(2026, 5, 15),
                runs=4,
                runs_allowed=2,
                hits=9,
                errors=0,
                is_home=True,
                won=True,
            )
        )
        session.add(
            PitcherGameLog(
                game_id=10,
                pitcher_id=500,
                team_id=110,
                game_date=date(2026, 5, 15),
                role="starter",
                started=True,
                innings_pitched=6.0,
                batters_faced=22,
                hits_allowed=4,
                earned_runs=2,
                walks=1,
                strikeouts=8,
                home_runs_allowed=1,
                pitches=88,
            )
        )
        session.commit()

    def override_db():
        with Session() as session:
            yield session

    app.dependency_overrides[_get_db] = override_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


# ── /health ────────────────────────────────────────────────────────────────────

def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "version" in data


def test_health_cache_control(client):
    res = client.get("/health")
    cc = res.headers.get("cache-control", "")
    assert "no-store" in cc


def test_health_has_timing_header(client):
    res = client.get("/health")
    assert "x-response-time" in res.headers


# ── /health/detailed ──────────────────────────────────────────────────────────

def test_health_detailed(client):
    res = client.get("/health/detailed")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert "records" in data
    assert "freshness" in data
    assert "cache" in data
    assert data["records"]["games"] >= 1


# ── /cache/clear ──────────────────────────────────────────────────────────────

def test_cache_clear(client):
    res = client.post("/cache/clear")
    assert res.status_code == 200
    data = res.json()
    assert "evicted" in data
    assert isinstance(data["evicted"], int)


# ── /model/constants ──────────────────────────────────────────────────────────

def test_model_constants(client):
    res = client.get("/model/constants")
    assert res.status_code == 200
    data = res.json()
    assert data["win_probability"]["home_advantage"] == pytest.approx(0.535)
    assert data["kelly"]["fraction"] == pytest.approx(0.25)
    assert "park_factors" in data
    assert "Coors Field" in data["park_factors"]
    assert data["park_factors"]["Coors Field"] == pytest.approx(1.16)


def test_model_constants_cache_long(client):
    res = client.get("/model/constants")
    cc = res.headers.get("cache-control", "")
    assert "max-age=3600" in cc


# ── /games/slate ──────────────────────────────────────────────────────────────

def test_slate_returns_list(client):
    res = client.get("/games/slate?game_date=2026-05-15")
    assert res.status_code == 200
    data = res.json()
    assert isinstance(data, list)
    assert len(data) == 1
    game = data[0]
    assert game["game_id"] == 10
    assert game["home_team_abbr"] == "BAL"
    assert game["away_team_abbr"] == "BOS"
    assert "home_bullpen" in game
    assert "away_bullpen" in game
    assert "analysis" in game


def test_slate_empty_date(client):
    res = client.get("/games/slate?game_date=2020-01-01")
    assert res.status_code == 200
    assert res.json() == []


def test_slate_cache_control(client):
    res = client.get("/games/slate?game_date=2026-05-15")
    cc = res.headers.get("cache-control", "")
    assert "max-age=60" in cc


# ── /games/{id}/context ────────────────────────────────────────────────────────

def test_game_context(client):
    res = client.get("/games/10/context?as_of=2026-05-15")
    assert res.status_code == 200
    data = res.json()
    assert data["game_id"] == 10
    assert data["home_team_abbr"] == "BAL"
    assert data["away_team_abbr"] == "BOS"
    assert "home_starter" in data
    assert "away_starter" in data
    assert "home_bullpen" in data
    assert "weather" in data
    assert "analysis" in data


def test_game_context_not_found(client):
    res = client.get("/games/99999/context?as_of=2026-05-15")
    assert res.status_code == 404


def test_game_context_cache_control(client):
    res = client.get("/games/10/context?as_of=2026-05-15")
    cc = res.headers.get("cache-control", "")
    assert "max-age=60" in cc


# ── /games ─────────────────────────────────────────────────────────────────────

def test_list_games(client):
    res = client.get("/games?game_date=2026-05-15")
    assert res.status_code == 200
    data = res.json()
    assert len(data) == 1
    assert data[0]["home_team_abbr"] == "BAL"
    assert data[0]["venue"] == "Oriole Park at Camden Yards"


def test_list_games_empty(client):
    res = client.get("/games?game_date=2020-01-01")
    assert res.status_code == 200
    assert res.json() == []


# ── /teams ─────────────────────────────────────────────────────────────────────

def test_list_teams(client):
    res = client.get("/teams")
    assert res.status_code == 200
    abbrs = {t["abbr"] for t in res.json()}
    assert "BAL" in abbrs
    assert "BOS" in abbrs
