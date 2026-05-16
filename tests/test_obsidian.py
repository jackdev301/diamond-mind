"""Tests for Obsidian link utilities and note templates."""

from datetime import date

from app.obsidian.link_utils import (
    wiki,
    game_slug,
    bullpen_slug,
    daily_report_link,
    game_link,
    bullpen_link,
)
from app.obsidian.note_templates import game_note, bullpen_note
from app.features.bullpen_vulnerability import BullpenReport
from app.reports.daily_report import GameBundle
from app.contracts import GameContext, TrendLabel, WindowKey, PitcherFormWindow
from datetime import datetime


# ── link_utils ─────────────────────────────────────────────────────────────────

def test_wiki():
    assert wiki("PHI") == "[[PHI]]"


def test_game_slug():
    assert game_slug(date(2026, 5, 15), "BOS", "NYY") == "2026-05-15_BOS_vs_NYY"


def test_bullpen_slug():
    assert bullpen_slug("LAD") == "LAD_Bullpen"


def test_daily_report_link():
    assert daily_report_link(date(2026, 5, 15)) == "[[2026-05-15]]"


def test_game_link():
    assert game_link(date(2026, 5, 15), "BOS", "NYY") == "[[2026-05-15_BOS_vs_NYY]]"


def test_bullpen_link():
    assert bullpen_link("NYM") == "[[NYM_Bullpen]]"


# ── note_templates ─────────────────────────────────────────────────────────────

def _make_bullpen(abbr: str = "PHI", vuln: float = 45.0) -> BullpenReport:
    return BullpenReport(
        team_abbr=abbr,
        fatigue_score=30.0,
        overall_quality=65.0,
        available_quality=60.0,
        vulnerability_score=vuln,
        unavailable_relievers=[],
        limited_relievers=["Jones"],
        best_available=["Smith", "Lee"],
        weakest_available=[],
        betting_implication="Moderate vulnerability — monitor late-game.",
    )


def _make_bundle() -> GameBundle:
    ctx = GameContext(
        game_id=1,
        game_date=date(2026, 5, 15),
        game_time_utc=datetime(2026, 5, 15, 23, 5),
        home_team_id=10,
        away_team_id=20,
        home_team_abbr="PHI",
        away_team_abbr="NYM",
        venue="Citizens Bank Park",
        is_doubleheader=False,
        game_number=1,
    )
    return GameBundle(
        context=ctx,
        home_bullpen=_make_bullpen("PHI", 45.0),
        away_bullpen=_make_bullpen("NYM", 72.0),
    )


def test_bullpen_note_contains_scores():
    bp = _make_bullpen("ATL", 55.0)
    note = bullpen_note(date(2026, 5, 15), "ATL", bp)
    assert "55/100" in note
    assert "ATL" in note
    assert "[[2026-05-15]]" in note
    assert "Limited" in note
    assert "Jones" in note
    assert "Smith" in note


def test_game_note_contains_matchup():
    bundle = _make_bundle()
    note = game_note(date(2026, 5, 15), bundle)
    assert "NYM @ PHI" in note
    assert "Citizens Bank Park" in note
    assert "[[PHI_Bullpen]]" in note
    assert "[[NYM_Bullpen]]" in note
    assert "[[2026-05-15]]" in note
    assert "#game" in note


def test_game_note_no_analysis_skips_model_section():
    bundle = _make_bundle()
    note = game_note(date(2026, 5, 15), bundle)
    assert "Model Signal" not in note


def test_game_note_with_analysis_includes_tier():
    from app.betting.game_analyzer import GameAnalysis
    bundle = _make_bundle()
    bundle.analysis = GameAnalysis(
        game_id=1,
        home_team_abbr="PHI",
        away_team_abbr="NYM",
        model_home_win_prob=0.58,
        model_away_win_prob=0.42,
        ml_lean="HOME",
        ml_confidence=0.58,
        ml_tier="LEAN",
        total_lean="PASS",
        total_confidence=0.5,
        projected_total=8.5,
        ml_kelly_fraction=0.032,
        ml_american_odds=-115,
        implied_prob=0.535,
        key_factors=["HOME SP edge: FIP 3.20 vs 4.10"],
    )
    note = game_note(date(2026, 5, 15), bundle)
    assert "Model Signal" in note
    assert "LEAN" in note
    assert "PHI to win" in note
    assert "Key factors" in note
