"""Deterministic tests for the backtest engine (Track B).

Strategy
--------
`run_backtest` does two things: (1) selects completed games from the DB and
(2) for each, calls `build_game_analysis` and grades the model's prediction
against the real box score. The DB selection / outcome logic is the part that
must be exercised against a real (in-memory SQLite) DB — so games, scores, and
exclusion of null-score rows are tested for real.

The *analysis* itself (probabilities, tiers, odds, Kelly stake) is the input
to the math under test, so it is stubbed with fixed `GameAnalysis` objects
keyed by game_id (spec Step 4: "stubbed analysis results with fixed
probabilities and tier labels"). This makes Brier / calibration / tier-hit /
P&L arithmetic exactly predictable and asserts the engine math, not the model.

One end-to-end test runs the *real* `build_game_analysis` over a seeded DB to
prove the no-stub path executes without look-ahead errors and honors the
null-score exclusion for real.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base
from app.models.entities import Player, Team
from app.models.games import Game, PitcherGameLog, PlayerGameLog, TeamGameLog
from app.betting.game_analyzer import GameAnalysis
from app.betting import backtest as backtest_mod
from app.betting.backtest import (
    BacktestResult,
    CalibrationBucket,
    TierHitRate,
    run_backtest,
)


# ---------------------------------------------------------------------------
# DB fixture — in-memory SQLite, same pattern as tests/test_api_aggregates.py
# ---------------------------------------------------------------------------

def _make_session():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def _add_game(
    session,
    *,
    gid: int,
    game_date: date,
    home_score,
    away_score,
    home_id: int = 10,
    away_id: int = 20,
):
    session.add(
        Game(
            id=gid,
            game_date=game_date,
            game_time_utc=datetime(game_date.year, game_date.month, game_date.day, 23, 5),
            home_team_id=home_id,
            away_team_id=away_id,
            venue="Test Park",
            status="Final" if home_score is not None else "Scheduled",
            home_score=home_score,
            away_score=away_score,
            is_doubleheader=False,
            game_number=1,
            home_probable_starter_id=None,
            away_probable_starter_id=None,
            odds_event_id=None,
        )
    )


@pytest.fixture
def db():
    Session = _make_session()
    with Session() as session:
        session.add(Team(id=10, abbr="HOM", name="Home", league="NL", division="East"))
        session.add(Team(id=20, abbr="AWY", name="Away", league="AL", division="West"))
        session.commit()
    with Session() as session:
        yield session


def _ga(
    game_id: int,
    *,
    home_prob: float,
    ml_lean: str,
    ml_tier: str,
    odds: int = -110,
    q_kelly: float = 0.0,
) -> GameAnalysis:
    """Build a minimal GameAnalysis stub with the fields the backtest reads."""
    return GameAnalysis(
        game_id=game_id,
        home_team_abbr="HOM",
        away_team_abbr="AWY",
        model_home_win_prob=home_prob,
        model_away_win_prob=round(1.0 - home_prob, 10),
        ml_lean=ml_lean,
        ml_confidence=max(home_prob, 1.0 - home_prob),
        ml_tier=ml_tier,
        total_lean="PASS",
        total_confidence=0.0,
        projected_total=8.5,
        ml_kelly_fraction=q_kelly,
        ml_american_odds=odds,
        q_kelly_sized=q_kelly,
    )


def _patch_analysis(monkeypatch, mapping: dict[int, GameAnalysis]):
    """Stub build_game_analysis so the engine sees fixed analysis per game.

    run_backtest does a deferred `from app.betting.analysis_builder import
    build_game_analysis`, so patch it on that module.
    """
    import app.betting.analysis_builder as ab

    def _fake(game_id, as_of, db):  # noqa: ARG001
        return mapping.get(game_id)

    monkeypatch.setattr(ab, "build_game_analysis", _fake)


# ---------------------------------------------------------------------------
# AC2 — empty range
# ---------------------------------------------------------------------------

def test_empty_range(db):
    result = run_backtest(db, date(2000, 1, 1), date(2000, 1, 2))
    assert isinstance(result, BacktestResult)
    assert result.n == 0
    assert result.brier_score is None
    assert result.flat_pnl == []
    assert result.kelly_pnl == []
    assert result.kelly_bankroll == []
    assert result.game_ids == []
    assert result.flat_pnl_total == 0.0
    assert result.kelly_pnl_total == 0.0
    assert result.start_date == "2000-01-01"
    assert result.end_date == "2000-01-02"
    # Calibration is always 10 fixed buckets, all empty when n=0
    assert len(result.calibration) == 10
    assert all(isinstance(b, CalibrationBucket) for b in result.calibration)
    assert all(b.n == 0 and b.actual_win_rate is None for b in result.calibration)
    # Tier hit rates are always the 4 fixed tiers, all empty
    assert [t.tier for t in result.tier_hit_rates] == [
        "STRONG LEAN", "LEAN", "PASS", "AVOID"
    ]
    assert all(t.n == 0 and t.hit_rate is None for t in result.tier_hit_rates)


def test_empty_range_when_only_null_score_games_exist(db, monkeypatch):
    # Games exist in range but none completed -> still n=0, honest empty result
    _add_game(db, gid=1, game_date=date(2026, 4, 10), home_score=None, away_score=None)
    _add_game(db, gid=2, game_date=date(2026, 4, 11), home_score=None, away_score=None)
    db.commit()
    _patch_analysis(monkeypatch, {})
    result = run_backtest(db, date(2026, 4, 1), date(2026, 5, 1))
    assert result.n == 0
    assert result.brier_score is None
    assert result.game_ids == []


# ---------------------------------------------------------------------------
# AC3 — Brier score arithmetic
# ---------------------------------------------------------------------------

def test_brier_score(db, monkeypatch):
    # 4 games, known home-win probs and known outcomes.
    # g1: prob 0.80, home WON   -> (0.80-1)^2 = 0.04
    # g2: prob 0.60, home LOST  -> (0.60-0)^2 = 0.36
    # g3: prob 0.50, home WON   -> (0.50-1)^2 = 0.25
    # g4: prob 0.30, home LOST  -> (0.30-0)^2 = 0.09
    # mean = (0.04+0.36+0.25+0.09)/4 = 0.185
    _add_game(db, gid=1, game_date=date(2026, 4, 1), home_score=5, away_score=2)  # home won
    _add_game(db, gid=2, game_date=date(2026, 4, 2), home_score=1, away_score=4)  # home lost
    _add_game(db, gid=3, game_date=date(2026, 4, 3), home_score=7, away_score=6)  # home won
    _add_game(db, gid=4, game_date=date(2026, 4, 4), home_score=0, away_score=3)  # home lost
    db.commit()
    _patch_analysis(
        monkeypatch,
        {
            1: _ga(1, home_prob=0.80, ml_lean="PASS", ml_tier="PASS"),
            2: _ga(2, home_prob=0.60, ml_lean="PASS", ml_tier="PASS"),
            3: _ga(3, home_prob=0.50, ml_lean="PASS", ml_tier="PASS"),
            4: _ga(4, home_prob=0.30, ml_lean="PASS", ml_tier="PASS"),
        },
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    assert result.n == 4
    assert result.brier_score == pytest.approx(0.185, abs=1e-6)


# ---------------------------------------------------------------------------
# AC4 — calibration bucket assignment
# ---------------------------------------------------------------------------

def test_calibration_buckets(db, monkeypatch):
    # ml_lean=HOME, model_home_win_prob=0.72 -> bucket [0.70,0.75) midpoint 0.725
    _add_game(db, gid=1, game_date=date(2026, 4, 5), home_score=6, away_score=1)
    db.commit()
    _patch_analysis(
        monkeypatch,
        {1: _ga(1, home_prob=0.72, ml_lean="HOME", ml_tier="LEAN", odds=-130)},
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))

    target = [b for b in result.calibration if b.midpoint == pytest.approx(0.725)]
    assert len(target) == 1
    bucket = target[0]
    assert bucket.n == 1
    assert bucket.actual_win_rate == pytest.approx(1.0)  # HOME leaned & home won

    # Every other bucket is empty
    others = [b for b in result.calibration if b.midpoint != pytest.approx(0.725)]
    assert all(b.n == 0 and b.actual_win_rate is None for b in others)


def test_calibration_uses_away_prob_for_away_lean(db, monkeypatch):
    # ml_lean=AWAY, model_away_win_prob = 1-0.38 = 0.62 -> bucket [0.60,0.65) mid 0.625
    # away lean, home LOST  -> predicted (away) side WON -> win rate 1.0
    _add_game(db, gid=1, game_date=date(2026, 4, 6), home_score=2, away_score=5)
    db.commit()
    _patch_analysis(
        monkeypatch,
        {1: _ga(1, home_prob=0.38, ml_lean="AWAY", ml_tier="LEAN", odds=+120)},
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    target = [b for b in result.calibration if b.midpoint == pytest.approx(0.625)]
    assert len(target) == 1
    assert target[0].n == 1
    assert target[0].actual_win_rate == pytest.approx(1.0)


def test_pass_lean_excluded_from_calibration_but_counted_in_n(db, monkeypatch):
    _add_game(db, gid=1, game_date=date(2026, 4, 7), home_score=3, away_score=1)
    db.commit()
    _patch_analysis(
        monkeypatch,
        {1: _ga(1, home_prob=0.66, ml_lean="PASS", ml_tier="PASS")},
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    assert result.n == 1                       # counted in n
    assert all(b.n == 0 for b in result.calibration)  # not bucketed
    assert result.game_ids == []               # not a graded bet


# ---------------------------------------------------------------------------
# AC (tier hit rate)
# ---------------------------------------------------------------------------

def test_tier_hit_rate_strong_lean(db, monkeypatch):
    # 3 STRONG LEAN games: 2 predicted-side wins, 1 loss -> hit rate 2/3
    _add_game(db, gid=1, game_date=date(2026, 4, 1), home_score=5, away_score=1)  # HOME lean, home won  -> hit
    _add_game(db, gid=2, game_date=date(2026, 4, 2), home_score=2, away_score=8)  # AWAY lean, home lost -> hit
    _add_game(db, gid=3, game_date=date(2026, 4, 3), home_score=4, away_score=3)  # HOME lean, home won? home won -> but lean AWAY -> miss
    db.commit()
    _patch_analysis(
        monkeypatch,
        {
            1: _ga(1, home_prob=0.78, ml_lean="HOME", ml_tier="STRONG LEAN"),
            2: _ga(2, home_prob=0.20, ml_lean="AWAY", ml_tier="STRONG LEAN"),
            3: _ga(3, home_prob=0.25, ml_lean="AWAY", ml_tier="STRONG LEAN"),
        },
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    by_tier = {t.tier: t for t in result.tier_hit_rates}
    sl = by_tier["STRONG LEAN"]
    assert sl.n == 3
    assert sl.hit_rate == pytest.approx(2 / 3)
    # other tiers empty
    assert by_tier["LEAN"].n == 0 and by_tier["LEAN"].hit_rate is None
    assert by_tier["PASS"].n == 0
    assert by_tier["AVOID"].n == 0


# ---------------------------------------------------------------------------
# AC (flat P&L)
# ---------------------------------------------------------------------------

def test_flat_pnl_cumulative_total(db, monkeypatch):
    # g1 HOME -110, home WON  -> +100/110 = +0.909090...
    # g2 AWAY +150, home WON (away lost) -> -1.0
    # g3 HOME +200, home WON  -> +2.0
    # cumulative flat: 0.90909..., -0.09090..., 1.90909...
    _add_game(db, gid=1, game_date=date(2026, 4, 1), home_score=5, away_score=2)
    _add_game(db, gid=2, game_date=date(2026, 4, 2), home_score=6, away_score=2)
    _add_game(db, gid=3, game_date=date(2026, 4, 3), home_score=9, away_score=1)
    db.commit()
    _patch_analysis(
        monkeypatch,
        {
            1: _ga(1, home_prob=0.60, ml_lean="HOME", ml_tier="LEAN", odds=-110),
            2: _ga(2, home_prob=0.40, ml_lean="AWAY", ml_tier="LEAN", odds=+150),
            3: _ga(3, home_prob=0.66, ml_lean="HOME", ml_tier="STRONG LEAN", odds=+200),
        },
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    assert len(result.flat_pnl) == 3
    assert result.flat_pnl[0] == pytest.approx(100 / 110)
    assert result.flat_pnl[1] == pytest.approx(100 / 110 - 1.0)
    assert result.flat_pnl[2] == pytest.approx(100 / 110 - 1.0 + 2.0)
    assert result.flat_pnl_total == pytest.approx(100 / 110 - 1.0 + 2.0)


# ---------------------------------------------------------------------------
# AC (Kelly P&L + bankroll)
# ---------------------------------------------------------------------------

def test_kelly_pnl_cumulative_total(db, monkeypatch):
    # g1 HOME -110 q_kelly 0.05, home WON  -> +0.05*(100/110)
    # g2 HOME +120 q_kelly 0.10, home LOST -> -0.10
    _add_game(db, gid=1, game_date=date(2026, 4, 1), home_score=5, away_score=2)
    _add_game(db, gid=2, game_date=date(2026, 4, 2), home_score=1, away_score=7)
    db.commit()
    _patch_analysis(
        monkeypatch,
        {
            1: _ga(1, home_prob=0.60, ml_lean="HOME", ml_tier="LEAN", odds=-110, q_kelly=0.05),
            2: _ga(2, home_prob=0.55, ml_lean="HOME", ml_tier="LEAN", odds=+120, q_kelly=0.10),
        },
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    assert len(result.kelly_pnl) == 2
    expected_k1 = 0.05 * (100 / 110)
    expected_k2 = expected_k1 - 0.10
    assert result.kelly_pnl[0] == pytest.approx(expected_k1)
    assert result.kelly_pnl[1] == pytest.approx(expected_k2)
    assert result.kelly_pnl_total == pytest.approx(expected_k2)

    # Compounding bankroll from 100:
    # after g1: 100 + 0.05*100*(100/110) = 100 + 5*(100/110)
    b1 = 100 + 0.05 * 100 * (100 / 110)
    # after g2 (loss): b1 - 0.10*b1 = b1*0.90
    b2 = b1 - 0.10 * b1
    assert result.kelly_bankroll[0] == pytest.approx(b1)
    assert result.kelly_bankroll[1] == pytest.approx(b2)


def test_negative_kelly_floored_at_zero(db, monkeypatch):
    # q_kelly negative -> staked 0 -> no bankroll/pnl movement, but still a graded game_id row
    _add_game(db, gid=1, game_date=date(2026, 4, 1), home_score=5, away_score=2)
    db.commit()
    _patch_analysis(
        monkeypatch,
        {1: _ga(1, home_prob=0.60, ml_lean="HOME", ml_tier="LEAN", odds=-110, q_kelly=-0.5)},
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    assert result.kelly_pnl == [pytest.approx(0.0)]
    assert result.kelly_bankroll == [pytest.approx(100.0)]
    # flat side still moves (1-unit flat stake)
    assert result.flat_pnl[0] == pytest.approx(100 / 110)


def test_even_money_fallback_when_no_odds(db, monkeypatch):
    # ml_american_odds == 0 -> payout per unit = 1.0
    _add_game(db, gid=1, game_date=date(2026, 4, 1), home_score=5, away_score=2)
    db.commit()
    _patch_analysis(
        monkeypatch,
        {1: _ga(1, home_prob=0.60, ml_lean="HOME", ml_tier="LEAN", odds=0)},
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    assert result.flat_pnl[0] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# AC5 — games with null scores excluded
# ---------------------------------------------------------------------------

def test_null_scores_excluded(db, monkeypatch):
    _add_game(db, gid=1, game_date=date(2026, 4, 1), home_score=5, away_score=2)   # completed
    _add_game(db, gid=2, game_date=date(2026, 4, 2), home_score=None, away_score=None)  # not played
    _add_game(db, gid=3, game_date=date(2026, 4, 3), home_score=None, away_score=3)     # half-null
    _add_game(db, gid=4, game_date=date(2026, 4, 4), home_score=4, away_score=None)     # half-null
    db.commit()
    _patch_analysis(
        monkeypatch,
        {
            1: _ga(1, home_prob=0.70, ml_lean="HOME", ml_tier="LEAN"),
            2: _ga(2, home_prob=0.70, ml_lean="HOME", ml_tier="LEAN"),
            3: _ga(3, home_prob=0.70, ml_lean="HOME", ml_tier="LEAN"),
            4: _ga(4, home_prob=0.70, ml_lean="HOME", ml_tier="LEAN"),
        },
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    assert result.n == 1
    assert result.game_ids == [1]
    assert 2 not in result.game_ids
    assert 3 not in result.game_ids
    assert 4 not in result.game_ids


# ---------------------------------------------------------------------------
# AC6 — P&L lists same length as graded game_ids
# ---------------------------------------------------------------------------

def test_pnl_length_equals_n(db, monkeypatch):
    # 6 completed games, all with HOME/AWAY leans -> all graded
    for i in range(1, 7):
        _add_game(db, gid=i, game_date=date(2026, 4, i), home_score=5, away_score=i)
    db.commit()
    _patch_analysis(
        monkeypatch,
        {
            i: _ga(i, home_prob=0.60, ml_lean="HOME", ml_tier="LEAN",
                   odds=-110, q_kelly=0.03)
            for i in range(1, 7)
        },
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    assert result.n == 6
    assert (
        len(result.flat_pnl)
        == len(result.kelly_pnl)
        == len(result.kelly_bankroll)
        == len(result.game_ids)
        == 6
    )
    # game_ids ordered by game_date ascending
    assert result.game_ids == [1, 2, 3, 4, 5, 6]


def test_game_ids_only_track_graded_bets(db, monkeypatch):
    # 3 completed: one PASS lean (counted in n, not graded), two HOME leans
    _add_game(db, gid=1, game_date=date(2026, 4, 1), home_score=5, away_score=2)
    _add_game(db, gid=2, game_date=date(2026, 4, 2), home_score=1, away_score=9)
    _add_game(db, gid=3, game_date=date(2026, 4, 3), home_score=7, away_score=0)
    db.commit()
    _patch_analysis(
        monkeypatch,
        {
            1: _ga(1, home_prob=0.66, ml_lean="HOME", ml_tier="LEAN"),
            2: _ga(2, home_prob=0.55, ml_lean="PASS", ml_tier="PASS"),
            3: _ga(3, home_prob=0.71, ml_lean="HOME", ml_tier="STRONG LEAN"),
        },
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    assert result.n == 3                       # all 3 completed games counted
    assert result.game_ids == [1, 3]           # only the 2 graded bets
    assert len(result.flat_pnl) == 2


# ---------------------------------------------------------------------------
# Date-range boundary & ordering
# ---------------------------------------------------------------------------

def test_range_is_inclusive_and_ordered(db, monkeypatch):
    _add_game(db, gid=1, game_date=date(2026, 3, 31), home_score=5, away_score=2)  # before range
    _add_game(db, gid=2, game_date=date(2026, 4, 1), home_score=5, away_score=2)   # start edge
    _add_game(db, gid=3, game_date=date(2026, 4, 30), home_score=5, away_score=2)  # end edge
    _add_game(db, gid=4, game_date=date(2026, 5, 1), home_score=5, away_score=2)   # after range
    db.commit()
    _patch_analysis(
        monkeypatch,
        {
            i: _ga(i, home_prob=0.60, ml_lean="HOME", ml_tier="LEAN")
            for i in range(1, 5)
        },
    )
    result = run_backtest(db, date(2026, 4, 1), date(2026, 4, 30))
    assert result.n == 2
    assert result.game_ids == [2, 3]


# ---------------------------------------------------------------------------
# End-to-end: real build_game_analysis path (no stub) over a seeded DB.
# Proves the non-stubbed path runs and that null-score exclusion holds for
# real, without look-ahead errors.
# ---------------------------------------------------------------------------

def test_real_analysis_path_runs_and_excludes_null_scores():
    Session = _make_session()
    with Session() as session:
        session.add(Team(id=10, abbr="HOM", name="Home", league="NL", division="East"))
        session.add(Team(id=20, abbr="AWY", name="Away", league="AL", division="West"))
        session.add(
            Player(
                id=901, full_name="SP One", primary_position="P",
                bats="R", throws="R", current_team_id=10,
            )
        )
        # One completed game (real analysis), one unplayed game (must be excluded)
        session.add(
            Game(
                id=1, game_date=date(2026, 4, 15),
                game_time_utc=datetime(2026, 4, 15, 23, 5),
                home_team_id=10, away_team_id=20, venue="Test Park",
                status="Final", home_score=6, away_score=3,
                is_doubleheader=False, game_number=1,
                home_probable_starter_id=901, away_probable_starter_id=None,
                odds_event_id=None,
            )
        )
        session.add(
            Game(
                id=2, game_date=date(2026, 4, 16),
                game_time_utc=datetime(2026, 4, 16, 23, 5),
                home_team_id=10, away_team_id=20, venue="Test Park",
                status="Scheduled", home_score=None, away_score=None,
                is_doubleheader=False, game_number=1,
                home_probable_starter_id=901, away_probable_starter_id=None,
                odds_event_id=None,
            )
        )
        session.add(
            TeamGameLog(
                game_id=1, team_id=10, game_date=date(2026, 4, 15),
                runs=6, runs_allowed=3, hits=10, errors=0, is_home=True, won=True,
            )
        )
        session.commit()

    with Session() as session:
        result = run_backtest(session, date(2026, 4, 1), date(2026, 4, 30))

    assert isinstance(result, BacktestResult)
    # Only the completed game is analyzed; the unplayed one is excluded.
    assert result.n == 1
    assert 2 not in result.game_ids
    assert result.brier_score is not None
    assert 0.0 <= result.brier_score <= 1.0
    assert len(result.calibration) == 10
    assert [t.tier for t in result.tier_hit_rates] == [
        "STRONG LEAN", "LEAN", "PASS", "AVOID"
    ]
    # P&L list lengths stay consistent
    assert (
        len(result.flat_pnl)
        == len(result.kelly_pnl)
        == len(result.kelly_bankroll)
        == len(result.game_ids)
    )
