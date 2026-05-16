"""Tests for the F5 (first-5-innings) moneyline model."""
from datetime import date

import pytest

from app.contracts import PitcherFormWindow, WindowKey, TrendLabel
from app.betting.f5_model import analyze_f5_moneyline, HOME_ADV_F5


def _sp(name: str, fip=None, xfip=None, insufficient=False) -> PitcherFormWindow:
    return PitcherFormWindow(
        pitcher_id=1, pitcher_name=name, team_id=1, window=WindowKey.LAST_5_STARTS,
        starts=5, innings_pitched=30.0, era=3.5, whip=1.15, k_per_9=9.0,
        bb_per_9=2.5, hr_per_9=1.0, avg_innings_per_start=6.0,
        trend_label=TrendLabel.STABLE_STRONG, as_of_date=date(2026, 5, 16),
        fip=fip, xfip=xfip, insufficient_sample=insufficient,
    )


class TestF5Projection:
    def test_no_starters_is_home_baseline(self):
        a = analyze_f5_moneyline(1, "HOM", "AWY", None, None)
        assert a.model_home_win_prob == pytest.approx(HOME_ADV_F5)
        assert a.sp_metric_name == "none"
        assert a.ml_tier == "PASS"
        assert "not actionable" in a.rationale.lower()

    def test_better_home_starter_lifts_home_prob(self):
        # Home SP xFIP 3.0 vs away 4.5 → home favored above baseline
        a = analyze_f5_moneyline(1, "HOM", "AWY", _sp("H", xfip=3.0), _sp("A", xfip=4.5))
        assert a.model_home_win_prob > HOME_ADV_F5
        assert a.sp_metric_name == "xFIP"
        assert a.fip_differential == pytest.approx(1.5)
        assert a.model_home_win_prob + a.model_away_win_prob == pytest.approx(1.0)

    def test_xfip_preferred_over_fip(self):
        a = analyze_f5_moneyline(1, "HOM", "AWY", _sp("H", fip=4.0, xfip=3.2), _sp("A", fip=4.0, xfip=4.0))
        assert a.sp_metric_name == "xFIP"
        assert a.home_sp_metric == 3.2

    def test_platoon_term_is_zero_until_data_exists(self):
        a = analyze_f5_moneyline(1, "HOM", "AWY", _sp("H", fip=3.5), _sp("A", fip=4.0))
        assert a.platoon_adj == 0.0  # blocked on Track A L/R splits, not faked

    def test_insufficient_sample_starter_ignored(self):
        a = analyze_f5_moneyline(1, "HOM", "AWY", _sp("H", xfip=2.5, insufficient=True), _sp("A", xfip=4.0))
        # home SP unusable → no differential applied
        assert a.home_sp_metric is None


class TestF5Betting:
    def test_no_line_means_projection_only(self):
        a = analyze_f5_moneyline(1, "HOM", "AWY", _sp("H", xfip=3.0), _sp("A", xfip=4.5))
        assert a.ml_american_odds is None
        assert a.ml_tier == "PASS"
        assert a.q_prob_positive is None

    def test_line_runs_quant_pipeline(self):
        a = analyze_f5_moneyline(
            1, "HOM", "AWY", _sp("H", xfip=2.8), _sp("A", xfip=4.6),
            home_f5_odds=-140, away_f5_odds=120, evidence_quality=0.8,
        )
        assert a.ml_american_odds == -140
        assert a.q_shin_vig_free is not None
        assert 0.0 <= a.q_prob_positive <= 1.0
        assert a.ml_tier in {"STRONG LEAN", "LEAN", "PASS", "AVOID"}

    def test_no_forbidden_language(self):
        a = analyze_f5_moneyline(
            1, "HOM", "AWY", _sp("H", xfip=2.5), _sp("A", xfip=5.0),
            home_f5_odds=-160, away_f5_odds=140,
        )
        for bad in ("lock", "guaranteed", "hammer", "free money", "must bet"):
            assert bad not in a.ml_tier.lower()
            assert bad not in a.rationale.lower()
