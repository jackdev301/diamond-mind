"""Wiki-link and path slug helpers for Obsidian notes."""

from datetime import date


def wiki(label: str) -> str:
    """Return an Obsidian wiki-link: [[label]]"""
    return f"[[{label}]]"


def game_slug(game_date: date, away: str, home: str) -> str:
    return f"{game_date}_{away}_vs_{home}"


def bullpen_slug(team_abbr: str) -> str:
    return f"{team_abbr}_Bullpen"


def daily_report_link(report_date: date) -> str:
    return wiki(str(report_date))


def game_link(game_date: date, away: str, home: str) -> str:
    return wiki(game_slug(game_date, away, home))


def bullpen_link(team_abbr: str) -> str:
    return wiki(bullpen_slug(team_abbr))
