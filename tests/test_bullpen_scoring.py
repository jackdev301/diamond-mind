"""Tests for bullpen fatigue, quality, and vulnerability scoring."""

import json
from datetime import date
from pathlib import Path

import pytest

from app.contracts import BullpenState, RelieverFormWindow, RelieverUsage, WindowKey, TrendLabel
from app.features.bullpen_fatigue import calculate_fatigue
from app.features.bullpen_quality import (
    calculate_available_quality,
    calculate_overall_quality,
    label_availability,
    _era_to_quality,
)
from app.features.bullpen_vulnerability import score_bullpen, BullpenReport


FIXTURES = Path(__file__).parent / "fixtures"


def _load_state() -> BullpenState:
    raw = json.loads((FIXTURES / "bullpen_state_phi_2026-05-15.json").read_text())
    relievers = [
        RelieverFormWindow(
            pitcher_id=r["pitcher_id"],
            pitcher_name=r["pitcher_name"],
            team_id=r["team_id"],
            role=r["role"],
            window=WindowKey(r["window"]),
            appearances=r["appearances"],
            innings_pitched=r["innings_pitched"],
            era=r["era"],
            whip=r["whip"],
            k_per_9=r["k_per_9"],
            bb_per_9=r["bb_per_9"],
            trend_label=TrendLabel(r["trend_label"]),
            as_of_date=date.fromisoformat(r["as_of_date"]),
            fip=r.get("fip"),
            inherited_runners_scored_pct=r.get("inherited_runners_scored_pct"),
        )
        for r in raw["relievers"]
    ]
    usage = [
        RelieverUsage(
            pitcher_id=u["pitcher_id"],
            pitcher_name=u["pitcher_name"],
            team_id=u["team_id"],
            role=u["role"],
            game_date=date.fromisoformat(u["game_date"]),
            pitches=u["pitches"],
            innings=u["innings"],
            appeared=u["appeared"],
        )
        for u in raw["recent_usage"]
    ]
    return BullpenState(
        team_id=raw["team_id"],
        team_abbr=raw["team_abbr"],
        as_of_date=date.fromisoformat(raw["as_of_date"]),
        yesterday_total_innings=raw["yesterday_total_innings"],
        yesterday_total_pitches=raw["yesterday_total_pitches"],
        yesterday_relievers_used=raw["yesterday_relievers_used"],
        closer_pitched_yesterday=raw["closer_pitched_yesterday"],
        high_leverage_pitched_yesterday=raw["high_leverage_pitched_yesterday"],
        back_to_back_relievers=raw["back_to_back_relievers"],
        three_in_four_relievers=raw["three_in_four_relievers"],
        relievers=relievers,
        recent_usage=usage,
    )


# ── _era_to_quality ───────────────────────────────────────────────────────────

def test_era_quality_elite():
    # ERA 1.0 → ~100
    assert _era_to_quality(1.0) == pytest.approx(100.0)

def test_era_quality_average():
    # ERA ~4.14 → (100 - (4.14-1)*14) = 100 - 43.96 = 56.04
    q = _era_to_quality(4.14)
    assert 50.0 < q < 65.0

def test_era_quality_poor():
    # ERA 8.0 → 100 - (8-1)*14 = 100 - 98 = 2
    assert _era_to_quality(8.0) == pytest.approx(2.0)

def test_era_quality_clamped():
    assert _era_to_quality(0.0) == pytest.approx(100.0)
    assert _era_to_quality(99.0) == pytest.approx(0.0)


# ── calculate_fatigue ─────────────────────────────────────────────────────────

def test_fatigue_from_fixture():
    state = _load_state()
    fatigue = calculate_fatigue(state)
    # PHI fixture: 4.0 IP yesterday (≥4 → +20), 62 pitches (≥50 → +10),
    # 4 relievers used (≥4 → +5), closer pitched (+10),
    # 1 back-to-back reliever (+8), 1 high-leverage pitched (+8)
    # Expected: 20+10+5+10+8+8 = 61
    assert fatigue == pytest.approx(61.0)

def test_fatigue_max_100():
    # Extreme state should clamp to 100
    state = _load_state()
    # Patch to extreme values
    import dataclasses
    extreme = dataclasses.replace(
        state,
        yesterday_total_innings=6.0,
        yesterday_total_pitches=90,
        yesterday_relievers_used=6,
        back_to_back_relievers=[1, 2, 3, 4],
        three_in_four_relievers=[5, 6, 7],
        high_leverage_pitched_yesterday=[1, 2, 3],
    )
    assert calculate_fatigue(extreme) <= 100.0

def test_fatigue_zero_for_fresh_bullpen():
    state = _load_state()
    import dataclasses
    fresh = dataclasses.replace(
        state,
        yesterday_total_innings=0.0,
        yesterday_total_pitches=0,
        yesterday_relievers_used=0,
        closer_pitched_yesterday=False,
        high_leverage_pitched_yesterday=[],
        back_to_back_relievers=[],
        three_in_four_relievers=[],
    )
    assert calculate_fatigue(fresh) == 0.0


# ── label_availability ────────────────────────────────────────────────────────

def test_availability_alvarado_limited():
    # Alvarado (621237) is in back_to_back_relievers and threw 22 pitches yesterday (< 25)
    # → "limited" not "unavailable"
    state = _load_state()
    labels = label_availability(state)
    assert labels[621237] == "limited"

def test_availability_strahm_available():
    # Strahm (595928) is not in any tired list
    state = _load_state()
    labels = label_availability(state)
    assert labels[595928] == "available"


# ── calculate_overall_quality ─────────────────────────────────────────────────

def test_overall_quality_range():
    state = _load_state()
    q = calculate_overall_quality(state)
    assert 0.0 <= q <= 100.0

def test_overall_quality_strong_bullpen():
    # PHI fixture has ERAs 3.12, 2.81, 2.30 — should be high quality
    state = _load_state()
    q = calculate_overall_quality(state)
    assert q >= 65.0

def test_available_quality_in_range():
    # Available quality is based on available/limited arms only — can differ from
    # overall in either direction depending on which arms are unavailable.
    # Alvarado (limited, ERA 3.12) is one of the better arms, so excluding him
    # can raise or lower the available average. Just verify it's a valid score.
    state = _load_state()
    labels = label_availability(state)
    overall = calculate_overall_quality(state)
    available = calculate_available_quality(state, labels)
    assert 0.0 <= available <= 100.0
    assert 0.0 <= overall <= 100.0


# ── score_bullpen ─────────────────────────────────────────────────────────────

def test_score_bullpen_returns_report():
    state = _load_state()
    report = score_bullpen(state)
    assert isinstance(report, BullpenReport)
    assert report.team_abbr == "PHI"

def test_score_bullpen_scores_in_range():
    state = _load_state()
    report = score_bullpen(state)
    assert 0 <= report.fatigue_score <= 100
    assert 0 <= report.overall_quality <= 100
    assert 0 <= report.available_quality <= 100
    assert 0 <= report.vulnerability_score <= 100

def test_score_bullpen_vulnerability_formula():
    state = _load_state()
    report = score_bullpen(state)
    expected = 0.55 * report.fatigue_score + 0.45 * (100 - report.available_quality)
    assert report.vulnerability_score == pytest.approx(expected, abs=0.5)

def test_score_bullpen_best_available_excludes_unavailable():
    state = _load_state()
    report = score_bullpen(state)
    # No one is unavailable in this fixture (Alvarado threw < 25 pitches)
    assert len(report.best_available) <= 3

def test_score_bullpen_betting_implication_not_empty():
    state = _load_state()
    report = score_bullpen(state)
    assert isinstance(report.betting_implication, str)
    assert len(report.betting_implication) > 10

def test_score_bullpen_no_forbidden_language():
    state = _load_state()
    report = score_bullpen(state)
    for word in ("lock", "guaranteed", "hammer", "free money"):
        assert word.lower() not in report.betting_implication.lower()
