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
from app.betting.implied_probability import vig_free_probability, expected_value
from app.betting.quant import compute_quant_edge, quant_recommendation

# ── Constants ─────────────────────────────────────────────────────────────────
HOME_ADVANTAGE = 0.535         # 2022-2024 MLB home win rate (declining from old 54% avg)
FIP_SCALE = 0.018              # each 1-run FIP advantage ≈ 1.8% win prob shift
BULLPEN_VULN_SCALE = 0.0009   # each 1-pt vulnerability differential ≈ 0.09% (lowered from 0.0012)
SP_DOMINANCE_FIP_THRESHOLD = 4.0   # starters below this FIP reduce bullpen reliance
SP_DOMINANCE_BP_DISCOUNT = 0.55    # when a starter is dominant, bullpen weight × 0.55
OFFENSE_SCALE = 0.025          # each 0.5 run/game offense edge ≈ 2.5%
KELLY_FRACTION = 0.25          # fractional Kelly multiplier (conservative)
WIND_OUT_THRESHOLD_MPH = 12    # wind blowing out at this speed favors Over
WIND_OUT_DEGREES = (30, 120)   # approximate "blowing out to CF" range

# Park run factors — multiplier on projected total (1.0 = neutral).
# Coors Field is the canonical outlier; domes are slightly pitcher-friendly.
PARK_FACTORS: dict[str, float] = {
    # Hitter-friendly
    "Coors Field": 1.16,
    "Great American Ball Park": 1.10,
    "Wrigley Field": 1.06,
    "Globe Life Field": 1.05,
    "American Family Field": 1.04,
    "Fenway Park": 1.03,
    "Oriole Park at Camden Yards": 1.02,
    "Yankee Stadium": 1.02,
    "Citizens Bank Park": 1.01,
    "Chase Field": 1.01,
    "Rate Field": 1.01,              # White Sox (formerly Guaranteed Rate Field)
    "Truist Park": 1.00,
    "Rogers Centre": 1.00,
    "Angel Stadium": 0.99,
    "Busch Stadium": 0.99,
    "Citi Field": 0.99,
    "Progressive Field": 0.99,
    "Target Field": 0.99,
    # Pitcher-friendly
    "Nationals Park": 0.98,
    "Kauffman Stadium": 0.98,
    "Daikin Park": 0.98,             # Astros (dome)
    "Comerica Park": 0.97,
    "loanDepot park": 0.97,
    "PNC Park": 0.97,
    "Tropicana Field": 0.97,
    "T-Mobile Park": 0.96,
    "UNIQLO Field at Dodger Stadium": 0.96,
    "Petco Park": 0.93,
    "Oracle Park": 0.92,
}

# Days-rest win probability adjustments for the pitcher (home perspective).
# Short rest (<4 days): fatigue penalty.  Long rest (6+ days): rust penalty.
REST_ADJ_SHORT = -0.018   # <4 days (short rest)
REST_ADJ_LONG  = -0.008   # 8+ days (skipped turn / injury return)

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

# Thresholds are against VIG-FREE implied probability.
# 5% vig-free edge ≈ 3% edge against a typical -110 line after removing ~4.5% juice.
RECOMMENDATION_TIERS = [
    ("STRONG LEAN", 0.05, 0.70),
    ("LEAN",        0.025, 0.55),
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
    total_tier: str = "PASS"    # "STRONG LEAN" / "LEAN" / "PASS"
    total_confidence: float = 0.5
    projected_total: float = 0.0      # projected combined runs
    total_line: Optional[float] = None
    total_kelly_fraction: float = 0.0

    # Totals quant layer
    qt_edge_quant: float = 0.0
    qt_edge_sd: float = 0.0
    qt_prob_positive: float = 0.5
    qt_p_model: float = 0.5
    qt_p_shrunk: float = 0.5
    qt_kelly_sized: float = 0.0
    qt_kelly_mult: float = 0.0
    qt_growth_rate: float = 0.0

    # Bet sizing (Kelly vs actual line)
    ml_kelly_fraction: float = 0.0
    ml_american_odds: int = -110  # actual line used for Kelly (default -110)

    # Factors
    key_factors: List[str] = field(default_factory=list)
    cautions: List[str] = field(default_factory=list)

    # Component breakdown (for transparency)
    sp_advantage: str = ""
    bullpen_edge: str = ""
    offense_edge: str = ""

    # Raw book implied probability (includes vig)
    implied_prob: float = 0.5238
    # Vig-free implied probability (Pinnacle method) — correct comparison target
    vig_free_implied: float = 0.5000
    # Book overround (1.05 = 5% vig)
    overround: float = 1.0476
    # Edge against vig-free probability — honest edge number
    edge_vig_free: float = 0.0
    # Expected value per dollar wagered: EV = b×p − q
    ev_per_dollar: float = 0.0

    # ── Quant layer (PhD-level) ──────────────────────────────────────────────
    # Devig method comparison: proportional (naive) vs Shin (favorite-longshot
    # corrected). q_* fields are the honest, risk-managed numbers.
    q_prop_vig_free: float = 0.5000   # Sonnet-4.6-theory devig
    q_shin_vig_free: float = 0.5000   # Opus-4.7 Shin devig
    q_shin_z: float = 0.0             # estimated insider proportion
    q_p_model: float = 0.5000         # raw model prob for the leaned side
    q_p_shrunk: float = 0.5000        # after Bayesian shrinkage to market
    q_shrink_weight: float = 0.0      # model reliability w
    q_edge_naive: float = 0.0         # p_model − proportional vig-free
    q_edge_quant: float = 0.0         # p_shrunk − Shin vig-free (honest)
    q_edge_sd: float = 0.0            # SD of the edge estimate
    q_prob_positive: float = 0.5      # P(edge > 0) — what you actually bet
    q_ci_low: float = 0.0             # 95% credible interval on edge
    q_ci_high: float = 0.0
    q_effective_n: float = 0.0        # effective sample size
    q_kelly_full: float = 0.0         # unscaled Kelly
    q_kelly_sized: float = 0.0        # uncertainty-adjusted stake
    q_kelly_mult: float = 0.0         # DERIVED fractional multiplier
    q_growth_rate: float = 0.0        # expected log-growth per bet
    q_doubling_bets: float = 0.0      # bets to double bankroll (0 = never)
    q_evidence_quality: float = 0.0   # data-completeness proxy ∈ [0,1]

    # Component breakdown for transparency (each value = prob shift from that factor)
    component_fip: float = 0.0
    component_bullpen: float = 0.0
    component_offense: float = 0.0
    component_trend: float = 0.0
    component_k_matchup: float = 0.0
    component_weather: float = 0.0
    component_rest: float = 0.0
    component_park: float = 0.0


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
WOBA_AVERAGE = 0.310   # 2024 MLB league wOBA (FanGraphs park-adjusted)


def _offense_adj(home_form: Optional[TeamFormWindow], away_form: Optional[TeamFormWindow]) -> tuple[float, str]:
    if home_form is None or away_form is None:
        return 0.0, ""
    home_off = home_form.runs_per_game or 0.0
    away_def = away_form.runs_allowed_per_game or 0.0
    away_off = away_form.runs_per_game or 0.0
    home_def = home_form.runs_allowed_per_game or 0.0

    # Primary: matchup-expected runs differential (Pythagorean-style)
    #   home_expected ≈ (home_off + away_def) / 2  — home's offense meets away's defensive baseline
    #   away_expected ≈ (away_off + home_def) / 2  — away's offense meets home's defensive baseline
    #   net = (home_expected - away_expected) / 2  ← built into SCALE
    # Bug fix 2026-05-17: previously had flipped signs on the defense terms,
    # which collapsed to (home_off + home_def) − (away_off + away_def) — i.e. it rewarded
    # teams that play in high-scoring games (Coors effect) rather than matchup edge.
    rpg_net = ((home_off + away_def) - (away_off + home_def)) / 2 * OFFENSE_SCALE

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
            woba_gap = abs(home_woba - away_woba)
            edge_rpg = home_off if side == "HOME" else away_off
            edge_woba = home_woba if side == "HOME" else away_woba
            other_rpg = away_off if side == "HOME" else home_off
            other_woba = away_woba if side == "HOME" else home_woba
            edge_str = (
                f"{side} offense edge: {edge_rpg:.1f} R/G wOBA {edge_woba:.3f}"
                f" vs {other_rpg:.1f} R/G wOBA {other_woba:.3f}"
                f" — wOBA gap {woba_gap:.3f} → +{abs(net) * 100:.1f}% net shift"
            )
        else:
            edge_off = home_off if side == "HOME" else away_off
            other_allowed = away_def if side == "HOME" else home_def
            edge_str = (
                f"{side} offense edge: {edge_off:.1f} R/G vs opponent {other_allowed:.1f} RA/G allowed"
                f" → +{abs(net) * 100:.1f}% net shift"
            )
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
        if home_sp is not None and away_sp is not None:
            return "", f"Probable starters announced ({home_sp.pitcher_name} vs {away_sp.pitcher_name}) — insufficient SP sample for edge"
        return "", "Probable starters TBD — no SP edge calculable"
    if home_fip is None:
        home_label = home_sp.pitcher_name if home_sp is not None else "home SP"
        return f"AWAY SP: FIP {away_fip:.2f}", f"{away_sp.pitcher_name} (AWAY) FIP {away_fip:.2f} — {home_label} lacks SP sample"
    if away_fip is None:
        away_label = away_sp.pitcher_name if away_sp is not None else "away SP"
        return f"HOME SP: FIP {home_fip:.2f}", f"{home_sp.pitcher_name} (HOME) FIP {home_fip:.2f} — {away_label} lacks SP sample"

    diff = away_fip - home_fip
    better = "HOME" if diff > 0 else "AWAY"
    better_name = home_sp.pitcher_name if diff > 0 else away_sp.pitcher_name
    worse_name = away_sp.pitcher_name if diff > 0 else home_sp.pitcher_name
    adv = (
        f"{better} SP edge: {better_name} FIP {min(home_fip, away_fip):.2f}"
        f" vs {worse_name} FIP {max(home_fip, away_fip):.2f}"
        f" — {abs(diff):.2f} run gap → +{abs(diff) * FIP_SCALE * 100:.1f}% win prob shift"
    )
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
    home_ml_odds: Optional[int] = None,
    away_ml_odds: Optional[int] = None,
    total_line: Optional[float] = None,
    over_odds: Optional[int] = None,
    under_odds: Optional[int] = None,
    home_k_rate: Optional[float] = None,
    away_k_rate: Optional[float] = None,
    home_iso: Optional[float] = None,
    away_iso: Optional[float] = None,
    home_bb_rate: Optional[float] = None,   # team walk rate (BB/PA)
    away_bb_rate: Optional[float] = None,
    home_sp_days_rest: Optional[int] = None,
    away_sp_days_rest: Optional[int] = None,
    venue: Optional[str] = None,
    home_h2h: Optional[tuple] = None,
    away_h2h: Optional[tuple] = None,
    home_home_record: Optional[tuple] = None,   # (wins, home_games) this season
    away_road_record: Optional[tuple] = None,   # (wins, road_games) this season
    home_sp_last_pitch_count: Optional[int] = None,
    away_sp_last_pitch_count: Optional[int] = None,
    home_sp_babip: Optional[float] = None,
    away_sp_babip: Optional[float] = None,
    home_sb_rate: Optional[float] = None,   # SB/PA this season
    away_sb_rate: Optional[float] = None,
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
    # 2024 MLB avg K% ≈ 22.6%; 1 SD ≈ 2.5pp → "high K%" = 25%+
    K_RATE_HIGH = 0.25
    comp_k = 0.0
    for sp, team_k_rate, side_label, opp_label in [
        (home_sp, away_k_rate, "HOME", "AWAY"),
        (away_sp, home_k_rate, "AWAY", "HOME"),
    ]:
        if sp and sp.k_per_9 and sp.k_per_9 >= 9.0 and team_k_rate and team_k_rate >= K_RATE_HIGH:
            factors.append(
                f"{side_label} K matchup: {sp.k_per_9:.1f} K/9 pitcher vs {opp_label} lineup {team_k_rate:.1%} K%"
                f" (lg avg 22.6%) — double strikeout environment → +1.2% win prob"
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

    # Short-starter amplifier — if either SP is a 5-inning type, bullpen matters more
    if home_sp and home_sp.avg_innings_per_start and home_sp.avg_innings_per_start < 5.5:
        bp_scale *= 1.4
    elif away_sp and away_sp.avg_innings_per_start and away_sp.avg_innings_per_start < 5.5:
        bp_scale *= 1.4

    # SP dominance discount — when the starter whose bullpen is being hurt is elite,
    # they'll pitch deep and reduce actual bullpen exposure. E.g. if home FIP < 4.0,
    # the home bullpen vulnerability matters less because the starter eats innings.
    # Only discount when the gap is hurting that team (vuln_diff > 0 = away bullpen worse,
    # so home team benefits from away bullpen; home's own bullpen isn't the issue).
    home_fip_dominant = home_fip is not None and home_fip < SP_DOMINANCE_FIP_THRESHOLD
    away_fip_dominant = away_fip is not None and away_fip < SP_DOMINANCE_FIP_THRESHOLD
    if home_fip_dominant or away_fip_dominant:
        bp_scale *= SP_DOMINANCE_BP_DISCOUNT

    bp_adj = vuln_diff * bp_scale
    prob += bp_adj
    comp_bp = bp_adj

    bp_edge = ""
    if abs(vuln_diff) >= 10:
        worse = "AWAY" if vuln_diff > 0 else "HOME"
        beneficiary = "HOME" if vuln_diff > 0 else "AWAY"
        bp_adj_pct = abs(bp_adj) * 100
        bp_edge = (
            f"{worse} bullpen exposed: {max(home_vuln, away_vuln):.0f}/100 vs {min(home_vuln, away_vuln):.0f}/100"
            f" — {abs(vuln_diff):.0f}-pt gap → +{bp_adj_pct:.1f}% for {beneficiary}"
        )
        factors.append(bp_edge)
        if max(home_vuln, away_vuln) >= 70:
            cautions.append(f"⚠ {worse} bullpen HIGH vulnerability (≥70) — late-game risk")

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
        home_label = home_form.trend_label.value if home_form and hasattr(home_form.trend_label, "value") else str(getattr(home_form, "trend_label", "?"))
        away_label = away_form.trend_label.value if away_form and hasattr(away_form.trend_label, "value") else str(getattr(away_form, "trend_label", "?"))
        factors.append(
            f"{side} form edge: HOME {home_label.replace('_', ' ')} vs AWAY {away_label.replace('_', ' ')}"
            f" → +{abs(trend_adj) * 100:.1f}% win prob shift"
        )

    # 6. Home/road split — how each team performs in their specific context
    if home_home_record and home_home_record[1] >= 10:
        h_wins, h_games = home_home_record
        home_win_rate = h_wins / h_games
        split_adj = (home_win_rate - HOME_ADVANTAGE) * 0.5
        split_adj = round(min(0.04, max(-0.04, split_adj)), 4)
        prob += split_adj
        comp_trend += split_adj
        if split_adj >= 0.025:
            factors.append(
                f"HOME elite at home: {h_wins}-{h_games - h_wins} ({home_win_rate:.1%} win rate)"
                f" vs 53.5% expected → +{split_adj * 100:.1f}% adjustment"
            )
        elif split_adj <= -0.025:
            cautions.append(
                f"⚠ HOME struggles at home: {h_wins}-{h_games - h_wins} ({home_win_rate:.1%} win rate)"
                f" vs 53.5% expected → {split_adj * 100:.1f}% adjustment"
            )

    if away_road_record and away_road_record[1] >= 10:
        a_wins, a_games = away_road_record
        road_win_rate = a_wins / a_games
        road_adj = (road_win_rate - (1 - HOME_ADVANTAGE)) * 0.5
        road_adj = round(min(0.04, max(-0.04, road_adj)), 4)
        prob -= road_adj   # positive road_adj means away team is strong on road → hurt home prob
        comp_trend -= road_adj
        if road_adj >= 0.025:
            cautions.append(
                f"⚠ AWAY strong on road: {a_wins}-{a_games - a_wins} ({road_win_rate:.1%})"
                f" vs 46.5% expected → counter-acts home edge by {road_adj * 100:.1f}%"
            )
        elif road_adj <= -0.025:
            factors.append(
                f"AWAY poor on road: {a_wins}-{a_games - a_wins} ({road_win_rate:.1%})"
                f" vs 46.5% expected → +{abs(road_adj) * 100:.1f}% for HOME"
            )

    # 7. Head-to-head season record
    if home_h2h and home_h2h[1] >= 4:
        h_wins, h_games = home_h2h
        h_win_rate = h_wins / h_games
        h2h_adj = (h_win_rate - 0.5) * 0.06   # max ~±3% at 0/N or N/N
        prob += h2h_adj
        comp_trend += h2h_adj
        if abs(h2h_adj) >= 0.015:
            side = "HOME" if h2h_adj > 0 else "AWAY"
            factors.append(
                f"{side} dominates season series: {h_wins}-{h_games - h_wins} H2H record"
            )

    # 7. Pitcher days rest
    comp_rest = 0.0
    for days, sp, side_label in [
        (home_sp_days_rest, home_sp, "HOME"),
        (away_sp_days_rest, away_sp, "AWAY"),
    ]:
        if days is None or sp is None or sp.insufficient_sample:
            continue
        if days < 4:
            adj = REST_ADJ_SHORT if side_label == "HOME" else -REST_ADJ_SHORT
            prob += adj
            comp_rest += adj
            cautions.append(f"⚠ {side_label} SP on short rest ({days}d) — fatigue risk")
        elif days <= 6:
            # 4-6 days is normal rotation cadence — no adjustment
            pass
        elif days >= 8:
            adj = REST_ADJ_LONG if side_label == "HOME" else -REST_ADJ_LONG
            prob += adj
            comp_rest += adj
            cautions.append(f"⚠ {side_label} SP on extended rest ({days}d) — skipped turn, possible rust")

    # Pitcher last-outing pitch count workload
    for pitches, sp, side_label in [
        (home_sp_last_pitch_count, home_sp, "HOME"),
        (away_sp_last_pitch_count, away_sp, "AWAY"),
    ]:
        if pitches is None or sp is None or sp.insufficient_sample:
            continue
        if pitches >= 105:
            adj = -0.012 if side_label == "HOME" else +0.012
            prob += adj
            comp_rest += adj
            cautions.append(f"⚠ {side_label} SP threw {pitches} pitches last outing — high workload")
        elif pitches >= 95:
            adj = -0.006 if side_label == "HOME" else +0.006
            prob += adj
            comp_rest += adj

    # 7. Team walk rate offensive signal — high BB% offenses reach base more
    # 2024 MLB avg BB% ≈ 8.5%; "high patience" = 10.5%+ (2 SD above avg)
    BB_RATE_HIGH = 0.105
    BB_RATE_LOW = 0.065   # genuinely free-swinging (1.5 SD below avg)
    for bb_rate, side_label in [(home_bb_rate, "HOME"), (away_bb_rate, "AWAY")]:
        if bb_rate is None:
            continue
        if bb_rate >= BB_RATE_HIGH:
            adj = 0.012 if side_label == "HOME" else -0.012
            prob += adj
            comp_off += adj
            factors.append(
                f"{side_label} lineup patient: {bb_rate:.1%} BB% (lg avg 8.5%, threshold 10.5%)"
                f" — working counts, on-base advantage → +1.2% win prob"
            )
        elif bb_rate <= BB_RATE_LOW:
            adj = -0.008 if side_label == "HOME" else +0.008
            prob += adj
            comp_off += adj

    # BABIP regression signal — prefer PitcherFormWindow.babip if available, else inline
    # Pitcher BABIP: league avg ≈ .298, SD ≈ 30pts
    # High = .340+ (1.4 SD above avg → unlucky, expect positive regression)
    # Low  = .265  (1.1 SD below avg → running lucky, negative regression risk)
    BABIP_HIGH = 0.340
    BABIP_LOW  = 0.265
    for _inline_babip, sp, side_label in [
        (home_sp_babip, home_sp, "HOME"),
        (away_sp_babip, away_sp, "AWAY"),
    ]:
        if sp is None or sp.insufficient_sample:
            continue
        babip = sp.babip if sp.babip is not None else _inline_babip
        if babip is None:
            continue
        if babip >= BABIP_HIGH:
            adj = 0.015 if side_label == "HOME" else -0.015
            prob += adj
            comp_fip += adj
            factors.append(
                f"{side_label} SP BABIP {babip:.3f} (lg avg .298) — 1.4+ SD above average, ERA inflated by bad luck"
                f" → +1.5% positive regression adjustment"
            )
        elif babip <= BABIP_LOW:
            adj = -0.015 if side_label == "HOME" else 0.015
            prob += adj
            comp_fip += adj
            cautions.append(
                f"⚠ {side_label} SP BABIP {babip:.3f} (lg avg .298) — 1.1+ SD below average, ERA flattered by luck"
                f" → −1.5% regression risk adjustment"
            )

    # Speed / pressure signal — use form window SB success rate if available
    SB_RATE_HIGH = 0.025
    # Break-even SB% = CS_value / (SB_value + CS_value) = 0.467 / (0.175 + 0.467) = 72.7%
    # 2024 MLB avg success rate ≈ 79%; "elite running game" = 80%+
    SB_SUCCESS_ELITE = 0.80
    for sb_rate, form, side_label in [
        (home_sb_rate, home_form, "HOME"),
        (away_sb_rate, away_form, "AWAY"),
    ]:
        # Prefer form window stolen_base_success_rate if populated
        sb_success = getattr(form, "stolen_base_success_rate", None) if form else None
        sb_attempts = getattr(form, "stolen_base_attempts", None) if form else None
        if sb_success is not None and sb_attempts and sb_attempts >= 5 and sb_success >= SB_SUCCESS_ELITE:
            adj = 0.010 if side_label == "HOME" else -0.010
            prob += adj
            comp_off += adj
            factors.append(
                f"{side_label} speed game: {sb_success:.0%} SB success on {int(sb_attempts)} attempts — baserunning edge"
            )
        elif sb_rate is not None and sb_rate >= SB_RATE_HIGH:
            adj = 0.007 if side_label == "HOME" else -0.007
            prob += adj
            comp_off += adj
            factors.append(f"{side_label} lineup speed threat: {sb_rate:.3f} SB/PA")

    # Lineup quality signal from TeamFormWindow.lineup_quality_score
    LQ_SCALE = 0.08   # each 0.010 above/below average wOBA → 0.8% shift
    LQ_AVERAGE = 0.310   # match 2024 MLB wOBA average
    for form, side_label in [(home_form, "HOME"), (away_form, "AWAY")]:
        lq = getattr(form, "lineup_quality_score", None) if form else None
        if lq is None:
            continue
        lq_adj = (lq - LQ_AVERAGE) * LQ_SCALE
        lq_adj = round(min(0.04, max(-0.04, lq_adj)), 4)
        prob += lq_adj if side_label == "HOME" else -lq_adj
        comp_off += lq_adj if side_label == "HOME" else -lq_adj
        if abs(lq_adj) >= 0.015:
            side = side_label if lq_adj > 0 else ("AWAY" if side_label == "HOME" else "HOME")
            factors.append(f"{side_label} lineup quality score {lq:.3f} — {'elite' if lq_adj > 0 else 'weak'} order")

    # Clamp
    prob = round(min(0.72, max(0.30, prob)), 4)
    away_prob = round(1 - prob, 4)

    # 6. Moneyline recommendation
    lean_prob = prob if prob >= 0.5 else away_prob
    lean_side = "HOME" if prob >= 0.5 else "AWAY"

    # Use actual line if available, otherwise assume -110 / +100 market
    if home_ml_odds is not None and away_ml_odds is not None:
        actual_home_odds = home_ml_odds
        actual_away_odds = away_ml_odds
    elif lean_side == "HOME" and home_ml_odds is not None:
        actual_home_odds = home_ml_odds
        actual_away_odds = -home_ml_odds + (10 if home_ml_odds < 0 else -10)  # rough mirror
    elif lean_side == "AWAY" and away_ml_odds is not None:
        actual_away_odds = away_ml_odds
        actual_home_odds = -away_ml_odds + (10 if away_ml_odds < 0 else -10)
    else:
        actual_home_odds = -110
        actual_away_odds = -110

    actual_odds = actual_home_odds if lean_side == "HOME" else actual_away_odds
    other_odds = actual_away_odds if lean_side == "HOME" else actual_home_odds

    # Vig removal — compare model to vig-free market, not raw implied
    vf_this, vf_other, overround_val = vig_free_probability(actual_odds, other_odds)
    raw_implied = abs(actual_odds) / (abs(actual_odds) + 100) if actual_odds < 0 else 100 / (actual_odds + 100)
    edge_vf = lean_prob - vf_this
    ev = expected_value(lean_prob, actual_odds)

    # ── Evidence quality: data-completeness proxy ∈ [0,1] ────────────────────
    # Drives both the Bayesian shrinkage weight and the posterior sample size.
    # A model with thin inputs is shrunk hard toward the market and its edge
    # interval widens — it cannot earn a STRONG LEAN on vibes.
    _signals = [
        home_fip is not None,
        away_fip is not None,
        home_bullpen is not None,
        away_bullpen is not None,
        home_form is not None,
        away_form is not None,
        home_ml_odds is not None and away_ml_odds is not None,
    ]
    evidence_quality = sum(1.0 for s in _signals if s) / len(_signals)
    if home_sp and home_sp.insufficient_sample:
        evidence_quality *= 0.85
    if away_sp and away_sp.insufficient_sample:
        evidence_quality *= 0.85
    evidence_quality = round(min(1.0, max(0.0, evidence_quality)), 4)

    # ── Quant pipeline: Shin devig → shrinkage → posterior → sized Kelly ─────
    # Only run if we have real market odds. Comparing model prob to -110/-110
    # fallback generates false edges — every game would look like STRONG LEAN.
    has_real_odds = home_ml_odds is not None and away_ml_odds is not None
    qe = compute_quant_edge(lean_prob, actual_odds, other_odds, evidence_quality)
    if not has_real_odds:
        tier = "PASS"
        ml_lean = "PASS"
        ml_kelly = 0.0
    else:
        tier = quant_recommendation(qe, model_confidence=lean_prob, evidence_quality=evidence_quality)
        if tier == "NEED MORE INFO":
            tier = "PASS"
        ml_lean = lean_side if tier in ("STRONG LEAN", "LEAN") else "PASS"
        ml_kelly = qe.kelly_sized if ml_lean != "PASS" else 0.0

    # 7. Total (runs projection)
    # Totals are very sensitive to tiny run samples. Regress R/G and RA/G
    # toward a league-average 4.5 runs/team until a window has a real sample.
    RUNS_BASELINE = 4.5
    TOTAL_SAMPLE_TARGET_GAMES = 10

    def _total_sample_weight(form: Optional[TeamFormWindow]) -> float:
        games = form.games if form is not None else 0
        return min(1.0, max(0.0, games / TOTAL_SAMPLE_TARGET_GAMES))

    def _regressed_runs(value: Optional[float], form: Optional[TeamFormWindow]) -> float:
        if value is None:
            return RUNS_BASELINE
        w = _total_sample_weight(form)
        return w * value + (1.0 - w) * RUNS_BASELINE

    home_rpg = _regressed_runs(home_form.runs_per_game if home_form else None, home_form)
    away_rpg = _regressed_runs(away_form.runs_per_game if away_form else None, away_form)
    home_rag = _regressed_runs(home_form.runs_allowed_per_game if home_form else None, home_form)
    away_rag = _regressed_runs(away_form.runs_allowed_per_game if away_form else None, away_form)
    total_sample_weight = min(_total_sample_weight(home_form), _total_sample_weight(away_form))
    if total_sample_weight < 0.6:
        cautions.append(
            f"⚠ Total projection heavily regressed toward league average: only "
            f"{home_form.games if home_form else 0}/{away_form.games if away_form else 0} games in team windows"
        )

    # Average offense vs allowed
    proj_home_runs = (home_rpg + away_rag) / 2
    proj_away_runs = (away_rpg + home_rag) / 2

    # SP suppression adjustment — better starting pitcher (lower FIP) should
    # SUPPRESS opposing offense. Multiplier scales opponent runs.
    #   Baseline = 4.0 (≈ 2024 MLB lg-avg FIP)
    #   FIP 4.0 → 1.00× (neutral)
    #   FIP 3.0 → 0.75× (clamped: ace suppresses)
    #   FIP 5.0 → 1.25× (clamped: poor pitcher allows more)
    # Bug fix 2026-05-17: previously was `3.5 / fip` (inverted direction
    # AND too generous a baseline — aces inflated opponent runs, bad pitchers
    # suppressed them). Now `fip / 4.0`, clamped [0.75, 1.25] for ±25% max swing.
    SP_FIP_BASELINE = 4.0
    if home_fip:
        sp_suppress = max(0.75, min(1.25, home_fip / SP_FIP_BASELINE))
        proj_away_runs *= sp_suppress
    if away_fip:
        sp_suppress = max(0.75, min(1.25, away_fip / SP_FIP_BASELINE))
        proj_home_runs *= sp_suppress

    projected_total = round(proj_home_runs + proj_away_runs, 1)

    # ISO power adjustment — high ISO lineups score more extra-base hits
    ISO_AVERAGE = 0.162   # 2024 MLB avg ISO (SLG − AVG) ≈ .162
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

    # Park factor adjustment on projected total
    comp_park = 0.0
    if venue:
        pf = PARK_FACTORS.get(venue)
        if pf is not None and pf != 1.0:
            original = projected_total
            projected_total = round(projected_total * pf, 1)
            comp_park = round((projected_total - original) * 0.005, 4)
            direction = "hitter-friendly" if pf > 1.0 else "pitcher-friendly"
            run_delta = projected_total - original
            factors.append(
                f"Park factor {pf:.2f}x at {venue} ({direction})"
                f" — total adjusted {original:.1f} → {projected_total:.1f} runs ({run_delta:+.1f})"
            )

    # ── Totals quant pipeline ────────────────────────────────────────────────
    # Convert projected_total → P(over) via a normal CDF.
    # σ starts at 3.0 runs: combined-game SD is larger than per-team SD
    # (~2.2 × √2 ≈ 3.1). Low sample quality widens σ and lowers the cap so
    # a two-game window cannot manufacture a 99% P(+) total.
    import math as _math
    total_evidence_quality = evidence_quality
    total_evidence_quality *= max(0.2, total_sample_weight)
    if home_sp is None or home_sp.insufficient_sample:
        total_evidence_quality *= 0.85
    if away_sp is None or away_sp.insufficient_sample:
        total_evidence_quality *= 0.85
    total_evidence_quality = round(min(1.0, max(0.0, total_evidence_quality)), 4)

    _TOTAL_SIGMA = 3.0 + (1.0 - total_evidence_quality) * 2.0
    _TOTAL_PROB_CAP = 0.60 + 0.25 * total_evidence_quality

    compare_line = total_line if total_line is not None else 8.5
    _z_over = (projected_total - compare_line) / _TOTAL_SIGMA
    _p_raw = 0.5 * (1.0 + _math.erf(_z_over / _math.sqrt(2.0)))
    p_over_model = min(_TOTAL_PROB_CAP, max(1.0 - _TOTAL_PROB_CAP, _p_raw))

    has_total_odds = over_odds is not None and under_odds is not None
    _actual_over_odds = over_odds if over_odds is not None else -110
    _actual_under_odds = under_odds if under_odds is not None else -110

    # Lean toward over or under
    if p_over_model >= 0.5:
        total_lean_side = "OVER"
        p_lean_side = p_over_model
        lean_over_odds = _actual_over_odds
        lean_under_odds = _actual_under_odds
    else:
        total_lean_side = "UNDER"
        p_lean_side = 1.0 - p_over_model
        lean_over_odds = _actual_under_odds
        lean_under_odds = _actual_over_odds

    qt = compute_quant_edge(
        p_model_side=p_lean_side,
        side_odds=lean_over_odds,
        other_odds=lean_under_odds,
        evidence_quality=total_evidence_quality,
    )

    if not has_total_odds:
        total_tier = "PASS"
        total_kelly = 0.0
        total_lean = "PASS"
        total_conf = 0.5
    else:
        total_tier = quant_recommendation(qt, model_confidence=p_lean_side, evidence_quality=total_evidence_quality)
        if total_tier == "NEED MORE INFO":
            total_tier = "PASS"
        if total_tier in ("STRONG LEAN", "LEAN"):
            total_lean = total_lean_side
            total_kelly = qt.kelly_sized
            total_conf = qt.prob_positive
        else:
            total_lean = "PASS"
            total_kelly = 0.0
            total_conf = 0.5

    # Insufficient data cautions
    if not has_real_odds:
        cautions.append("⚠ No market odds available — tier/Kelly suppressed. Set ODDS_API_KEY for real edges.")
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
        total_tier=total_tier,
        total_confidence=total_conf,
        projected_total=projected_total,
        total_line=compare_line,
        total_kelly_fraction=total_kelly,
        qt_edge_quant=qt.edge_quant,
        qt_edge_sd=qt.edge_sd,
        qt_prob_positive=qt.prob_positive,
        qt_p_model=round(p_lean_side, 4),
        qt_p_shrunk=qt.p_shrunk,
        qt_kelly_sized=qt.kelly_sized,
        qt_kelly_mult=qt.kelly_multiplier,
        qt_growth_rate=qt.growth_rate,
        ml_kelly_fraction=ml_kelly,
        ml_american_odds=actual_odds,
        key_factors=factors,
        cautions=cautions,
        sp_advantage=sp_adv,
        bullpen_edge=bp_edge,
        offense_edge=off_str,
        implied_prob=round(raw_implied, 4),
        vig_free_implied=round(vf_this, 4),
        overround=round(overround_val, 4),
        edge_vig_free=round(edge_vf, 4),
        ev_per_dollar=round(ev, 4),
        q_prop_vig_free=qe.prop_vig_free,
        q_shin_vig_free=qe.shin_vig_free,
        q_shin_z=qe.shin_z,
        q_p_model=qe.p_model,
        q_p_shrunk=qe.p_shrunk,
        q_shrink_weight=qe.shrink_weight,
        q_edge_naive=qe.edge_naive,
        q_edge_quant=qe.edge_quant,
        q_edge_sd=qe.edge_sd,
        q_prob_positive=qe.prob_positive,
        q_ci_low=qe.ci_low,
        q_ci_high=qe.ci_high,
        q_effective_n=qe.effective_n,
        q_kelly_full=qe.kelly_full,
        q_kelly_sized=qe.kelly_sized,
        q_kelly_mult=qe.kelly_multiplier,
        q_growth_rate=qe.growth_rate,
        q_doubling_bets=qe.doubling_bets if qe.doubling_bets is not None else 0.0,
        q_evidence_quality=evidence_quality,
        component_fip=round(comp_fip, 4),
        component_bullpen=round(comp_bp, 4),
        component_offense=round(comp_off, 4),
        component_trend=round(comp_trend, 4),
        component_k_matchup=round(comp_k, 4),
        component_weather=round(comp_weather, 4),
        component_rest=round(comp_rest, 4),
        component_park=round(comp_park, 4),
    )
