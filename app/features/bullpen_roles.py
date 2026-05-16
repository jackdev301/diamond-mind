"""Reliever role inference (Track B).

Problem (audit, collab #28): ingestion never assigns leverage roles — every
reliever lands as "middle". `bullpen_quality` weights by role, so the
role-weighting silently does nothing and vulnerability scoring is degraded.

This module re-derives roles from observable performance + workload signals
that ARE present on RelieverFormWindow, with no fabricated data. It is an
explicit heuristic (Arnav green-lit "heuristic from inherited runners +
leverage" as an acceptable Track B approach) and is only applied when the
ingested roles are undifferentiated — if real roles ever arrive, they win.

Heuristic, in order:
  1. Multi-inning arms (IP/appearance >= 1.8) → "long".
  2. Of the short-stint arms, rank by effectiveness (FIP, else ERA, lower =
     better). Best → "closer", next two → "setup"/"high_leverage", worst
     third → "low_leverage", everyone else → "middle".
Inherited-runner stranding breaks ties toward higher leverage when present.
"""
from __future__ import annotations

from typing import Dict, List

from app.contracts import BullpenState, RelieverFormWindow

_LONG_IP_PER_APP = 1.8
_FALLBACK_ERA = 4.50


def _group_by_pitcher(relievers: List[RelieverFormWindow]) -> Dict[int, List[RelieverFormWindow]]:
    groups: Dict[int, List[RelieverFormWindow]] = {}
    for r in relievers:
        groups.setdefault(r.pitcher_id, []).append(r)
    return groups


def _effectiveness(windows: List[RelieverFormWindow]) -> float:
    """Lower is better. Prefer FIP, fall back to ERA, then a neutral default."""
    fips = [w.fip for w in windows if w.fip is not None]
    if fips:
        return sum(fips) / len(fips)
    eras = [w.era for w in windows if w.era is not None]
    if eras:
        return sum(eras) / len(eras)
    return _FALLBACK_ERA


def _ip_per_appearance(windows: List[RelieverFormWindow]) -> float:
    ip = sum(w.innings_pitched for w in windows)
    app = sum(w.appearances for w in windows)
    return ip / app if app > 0 else 1.0


def roles_are_undifferentiated(state: BullpenState) -> bool:
    """True when ingestion gave us no real role signal (all same / no closer)."""
    roles = {r.role for r in state.relievers}
    return len(roles) <= 1 or "closer" not in roles


def infer_reliever_roles(state: BullpenState) -> Dict[int, str]:
    """Map pitcher_id → inferred role. Deterministic; ties broken by IRS% then id."""
    by_pitcher = _group_by_pitcher(state.relievers)
    if not by_pitcher:
        return {}

    long_arms: list[int] = []
    short: list[tuple[float, float, int]] = []  # (effectiveness, irs_pct, pid)
    for pid, windows in by_pitcher.items():
        if _ip_per_appearance(windows) >= _LONG_IP_PER_APP:
            long_arms.append(pid)
            continue
        irs = [w.inherited_runners_scored_pct for w in windows
               if w.inherited_runners_scored_pct is not None]
        irs_pct = (sum(irs) / len(irs)) if irs else 1.0  # unknown → worst tiebreak
        short.append((_effectiveness(windows), irs_pct, pid))

    short.sort(key=lambda t: (t[0], t[1], t[2]))  # best effectiveness first
    out: Dict[int, str] = {pid: "long" for pid in long_arms}

    n = len(short)
    for rank, (_eff, _irs, pid) in enumerate(short):
        if rank == 0:
            out[pid] = "closer"
        elif rank <= 2:
            out[pid] = "setup" if rank == 1 else "high_leverage"
        elif rank >= n - max(1, n // 3) and n >= 4:
            out[pid] = "low_leverage"
        else:
            out[pid] = "middle"
    return out


def effective_roles(state: BullpenState) -> Dict[int, str]:
    """Roles to score with: ingested roles if differentiated, else inferred."""
    if roles_are_undifferentiated(state):
        return infer_reliever_roles(state)
    return {r.pitcher_id: r.role for r in state.relievers}
