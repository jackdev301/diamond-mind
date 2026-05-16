"""Bullpen fatigue scoring.

Implements the point-accumulation formula from PROJECT_BRIEF.md.
Input: BullpenState (produced by Track A).
Output: float 0–100 (higher = more fatigued).
"""

from app.contracts import BullpenState


def calculate_fatigue(state: BullpenState) -> float:
    score = 0

    ip = state.yesterday_total_innings
    if ip >= 5:
        score += 30
    elif ip >= 4:
        score += 20
    elif ip >= 3:
        score += 10

    pitches = state.yesterday_total_pitches
    if pitches >= 70:
        score += 20
    elif pitches >= 50:
        score += 10

    used = state.yesterday_relievers_used
    if used >= 5:
        score += 10
    elif used >= 4:
        score += 5

    score += min(len(state.back_to_back_relievers) * 8, 24)
    score += min(len(state.three_in_four_relievers) * 10, 20)

    if state.closer_pitched_yesterday:
        score += 10

    score += min(len(state.high_leverage_pitched_yesterday) * 8, 16)

    return float(min(score, 100))
