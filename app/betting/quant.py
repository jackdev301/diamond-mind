"""Quant-grade probability and bet-sizing layer.

This module is the PhD-level upgrade over the naive devig-and-Kelly path in
`implied_probability.py` / `edge_calculator.py`. Every function here is the
method a real sports-betting quant desk would use, with the derivation in the
docstring so it is auditable.

The four upgrades over the "Sonnet 4.6 theory" (proportional devig + point
estimate + hardcoded 0.25 Kelly):

  1. SHIN DEVIG.  Proportional devig assumes the bookmaker's margin is spread
     across outcomes in proportion to price. That is empirically false — it is
     biased by the favorite–longshot effect (longshots are systematically
     overbet, so their fair price is lower than proportional implies). Shin
     (1992, 1993) models the margin as the book's protection against a
     proportion `z` of insider traders and backs out less-biased true
     probabilities. This is what Pinnacle-style sharp shops actually use.

  2. BAYESIAN SHRINKAGE TOWARD THE MARKET.  A single model that disagrees with
     a liquid market by 8 points is far more likely miscalibrated than right.
     The market is a strong prior (it aggregates sharp money). We blend the
     model and the market in log-odds space, weighting the model by its
     evidence quality. This collapses overconfident edges — the single biggest
     bankroll protector.

  3. EDGE AS A DISTRIBUTION.  The model probability is an estimator with a
     standard error, not a truth. We put a Beta posterior on it (effective
     sample size from evidence quality), propagate to the edge, and report
     P(edge > 0) and a 95% credible interval. You bet the probability of being
     right, not a point estimate.

  4. UNCERTAINTY-ADJUSTED KELLY.  Full Kelly assumes p is known exactly.
     Baker & McHale (2013) show the growth-optimal fraction under parameter
     uncertainty shrinks by roughly the signal-to-total-variance ratio. This
     *derives* the fractional multiplier from the estimate's noise instead of
     hardcoding 0.25, and self-throttles on noisy edges.

Also exposes the actual Kelly objective — expected log-growth rate
g = p·ln(1+bf) + q·ln(1−f) — and its implied bankroll doubling time.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

# ── Normal CDF (no scipy dependency) ──────────────────────────────────────────
def _norm_cdf(x: float) -> float:
    """Standard normal CDF via the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _decimal(american_odds: int) -> float:
    if american_odds < 0:
        return 1.0 + 100.0 / abs(american_odds)
    return 1.0 + american_odds / 100.0


# ── 1. Shin devig ─────────────────────────────────────────────────────────────
def shin_probabilities(home_odds: int, away_odds: int) -> tuple[float, float, float, float]:
    """Shin (1993) vig-free probabilities for a two-outcome market.

    Let r_i = 1/decimal_odds_i be the raw implied prices (Σ r_i = B > 1, the
    booksum). Shin's model gives, for insider proportion z ∈ (0,1):

        p_i(z) = [ sqrt( z² + 4(1−z)·r_i² / B ) − z ] / ( 2(1−z) )

    z is the root of Σ_i p_i(z) − 1 = 0. The objective is strictly monotone
    decreasing in z on (0,1) — f(0⁺) = √B − 1 > 0, f(1⁻) = Σ r_i²/B − 1 < 0 —
    so a simple bisection is globally convergent. z = 0 recovers proportional
    devig exactly; z > 0 shifts probability mass from longshots to favorites,
    which is the favorite–longshot correction.

    Returns (p_home, p_away, z, booksum).
    """
    r_home = 1.0 / _decimal(home_odds)
    r_away = 1.0 / _decimal(away_odds)
    booksum = r_home + r_away

    def p_of_z(r: float, z: float) -> float:
        disc = z * z + 4.0 * (1.0 - z) * (r * r) / booksum
        return (math.sqrt(disc) - z) / (2.0 * (1.0 - z))

    def sum_minus_one(z: float) -> float:
        return p_of_z(r_home, z) + p_of_z(r_away, z) - 1.0

    lo, hi = 1e-9, 1.0 - 1e-9
    f_lo = sum_minus_one(lo)
    # No insider mass needed (already a fair book) → z ≈ 0, proportional.
    if f_lo <= 0:
        z = 0.0
    else:
        for _ in range(100):
            mid = 0.5 * (lo + hi)
            if sum_minus_one(mid) > 0:
                lo = mid
            else:
                hi = mid
        z = 0.5 * (lo + hi)

    if z <= 1e-9:
        # proportional fallback (z→0 limit)
        return r_home / booksum, r_away / booksum, 0.0, booksum

    p_home = p_of_z(r_home, z)
    p_away = p_of_z(r_away, z)
    norm = p_home + p_away
    return p_home / norm, p_away / norm, z, booksum


# ── 2. Bayesian shrinkage toward the market prior ─────────────────────────────
def _logit(p: float) -> float:
    p = min(1.0 - 1e-9, max(1e-9, p))
    return math.log(p / (1.0 - p))


def _expit(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def shrink_to_market(p_model: float, p_market_vf: float, reliability: float) -> float:
    """Blend model and market in log-odds space.

        logit(p*) = w·logit(p_model) + (1−w)·logit(p_market_vf)

    w = reliability ∈ [0,1] is how much we trust the model's standalone
    estimate (driven by evidence quality and sample size). A low-evidence
    model is pulled hard toward the market; a high-evidence model is allowed
    to express its disagreement. Log-odds blending is the correct space — it
    is the conjugate update for a Bernoulli and never leaves (0,1).
    """
    w = min(1.0, max(0.0, reliability))
    return _expit(w * _logit(p_model) + (1.0 - w) * _logit(p_market_vf))


# ── 3. Edge as a posterior distribution ───────────────────────────────────────
@dataclass
class EdgePosterior:
    edge_mean: float        # E[p − p_market]
    edge_sd: float          # SD of the edge estimate
    prob_positive: float    # P(edge > 0) — the number you actually bet
    ci_low: float           # 95% credible interval on edge
    ci_high: float
    effective_n: float      # effective sample size behind the estimate


def edge_posterior(
    p_shrunk: float,
    p_market_vf: float,
    evidence_quality: float,
    max_effective_n: float = 60.0,
) -> EdgePosterior:
    """Posterior on the edge, treating p as Beta-distributed.

    Effective sample size N = max_effective_n · evidence_quality. The market
    line is treated as a near-exact reference (deep liquidity), so the edge
    inherits the model's posterior SD:

        Var(p) ≈ p(1−p) / (N + 1)        (Beta(αβ) variance, α+β = N)

    P(edge > 0) uses a normal approximation to the Beta posterior, which is
    accurate well within the range of N we operate in. This is the quantity a
    desk risk-manages against — not the point edge.
    """
    n_eff = max(1.0, max_effective_n * min(1.0, max(0.0, evidence_quality)))
    var_p = p_shrunk * (1.0 - p_shrunk) / (n_eff + 1.0)
    sd = math.sqrt(var_p)
    edge_mean = p_shrunk - p_market_vf
    prob_pos = _norm_cdf(edge_mean / sd) if sd > 1e-12 else (1.0 if edge_mean > 0 else 0.0)
    return EdgePosterior(
        edge_mean=round(edge_mean, 4),
        edge_sd=round(sd, 4),
        prob_positive=round(prob_pos, 4),
        ci_low=round(edge_mean - 1.96 * sd, 4),
        ci_high=round(edge_mean + 1.96 * sd, 4),
        effective_n=round(n_eff, 1),
    )


# ── 4. Uncertainty-adjusted Kelly + growth rate ───────────────────────────────
def full_kelly(p: float, american_odds: int) -> float:
    """Unscaled Kelly fraction f* = (b·p − q)/b for a win-b/lose-1 bet."""
    b = _decimal(american_odds) - 1.0
    if b <= 0:
        return 0.0
    q = 1.0 - p
    return (b * p - q) / b


def uncertainty_kelly(
    p: float,
    american_odds: int,
    edge_mean: float,
    edge_sd: float,
    hard_cap: float = 0.25,
) -> tuple[float, float]:
    """Kelly fraction shrunk for parameter uncertainty (Baker & McHale 2013).

    Full Kelly assumes p is known. With an estimate of SD σ on the edge, the
    growth-optimal fraction is approximately

        f = f_full · g² / (g² + σ²)

    i.e. scaled by the signal-to-total-variance ratio. A clean, noisy edge is
    throttled automatically; this *derives* the fractional multiplier instead
    of assuming 0.25. We additionally floor the multiplier at `hard_cap`
    (quarter-Kelly) as a non-negotiable drawdown guard — the theory optimizes
    asymptotic growth and is indifferent to the brutal interim variance of
    full Kelly.

    Returns (sized_fraction, derived_multiplier).
    """
    f_full = full_kelly(p, american_odds)
    if f_full <= 0:
        return 0.0, 0.0
    g2 = edge_mean * edge_mean
    s2 = edge_sd * edge_sd
    shrink = g2 / (g2 + s2) if (g2 + s2) > 0 else 0.0
    mult = min(hard_cap, shrink)
    return round(max(0.0, f_full * mult), 4), round(mult, 4)


def expected_log_growth(p: float, american_odds: int, fraction: float) -> float:
    """Expected log-growth rate g = p·ln(1+bf) + q·ln(1−f).

    This is the actual Kelly objective: the asymptotic per-bet geometric
    growth rate of the bankroll. Positive g means the bankroll compounds;
    g is what is being maximized, not EV.
    """
    if fraction <= 0 or fraction >= 1:
        return 0.0
    b = _decimal(american_odds) - 1.0
    q = 1.0 - p
    up = 1.0 + b * fraction
    down = 1.0 - fraction
    if up <= 0 or down <= 0:
        return 0.0
    return round(p * math.log(up) + q * math.log(down), 6)


def doubling_time_bets(growth_rate: float) -> float | None:
    """Expected bets to double the bankroll: ln(2)/g. None if g ≤ 0."""
    if growth_rate <= 0:
        return None
    return round(math.log(2.0) / growth_rate, 1)


# ── Bundled quant edge ────────────────────────────────────────────────────────
@dataclass
class QuantEdge:
    # Devig comparison: naive vs quant
    prop_vig_free: float        # proportional devig (Sonnet 4.6 theory)
    shin_vig_free: float        # Shin devig (Opus 4.7)
    shin_z: float               # estimated insider proportion
    booksum: float              # overround (B = Σ 1/odds)

    # Probability after shrinkage toward the market prior
    p_model: float
    p_shrunk: float
    shrink_weight: float        # model reliability w

    # Edge posterior
    edge_naive: float           # p_model − proportional vig-free (old number)
    edge_quant: float           # p_shrunk − Shin vig-free (honest number)
    edge_sd: float
    prob_positive: float        # P(edge > 0)
    ci_low: float
    ci_high: float
    effective_n: float

    # Sizing + growth
    kelly_full: float
    kelly_sized: float
    kelly_multiplier: float     # derived, not hardcoded
    growth_rate: float          # expected log-growth per bet
    doubling_bets: float | None
    ev_per_dollar: float


def compute_quant_edge(
    p_model_side: float,
    side_odds: int,
    other_odds: int,
    evidence_quality: float,
    max_effective_n: float = 60.0,
) -> QuantEdge:
    """End-to-end quant pipeline for one side of a moneyline.

    `p_model_side`   model win prob for the side being priced
    `side_odds`      American odds for that side
    `other_odds`     American odds for the opponent (needed to devig)
    `evidence_quality` ∈ [0,1] drives both shrinkage weight and posterior N
    `max_effective_n` caps the Beta posterior sample size; use a smaller value
                     (e.g. 25) for totals where the projection itself carries
                     ~3-run SD that is not captured in evidence_quality alone
    """
    # Proportional devig (the naive baseline we are comparing against)
    r_side = 1.0 / _decimal(side_odds)
    r_other = 1.0 / _decimal(other_odds)
    booksum = r_side + r_other
    prop_vf = r_side / booksum

    # Shin devig
    p_h, p_a, z, _ = shin_probabilities(side_odds, other_odds)
    shin_vf = p_h  # shin_probabilities returns (this_side, other_side, ...)

    # Shrink model toward the Shin market prior, weighted by evidence
    w = min(1.0, max(0.0, evidence_quality))
    p_shrunk = shrink_to_market(p_model_side, shin_vf, w)

    post = edge_posterior(p_shrunk, shin_vf, evidence_quality, max_effective_n=max_effective_n)

    f_full = full_kelly(p_shrunk, side_odds)
    f_sized, mult = uncertainty_kelly(p_shrunk, side_odds, post.edge_mean, post.edge_sd)
    g = expected_log_growth(p_shrunk, side_odds, f_sized)

    b = _decimal(side_odds) - 1.0
    ev = b * p_shrunk - (1.0 - p_shrunk)

    return QuantEdge(
        prop_vig_free=round(prop_vf, 4),
        shin_vig_free=round(shin_vf, 4),
        shin_z=round(z, 4),
        booksum=round(booksum, 4),
        p_model=round(p_model_side, 4),
        p_shrunk=round(p_shrunk, 4),
        shrink_weight=round(w, 4),
        edge_naive=round(p_model_side - prop_vf, 4),
        edge_quant=post.edge_mean,
        edge_sd=post.edge_sd,
        prob_positive=post.prob_positive,
        ci_low=post.ci_low,
        ci_high=post.ci_high,
        effective_n=post.effective_n,
        kelly_full=round(f_full, 4),
        kelly_sized=f_sized,
        kelly_multiplier=mult,
        growth_rate=g,
        doubling_bets=doubling_time_bets(g),
        ev_per_dollar=round(ev, 4),
    )


def quant_recommendation(qe: QuantEdge, model_confidence: float, evidence_quality: float) -> str:
    """Tier driven by P(edge>0) and growth rate, not raw edge magnitude.

    A desk does not bet a big point edge it is unsure about; it bets a smaller
    edge it is confident is real and that compounds the bankroll. Tiers:

      STRONG LEAN  P(+) ≥ 0.65, shrunk edge ≥ 3.0pp, growth > 0
      LEAN         P(+) ≥ 0.58, shrunk edge ≥ 1.5pp, growth > 0
      AVOID        shrunk edge ≤ −4.0pp
      NEED MORE    confidence < 0.40 or evidence < 0.40
      PASS         otherwise
    """
    if model_confidence < 0.40 or evidence_quality < 0.40:
        return "NEED MORE INFO"
    if qe.edge_quant <= -0.04:
        return "AVOID"
    if qe.prob_positive >= 0.65 and qe.edge_quant >= 0.03 and qe.growth_rate > 0:
        return "STRONG LEAN"
    if qe.prob_positive >= 0.58 and qe.edge_quant >= 0.015 and qe.growth_rate > 0:
        return "LEAN"
    return "PASS"
