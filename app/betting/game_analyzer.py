"""Game analysis engine — produces probability estimates and betting recommendations.

Deterministic model using available stats. No LLM — LLM is only for report polish.

Model components:
  1. Starting pitcher quality (FIP differential → win probability adjustment)
  2. Bullpen vulnerability differential
  3. Offense vs defense (runs_per_game, runs_allowed_per_game, wOBA)
  4. Recent form (trend_label)
  5. Home field advantage (54% base rate, per MLB historical)
  6. Weather (wind out → favor Over, dome → neutral)

Output: GameAnalysis dataclass with model probabilities, recommendation tier,
Kelly fraction, and human-readable key_factors.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import List, Optional

from app.contracts import PitcherFormWindow, TeamFormWindow, WeatherSnapshot
from app.features.bullpen_vulnerability import BullpenReport

# ── Constants ─────────────────────────────────────────────────────────────────
HOME_ADVANTAGE = 0.54          # historical MLB home win rate
FIP_SCALE = 0.018              # each 1-run FIP advantage ≈ 1.8% win prob shift
BULLPEN_VULN_SCALE = 0.0012   # each 1-pt vulnerability differential ≈ 0.12%
OFFENSE_SCALE = 0.025          # each 0.5 run/game offense edge ≈ 2.5%
KELLY_FRACTION = 0.25          # fractional Kelly multiplier (conservative)
WIND_OUT_THRESHOLD_MPH = 12    # wind blowing out at this speed favors Over
WIND_OUT_DEGREES = (30, 120)   # approximate "blowing out to CF" range

TREND_ADJUSTMENTS = {
    # TrendLabel enum values (from contracts.py)
    "heating_up": +0.025,
    "stable_strong": +0.01,
    "volatile": 0.0,
    "stable_weak": -0.01,
    "cooling_off": -0.025,
    "regression_risk": -0.02,
    "small_sample_warning": 0.0,
}

RECOMMENDATION_TIERS = [
    ("STRONG LEAN", 0.06, 0.70),
    ("LEAN",        0.03, 0.55),
    ("PASS",        0.00, 0.00),
    ("AVOID",      -0.05, 0.00),
]


# ── Output types ──────────────────────────────────────────────────────────────
@dataclass
class GameAnalysis:
    game_id: int
    home_team_abbr: str
    away_team_abbr: str

    # Probabilities
    model_home_win_prob: float
    model_away_win_prob: float

    # Moneyline recommendation
    ml_lean: str                # "HOME", "AWAY", or "PASS"
    ml_confidence: float        # 0-1
    ml_tier: str                # "STRONG LEAN" / "LEAN" / "PASS"

    # Total recommendation
    total_lean: str             # "OVER", "UNDER", "PASS"
    total_confidence: float
    projected_total: float      # projected combined runs

    # Bet sizing (Kelly vs actual line)
    ml_kelly_fraction: float    # fraction of bankroll to bet
    ml_american_odds: int = -110  # actual line used for Kelly (default -110)

    # Factors
    key_factors: List[str] = field(default_factory=list)
    cautions: List[str] = field(default_factory=list)

    # Component breakdown (for transparency)
    sp_advantage: str = ""
    bullpen_edge: str = ""
    offense_edge: str = ""
    implied_prob: float = 0.5238
    # Component breakdown for transparency (each value = prob shift from that factor)
    component_fip: float = 0.0
    component_bullpen: float = 0.0
    component_offense: float = 0.0
    component_trend: float = 0.0
    component_k_matchup: float = 0.0
    component_weather: float = 0.0


# ── Kelly criterion ────────────────────────────────────────────────────────────
def kelly(p: float, american_odds: int = -110) -> float:
    """Fractional Kelly bet size given model probability p and American odds."""
    if american_odds < 0:
        b = 100 / abs(american_odds)
    else:
        b = american_odds / 100
    q = 1 - p
    raw = (b * p - q) / b
    return max(0.0, round(raw * KELLY_FRACTION, 4))


FIP_CONSTANT = 3.20   # league-average FIP constant (ERA-scale normalizer)


def _derive_fip(sp: Optional[PitcherFormWindow]) -> Optional[float]:
    """Compute FIP from rate stats when the stored fip field is None.
    FIP = (13*HR + 3*BB - 2*K) / IP + FIP_constant
        = (13*hr_per_9 + 3*bb_per_9 - 2*k_per_9) / 9 + FIP_constant
    Returns None if insufficient data."""
    if sp is None:
        return None
    if sp.fip is not None:
        return sp.fip
    if sp.hr_per_9 is None or sp.bb_per_9 is None or sp.k_per_9 is None:
        return None
    if sp.insufficient_sample or sp.innings_pitched < 5:
        return None
    fip = (13 * sp.hr_per_9 + 3 * sp.bb_per_9 - 2 * sp.k_per_9) / 9 + FIP_CONSTANT
    return round(max(0.5, min(8.0, fip)), 2)


# ── FIP → win probability adjustment ─────────────────────────────────────────
def fip_to_prob_adj(home_fip: Optional[float], away_fip: Optional[float]) -> float:
    """Return home win probability adjustment from FIP differential."""
    if home_fip is None or away_fip is None:
        return 0.0
    diff = away_fip - home_fip   # positive = home pitcher has better FIP
    return round(min(0.12, max(-0.12, diff * FIP_SCALE)), 4)


def _trend_adj(form: Optional[TeamFormWindow]) -> float:
    if form is None:
        return 0.0
    label = form.trend_label.value if hasattr(form.trend_label, "value") else str(form.trend_label)
    return TREND_ADJUSTMENTS.get(label, 0.0)


WOBA_SCALE = 0.15   # each 0.010 wOBA advantage ≈ 1.5% win prob shift
WOBA_AVERAGE = 0.320


def _offense_adj(home_form: Optional[TeamFormWindow], away_form: Optional[TeamFormWindow]) -> tuple[float, str]:
    if home_form is None or away_form is None:
        return 0.0, ""
    home_off = home_form.runs_per_game or 0.0
    away_def = away_form.runs_allowed_per_game or 0.0
    away_off = away_form.runs_per_game or 0.0
    home_def = home_form.runs_allowed_per_game or 0.0

    # Primary: runs/game vs runs allowed/game differential
    rpg_net = ((home_off - away_def) - (away_off - home_def)) * OFFENSE_SCALE

    # Secondary: wOBA differential (better contact quality signal)
    woba_net = 0.0
    home_woba = home_form.team_woba
    away_woba = away_form.team_woba
    if home_woba and away_woba:
        woba_net = (home_woba - away_woba) * WOBA_SCALE

    net = round(min(0.10, max(-0.10, rpg_net + woba_net)), 4)

    edge_str = ""
    if abs(net) > 0.01:
        side = "HOME" if net > 0 else "AWAY"
        if home_woba and away_woba:
            edge_str = f"{side} offense edge: {home_off:.1f} R/G, wOBA {home_woba:.3f} vs {away_woba:.3f}"
        else:
            edge_str = f"{side} offense edge: {home_off:.1f} vs {away_def:.1f} R/G allowed"
    return net, edge_str


def _weather_adj(weather: Optional[WeatherSnapshot]) -> tuple[float, str, str]:
    """Returns (total_adj, factor_str, caution_str). Positive = favor Over."""
    if weather is None or weather.is_dome:
        return 0.0, "", ""
    speed = weather.wind_speed_mph or 0
    deg = weather.wind_direction_deg or 0
    precip = weather.precipitation_chance or 0

    total_adj = 0.0
    factor = ""
    caution = ""

    if speed >= WIND_OUT_THRESHOLD_MPH and WIND_OUT_DEGREES[0] <= deg <= WIND_OUT_DEGREES[1]:
        total_adj = 0.3
        factor = f"Wind {speed:.0f}mph blowing out ({deg:.0f}°) — favors Over"
    elif speed >= WIND_OUT_THRESHOLD_MPH:
        total_adj = -0.2
        factor = f"Wind {speed:.0f}mph ({deg:.0f}°) — slight Under lean"

    if precip >= 40:
        caution = f"⚠ {precip:.0f}% precipitation chance — game may be shortened"

    temp = weather.temperature_f or 72
    if temp >= 85:
        total_adj += 0.2
        factor = (factor + " · " if factor else "") + f"High temp {temp:.0f}°F — hitter-friendly"
    elif temp <= 50:
        total_adj -= 0.2
        factor = (factor + " · " if factor else "") + f"Cold {temp:.0f}°F — pitcher-friendly"

    return total_adj, factor, caution


def _sp_factor_str(home_sp: Optional[PitcherFormWindow], away_sp: Optional[PitcherFormWindow], adj: float) -> tuple[str, str]:
    """Returns (sp_advantage_str, factor_str)."""
    home_fip = _derive_fip(home_sp)
    away_fip = _derive_fip(away_sp)
    if home_fip is None and away_fip is None:
        return "", "Probable starters TBD — no SP edge calculable"
    if home_fip is None:
        return f"AWAY SP: FIP {away_fip:.2f}", f"{away_sp.pitcher_name} starting (AWAY) — home SP TBD"
    if away_fip is None:
        return f"HOME SP: FIP {home_fip:.2f}", f"{home_sp.pitcher_name} starting (HOME) — away SP TBD"

    diff = away_fip - home_fip
    better = "HOME" if diff > 0 else "AWAY"
    name = home_sp.pitcher_name if diff > 0 else away_sp.pitcher_name
    adv = f"{better} SP edge: {name} FIP {min(home_fip, away_fip):.2f} vs {max(home_fip, away_fip):.2f}"
    factor = adv if abs(diff) > 0.3 else ""
    return adv, factor


# ── Main entry point ───────────────────────────────────────────────────────────
def analyze_game(
    game_id: int,
    home_abbr: str,
    away_abbr: str,
    home_sp: Optional[PitcherFormWindow],
    away_sp: Optional[PitcherFormWindow],
    home_bullpen: Optional[BullpenReport],
    away_bullpen: Optional[BullpenReport],
    home_form: Optional[TeamFormWindow],
    away_form: Optional[TeamFormWindow],
    weather: Optional[WeatherSnapshot],
    home_ml_odds: Optional[int] = None,   # actual moneyline (e.g. -150, +130)
    away_ml_odds: Optional[int] = None,
    total_line: Optional[float] = None,   # posted O/U total (e.g. 8.5)
    home_k_rate: Optional[float] = None,  # team strikeout rate (0-1) from batting
    away_k_rate: Optional[float] = None,
    home_iso: Optional[float] = None,     # team ISO from batting
    away_iso: Optional[float] = None,
) -> GameAnalysis:

    factors: list[str] = []
    cautions: list[str] = []

    # 1. Base home advantage
    prob = HOME_ADVANTAGE

    # 2. Starting pitcher
    home_fip = _derive_fip(home_sp)
    away_fip = _derive_fip(away_sp)
    sp_adj = fip_to_prob_adj(home_fip, away_fip)
    prob += sp_adj
    comp_fip = sp_adj   # track for breakdown
    sp_adv, sp_factor = _sp_factor_str(home_sp, away_sp, sp_adj)
    if sp_factor:
        factors.append(sp_factor)

    # Starter K/9 edge
    if home_sp and away_sp and home_sp.k_per_9 and away_sp.k_per_9:
        k_diff = home_sp.k_per_9 - away_sp.k_per_9
        if abs(k_diff) > 1.5:
            side = "HOME" if k_diff > 0 else "AWAY"
            sp_name = home_sp.pitcher_name if k_diff > 0 else away_sp.pitcher_name
            factors.append(f"{side} SP K/9 edge: {sp_name} {max(home_sp.k_per_9, away_sp.k_per_9):.1f} K/9")
            adj = k_diff * 0.005
            prob += adj
            comp_fip += adj

    # BB/9 control edge — high walk rate signals instability
    for sp, side_label in [(home_sp, "HOME"), (away_sp, "AWAY")]:
        if sp and sp.bb_per_9 and sp.bb_per_9 > 4.5 and not sp.insufficient_sample:
            cautions.append(f"⚠ {side_label} SP walk rate {sp.bb_per_9:.1f} BB/9 — control concern")
            adj = -0.015 if side_label == "HOME" else +0.015
            prob += adj
            comp_fip += adj

    # ERA vs FIP divergence — flags regression risk
    for sp, side_label in [(home_sp, "HOME"), (away_sp, "AWAY")]:
        if sp and sp.era and not sp.insufficient_sample:
            fip_val = _derive_fip(sp)
            if fip_val:
                divergence = sp.era - fip_val
                if divergence < -1.0:
                    cautions.append(
                        f"⚠ {side_label} SP ERA {sp.era:.2f} significantly below FIP {fip_val:.2f} — regression risk"
                    )
                elif divergence > 1.2:
                    factors.append(
                        f"{side_label} SP ERA ({sp.era:.2f}) above FIP ({fip_val:.2f}) — positive regression candidate"
                    )

    # K% matchup edge
    K_RATE_HIGH = 0.24
    comp_k = 0.0
    for sp, team_k_rate, side_label, opp_label in [
        (home_sp, away_k_rate, "HOME", "AWAY"),
        (away_sp, home_k_rate, "AWAY", "HOME"),
    ]:
        if sp and sp.k_per_9 and sp.k_per_9 >= 9.0 and team_k_rate and team_k_rate >= K_RATE_HIGH:
            factors.append(
                f"{side_label} SP strikeout pitcher ({sp.k_per_9:.1f} K/9) vs high-K% {opp_label} lineup ({team_k_rate:.1%}) — amplified edge"
            )
            adj = 0.012 if side_label == "HOME" else -0.012
            prob += adj
            comp_k += adj

    # Short-start amplifier
    for sp, bp, side_label in [(home_sp, home_bullpen, "HOME"), (away_sp, away_bullpen, "AWAY")]:
        if sp and sp.avg_innings_per_start and sp.avg_innings_per_start < 5.0 and not sp.insufficient_sample:
            cautions.append(
                f"⚠ {side_label} SP averaging {sp.avg_innings_per_start:.1f} IP/start — heavy bullpen reliance expected"
            )

    # 3. Bullpen vulnerability
    home_vuln = home_bullpen.vulnerability_score if home_bullpen else 50.0
    away_vuln = away_bullpen.vulnerability_score if away_bullpen else 50.0
    vuln_diff = away_vuln - home_vuln

    bp_scale = BULLPEN_VULN_SCALE
    if home_sp and home_sp.avg_innings_per_start and home_sp.avg_innings_per_start < 5.5:
        bp_scale *= 1.4
    elif away_sp and away_sp.avg_innings_per_start and away_sp.avg_innings_per_start < 5.5:
        bp_scale *= 1.4

    bp_adj = vuln_diff * bp_scale
    prob += bp_adj
    comp_bp = bp_adj

    bp_edge = ""
    if abs(vuln_diff) >= 10:
        worse = "AWAY" if vuln_diff > 0 else "HOME"
        bp_edge = f"{worse} bullpen vulnerable: {max(home_vuln, away_vuln):.0f}/100 vs {min(home_vuln, away_vuln):.0f}/100"
        factors.append(bp_edge)
        if max(home_vuln, away_vuln) >= 70:
            cautions.append(f"⚠ {worse} bullpen at HIGH vulnerability — late-game risk")

    # 4. Offense / defense
    off_adj, off_str = _offense_adj(home_form, away_form)
    prob += off_adj
    comp_off = off_adj
    if off_str:
        factors.append(off_str)

    # 5. Recent form
    home_trend = _trend_adj(home_form)
    away_trend = _trend_adj(away_form)
    trend_adj = home_trend - away_trend
    prob += trend_adj
    comp_trend = trend_adj
    if abs(trend_adj) >= 0.02:
        side = "HOME" if trend_adj > 0 else "AWAY"
        factors.append(f"{side} team trending better recently")

    # Clamp
    prob = round(min(0.72, max(0.30, prob)), 4)
    away_prob = round(1 - prob, 4)

    # 6. Moneyline recommendation
    lean_prob = prob if prob >= 0.5 else away_prob
    lean_side = "HOME" if prob >= 0.5 else "AWAY"
    lean_abbr = home_abbr if lean_side == "HOME" else away_abbr

    implied = 0.5238  # -110 implied probability
    edge = lean_prob - implied
    tier = "PASS"
    for t, min_edge, min_conf in RECOMMENDATION_TIERS:
        if t == "AVOID":
            if edge <= min_edge:
                tier = t
                break
        elif edge >= min_edge and lean_prob >= min_conf:
            tier = t
            break

    ml_lean = lean_side if tier not in ("PASS", "AVOID") else "PASS"

    # Use actual line if available, otherwise assume -110
    if lean_side == "HOME" and home_ml_odds is not None:
        actual_odds = home_ml_odds
    elif lean_side == "AWAY" and away_ml_odds is not None:
        actual_odds = away_ml_odds
    else:
        actual_odds = -110

    def _implied(american_odds: int) -> float:
        if american_odds < 0:
            return abs(american_odds) / (abs(american_odds) + 100)
        return 100 / (american_odds + 100)

    implied = _implied(actual_odds)
    edge = lean_prob - implied  # recompute with real line
    # Re-check tier against real edge (actual line may shift recommendation)
    tier = "PASS"
    for t, min_edge, min_conf in RECOMMENDATION_TIERS:
        if t == "AVOID":
            if edge <= min_edge:
                tier = t
                break
        elif edge >= min_edge and lean_prob >= min_conf:
            tier = t
            break
    ml_lean = lean_side if tier not in ("PASS", "AVOID") else "PASS"
    ml_kelly = kelly(lean_prob, actual_odds) if ml_lean != "PASS" else 0.0

    # 7. Total (runs projection)
    home_rpg = home_form.runs_per_game if home_form else 4.5
    away_rpg = away_form.runs_per_game if away_form else 4.5
    home_rag = home_form.runs_allowed_per_game if home_form else 4.5
    away_rag = away_form.runs_allowed_per_game if away_form else 4.5

    # Average offense vs allowed
    proj_home_runs = (home_rpg + away_rag) / 2
    proj_away_runs = (away_rpg + home_rag) / 2

    # SP suppression adjustment
    if home_fip:
        sp_suppress = max(0.5, min(1.2, 3.5 / home_fip))
        proj_away_runs *= sp_suppress
    if away_fip:
        sp_suppress = max(0.5, min(1.2, 3.5 / away_fip))
        proj_home_runs *= sp_suppress

    projected_total = round(proj_home_runs + proj_away_runs, 1)

    # ISO power adjustment — high ISO lineups score more extra-base hits
    ISO_AVERAGE = 0.160
    for iso_val, label in [(home_iso, "HOME"), (away_iso, "AWAY")]:
        if iso_val is not None:
            iso_adj = (iso_val - ISO_AVERAGE) * 2.0   # each 0.050 ISO above avg adds ~0.1 runs
            projected_total = round(projected_total + iso_adj, 1)
            if iso_val >= 0.200:
                factors.append(f"{label} lineup power surge: ISO {iso_val:.3f} — favors Over")

    # Weather adjustment
    weather_total_adj, weather_factor, weather_caution = _weather_adj(weather)
    comp_weather = weather_total_adj * 0.01  # rough win-prob proxy for breakdown display
    projected_total = round(projected_total + weather_total_adj, 1)
    if weather_factor:
        factors.append(weather_factor)
    if weather_caution:
        cautions.append(weather_caution)

    # Compare against actual posted line if available, else typical
    compare_line = total_line if total_line is not None else 8.5
    threshold = 0.6 if total_line is not None else 0.8  # tighter when real line exists
    if projected_total > compare_line + threshold:
        total_lean, total_conf = "OVER", min(0.65, 0.50 + (projected_total - compare_line) * 0.03)
    elif projected_total < compare_line - threshold:
        total_lean, total_conf = "UNDER", min(0.65, 0.50 + (compare_line - projected_total) * 0.03)
    else:
        total_lean, total_conf = "PASS", 0.5

    # Insufficient data cautions
    if (home_sp is None or home_sp.insufficient_sample) and (away_sp is None or away_sp.insufficient_sample):
        cautions.append("⚠ Both starters have small samples — SP edge unreliable")

    if not factors:
        factors.append("No strong edges identified — statistical dead heat")

    return GameAnalysis(
        game_id=game_id,
        home_team_abbr=home_abbr,
        away_team_abbr=away_abbr,
        model_home_win_prob=prob,
        model_away_win_prob=away_prob,
        ml_lean=ml_lean,
        ml_confidence=lean_prob,
        ml_tier=tier,
        total_lean=total_lean,
        total_confidence=total_conf,
        projected_total=projected_total,
        ml_kelly_fraction=ml_kelly,
        ml_american_odds=actual_odds,
        key_factors=factors,
        cautions=cautions,
        sp_advantage=sp_adv,
        bullpen_edge=bp_edge,
        offense_edge=off_str,
        implied_prob=implied,
        component_fip=round(comp_fip, 4),
        component_bullpen=round(comp_bp, 4),
        component_offense=round(comp_off, 4),
        component_trend=round(comp_trend, 4),
        component_k_matchup=round(comp_k, 4),
        component_weather=round(comp_weather, 4),
    )
