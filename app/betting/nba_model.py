"""NBA moneyline model — the quant core ported to basketball.

The quant layer (`app/betting/quant.py`: Shin devig, Bayesian shrinkage,
edge posterior, uncertainty-adjusted Kelly, log-growth) is sport-agnostic —
it operates on probabilities and odds, not baseball. This module supplies the
basketball-specific deterministic win-probability model and routes it through
that same pipeline, exactly mirroring `f5_model.py`.

Win-probability drivers (deterministic, well-established, no fabricated data):
  1. Home-court advantage — ~0.60 base in the NBA (much stronger than MLB).
  2. Net-rating differential — (off_rtg − def_rtg) gap is the dominant signal;
     ~3.5 net-rating points ≈ a standard NBA point spread point.
  3. Rest / back-to-back — a road back-to-back is a large, documented penalty;
     a rest edge is a real, modest signal.

No NBA data ingestion exists in this repo (Track A is MLB-only). So this is
an on-demand analysis function over EXPLICIT inputs (the API passes them as
params, like /quant/verify) — it never reads a DB and never fabricates team
data. Live NBA ingestion is a separate, out-of-scope effort, documented in
ARC.md §8.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.betting.quant import compute_quant_edge, quant_recommendation

# ── Parameters (model assumptions, stated as such) ───────────────────────────
HOME_COURT_ADV = 0.60          # NBA home win rate baseline (~0.58–0.61 historically)
# A net-rating point is ~0.030 win-prob near a coin flip; capped so a blowout
# mismatch can't push past a sane ceiling for a single regular-season game.
NET_RATING_SCALE = 0.030
NET_RATING_CAP = 0.28
ROAD_B2B_PENALTY = 0.045       # road team on zero days rest, second night
REST_EDGE_PER_DAY = 0.012      # per-day rest advantage, capped
REST_EDGE_CAP = 0.04


@dataclass
class NBAAnalysis:
    home_team: str
    away_team: str
    model_home_win_prob: float
    model_away_win_prob: float
    net_rating_diff: float          # home_net - away_net (home perspective)
    rest_adjustment: float          # net win-prob shift from rest/B2B
    rationale: str
    ml_lean: str = "PASS"
    ml_tier: str = "PASS"
    ml_confidence: float = 0.0
    ml_kelly_fraction: float = 0.0
    ml_american_odds: Optional[int] = None
    q_shin_vig_free: Optional[float] = None
    q_edge_quant: Optional[float] = None
    q_prob_positive: Optional[float] = None
    q_growth_rate: Optional[float] = None


def _rest_adjustment(
    home_rest_days: Optional[int],
    away_rest_days: Optional[int],
    home_back_to_back: bool,
    away_back_to_back: bool,
) -> float:
    """Net home-perspective win-prob shift from rest. Positive favors home."""
    adj = 0.0
    if away_back_to_back and not home_back_to_back:
        adj += ROAD_B2B_PENALTY          # away tired → helps home
    if home_back_to_back and not away_back_to_back:
        adj -= ROAD_B2B_PENALTY
    if home_rest_days is not None and away_rest_days is not None:
        diff = home_rest_days - away_rest_days
        adj += max(-REST_EDGE_CAP, min(REST_EDGE_CAP, diff * REST_EDGE_PER_DAY))
    return round(adj, 4)


def analyze_nba_game(
    home_team: str,
    away_team: str,
    home_net_rating: float,
    away_net_rating: float,
    home_ml_odds: Optional[int] = None,
    away_ml_odds: Optional[int] = None,
    home_rest_days: Optional[int] = None,
    away_rest_days: Optional[int] = None,
    home_back_to_back: bool = False,
    away_back_to_back: bool = False,
    evidence_quality: float = 0.6,
) -> NBAAnalysis:
    """Deterministic NBA moneyline projection (+ quant rec if a line exists)."""
    net_diff = home_net_rating - away_net_rating
    net_swing = max(-NET_RATING_CAP, min(NET_RATING_CAP, net_diff * NET_RATING_SCALE))
    rest_adj = _rest_adjustment(
        home_rest_days, away_rest_days, home_back_to_back, away_back_to_back
    )

    prob = round(min(0.92, max(0.08, HOME_COURT_ADV + net_swing + rest_adj)), 4)
    away_prob = round(1.0 - prob, 4)

    rationale = (
        f"Net-rating diff {net_diff:+.1f} ({home_team} {home_net_rating:+.1f} vs "
        f"{away_team} {away_net_rating:+.1f}) → {net_swing:+.3f}; "
        f"rest/B2B {rest_adj:+.3f}; home-court base {HOME_COURT_ADV:.2f}."
    )

    result = NBAAnalysis(
        home_team=home_team,
        away_team=away_team,
        model_home_win_prob=prob,
        model_away_win_prob=away_prob,
        net_rating_diff=round(net_diff, 2),
        rest_adjustment=rest_adj,
        rationale=rationale,
    )

    if home_ml_odds is not None and away_ml_odds is not None:
        lean_side = "HOME" if prob >= 0.5 else "AWAY"
        lean_prob = prob if prob >= 0.5 else away_prob
        side_odds = home_ml_odds if lean_side == "HOME" else away_ml_odds
        other_odds = away_ml_odds if lean_side == "HOME" else home_ml_odds

        qe = compute_quant_edge(lean_prob, side_odds, other_odds, evidence_quality)
        tier = quant_recommendation(
            qe, model_confidence=lean_prob, evidence_quality=evidence_quality
        )
        if tier == "NEED MORE INFO":
            tier = "PASS"
        result.ml_lean = lean_side if tier in ("STRONG LEAN", "LEAN") else "PASS"
        result.ml_tier = tier
        result.ml_confidence = lean_prob
        result.ml_kelly_fraction = qe.kelly_sized if result.ml_lean != "PASS" else 0.0
        result.ml_american_odds = side_odds
        result.q_shin_vig_free = qe.shin_vig_free
        result.q_edge_quant = qe.edge_quant
        result.q_prob_positive = qe.prob_positive
        result.q_growth_rate = qe.growth_rate

    return result
