"""Tests for pure betting utility functions."""

import pytest

from app.betting.implied_probability import implied_probability
from app.betting.edge_calculator import edge, recommendation


class TestImpliedProbability:
    def test_minus_110(self):
        # -110 = 110 / 210 ≈ 52.38%
        assert implied_probability(-110) == pytest.approx(110 / 210)

    def test_minus_150(self):
        assert implied_probability(-150) == pytest.approx(150 / 250)

    def test_plus_110(self):
        # +110 = 100 / 210 ≈ 47.62%
        assert implied_probability(110) == pytest.approx(100 / 210)

    def test_plus_200(self):
        assert implied_probability(200) == pytest.approx(100 / 300)

    def test_even_money_100(self):
        assert implied_probability(100) == pytest.approx(0.5)

    def test_negative_100(self):
        # -100 is even money from the other side
        assert implied_probability(-100) == pytest.approx(0.5)

    def test_heavy_favourite(self):
        # -300: implied = 300/400 = 75%
        assert implied_probability(-300) == pytest.approx(0.75)

    def test_heavy_underdog(self):
        # +300: implied = 100/400 = 25%
        assert implied_probability(300) == pytest.approx(0.25)

    def test_result_between_0_and_1(self):
        for odds in [-500, -200, -110, 100, 150, 300]:
            p = implied_probability(odds)
            assert 0.0 < p < 1.0, f"implied_probability({odds}) = {p} out of (0,1)"


class TestEdge:
    def test_positive_edge(self):
        # Model says 58%, book says 52.38% (-110) → edge ≈ +5.6%
        e = edge(0.58, -110)
        assert e == pytest.approx(0.58 - 110 / 210, abs=1e-6)
        assert e > 0

    def test_negative_edge(self):
        # Model says 40%, book says 75% (-300) → negative edge
        e = edge(0.40, -300)
        assert e < 0

    def test_no_edge(self):
        # Model matches implied probability exactly
        implied = 110 / 210
        e = edge(implied, -110)
        assert e == pytest.approx(0.0, abs=1e-9)


class TestRecommendation:
    def test_strong_lean(self):
        # edge ≥ 6%, confidence ≥ 70%, evidence ≥ 70%
        assert recommendation(0.07, 0.75, 0.80) == "strong_lean"

    def test_lean(self):
        # edge ≥ 3%, confidence ≥ 55%, evidence ≥ 40%
        assert recommendation(0.04, 0.60, 0.65) == "lean"

    def test_pass_small_edge(self):
        # edge exists but below thresholds
        assert recommendation(0.01, 0.65, 0.65) == "pass"

    def test_avoid(self):
        # edge ≤ -5%
        assert recommendation(-0.06, 0.65, 0.65) == "avoid"

    def test_need_more_info_low_confidence(self):
        # confidence < 40% regardless of edge
        assert recommendation(0.10, 0.30, 0.80) == "need_more_info"

    def test_need_more_info_low_evidence(self):
        # evidence_quality < 40% regardless of edge
        assert recommendation(0.10, 0.80, 0.35) == "need_more_info"

    def test_strong_lean_not_triggered_without_evidence(self):
        # edge and confidence meet strong_lean but evidence is low
        assert recommendation(0.07, 0.75, 0.50) != "strong_lean"

    def test_boundary_lean_edge(self):
        # exactly 3% edge, exactly 55% confidence → lean
        assert recommendation(0.030, 0.55, 0.50) == "lean"

    def test_no_forbidden_language(self):
        for e_val in [-0.10, 0.0, 0.05, 0.10]:
            result = recommendation(e_val, 0.70, 0.70)
            for forbidden in ("lock", "guaranteed", "hammer", "free money", "must bet"):
                assert forbidden not in result.lower()
