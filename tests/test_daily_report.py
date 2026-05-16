"""Tests for the daily report generator."""

from datetime import date, datetime

import pytest

from app.betting.game_analyzer import GameAnalysis
from app.contracts import GameContext
from app.features.bullpen_vulnerability import BullpenReport
from app.reports.daily_report import GameBundle, generate_daily_report


def _bp(abbr: str, vuln: float = 40.0) -> BullpenReport:
    return BullpenReport(
        team_abbr=abbr,
        fatigue_score=20.0,
        overall_quality=70.0,
        available_quality=65.0,
        vulnerability_score=vuln,
        unavailable_relievers=[],
        limited_relievers=[],
        best_available=["Arm A", "Arm B"],
        weakest_available=[],
        betting_implication="Low vulnerability — bullpen not a concern.",
    )


def _ctx(home: str = "PHI", away: str = "NYM") -> GameContext:
    return GameContext(
        game_id=42,
        game_date=date(2026, 5, 15),
        game_time_utc=datetime(2026, 5, 15, 23, 5),
        home_team_id=10,
        away_team_id=20,
        home_team_abbr=home,
        away_team_abbr=away,
        venue="Citizens Bank Park",
        is_doubleheader=False,
        game_number=1,
    )


def _bundle(home: str = "PHI", away: str = "NYM", vuln_home: float = 35.0, vuln_away: float = 65.0) -> GameBundle:
    return GameBundle(
        context=_ctx(home, away),
        home_bullpen=_bp(home, vuln_home),
        away_bullpen=_bp(away, vuln_away),
    )


# ── generate_daily_report ──────────────────────────────────────────────────────

def test_report_returns_string():
    report = generate_daily_report(date(2026, 5, 15), [_bundle()])
    assert isinstance(report, str)
    assert len(report) > 100


def test_report_header():
    report = generate_daily_report(date(2026, 5, 15), [_bundle()])
    assert "Diamond Mind" in report
    assert "2026" in report
    assert "not financial advice" in report.lower() or "not be treated as financial advice" in report.lower()


def test_report_slate_overview_count():
    bundles = [_bundle("PHI", "NYM"), _bundle("LAD", "SD")]
    report = generate_daily_report(date(2026, 5, 15), bundles)
    assert "2 game" in report


def test_report_contains_all_teams():
    bundles = [_bundle("PHI", "NYM"), _bundle("LAD", "SD")]
    report = generate_daily_report(date(2026, 5, 15), bundles)
    for abbr in ("PHI", "NYM", "LAD", "SD"):
        assert abbr in report


def test_report_contains_bullpen_scores():
    report = generate_daily_report(date(2026, 5, 15), [_bundle("PHI", "NYM", 35.0, 72.0)])
    assert "35" in report
    assert "72" in report


def test_report_uncertainty_footer():
    report = generate_daily_report(date(2026, 5, 15), [_bundle()])
    assert "Uncertainty" in report
    assert "Strong Lean" in report or "strong_lean" in report.lower()


def test_report_no_forbidden_language():
    report = generate_daily_report(date(2026, 5, 15), [_bundle()])
    for word in ("lock", "guaranteed", "hammer", "free money", "must bet"):
        assert word.lower() not in report.lower(), f"Forbidden term found: '{word}'"


def test_report_empty_slate():
    report = generate_daily_report(date(2026, 5, 15), [])
    assert "0 game" in report


def test_report_with_analysis_includes_tier():
    bundle = _bundle()
    bundle.analysis = GameAnalysis(
        game_id=42,
        home_team_abbr="PHI",
        away_team_abbr="NYM",
        model_home_win_prob=0.60,
        model_away_win_prob=0.40,
        ml_lean="HOME",
        ml_confidence=0.60,
        ml_tier="STRONG LEAN",
        total_lean="OVER",
        total_confidence=0.55,
        projected_total=9.2,
        ml_kelly_fraction=0.048,
        ml_american_odds=-120,
        implied_prob=0.545,
        key_factors=["HOME SP edge: FIP 2.95 vs 4.10 — +2.1% shift"],
    )
    report = generate_daily_report(date(2026, 5, 15), [bundle])
    assert "STRONG LEAN" in report
    assert "PHI to win" in report
    assert "Kelly" in report
    assert "HOME SP edge" in report


def test_slate_overview_actionable_count():
    bundle1 = _bundle("PHI", "NYM")
    bundle1.analysis = GameAnalysis(
        game_id=1, home_team_abbr="PHI", away_team_abbr="NYM",
        model_home_win_prob=0.60, model_away_win_prob=0.40,
        ml_lean="HOME", ml_confidence=0.60, ml_tier="LEAN",
        total_lean="PASS", total_confidence=0.5, projected_total=8.5,
        ml_kelly_fraction=0.02, ml_american_odds=-115, implied_prob=0.535,
    )
    bundle2 = _bundle("LAD", "SD")  # no analysis → pass
    report = generate_daily_report(date(2026, 5, 15), [bundle1, bundle2])
    assert "1 actionable" in report
