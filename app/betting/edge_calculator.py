"""Edge calculation and recommendation tiers."""

from app.betting.implied_probability import implied_probability


def edge(model_probability: float, american_odds: int) -> float:
    """Edge = model probability - implied probability."""
    return model_probability - implied_probability(american_odds)


def recommendation(
    edge_val: float,
    confidence: float,
    evidence_quality: float,
) -> str:
    """
    Map (edge, confidence, evidence_quality) to a cautious recommendation tier.

    Tiers: strong_lean | lean | pass | avoid | need_more_info
    Forbidden: lock, guaranteed, hammer, free money, must bet.
    """
    if confidence < 0.4 or evidence_quality < 0.4:
        return "need_more_info"

    if edge_val >= 0.06 and confidence >= 0.7 and evidence_quality >= 0.7:
        return "strong_lean"
    if edge_val >= 0.03 and confidence >= 0.55:
        return "lean"
    if edge_val <= -0.05:
        return "avoid"
    return "pass"
