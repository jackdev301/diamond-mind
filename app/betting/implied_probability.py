"""American odds → implied probability conversion, with vig removal."""


def implied_probability(american_odds: int) -> float:
    """Raw implied probability from American odds. Includes bookmaker vig."""
    if american_odds < 0:
        return abs(american_odds) / (abs(american_odds) + 100)
    return 100 / (american_odds + 100)


def decimal_odds(american_odds: int) -> float:
    """Convert American odds to decimal (European) format."""
    if american_odds < 0:
        return 1 + 100 / abs(american_odds)
    return 1 + american_odds / 100


def vig_free_probability(home_odds: int, away_odds: int) -> tuple[float, float, float]:
    """
    Remove bookmaker vig using the proportional (Pinnacle) method.

    The book prices both sides such that raw implied probs sum to 1 + vig.
    Vig-free prob = raw_side / (raw_home + raw_away).

    Returns (vig_free_home, vig_free_away, overround).
    overround > 1.0 = the book's edge expressed as a multiplier.
    """
    raw_home = implied_probability(home_odds)
    raw_away = implied_probability(away_odds)
    overround = raw_home + raw_away
    return raw_home / overround, raw_away / overround, overround


def expected_value(model_prob: float, american_odds: int) -> float:
    """
    Expected value per unit wagered.

    EV = b×p − q  where b = decimal odds − 1, p = model probability, q = 1−p.
    Positive EV = +edge. EV of 0.05 means $0.05 expected profit per $1 wagered.
    """
    b = decimal_odds(american_odds) - 1
    return b * model_prob - (1 - model_prob)
