"""Edge calculation and recommendation tiers.

All edge comparisons use VIG-FREE implied probability (Pinnacle method).
Raw implied prob includes book margin (~4-7%) and systematically understates
true edge. Comparing model prob to vig-free prob gives the honest number.

Edge thresholds are calibrated against vig-free probability:
  - "STRONG LEAN" requires ≥5% vig-free edge (≈3% against raw -110 line)
  - "LEAN" requires ≥2.5% vig-free edge
These are tighter than they sound — a 5% vig-free edge on a coin-flip game
means the model disagrees with the market by 5pp after removing juice.
"""

from typing import Optional
from app.betting.implied_probability import implied_probability, vig_free_probability, expected_value


def edge(model_probability: float, american_odds: int) -> float:
    """Raw edge = model probability − raw implied probability. Includes vig."""
    return model_probability - implied_probability(american_odds)


def edge_vig_free(
    model_probability: float,
    side_odds: int,
    other_side_odds: int,
) -> tuple[float, float]:
    """
    Vig-free edge and EV per dollar wagered.

    edge_vf = model_prob − vig_free_implied
    ev      = (decimal_odds − 1) × model_prob − (1 − model_prob)

    Returns (edge_vf, ev_per_dollar).
    """
    vf_this, _, _ = vig_free_probability(side_odds, other_side_odds)
    edge_vf = model_probability - vf_this
    ev = expected_value(model_probability, side_odds)
    return round(edge_vf, 4), round(ev, 4)


def recommendation(
    edge_val: float,
    confidence: float,
    evidence_quality: float,
) -> str:
    """
    Map (vig-free edge, confidence, evidence_quality) → recommendation tier.

    Tiers: strong_lean | lean | pass | avoid | need_more_info
    Forbidden: lock, guaranteed, hammer, free money, must bet.

    Thresholds are against VIG-FREE edge, not raw implied probability.
    """
    if confidence < 0.4 or evidence_quality < 0.4:
        return "need_more_info"

    if edge_val >= 0.05 and confidence >= 0.70 and evidence_quality >= 0.70:
        return "strong_lean"
    if edge_val >= 0.025 and confidence >= 0.55:
        return "lean"
    if edge_val <= -0.05:
        return "avoid"
    return "pass"
