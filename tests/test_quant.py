"""Proof tests for the quant layer.

These pin the mathematical behavior — they are the audit, not my memory.
"""
import math

import pytest

from app.betting.quant import (
    shin_probabilities,
    shrink_to_market,
    edge_posterior,
    full_kelly,
    uncertainty_kelly,
    expected_log_growth,
    doubling_time_bets,
    compute_quant_edge,
    quant_recommendation,
)


def _prop(side_odds: int, other_odds: int) -> float:
    def dec(o):
        return 1 + 100 / abs(o) if o < 0 else 1 + o / 100
    rs, ro = 1 / dec(side_odds), 1 / dec(other_odds)
    return rs / (rs + ro)


class TestShin:
    def test_fair_book_is_fifty_fifty(self):
        # +100 / +100 is a zero-vig market → Shin returns (0.5, 0.5), z≈0
        p_h, p_a, z, B = shin_probabilities(100, 100)
        assert p_h == pytest.approx(0.5, abs=1e-6)
        assert p_a == pytest.approx(0.5, abs=1e-6)
        assert z == pytest.approx(0.0, abs=1e-6)
        assert B == pytest.approx(1.0, abs=1e-6)

    def test_probabilities_sum_to_one(self):
        for odds in [(-150, 130), (-110, -110), (-300, 250), (120, -140)]:
            p_h, p_a, z, B = shin_probabilities(*odds)
            assert p_h + p_a == pytest.approx(1.0, abs=1e-6)
            assert 0.0 <= z < 1.0
            assert B > 1.0  # vig present

    def test_favorite_longshot_correction(self):
        # Heavy favorite at -300, dog at +260 (a vigged book).
        # Shin must give the FAVORITE a HIGHER true prob than proportional
        # devig (longshots are overbet → their fair price is lower).
        fav_odds, dog_odds = -300, 260
        p_fav_shin, p_dog_shin, z, B = shin_probabilities(fav_odds, dog_odds)
        p_fav_prop = _prop(fav_odds, dog_odds)
        assert z > 0.0
        assert p_fav_shin > p_fav_prop, (
            f"Shin favorite {p_fav_shin:.4f} should exceed "
            f"proportional {p_fav_prop:.4f}"
        )
        assert p_dog_shin < (1 - p_fav_prop)


class TestShrinkage:
    def test_full_reliability_keeps_model(self):
        assert shrink_to_market(0.60, 0.50, 1.0) == pytest.approx(0.60, abs=1e-6)

    def test_zero_reliability_becomes_market(self):
        assert shrink_to_market(0.60, 0.50, 0.0) == pytest.approx(0.50, abs=1e-6)

    def test_partial_shrinks_toward_market(self):
        # Model 0.62, market 0.50, half trust → strictly between, closer in
        blended = shrink_to_market(0.62, 0.50, 0.5)
        assert 0.50 < blended < 0.62
        assert abs(blended - 0.50) < abs(0.62 - 0.50)


class TestEdgePosterior:
    def test_more_evidence_tightens_interval(self):
        wide = edge_posterior(0.58, 0.50, evidence_quality=0.3)
        tight = edge_posterior(0.58, 0.50, evidence_quality=0.9)
        assert tight.edge_sd < wide.edge_sd
        assert tight.prob_positive > wide.prob_positive
        assert tight.effective_n > wide.effective_n

    def test_prob_positive_bounds(self):
        post = edge_posterior(0.55, 0.50, 0.7)
        assert 0.0 <= post.prob_positive <= 1.0
        assert post.ci_low < post.edge_mean < post.ci_high

    def test_no_edge_is_coinflip_confidence(self):
        post = edge_posterior(0.50, 0.50, 0.7)
        assert post.prob_positive == pytest.approx(0.5, abs=1e-6)


class TestKelly:
    def test_full_kelly_positive_edge(self):
        # p=0.58 at -110 (b≈0.909): f* = (b·p − q)/b > 0
        f = full_kelly(0.58, -110)
        assert f > 0
        b = 100 / 110
        assert f == pytest.approx((b * 0.58 - 0.42) / b, abs=1e-6)

    def test_full_kelly_no_edge_is_zero_or_negative(self):
        # Fair coin at +100: f* = 0
        assert full_kelly(0.50, 100) == pytest.approx(0.0, abs=1e-9)

    def test_uncertainty_shrinks_and_caps(self):
        # A 5pp edge with 15pp SD is barely a signal → multiplier far below
        # the cap; a 5pp edge with 0.5pp SD is rock-solid → pinned at the cap.
        f_noisy, m_noisy = uncertainty_kelly(0.58, -110, edge_mean=0.05, edge_sd=0.15)
        f_clean, m_clean = uncertainty_kelly(0.58, -110, edge_mean=0.05, edge_sd=0.005)
        assert m_noisy < m_clean
        assert m_clean <= 0.25  # hard cap holds
        assert m_noisy < 0.25   # noisy edge is throttled below the cap
        assert f_noisy < f_clean

    def test_growth_rate_positive_for_real_edge(self):
        g = expected_log_growth(0.58, -110, 0.05)
        assert g > 0
        assert doubling_time_bets(g) is not None
        assert doubling_time_bets(g) > 0

    def test_growth_rate_zero_when_no_stake(self):
        assert expected_log_growth(0.58, -110, 0.0) == 0.0
        assert doubling_time_bets(0.0) is None


class TestQuantEdgePipeline:
    def test_end_to_end_real_edge(self):
        # Model loves the home favorite; decent evidence.
        qe = compute_quant_edge(0.62, -140, 120, evidence_quality=0.8)
        assert qe.shin_vig_free != qe.prop_vig_free  # methods differ under vig
        assert 0.0 <= qe.prob_positive <= 1.0
        assert qe.kelly_multiplier <= 0.25
        assert qe.p_shrunk <= qe.p_model  # shrunk toward lower market prior
        # Quant edge is the honest (smaller) number vs the naive one
        assert qe.edge_quant <= qe.edge_naive + 1e-9

    def test_recommendation_needs_confidence_in_the_edge(self):
        # Big point edge but tiny sample → not STRONG LEAN
        qe = compute_quant_edge(0.70, -110, -110, evidence_quality=0.2)
        rec = quant_recommendation(qe, model_confidence=0.70, evidence_quality=0.2)
        assert rec == "NEED MORE INFO"

    def test_recommendation_no_forbidden_language(self):
        qe = compute_quant_edge(0.60, -120, 100, evidence_quality=0.7)
        rec = quant_recommendation(qe, 0.60, 0.7)
        for bad in ("lock", "guaranteed", "hammer", "free money", "must bet"):
            assert bad not in rec.lower()
        assert rec in {"STRONG LEAN", "LEAN", "PASS", "AVOID", "NEED MORE INFO"}
