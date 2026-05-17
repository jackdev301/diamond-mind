from datetime import date

import pytest

from app.betting.game_analyzer import analyze_game, kelly
from app.contracts import PitcherFormWindow, TeamFormWindow, TrendLabel, WindowKey
from app.features.bullpen_vulnerability import BullpenReport


def _team(abbr: str, *, rpg: float, rag: float, woba: float, games: int = 10) -> TeamFormWindow:
    return TeamFormWindow(
        team_id=1,
        team_abbr=abbr,
        window=WindowKey.L10,
        games=games,
        runs_per_game=rpg,
        runs_allowed_per_game=rag,
        team_ops=0.760,
        record_wins=min(6, games),
        record_losses=max(0, games - min(6, games)),
        trend_label=TrendLabel.STABLE_STRONG,
        as_of_date=date(2026, 5, 16),
        team_woba=woba,
    )


def _starter(name: str, *, fip: float, k9: float, ip_per_start: float = 6.0) -> PitcherFormWindow:
    return PitcherFormWindow(
        pitcher_id=1,
        pitcher_name=name,
        team_id=1,
        window=WindowKey.LAST_5_STARTS,
        starts=5,
        innings_pitched=ip_per_start * 5,
        era=fip,
        whip=1.1,
        k_per_9=k9,
        bb_per_9=2.0,
        hr_per_9=1.0,
        avg_innings_per_start=ip_per_start,
        trend_label=TrendLabel.STABLE_STRONG,
        as_of_date=date(2026, 5, 16),
        fip=fip,
        avg_pitches_per_start=90,
    )


def _bullpen(team: str, vulnerability: float) -> BullpenReport:
    return BullpenReport(
        team_abbr=team,
        fatigue_score=20,
        overall_quality=70,
        available_quality=70,
        vulnerability_score=vulnerability,
        unavailable_relievers=[],
        limited_relievers=[],
        best_available=[],
        weakest_available=[],
        betting_implication="test",
    )


def test_kelly_uses_american_odds():
    assert kelly(0.57, -110) == pytest.approx(0.0242)
    assert kelly(0.57, +130) > kelly(0.57, -110)
    assert kelly(0.50, -110) == 0.0


def test_analyze_game_uses_real_line_for_edge_and_kelly():
    analysis = analyze_game(
        game_id=1,
        home_abbr="HOM",
        away_abbr="AWY",
        home_sp=_starter("Home Starter", fip=3.0, k9=10.5),
        away_sp=_starter("Away Starter", fip=4.8, k9=7.0),
        home_bullpen=_bullpen("HOM", 20),
        away_bullpen=_bullpen("AWY", 65),
        home_form=_team("HOM", rpg=5.2, rag=3.7, woba=0.360),
        away_form=_team("AWY", rpg=3.8, rag=5.0, woba=0.300),
        weather=None,
        home_ml_odds=-105,
        away_ml_odds=+115,
        away_k_rate=0.26,
        home_iso=0.230,
    )

    assert analysis.ml_lean == "HOME"
    assert analysis.ml_american_odds == -105
    assert analysis.implied_prob == pytest.approx(105 / 205, abs=0.001)
    assert analysis.ml_kelly_fraction > 0
    assert any("K matchup" in factor or "K/9" in factor for factor in analysis.key_factors)
    assert any("ISO" in factor for factor in analysis.key_factors)


def test_short_start_amplifies_bullpen_edge():
    common = dict(
        game_id=1,
        home_abbr="HOM",
        away_abbr="AWY",
        home_sp=_starter("Home Starter", fip=4.0, k9=8.0, ip_per_start=6.2),
        away_sp=_starter("Away Starter", fip=4.0, k9=8.0, ip_per_start=6.2),
        home_bullpen=_bullpen("HOM", 20),
        away_bullpen=_bullpen("AWY", 70),
        home_form=_team("HOM", rpg=4.5, rag=4.5, woba=0.320),
        away_form=_team("AWY", rpg=4.5, rag=4.5, woba=0.320),
        weather=None,
    )
    normal = analyze_game(**common)
    short = analyze_game(
        **{
            **common,
            "home_sp": _starter("Home Starter", fip=4.0, k9=8.0, ip_per_start=4.8),
        }
    )

    assert short.model_home_win_prob > normal.model_home_win_prob
    assert any("heavy bullpen reliance" in caution for caution in short.cautions)


def test_key_factor_text_orders_away_offense_edge_values():
    analysis = analyze_game(
        game_id=1,
        home_abbr="SEA",
        away_abbr="SD",
        home_sp=None,
        away_sp=None,
        home_bullpen=_bullpen("SEA", 10),
        away_bullpen=_bullpen("SD", 31),
        home_form=_team("SEA", rpg=2.0, rag=4.5, woba=0.270),
        away_form=_team("SD", rpg=4.5, rag=2.0, woba=0.311),
        weather=None,
        home_ml_odds=-145,
        away_ml_odds=135,
    )

    assert any(
        factor.startswith("AWAY offense edge: 4.5 R/G wOBA 0.311 vs 2.0 R/G wOBA 0.270")
        for factor in analysis.key_factors
    )
    assert any("AWAY bullpen exposed" in factor and "for HOME" in factor for factor in analysis.key_factors)


def test_total_edge_is_suppressed_with_tiny_run_samples():
    analysis = analyze_game(
        game_id=1,
        home_abbr="SEA",
        away_abbr="SD",
        home_sp=_starter("George Kirby", fip=4.0, k9=8.0),
        away_sp=_starter("Lucas Giolito", fip=4.0, k9=8.0),
        home_bullpen=_bullpen("SEA", 10),
        away_bullpen=_bullpen("SD", 31),
        home_form=_team("SEA", rpg=2.0, rag=4.5, woba=0.270, games=2),
        away_form=_team("SD", rpg=4.5, rag=2.0, woba=0.311, games=2),
        weather=None,
        total_line=7.5,
        over_odds=-110,
        under_odds=-110,
    )

    assert analysis.projected_total == pytest.approx(8.5)
    assert analysis.total_tier == "PASS"
    assert analysis.total_lean == "PASS"
    assert analysis.qt_p_model < 0.60
    assert any("Total projection heavily regressed" in caution for caution in analysis.cautions)
