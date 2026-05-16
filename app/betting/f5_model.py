"""First-5-innings (F5) moneyline model.

Per Arnav's Track A/B split (collab msg #13): F5 ML isolates starting-pitcher
skill and removes bullpen variance, so the model is deliberately narrow —
home-field baseline + starter quality differential ONLY. No bullpen, no
late-game trend, no cumulative noise (W/L, RBI, AVG).

Platoon-adjusted wOBA vs SP handedness is part of Arnav's vision but is
BLOCKED: the contracts carry no batter-vs-handedness / L/R split fields yet
(Track A is shipping L/R platoon splits on player_game_logs). Until that data
exists this model does not fabricate a platoon term — there is a documented
hook (`platoon_adj`) that stays 0.0 with no inputs.

Win probability is routed through the same quant pipeline as the full-game
model (Shin devig → Bayesian shrink → edge posterior → uncertainty Kelly)
when an F5 line is supplied. If no F5 odds are given, only the projection is
returned — no invented line.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.contracts import PitcherFormWindow
from app.betting.quant import compute_quant_edge, quant_recommendation

# ── Parameters (model assumptions, not empirical claims) ─────────────────────
# Full-game home win rate is ~0.535 in this codebase (HOME_ADVANTAGE). F5
# markets price the home edge smaller: no late-inning home leverage, no save
# situations inside the first 5. 0.52 is the F5 baseline assumption.
HOME_ADV_F5 = 0.52

# SP explains a larger share of a 5-inning result than a 9-inning one (the
# bullpen is excluded entirely), so the FIP differential is weighted heavier
# than the full-game FIP_SCALE (0.018/run).
F5_FIP_SCALE = 0.028
F5_FIP_CAP = 0.15  # max win-prob swing from the starter differential


@dataclass
class F5Analysis:
    game_id: int
    home_team_abbr: str
    away_team_abbr: str
    model_home_win_prob: float
    model_away_win_prob: float
    home_sp_metric: Optional[float]   # xFIP if present else FIP
    away_sp_metric: Optional[float]
    sp_metric_name: str               # "xFIP" | "FIP" | "none"
    fip_differential: float           # away_metric - home_metric (home perspective)
    platoon_adj: float                # 0.0 until Arnav's L/R splits land
    rationale: str
    # Betting fields populated only when an F5 line is supplied
    ml_lean: str = "PASS"
    ml_tier: str = "PASS"
    ml_confidence: float = 0.0
    ml_kelly_fraction: float = 0.0
    ml_american_odds: Optional[int] = None
    q_shin_vig_free: Optional[float] = None
    q_edge_quant: Optional[float] = None
    q_prob_positive: Optional[float] = None
    q_growth_rate: Optional[float] = None


def _sp_metric(sp: Optional[PitcherFormWindow]) -> tuple[Optional[float], str]:
    """Prefer xFIP (more regressed / predictive), fall back to FIP.

    Returns (value, name). No derivation from rate stats here — if neither
    xFIP nor FIP is present, the starter contributes nothing rather than a
    fabricated estimate.
    """
    if sp is None or sp.insufficient_sample:
        return None, "none"
    if sp.xfip is not None:
        return sp.xfip, "xFIP"
    if sp.fip is not None:
        return sp.fip, "FIP"
    return None, "none"


def analyze_f5_moneyline(
    game_id: int,
    home_abbr: str,
    away_abbr: str,
    home_sp: Optional[PitcherFormWindow],
    away_sp: Optional[PitcherFormWindow],
    home_f5_odds: Optional[int] = None,
    away_f5_odds: Optional[int] = None,
    evidence_quality: float = 0.6,
) -> F5Analysis:
    """Deterministic F5 moneyline projection (+ quant bet rec if a line exists)."""
    home_metric, home_name = _sp_metric(home_sp)
    away_metric, away_name = _sp_metric(away_sp)
    metric_name = home_name if home_name != "none" else away_name

    prob = HOME_ADV_F5
    fip_diff = 0.0
    if home_metric is not None and away_metric is not None:
        # positive diff = home starter has the lower (better) FIP/xFIP
        fip_diff = away_metric - home_metric
        swing = max(-F5_FIP_CAP, min(F5_FIP_CAP, fip_diff * F5_FIP_SCALE))
        prob += swing

    platoon_adj = 0.0  # BLOCKED on Arnav's L/R platoon splits — no fake data

    prob = round(min(0.80, max(0.20, prob + platoon_adj)), 4)
    away_prob = round(1.0 - prob, 4)

    if metric_name == "none":
        rationale = "No usable starter FIP/xFIP — F5 projection is home-field baseline only; not actionable."
    else:
        better = "HOME" if fip_diff > 0 else "AWAY"
        rationale = (
            f"F5 isolates the starters: {metric_name} differential {abs(fip_diff):.2f} favors {better} "
            f"({home_abbr} {home_metric if home_metric is not None else 'n/a'} vs "
            f"{away_abbr} {away_metric if away_metric is not None else 'n/a'}). "
            f"Bullpen excluded by design. Platoon term pending Track A L/R splits."
        )

    result = F5Analysis(
        game_id=game_id,
        home_team_abbr=home_abbr,
        away_team_abbr=away_abbr,
        model_home_win_prob=prob,
        model_away_win_prob=away_prob,
        home_sp_metric=home_metric,
        away_sp_metric=away_metric,
        sp_metric_name=metric_name,
        fip_differential=round(fip_diff, 4),
        platoon_adj=platoon_adj,
        rationale=rationale,
    )

    # Betting recommendation only if a real F5 line is supplied
    if home_f5_odds is not None and away_f5_odds is not None and metric_name != "none":
        lean_side = "HOME" if prob >= 0.5 else "AWAY"
        lean_prob = prob if prob >= 0.5 else away_prob
        side_odds = home_f5_odds if lean_side == "HOME" else away_f5_odds
        other_odds = away_f5_odds if lean_side == "HOME" else home_f5_odds

        qe = compute_quant_edge(lean_prob, side_odds, other_odds, evidence_quality)
        tier = quant_recommendation(qe, model_confidence=lean_prob, evidence_quality=evidence_quality)
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
