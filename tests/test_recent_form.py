"""Phase 5 tests: pure helpers, DB-backed builders, fixture round-trip."""

from __future__ import annotations

from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.models  # noqa: F401 — registers Base.metadata
from app.contracts import (
    BullpenState,
    GameContext,
    OddsSnapshot,
    PitcherFormWindow,
    PlayerFormWindow,
    RelieverFormWindow,
    TeamFormWindow,
    TrendLabel,
    WeatherSnapshot,
    WindowKey,
)
from app.database import Base
from app.features.recent_form import (
    DEFAULT_WINDOW_WEIGHTS,
    HEATING_DELTA,
    HITTER_STRONG_OPS,
    MIN_SAMPLE,
    PITCHER_STRONG_ERA,
    TEAM_STRONG_RUNS_PER_GAME,
    aggregate_hitter,
    aggregate_pitcher,
    aggregate_team,
    build_hitter_form_window,
    build_starter_form_window,
    build_team_form_window,
    classify_trend,
    load_team_form_window,
    upsert_hitter_form_window,
    upsert_team_form_window,
    weighted_form_metric,
)
from app.models.entities import Player, Team
from app.models.games import PitcherGameLog, PlayerGameLog, TeamGameLog
from tests.fixtures import load_fixture


# --- Pure aggregators ------------------------------------------------------

def test_aggregate_hitter_basic():
    out = aggregate_hitter(
        games=10, plate_appearances=44, at_bats=40,
        hits=12, doubles=3, triples=0, home_runs=2,
        walks=4, hit_by_pitch=0, sac_flies=0, strikeouts=9,
    )
    assert out["batting_avg"] == round(12 / 40, 3)
    # OBP = (12 + 4) / (40 + 4) = 16/44
    assert out["on_base_pct"] == round(16 / 44, 3)
    # SLG: 1B=7, 2B=3, 3B=0, HR=2 → TB = 7 + 6 + 0 + 8 = 21 → 21/40
    assert out["slugging_pct"] == round(21 / 40, 3)
    assert out["ops"] == out["on_base_pct"] + out["slugging_pct"]


def test_aggregate_hitter_empty_window_does_not_divide_by_zero():
    out = aggregate_hitter(
        games=0, plate_appearances=0, at_bats=0, hits=0,
        doubles=0, triples=0, home_runs=0, walks=0,
        hit_by_pitch=0, sac_flies=0, strikeouts=0,
    )
    assert out["batting_avg"] == 0.0
    assert out["ops"] == 0.0


def test_aggregate_pitcher_basic():
    out = aggregate_pitcher(
        innings_pitched=63.0, hits_allowed=52, earned_runs=18,
        walks=14, strikeouts=72, home_runs_allowed=6,
        pitches=985, outings=10,
    )
    # ERA = 9 * 18 / 63 = 2.57
    assert out["era"] == round(9 * 18 / 63, 2)
    assert out["whip"] == round((14 + 52) / 63, 2)
    assert out["k_per_9"] == round(9 * 72 / 63, 1)
    assert out["avg_innings_per_start"] == round(63 / 10, 2)


def test_aggregate_team_basic():
    out = aggregate_team(games=10, runs=54, runs_allowed=38, wins=7, losses=3, team_ops=0.768)
    assert out["runs_per_game"] == 5.4
    assert out["runs_allowed_per_game"] == 3.8
    assert out["record_wins"] == 7
    assert out["team_ops"] == 0.768


# --- Trend classifier ------------------------------------------------------

@pytest.mark.parametrize(
    "window_metric, season_metric, expected",
    [
        (0.800, 0.700, TrendLabel.HEATING_UP),       # +14% > HEATING_DELTA
        (0.620, 0.730, TrendLabel.COOLING_OFF),      # -15% < -HEATING_DELTA
        (0.770, 0.760, TrendLabel.STABLE_STRONG),    # small delta, season > strong threshold (0.740)
        (0.620, 0.610, TrendLabel.STABLE_WEAK),      # small delta, season < strong threshold
        (1.100, 0.700, TrendLabel.REGRESSION_RISK),  # +57% > REGRESSION_DELTA
    ],
)
def test_classify_trend_offense(window_metric, season_metric, expected):
    label = classify_trend(
        window_metric=window_metric,
        season_metric=season_metric,
        sample_size=10,
        min_sample=MIN_SAMPLE[WindowKey.L10],
        higher_is_better=True,
        strong_threshold=HITTER_STRONG_OPS,
    )
    assert label is expected


def test_classify_trend_inverted_for_era():
    # A *lower* window ERA than season → heating up.
    label = classify_trend(
        window_metric=2.50,
        season_metric=3.50,
        sample_size=6,
        min_sample=MIN_SAMPLE[WindowKey.LAST_10_STARTS],
        higher_is_better=False,
        strong_threshold=PITCHER_STRONG_ERA,
    )
    assert label is TrendLabel.HEATING_UP


def test_classify_trend_small_sample():
    label = classify_trend(
        window_metric=0.900, season_metric=0.700,
        sample_size=2, min_sample=MIN_SAMPLE[WindowKey.L10],
        higher_is_better=True,
    )
    assert label is TrendLabel.SMALL_SAMPLE_WARN


# --- Weighted form metric --------------------------------------------------

def test_weighted_form_metric_uses_default_weights():
    metrics = {
        WindowKey.SEASON: 0.700,
        WindowKey.L20: 0.740,
        WindowKey.L10: 0.760,
        WindowKey.L5: 0.800,
    }
    out = weighted_form_metric(metrics)
    expected = sum(metrics[w] * DEFAULT_WINDOW_WEIGHTS[w] for w in metrics)
    assert out == pytest.approx(expected, rel=1e-6)


def test_weighted_form_metric_redistributes_when_window_missing():
    # Only SEASON present → it gets full weight.
    out = weighted_form_metric({WindowKey.SEASON: 0.700})
    assert out == pytest.approx(0.700, rel=1e-6)


# --- Fixture round-trip (Track B's primary use case) -----------------------

def test_fixture_team_form_l10_round_trips():
    w = load_fixture("team_form_phi_l10", TeamFormWindow)
    assert w.team_abbr == "PHI"
    assert w.window is WindowKey.L10
    assert w.trend_label is TrendLabel.HEATING_UP
    assert w.as_of_date == date(2026, 5, 15)
    assert w.runs_per_game == 5.4


def test_fixture_pitcher_form_wheeler():
    w = load_fixture("pitcher_form_wheeler_season", PitcherFormWindow)
    assert w.pitcher_name == "Zack Wheeler"
    assert w.window is WindowKey.SEASON
    assert w.era == 2.86


def test_fixture_reliever_form_alvarado():
    w = load_fixture("reliever_form_alvarado_l20", RelieverFormWindow)
    assert w.role == "high_leverage"
    assert w.appearances == 18


def test_fixture_bullpen_state_phi():
    bs = load_fixture("bullpen_state_phi_2026-05-15", BullpenState)
    assert bs.team_abbr == "PHI"
    assert bs.closer_pitched_yesterday is True
    assert len(bs.relievers) == 3
    assert all(isinstance(r, RelieverFormWindow) for r in bs.relievers)
    assert bs.recent_usage[0].game_date == date(2026, 5, 14)


def test_fixture_game_context_phi_vs_nym():
    g = load_fixture("game_context_phi_vs_nym_2026-05-15", GameContext)
    assert g.home_team_abbr == "PHI"
    assert g.away_team_abbr == "NYM"
    assert g.game_time_utc.year == 2026


def test_fixture_odds_snapshot():
    o = load_fixture("odds_snapshot_phi_vs_nym", OddsSnapshot)
    assert o.american_odds == -135
    assert o.market == "moneyline"


def test_fixture_weather_snapshot():
    w = load_fixture("weather_snapshot_phi_vs_nym", WeatherSnapshot)
    assert w.is_dome is False
    assert w.temperature_f == 72.0


# --- DB-backed builders ----------------------------------------------------

@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s
    engine.dispose()


def _seed_team_with_games(session: Session, *, team_id=143, abbr="PHI"):
    session.add(Team(id=team_id, abbr=abbr, name="Phillies"))
    session.flush()
    # 10 recent games, then 10 earlier "season" games with weaker performance.
    # Most-recent block: 7 wins, 5 runs/g, 3.5 allowed/g
    for i in range(10):
        d = date(2026, 5, 5 + i)
        won = i < 7
        session.add(TeamGameLog(
            game_id=10000 + i, team_id=team_id, game_date=d,
            runs=5, runs_allowed=3 + (1 if not won else 0),
            won=won, is_home=(i % 2 == 0),
        ))
    # Earlier block: 4 wins, 4 runs/g, 4.5 allowed/g
    for i in range(10):
        d = date(2026, 4, 5 + i)
        won = i < 4
        session.add(TeamGameLog(
            game_id=11000 + i, team_id=team_id, game_date=d,
            runs=4, runs_allowed=4 + (1 if not won else 0),
            won=won, is_home=(i % 2 == 0),
        ))
    session.commit()


def test_build_team_form_window_l10_vs_season(db_session):
    _seed_team_with_games(db_session)
    as_of = date(2026, 5, 15)

    season = build_team_form_window(
        db_session, team_id=143, window=WindowKey.SEASON, as_of_date=as_of
    )
    assert season is not None
    assert season.games == 20
    assert season.record_wins == 11

    l10 = build_team_form_window(
        db_session, team_id=143, window=WindowKey.L10, as_of_date=as_of
    )
    assert l10 is not None
    assert l10.games == 10
    assert l10.record_wins == 7
    # L10 runs/g (5.0) is > 10% above season baseline → HEATING_UP.
    assert l10.trend_label in {TrendLabel.HEATING_UP, TrendLabel.REGRESSION_RISK}


def test_build_team_form_returns_none_for_unknown_team(db_session):
    out = build_team_form_window(
        db_session, team_id=999, window=WindowKey.L10, as_of_date=date(2026, 5, 15)
    )
    assert out is None


def test_team_form_persistence_round_trip(db_session):
    _seed_team_with_games(db_session)
    as_of = date(2026, 5, 15)
    w = build_team_form_window(
        db_session, team_id=143, window=WindowKey.L10, as_of_date=as_of
    )
    upsert_team_form_window(db_session, w)
    db_session.commit()

    loaded = load_team_form_window(
        db_session, team_id=143, window=WindowKey.L10, as_of_date=as_of
    )
    assert loaded is not None
    assert loaded.runs_per_game == w.runs_per_game
    assert loaded.trend_label is w.trend_label


def test_team_form_upsert_replaces_existing(db_session):
    _seed_team_with_games(db_session)
    as_of = date(2026, 5, 15)
    w1 = build_team_form_window(db_session, team_id=143, window=WindowKey.L10, as_of_date=as_of)
    upsert_team_form_window(db_session, w1)
    db_session.commit()

    # Mutate and re-upsert.
    w2 = TeamFormWindow(
        team_id=143, team_abbr="PHI", window=WindowKey.L10, games=10,
        runs_per_game=6.0, runs_allowed_per_game=2.0, team_ops=0.800,
        record_wins=10, record_losses=0, trend_label=TrendLabel.REGRESSION_RISK,
        as_of_date=as_of,
    )
    upsert_team_form_window(db_session, w2)
    db_session.commit()

    loaded = load_team_form_window(
        db_session, team_id=143, window=WindowKey.L10, as_of_date=as_of
    )
    assert loaded.runs_per_game == 6.0
    assert loaded.trend_label is TrendLabel.REGRESSION_RISK


def test_build_hitter_form_window(db_session):
    db_session.add(Team(id=143, abbr="PHI", name="Phillies"))
    db_session.add(Player(id=547180, full_name="Bryce Harper", primary_position="1B", bats="L"))
    db_session.flush()
    # 10 games: 12-for-40, 3 2B, 2 HR, 4 BB, 9 K.
    # Per game ~1 hit, distribute so totals match.
    for i in range(10):
        db_session.add(PlayerGameLog(
            game_id=20000 + i, player_id=547180, team_id=143,
            game_date=date(2026, 5, 5 + i),
            plate_appearances=4 + (1 if i < 4 else 0),
            at_bats=4, hits=1 + (1 if i in (1, 3) else 0),
            doubles=(1 if i in (2, 4, 6) else 0),
            home_runs=(1 if i in (5, 8) else 0),
            walks=(1 if i in (0, 2, 5, 9) else 0),
            strikeouts=1,
        ))
    db_session.commit()

    w = build_hitter_form_window(
        db_session, player_id=547180, window=WindowKey.L10, as_of_date=date(2026, 5, 15)
    )
    assert w is not None
    assert w.games == 10
    assert w.player_name == "Bryce Harper"
    assert w.home_runs == 2
    assert w.walks == 4
    # OPS should be > 0 since hits and walks are present.
    assert w.ops > 0


def test_build_starter_form_window(db_session):
    db_session.add(Team(id=143, abbr="PHI", name="Phillies"))
    db_session.add(Player(id=554430, full_name="Zack Wheeler", primary_position="P", throws="R"))
    db_session.flush()
    for i in range(10):
        db_session.add(PitcherGameLog(
            game_id=30000 + i, pitcher_id=554430, team_id=143,
            game_date=date(2026, 5, 1 + i),
            role="starter", started=True,
            innings_pitched=6.0, batters_faced=24,
            hits_allowed=4, earned_runs=2, walks=1, strikeouts=8,
            home_runs_allowed=1, pitches=95,
        ))
    db_session.commit()

    w = build_starter_form_window(
        db_session, pitcher_id=554430, window=WindowKey.LAST_5_STARTS, as_of_date=date(2026, 5, 15)
    )
    assert w is not None
    assert w.starts == 5
    assert w.innings_pitched == 30.0
    assert w.era == round(9 * (2 * 5) / 30.0, 2)
    assert w.avg_pitches_per_start == 95.0
