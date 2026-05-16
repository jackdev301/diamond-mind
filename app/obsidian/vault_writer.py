"""Obsidian vault writer.

Writes daily reports and game notes to the local obsidian_vault/ directory
using the path conventions from PROJECT_BRIEF.md and wiki-style links.

Path conventions:
    obsidian_vault/Reports/Daily/YYYY-MM-DD.md
    obsidian_vault/Games/YYYY-MM-DD_AWAY_vs_HOME.md
    obsidian_vault/Bullpens/Team_Name_Bullpen.md
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import List

from app.reports.daily_report import GameBundle, generate_daily_report
from app.obsidian.note_templates import game_note, bullpen_note
from app.obsidian.link_utils import wiki, game_slug, bullpen_slug


_VAULT = Path("obsidian_vault")


def _write(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def write_daily_report(report_date: date, games: List[GameBundle]) -> Path:
    markdown = generate_daily_report(report_date, games)
    path = _VAULT / "Reports" / "Daily" / f"{report_date}.md"
    return _write(path, markdown)


def write_game_notes(report_date: date, games: List[GameBundle]) -> List[Path]:
    written = []
    for bundle in games:
        ctx = bundle.context
        slug = game_slug(report_date, ctx.away_team_abbr, ctx.home_team_abbr)
        path = _VAULT / "Games" / f"{slug}.md"
        content = game_note(report_date, bundle)
        written.append(_write(path, content))
    return written


def write_bullpen_notes(report_date: date, games: List[GameBundle]) -> List[Path]:
    written = []
    seen = set()
    for bundle in games:
        for abbr, bp in [
            (bundle.context.home_team_abbr, bundle.home_bullpen),
            (bundle.context.away_team_abbr, bundle.away_bullpen),
        ]:
            if abbr in seen:
                continue
            seen.add(abbr)
            slug = bullpen_slug(abbr)
            path = _VAULT / "Bullpens" / f"{slug}.md"
            content = bullpen_note(report_date, abbr, bp)
            written.append(_write(path, content))
    return written


def export_all(report_date: date, games: List[GameBundle]) -> dict:
    daily = write_daily_report(report_date, games)
    game_notes = write_game_notes(report_date, games)
    bullpen_notes = write_bullpen_notes(report_date, games)
    return {
        "daily_report": str(daily),
        "game_notes": [str(p) for p in game_notes],
        "bullpen_notes": [str(p) for p in bullpen_notes],
    }
