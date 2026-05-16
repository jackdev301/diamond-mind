"""Obsidian note templates for game and bullpen notes."""

from __future__ import annotations

from datetime import date

from app.reports.daily_report import GameBundle
from app.features.bullpen_vulnerability import BullpenReport
from app.obsidian.link_utils import daily_report_link, bullpen_link, game_link


def game_note(report_date: date, bundle: GameBundle) -> str:
    ctx = bundle.context
    home, away = ctx.home_team_abbr, ctx.away_team_abbr

    lines = [
        f"# {away} @ {home} — {report_date}",
        f"\n**Date:** {report_date}  ",
        f"**Venue:** {ctx.venue}  ",
        f"**Daily Report:** {daily_report_link(report_date)}\n",
        "## Bullpen",
        f"- {home}: {bullpen_link(home)} — Vulnerability {bundle.home_bullpen.vulnerability_score:.0f}/100",
        f"- {away}: {bullpen_link(away)} — Vulnerability {bundle.away_bullpen.vulnerability_score:.0f}/100\n",
    ]

    if bundle.home_starter or bundle.away_starter:
        lines.append("## Starters")
        if bundle.home_starter:
            s = bundle.home_starter
            lines.append(f"- {home}: {s.pitcher_name} — ERA {s.era:.2f}, WHIP {s.whip:.2f}, {s.trend_label.value}")
        if bundle.away_starter:
            s = bundle.away_starter
            lines.append(f"- {away}: {s.pitcher_name} — ERA {s.era:.2f}, WHIP {s.whip:.2f}, {s.trend_label.value}")
        lines.append("")

    lines += [
        "## Notes",
        "_Add postgame notes here._\n",
        "## Tags",
        f"#game #{home.lower()} #{away.lower()} #{report_date}",
    ]
    return "\n".join(lines)


def bullpen_note(report_date: date, team_abbr: str, bp: BullpenReport) -> str:
    lines = [
        f"# {team_abbr} Bullpen — {report_date}",
        f"\n**As of:** {report_date}  ",
        f"**Daily Report:** {daily_report_link(report_date)}\n",
        "## Scores",
        f"| Metric | Score |",
        f"|--------|-------|",
        f"| Fatigue | {bp.fatigue_score:.0f}/100 |",
        f"| Overall Quality | {bp.overall_quality:.0f}/100 |",
        f"| Available Quality | {bp.available_quality:.0f}/100 |",
        f"| **Vulnerability** | **{bp.vulnerability_score:.0f}/100** |\n",
        "## Availability",
    ]
    if bp.unavailable_relievers:
        lines.append(f"- **Unavailable:** {', '.join(bp.unavailable_relievers)}")
    if bp.limited_relievers:
        lines.append(f"- **Limited:** {', '.join(bp.limited_relievers)}")
    if bp.best_available:
        lines.append(f"- **Best available:** {', '.join(bp.best_available)}")
    lines += [
        "",
        "## Betting Implication",
        f"_{bp.betting_implication}_\n",
        "## Tags",
        f"#bullpen #{team_abbr.lower()} #{report_date}",
    ]
    return "\n".join(lines)
