"""Deterministic backtest engine (Track B).

Replays the deterministic MLB model over *completed* games already in the DB
and compares model predictions to actual win/loss outcomes from real box
scores. This is standard quant backtesting on real data — **never** fabricated.

Hard rules enforced here (from PROJECT_BRIEF / goal.md):

- **No look-ahead bias.** Every model input for a game is computed
  `as_of=game.game_date` via `analysis_builder.build_game_analysis`, exactly
  as the live `/games/{id}/analyze` endpoint does.
- **No fake data.** A game is only counted if BOTH `home_score` and
  `away_score` are non-null. Any scalar metric with `n=0` is `None` (never
  `0.0`); any list-valued field with `n=0` is `[]`.
- **Betting language.** Tier hit-rates use the model's own tier labels
  (STRONG LEAN / LEAN / PASS / AVOID); this module makes no recommendations.

The single public entry point is `run_backtest(db, start, end) -> BacktestResult`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.games import Game


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------

@dataclass
class CalibrationBucket:
    midpoint: float                 # bucket center (e.g. 0.525)
    n: int
    actual_win_rate: Optional[float]  # None when n=0


@dataclass
class TierHitRate:
    tier: str                       # "STRONG LEAN", "LEAN", "PASS", "AVOID"
    n: int
    hit_rate: Optional[float]       # None when n=0


@dataclass
class BacktestResult:
    start_date: str                 # YYYY-MM-DD
    end_date: str                   # YYYY-MM-DD
    n: int                          # total completed games analyzed
    brier_score: Optional[float]
    calibration: List[CalibrationBucket]
    tier_hit_rates: List[TierHitRate]
    flat_pnl: List[float] = field(default_factory=list)        # cumulative P&L per bet, length == len(game_ids)
    kelly_pnl: List[float] = field(default_factory=list)       # cumulative Kelly P&L per bet
    kelly_bankroll: List[float] = field(default_factory=list)  # bankroll value per bet, starting from 100
    flat_pnl_total: float = 0.0
    kelly_pnl_total: float = 0.0
    game_ids: List[int] = field(default_factory=list)          # ordered game_ids, same length as pnl lists


# ---------------------------------------------------------------------------
# Calibration bucket layout — 10 equal-width buckets covering [0.50, 1.00]
# [0.50,0.55), [0.55,0.60), ... [0.90,0.95), [0.95,1.00]
# ---------------------------------------------------------------------------
_BUCKET_EDGES = [round(0.50 + 0.05 * i, 10) for i in range(11)]  # 0.50 ... 1.00
_BUCKET_MIDPOINTS = [
    round((_BUCKET_EDGES[i] + _BUCKET_EDGES[i + 1]) / 2, 10) for i in range(10)
]

_TIERS = ["STRONG LEAN", "LEAN", "PASS", "AVOID"]


def _bucket_index(p: float) -> Optional[int]:
    """Return the calibration bucket index [0,9] for probability p, or None.

    Only the predicted side's probability is bucketed, so p should be >= 0.50
    in practice. Probabilities below 0.50 fall outside the [0.50,1.00] grid and
    are not bucketed (excluded from calibration but still counted in n).
    The final bucket [0.95, 1.00] is inclusive of 1.00.
    """
    if p < 0.50 or p > 1.0:
        return None
    if p >= 1.0:
        return 9
    idx = int((p - 0.50) // 0.05)
    if idx < 0:
        return None
    if idx > 9:
        idx = 9
    return idx


def _payout_per_unit(american_odds: int) -> float:
    """Profit per 1 unit staked if the bet wins.

    american > 0  -> odds/100
    american < 0  -> 100/abs(odds)
    american == 0 -> 1.0 (even-money fallback; no odds present)
    """
    if american_odds > 0:
        return american_odds / 100.0
    if american_odds < 0:
        return 100.0 / abs(american_odds)
    return 1.0


def run_backtest(db: Session, start: date, end: date) -> BacktestResult:
    """Replay the model over completed games in [start, end] inclusive.

    A game is "completed" iff both `home_score` and `away_score` are non-null.
    Games are processed in `game_date` ascending order (ties broken by id) so
    the P&L / bankroll series is reproducible.
    """
    # Deferred import: build_game_analysis -> analyze_game pulls in heavy
    # feature modules; importing at module load would also create an import
    # cycle through app.api.routes in some entry points.
    from app.betting.analysis_builder import build_game_analysis

    start_str = start.isoformat()
    end_str = end.isoformat()

    games = list(
        db.execute(
            select(Game)
            .where(
                Game.game_date >= start,
                Game.game_date <= end,
                Game.home_score.is_not(None),
                Game.away_score.is_not(None),
            )
            .order_by(Game.game_date.asc(), Game.id.asc())
        ).scalars()
    )

    n = len(games)

    # Calibration buckets are always reported as 10 fixed buckets so the
    # frontend can render a consistent grid even when empty.
    bucket_counts = [0] * 10
    bucket_wins = [0] * 10

    tier_counts = {t: 0 for t in _TIERS}
    tier_wins = {t: 0 for t in _TIERS}

    brier_sum = 0.0          # sum of (predicted_home_prob - home_outcome)^2 over all n
    brier_n = 0

    game_ids: List[int] = []
    flat_pnl: List[float] = []
    kelly_pnl: List[float] = []
    kelly_bankroll: List[float] = []

    flat_cum = 0.0
    kelly_cum = 0.0
    bankroll = 100.0

    for game in games:
        analysis = build_game_analysis(game.id, game.game_date, db)
        if analysis is None:
            # Game row vanished between query and load — skip it entirely.
            # It is not counted in n (n is recomputed below from processed).
            continue

        home_won = game.home_score > game.away_score

        # --- Brier score (over every analyzable completed game) ---
        predicted_home_prob = analysis.model_home_win_prob
        home_outcome = 1.0 if home_won else 0.0
        brier_sum += (predicted_home_prob - home_outcome) ** 2
        brier_n += 1

        # --- Tier hit rate ---
        tier = analysis.ml_tier
        ml_lean = analysis.ml_lean
        predicted_side_won: Optional[bool] = None
        if ml_lean == "HOME":
            predicted_side_won = home_won
        elif ml_lean == "AWAY":
            predicted_side_won = not home_won

        if tier in tier_counts:
            tier_counts[tier] += 1
            if predicted_side_won:
                tier_wins[tier] += 1

        # --- Calibration: bucket the predicted (leaned) side's probability ---
        if ml_lean == "HOME":
            lean_prob = analysis.model_home_win_prob
        elif ml_lean == "AWAY":
            lean_prob = analysis.model_away_win_prob
        else:
            lean_prob = None  # PASS / unknown — excluded from calibration

        if lean_prob is not None:
            bi = _bucket_index(lean_prob)
            if bi is not None:
                bucket_counts[bi] += 1
                if predicted_side_won:
                    bucket_wins[bi] += 1

        # --- P&L simulation (only graded bets: HOME or AWAY lean) ---
        if ml_lean in ("HOME", "AWAY") and predicted_side_won is not None:
            payout = _payout_per_unit(analysis.ml_american_odds)

            # Flat stake: 1 unit
            if predicted_side_won:
                flat_cum += payout * 1.0
            else:
                flat_cum -= 1.0

            # Kelly stake: q_kelly_sized fraction, floored at 0 (never negative)
            kelly_frac = max(0.0, analysis.q_kelly_sized)
            kelly_stake_units = kelly_frac  # flat-bankroll Kelly P&L (unit base)
            if predicted_side_won:
                kelly_cum += payout * kelly_stake_units
            else:
                kelly_cum -= kelly_stake_units

            # Compounding bankroll simulation, starting at 100 units
            bankroll_stake = kelly_frac * bankroll
            if predicted_side_won:
                bankroll += payout * bankroll_stake
            else:
                bankroll -= bankroll_stake

            game_ids.append(game.id)
            flat_pnl.append(round(flat_cum, 10))
            kelly_pnl.append(round(kelly_cum, 10))
            kelly_bankroll.append(round(bankroll, 10))

    n = brier_n  # actual analyzable completed games

    brier_score: Optional[float] = (
        brier_sum / brier_n if brier_n > 0 else None
    )

    calibration = [
        CalibrationBucket(
            midpoint=_BUCKET_MIDPOINTS[i],
            n=bucket_counts[i],
            actual_win_rate=(
                bucket_wins[i] / bucket_counts[i] if bucket_counts[i] > 0 else None
            ),
        )
        for i in range(10)
    ]

    tier_hit_rates = [
        TierHitRate(
            tier=t,
            n=tier_counts[t],
            hit_rate=(
                tier_wins[t] / tier_counts[t] if tier_counts[t] > 0 else None
            ),
        )
        for t in _TIERS
    ]

    return BacktestResult(
        start_date=start_str,
        end_date=end_str,
        n=n,
        brier_score=brier_score,
        calibration=calibration,
        tier_hit_rates=tier_hit_rates,
        flat_pnl=flat_pnl,
        kelly_pnl=kelly_pnl,
        kelly_bankroll=kelly_bankroll,
        flat_pnl_total=round(flat_cum, 10) if game_ids else 0.0,
        kelly_pnl_total=round(kelly_cum, 10) if game_ids else 0.0,
        game_ids=game_ids,
    )
