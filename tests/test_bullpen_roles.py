"""Tests for reliever role inference (the audit-flagged gap)."""
from datetime import date

from app.contracts import BullpenState, RelieverFormWindow, WindowKey, TrendLabel
from app.features.bullpen_roles import (
    infer_reliever_roles,
    effective_roles,
    roles_are_undifferentiated,
)
from app.features.bullpen_quality import calculate_overall_quality


def _rfw(pid, fip, role="middle", ip=20.0, app=20, irs=None):
    return RelieverFormWindow(
        pitcher_id=pid, pitcher_name=f"P{pid}", team_id=1, role=role,
        window=WindowKey.SEASON, appearances=app, innings_pitched=ip,
        era=fip, whip=1.2, k_per_9=9.0, bb_per_9=3.0,
        trend_label=TrendLabel.STABLE_STRONG, as_of_date=date(2026, 5, 16),
        fip=fip, inherited_runners_scored_pct=irs,
    )


def _state(relievers):
    return BullpenState(
        team_id=1, team_abbr="TST", as_of_date=date(2026, 5, 16),
        yesterday_total_innings=0.0, yesterday_total_pitches=0,
        yesterday_relievers_used=0, closer_pitched_yesterday=False,
        high_leverage_pitched_yesterday=[], back_to_back_relievers=[],
        three_in_four_relievers=[], relievers=relievers,
    )


class TestRoleInference:
    def test_all_middle_is_undifferentiated(self):
        st = _state([_rfw(1, 2.0), _rfw(2, 3.5), _rfw(3, 5.0)])
        assert roles_are_undifferentiated(st) is True

    def test_best_arm_becomes_closer(self):
        st = _state([_rfw(1, 4.8), _rfw(2, 2.1), _rfw(3, 3.9), _rfw(4, 5.5)])
        roles = infer_reliever_roles(st)
        assert roles[2] == "closer"          # lowest FIP
        assert roles[1] in ("setup", "high_leverage", "middle", "low_leverage")

    def test_multi_inning_arm_is_long(self):
        # pid 9 averages 2.5 IP/appearance → long reliever
        st = _state([_rfw(1, 3.0), _rfw(9, 4.0, ip=25.0, app=10)])
        roles = infer_reliever_roles(st)
        assert roles[9] == "long"

    def test_real_roles_are_respected(self):
        st = _state([_rfw(1, 4.0, role="closer"), _rfw(2, 3.0, role="middle")])
        assert roles_are_undifferentiated(st) is False
        assert effective_roles(st) == {1: "closer", 2: "middle"}

    def test_irs_breaks_ties(self):
        # equal FIP; pid 2 strands fewer inherited runners (lower IRS%) → ranks higher
        st = _state([_rfw(1, 3.0, irs=0.60), _rfw(2, 3.0, irs=0.10), _rfw(3, 3.0, irs=0.90)])
        roles = infer_reliever_roles(st)
        assert roles[2] == "closer"


class TestScoringActuallyUsesRoles:
    def test_inference_changes_quality_vs_flat_middle(self):
        # Same arms; with inference the elite closer is up-weighted, so overall
        # quality differs from the degraded all-middle (flat 1.0) computation.
        relievers = [_rfw(1, 1.5), _rfw(2, 4.5), _rfw(3, 5.0), _rfw(4, 4.8)]
        st = _state(relievers)
        inferred = calculate_overall_quality(st)

        flat = _state([_rfw(r.pitcher_id, r.fip, role="middle") for r in relievers])
        # force "differentiated" so effective_roles returns the flat middles
        flat.relievers.append(_rfw(99, 4.0, role="closer"))
        flat_score = calculate_overall_quality(flat)
        assert inferred != flat_score
