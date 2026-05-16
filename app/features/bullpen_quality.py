"""Bullpen quality scoring.

Computes overall and available quality scores from RelieverFormWindow data.
Assigns availability labels (available / limited / unavailable) based on
rest patterns in BullpenState.

Availability rules (documented here per Track B working agreements):
  unavailable — pitcher in back_to_back_relievers AND threw >= 25 pitches yesterday
  limited     — pitcher in three_in_four_relievers, OR closer who pitched yesterday,
                OR in back_to_back but threw < 25 pitches yesterday
  available   — everyone else
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Literal

from app.contracts import BullpenState, RelieverFormWindow, RelieverUsage, WindowKey
from app.features.bullpen_roles import effective_roles

AvailabilityLabel = Literal["available", "limited", "unavailable"]

_WINDOW_WEIGHTS: Dict[WindowKey, float] = {
    WindowKey.SEASON: 0.50,
    WindowKey.L20: 0.25,
    WindowKey.L10: 0.15,
    WindowKey.L5: 0.10,
}

_ROLE_WEIGHTS: Dict[str, float] = {
    "closer": 1.5,
    "setup": 1.3,
    "high_leverage": 1.2,
    "middle": 1.0,
    "long": 0.9,
    "low_leverage": 0.8,
}

_FALLBACK_ERA = 4.50


def _era_to_quality(era: float) -> float:
    """Map ERA to a 0–100 quality score. ERA 1.0 → ~100, ERA 8.0 → ~2."""
    return max(0.0, min(100.0, 100.0 - (era - 1.0) * 14.0))


def _weighted_era(windows: List[RelieverFormWindow]) -> float:
    total_weight = 0.0
    weighted_sum = 0.0
    for w in windows:
        weight = _WINDOW_WEIGHTS.get(w.window, 0.0)
        if weight > 0:
            weighted_sum += w.era * weight
            total_weight += weight
    return weighted_sum / total_weight if total_weight > 0 else _FALLBACK_ERA


def _yesterday_pitches(
    pitcher_id: int, as_of_date: date, usage: List[RelieverUsage]
) -> int:
    yesterday = as_of_date - timedelta(days=1)
    for u in usage:
        if u.pitcher_id == pitcher_id and u.game_date == yesterday:
            return u.pitches
    return 0


def label_availability(state: BullpenState) -> Dict[int, AvailabilityLabel]:
    pitcher_ids = {r.pitcher_id for r in state.relievers}
    labels: Dict[int, AvailabilityLabel] = {}

    for pid in pitcher_ids:
        in_bb = pid in state.back_to_back_relievers
        in_tif = pid in state.three_in_four_relievers
        is_closer = any(
            r.role == "closer" for r in state.relievers if r.pitcher_id == pid
        )
        pitches_yesterday = _yesterday_pitches(pid, state.as_of_date, state.recent_usage)

        if in_bb and pitches_yesterday >= 25:
            labels[pid] = "unavailable"
        elif in_tif or (is_closer and state.closer_pitched_yesterday) or in_bb:
            labels[pid] = "limited"
        else:
            labels[pid] = "available"

    return labels


def _group_by_pitcher(
    relievers: List[RelieverFormWindow],
) -> Dict[int, List[RelieverFormWindow]]:
    groups: Dict[int, List[RelieverFormWindow]] = {}
    for r in relievers:
        groups.setdefault(r.pitcher_id, []).append(r)
    return groups


def calculate_overall_quality(state: BullpenState) -> float:
    """Role-weighted quality score across all rostered relievers."""
    by_pitcher = _group_by_pitcher(state.relievers)
    if not by_pitcher:
        return 50.0

    roles = effective_roles(state)
    total_weight = 0.0
    weighted_sum = 0.0
    for pid, windows in by_pitcher.items():
        role_weight = _ROLE_WEIGHTS.get(roles.get(pid, windows[0].role), 1.0)
        quality = _era_to_quality(_weighted_era(windows))
        weighted_sum += quality * role_weight
        total_weight += role_weight

    return weighted_sum / total_weight if total_weight > 0 else 50.0


def calculate_available_quality(
    state: BullpenState,
    availability: Dict[int, AvailabilityLabel],
) -> float:
    """Quality score using only available arms; limited arms count at half weight."""
    by_pitcher = _group_by_pitcher(state.relievers)
    if not by_pitcher:
        return 50.0

    roles = effective_roles(state)
    total_weight = 0.0
    weighted_sum = 0.0
    for pid, windows in by_pitcher.items():
        label = availability.get(pid, "available")
        if label == "unavailable":
            continue
        role_weight = _ROLE_WEIGHTS.get(roles.get(pid, windows[0].role), 1.0)
        if label == "limited":
            role_weight *= 0.5
        quality = _era_to_quality(_weighted_era(windows))
        weighted_sum += quality * role_weight
        total_weight += role_weight

    return weighted_sum / total_weight if total_weight > 0 else 50.0
