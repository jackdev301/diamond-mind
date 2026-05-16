"""American odds → implied probability conversion."""


def implied_probability(american_odds: int) -> float:
    """Convert American odds to implied probability (0.0–1.0)."""
    if american_odds < 0:
        return abs(american_odds) / (abs(american_odds) + 100)
    return 100 / (american_odds + 100)
