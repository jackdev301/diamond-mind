"""The Odds API client.

Returns List[OddsSnapshot] for a given game.
Stubs gracefully when ODDS_API_KEY is missing — never fabricates data.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from datetime import datetime, timezone
from typing import List, Optional

from app.config import get_settings
settings = get_settings()
from app.contracts import OddsSnapshot

_BASE = "https://api.the-odds-api.com/v4"
_SPORT = "baseball_mlb"


def _get(path: str, params: dict) -> Optional[list]:
    if not settings.odds_api_key:
        return None
    query = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"{_BASE}{path}?{query}&apiKey={settings.odds_api_key}"
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, json.JSONDecodeError):
        return None


def fetch_odds(game_id: int, event_id: str) -> List[OddsSnapshot]:
    """Fetch odds snapshots for a game. Returns [] if key missing or request fails."""
    data = _get(f"/sports/{_SPORT}/events/{event_id}/odds", {
        "regions": "us",
        "markets": "h2h,spreads,totals",
        "oddsFormat": "american",
    })
    if not data:
        return []

    snapshots = []
    captured_at = datetime.now(tz=timezone.utc)
    bookmakers = data.get("bookmakers", [])

    for book in bookmakers:
        bookmaker = book.get("key", "unknown")
        for market in book.get("markets", []):
            market_key = market.get("key", "")
            for outcome in market.get("outcomes", []):
                snapshots.append(OddsSnapshot(
                    game_id=game_id,
                    bookmaker=bookmaker,
                    market=_normalize_market(market_key),
                    selection=outcome.get("name", "").lower(),
                    american_odds=int(outcome.get("price", 0)),
                    line=outcome.get("point"),
                    captured_at=captured_at,
                ))
    return snapshots


def is_available() -> bool:
    return bool(settings.odds_api_key)


def _normalize_market(key: str) -> str:
    mapping = {
        "h2h": "moneyline",
        "spreads": "spread",
        "totals": "total",
    }
    return mapping.get(key, key)
