"""Tests for the NBA quant port."""
import pytest

from app.betting.nba_model import analyze_nba_game, HOME_COURT_ADV


class TestNBAProjection:
    def test_even_teams_is_home_court_baseline(self):
        a = analyze_nba_game("HOM", "AWY", home_net_rating=0.0, away_net_rating=0.0)
        assert a.model_home_win_prob == pytest.approx(HOME_COURT_ADV)
        assert a.model_home_win_prob + a.model_away_win_prob == pytest.approx(1.0)

    def test_better_net_rating_lifts_home(self):
        a = analyze_nba_game("HOM", "AWY", home_net_rating=6.0, away_net_rating=-3.0)
        assert a.model_home_win_prob > HOME_COURT_ADV
        assert a.net_rating_diff == pytest.approx(9.0)

    def test_road_back_to_back_helps_home(self):
        base = analyze_nba_game("HOM", "AWY", 2.0, 2.0)
        b2b = analyze_nba_game("HOM", "AWY", 2.0, 2.0, away_back_to_back=True)
        assert b2b.model_home_win_prob > base.model_home_win_prob
        assert b2b.rest_adjustment > 0

    def test_rest_edge_capped(self):
        a = analyze_nba_game("HOM", "AWY", 0.0, 0.0, home_rest_days=10, away_rest_days=0)
        assert a.rest_adjustment <= 0.04 + 1e-9

    def test_probabilities_bounded(self):
        a = analyze_nba_game("HOM", "AWY", home_net_rating=40.0, away_net_rating=-40.0)
        assert 0.08 <= a.model_home_win_prob <= 0.92


class TestNBABetting:
    def test_no_line_projection_only(self):
        a = analyze_nba_game("HOM", "AWY", 5.0, -2.0)
        assert a.ml_american_odds is None
        assert a.ml_tier == "PASS"
        assert a.q_prob_positive is None

    def test_line_runs_quant_pipeline(self):
        a = analyze_nba_game(
            "HOM", "AWY", home_net_rating=7.0, away_net_rating=-4.0,
            home_ml_odds=-180, away_ml_odds=155, evidence_quality=0.75,
        )
        assert a.ml_american_odds == -180
        assert a.q_shin_vig_free is not None
        assert 0.0 <= a.q_prob_positive <= 1.0
        assert a.ml_tier in {"STRONG LEAN", "LEAN", "PASS", "AVOID"}

    def test_no_forbidden_language(self):
        a = analyze_nba_game(
            "HOM", "AWY", 9.0, -6.0, home_ml_odds=-220, away_ml_odds=185
        )
        for bad in ("lock", "guaranteed", "hammer", "free money", "must bet"):
            assert bad not in a.ml_tier.lower()
            assert bad not in a.rationale.lower()
