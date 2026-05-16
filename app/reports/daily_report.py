"""Daily report generator.

Entry point: generate_daily_report(date, games) -> str (markdown)

Takes a list of GameBundle (one per game) and renders the full
daily MLB intelligence report. Deterministic/template-based — no LLM.
LLM polish layer comes in Phase 12.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional

from app.contracts import (
    GameContext,
    OddsSnapshot,
    PitcherFormWindow,
    TeamFormWindow,
    WeatherSnapshot,
    WindowKey,
)
from app.features.bullpen_vulnerability import BullpenReport


@dataclass
class GameBundle:
    context: GameContext
    home_bullpen: BullpenReport
    away_bullpen: BullpenReport
    home_starter: Optional[PitcherFormWindow] = None
    away_starter: Optional[PitcherFormWindow] = None
    home_form: Optional[TeamFormWindow] = None   # season window
    away_form: Optional[TeamFormWindow] = None
    odds: Optional[List[OddsSnapshot]] = None
    weather: Optional[WeatherSnapshot] = None


def generate_daily_report(report_date: date, games: List[GameBundle]) -> str:
    sections = [
        _header(report_date, games),
        _slate_overview(games),
    ]
    for bundle in games:
        sections.append(_game_section(bundle))
    sections.append(_uncertainty_footer())
    return "\n\n---\n\n".join(sections)


def _header(report_date: date, games: List[GameBundle]) -> str:
    return (
        f"# Diamond Mind — MLB Intelligence Report\n"
        f"## {report_date.strftime('%A, %B %-d, %Y')}\n\n"
        f"> diamond-mind provides probabilistic baseball analysis and market verification. "
        f"It does not guarantee betting outcomes and should not be treated as financial advice."
    )


def _slate_overview(games: List[GameBundle]) -> str:
    lines = [f"## Slate Overview\n", f"**{len(games)} game(s) today.**\n"]
    for b in games:
        ctx = b.context
        vuln_home = b.home_bullpen.vulnerability_score
        vuln_away = b.away_bullpen.vulnerability_score
        lines.append(
            f"- **{ctx.away_team_abbr} @ {ctx.home_team_abbr}** "
            f"— Bullpen vulnerability: {ctx.away_team_abbr} {vuln_away:.0f} / "
            f"{ctx.home_team_abbr} {vuln_home:.0f}"
        )
    return "\n".join(lines)


def _game_section(b: GameBundle) -> str:
    ctx = b.context
    title = f"## {ctx.away_team_abbr} @ {ctx.home_team_abbr}"
    if ctx.is_doubleheader:
        title += f" (Game {ctx.game_number})"

    parts = [title, f"**Venue:** {ctx.venue}\n"]
    parts.append(_starters_block(b))
    parts.append(_bullpen_block(b))
    if b.home_form or b.away_form:
        parts.append(_form_block(b))
    if b.odds:
        parts.append(_odds_block(b))
    if b.weather:
        parts.append(_weather_block(b.weather))

    return "\n\n".join(parts)


def _starters_block(b: GameBundle) -> str:
    lines = ["### Starting Pitchers\n"]
    home_s = b.home_starter
    away_s = b.away_starter

    def starter_line(label: str, s: Optional[PitcherFormWindow]) -> str:
        if not s:
            return f"| {label} | TBD |"
        sample = " ⚠ small sample" if s.insufficient_sample else ""
        return (
            f"| {label} | {s.pitcher_name} — ERA {s.era:.2f}, "
            f"WHIP {s.whip:.2f}, {s.trend_label.value}{sample} |"
        )

    lines.append("| Side | Pitcher |")
    lines.append("|------|---------|")
    lines.append(starter_line(b.context.home_team_abbr, home_s))
    lines.append(starter_line(b.context.away_team_abbr, away_s))
    return "\n".join(lines)


def _bullpen_block(b: GameBundle) -> str:
    lines = ["### Bullpen Intelligence\n"]
    for team_abbr, bp in [
        (b.context.home_team_abbr, b.home_bullpen),
        (b.context.away_team_abbr, b.away_bullpen),
    ]:
        lines.append(f"**{team_abbr}**")
        lines.append(f"- Fatigue: {bp.fatigue_score:.0f}/100")
        lines.append(f"- Overall Quality: {bp.overall_quality:.0f}/100")
        lines.append(f"- Available Quality: {bp.available_quality:.0f}/100")
        lines.append(f"- Vulnerability: **{bp.vulnerability_score:.0f}/100**")
        if bp.unavailable_relievers:
            lines.append(f"- Unavailable: {', '.join(bp.unavailable_relievers)}")
        if bp.limited_relievers:
            lines.append(f"- Limited: {', '.join(bp.limited_relievers)}")
        if bp.best_available:
            lines.append(f"- Best available: {', '.join(bp.best_available)}")
        if bp.weakest_available:
            lines.append(f"- Weakest available: {', '.join(bp.weakest_available)}")
        lines.append(f"- *{bp.betting_implication}*\n")
    return "\n".join(lines)


def _form_block(b: GameBundle) -> str:
    lines = ["### Recent Team Form (Season)\n"]
    lines.append("| | Runs/G | RA/G | OPS | Record | Trend |")
    lines.append("|--|--|--|--|--|--|")
    for abbr, form in [
        (b.context.home_team_abbr, b.home_form),
        (b.context.away_team_abbr, b.away_form),
    ]:
        if form:
            rec = f"{form.record_wins}-{form.record_losses}"
            sample = " ⚠" if form.insufficient_sample else ""
            lines.append(
                f"| {abbr} | {form.runs_per_game:.2f} | {form.runs_allowed_per_game:.2f} "
                f"| {form.team_ops:.3f} | {rec} | {form.trend_label.value}{sample} |"
            )
        else:
            lines.append(f"| {abbr} | — | — | — | — | — |")
    return "\n".join(lines)


def _odds_block(b: GameBundle) -> str:
    if not b.odds:
        return ""
    lines = ["### Betting Market\n"]
    lines.append("| Book | Market | Selection | Line | Odds |")
    lines.append("|------|--------|-----------|------|------|")
    for o in b.odds:
        line_str = str(o.line) if o.line is not None else "—"
        odds_str = f"+{o.american_odds}" if o.american_odds > 0 else str(o.american_odds)
        lines.append(
            f"| {o.bookmaker} | {o.market} | {o.selection} | {line_str} | {odds_str} |"
        )
    return "\n".join(lines)


def _weather_block(w: WeatherSnapshot) -> str:
    if w.is_dome:
        return "### Weather\nIndoor venue — weather not a factor."
    lines = ["### Weather\n"]
    if w.temperature_f is not None:
        lines.append(f"- Temp: {w.temperature_f:.0f}°F")
    if w.wind_speed_mph is not None and w.wind_direction_deg is not None:
        lines.append(f"- Wind: {w.wind_speed_mph:.0f} mph @ {w.wind_direction_deg}°")
    if w.precipitation_chance is not None:
        lines.append(f"- Precip chance: {w.precipitation_chance * 100:.0f}%")
    return "\n".join(lines)


def _uncertainty_footer() -> str:
    return (
        "## Uncertainty & Data Quality\n\n"
        "- Scores marked ⚠ have insufficient sample sizes — treat as directional only.\n"
        "- Bullpen quality scores are ERA-weighted; FIP/xFIP not yet incorporated.\n"
        "- Odds and weather data may be delayed or unavailable.\n"
        "- All recommendations use cautious tiers: "
        "Strong Lean / Lean / Pass / Avoid / Need More Info.\n"
        "- This report is for research purposes only. Not financial advice."
    )
