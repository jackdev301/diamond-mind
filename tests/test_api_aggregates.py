from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import _get_db, app
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
        session.add(Team(id=120, abbr="WSH", name="Nationals", league="NL", division="East"))
        session.add(
            Player(
                id=999,
                full_name="Starter One",
                primary_position="P",
                bats="R",
                throws="R",
                current_team_id=120,
            )
        )
        session.add(
            Game(
                id=1,
                game_date=date(2026, 5, 15),
                game_time_utc=datetime(2026, 5, 15, 23, 5),
                home_team_id=120,
                away_team_id=120,
                venue="Nationals Park",
                status="Final",
                home_score=5,
                away_score=3,
                is_doubleheader=False,
                game_number=1,
                home_probable_starter_id=999,
                away_probable_starter_id=None,
                odds_event_id=None,
            )
        )
        session.add(
            TeamGameLog(
                game_id=1,
                team_id=120,
                game_date=date(2026, 5, 15),
                runs=5,
                runs_allowed=3,
                hits=8,
                errors=0,
                is_home=True,
                won=True,
            )
        )
        session.add(
            PlayerGameLog(
                game_id=1,
                player_id=10,
                team_id=120,
                game_date=date(2026, 5, 15),
                plate_appearances=5,
                at_bats=4,
                hits=2,
                doubles=1,
                triples=0,
                home_runs=1,
                rbis=3,
                walks=1,
                strikeouts=1,
                hit_by_pitch=0,
                sac_flies=0,
                stolen_bases=1,
                caught_stealing=1,
            )
        )
        session.add(
            PitcherGameLog(
                game_id=1,
                pitcher_id=999,
                team_id=120,
                game_date=date(2026, 5, 15),
                role="starter",
                started=True,
                innings_pitched=6.0,
                batters_faced=24,
                hits_allowed=5,
                earned_runs=2,
                walks=2,
                strikeouts=7,
                home_runs_allowed=1,
                pitches=91,
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


def test_team_batting_endpoint(client):
    res = client.get("/teams/120/batting?as_of=2026-05-16&window=season")
    assert res.status_code == 200
    data = res.json()
    assert data["team_abbr"] == "WSH"
    assert data["plate_appearances"] == 5
    assert data["home_runs"] == 1
    assert data["stolen_bases"] == 1
    assert data["caught_stealing"] == 1
    assert data["stolen_base_attempts"] == 2
    assert data["stolen_base_success_rate"] == pytest.approx(0.5)
    assert data["ops"] == pytest.approx(2.1)
    assert data["iso"] == pytest.approx(1.0)
    assert data["unsupported"]["handedness_splits"]


def test_pitcher_advanced_endpoint(client):
    res = client.get("/pitchers/999/advanced?as_of=2026-05-16&window=season")
    assert res.status_code == 200
    data = res.json()
    assert data["pitcher_name"] == "Starter One"
    assert data["throws"] == "R"
    assert data["era"] == pytest.approx(3.0)
    assert data["fip"] == pytest.approx(((13 + 6 - 14) / 6) + 3.10)
    assert data["babip"] == pytest.approx(4 / 14)
    assert data["unsupported"]["left_right_splits"]
