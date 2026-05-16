"""FastAPI routes — data query layer for the web frontend.

All endpoints are read-only. They query the DB via Track A's form helpers
and return dataclass-compatible JSON. The Next.js/React frontend (Track B)
consumes these via HTTP.

Run with:
    uvicorn app.api.routes:app --reload --port 8000
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from app.contracts import WindowKey
from app.database import SessionLocal
from app.features.recent_form import (
    build_bullpen_state,
    build_hitter_form_window,
    build_starter_form_window,
    build_team_form_window,
    load_hitter_form_window,
    load_team_form_window,
)
from app.features.bullpen_vulnerability import score_bullpen
from app.models.entities import Team
from app.models.games import Game

app = FastAPI(
    title="diamond-mind API",
    description="Data query layer for the MLB intelligence system.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_db():
    with SessionLocal() as session:
        yield session


def _dc(obj) -> dict:
    """Serialize a dataclass (including nested ones) to JSON-safe dict."""
    if obj is None:
        return None
    if dataclasses.is_dataclass(obj):
        return {
            k: _dc(v)
            for k, v in dataclasses.asdict(obj).items()
        }
    if isinstance(obj, list):
        return [_dc(item) for item in obj]
    if hasattr(obj, "value"):  # Enum
        return obj.value
    return obj


@app.get("/health")
def health():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------

@app.get("/games")
def list_games(
    game_date: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """Return all games scheduled for a date, including team abbreviations."""
    from app.models.entities import Team as TeamModel
    HomeTeam = aliased(TeamModel)
    AwayTeam = aliased(TeamModel)
    rows = db.execute(
        select(Game, HomeTeam, AwayTeam)
        .join(HomeTeam, Game.home_team_id == HomeTeam.id)
        .join(AwayTeam, Game.away_team_id == AwayTeam.id)
        .where(Game.game_date == game_date)
        .order_by(Game.id)
    ).all()
    return [
        {
            "game_id": g.id,
            "game_date": g.game_date.isoformat(),
            "status": g.status,
            "home_team_id": g.home_team_id,
            "home_team_abbr": home.abbr,
            "away_team_id": g.away_team_id,
            "away_team_abbr": away.abbr,
            "venue": g.venue,
            "is_doubleheader": g.is_doubleheader,
            "game_number": g.game_number,
            "home_probable_starter_id": g.home_probable_starter_id,
            "away_probable_starter_id": g.away_probable_starter_id,
        }
        for g, home, away in rows
    ]


# ---------------------------------------------------------------------------
# Teams
# ---------------------------------------------------------------------------

@app.get("/teams")
def list_teams(db: Session = Depends(_get_db)):
    teams = db.execute(select(Team)).scalars().all()
    return [
        {"id": t.id, "abbr": t.abbr, "name": t.name,
         "league": t.league, "division": t.division}
        for t in teams
    ]


@app.get("/teams/{team_id}/form")
def team_form(
    team_id: int,
    window: str = Query("l10", description="season|l20|l10|l5"),
    as_of: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    try:
        wk = WindowKey(window)
    except ValueError:
        raise HTTPException(400, f"Unknown window: {window}")

    # Try cached row first, then build fresh.
    w = load_team_form_window(db, team_id=team_id, window=wk, as_of_date=as_of)
    if w is None:
        w = build_team_form_window(db, team_id=team_id, window=wk, as_of_date=as_of)
    if w is None:
        raise HTTPException(404, f"No form data for team {team_id} window={window}")
    return _dc(w)


@app.get("/teams/{team_id}/bullpen")
def team_bullpen(
    team_id: int,
    as_of: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    state = build_bullpen_state(db, team_id=team_id, as_of_date=as_of)
    if state is None:
        raise HTTPException(404, f"No bullpen data for team {team_id}")
    return _dc(score_bullpen(state))


# ---------------------------------------------------------------------------
# Players
# ---------------------------------------------------------------------------

@app.get("/players/{player_id}/form")
def player_form(
    player_id: int,
    window: str = Query("l10"),
    as_of: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    try:
        wk = WindowKey(window)
    except ValueError:
        raise HTTPException(400, f"Unknown window: {window}")

    w = load_hitter_form_window(db, player_id=player_id, window=wk, as_of_date=as_of)
    if w is None:
        w = build_hitter_form_window(db, player_id=player_id, window=wk, as_of_date=as_of)
    if w is None:
        raise HTTPException(404, f"No form data for player {player_id}")
    return _dc(w)


# ---------------------------------------------------------------------------
# Pitchers
# ---------------------------------------------------------------------------

@app.get("/pitchers/{pitcher_id}/form")
def pitcher_form(
    pitcher_id: int,
    window: str = Query("last_5_starts"),
    as_of: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    try:
        wk = WindowKey(window)
    except ValueError:
        raise HTTPException(400, f"Unknown window: {window}")

    w = build_starter_form_window(db, pitcher_id=pitcher_id, window=wk, as_of_date=as_of)
    if w is None:
        raise HTTPException(404, f"No starter form data for pitcher {pitcher_id}")
    return _dc(w)


# ---------------------------------------------------------------------------
# GameBundle — single-call composite for the frontend
# ---------------------------------------------------------------------------

@app.get("/games/{game_id}/bundle")
def game_bundle(
    game_id: int,
    as_of: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """Return a full GameBundle payload in one call — home/away form, bullpen,
    starters, all windows. Saves multiple round trips from the frontend."""
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(404, f"Game {game_id} not found")

    def _team_form(team_id: int, window: WindowKey):
        w = load_team_form_window(db, team_id=team_id, window=window, as_of_date=as_of)
        if w is None:
            w = build_team_form_window(db, team_id=team_id, window=window, as_of_date=as_of)
        return _dc(w)

    def _starter(pitcher_id):
        if pitcher_id is None:
            return None
        w = build_starter_form_window(
            db, pitcher_id=pitcher_id,
            window=WindowKey.LAST_5_STARTS, as_of_date=as_of,
        )
        return _dc(w)

    def _bullpen(team_id: int):
        state = build_bullpen_state(db, team_id=team_id, as_of_date=as_of)
        if state is None:
            return None
        return _dc(score_bullpen(state))

    home_id = game.home_team_id
    away_id = game.away_team_id
    home_team = db.get(Team, home_id)
    away_team = db.get(Team, away_id)

    return {
        "game_id": game_id,
        "game_date": game.game_date.isoformat(),
        "status": game.status,
        "venue": game.venue,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_team_abbr": home_team.abbr if home_team else None,
        "away_team_abbr": away_team.abbr if away_team else None,
        "is_doubleheader": game.is_doubleheader,
        "game_number": game.game_number,
        "home_form": {
            "season": _team_form(home_id, WindowKey.SEASON),
            "l10": _team_form(home_id, WindowKey.L10),
            "l5": _team_form(home_id, WindowKey.L5),
        },
        "away_form": {
            "season": _team_form(away_id, WindowKey.SEASON),
            "l10": _team_form(away_id, WindowKey.L10),
            "l5": _team_form(away_id, WindowKey.L5),
        },
        "home_starter": _starter(game.home_probable_starter_id),
        "away_starter": _starter(game.away_probable_starter_id),
        "home_bullpen": _bullpen(home_id),
        "away_bullpen": _bullpen(away_id),
    }


# ---------------------------------------------------------------------------
# Odds and weather
# ---------------------------------------------------------------------------

@app.get("/games/{game_id}/odds")
def game_odds(game_id: int, db: Session = Depends(_get_db)):
    """Return the most recent odds snapshots for a game."""
    from sqlalchemy import desc
    from app.models.odds import OddsSnapshotRow
    rows = db.execute(
        select(OddsSnapshotRow)
        .where(OddsSnapshotRow.game_id == game_id)
        .order_by(desc(OddsSnapshotRow.captured_at))
    ).scalars().all()
    return [
        {
            "game_id": r.game_id,
            "bookmaker": r.bookmaker,
            "market": r.market,
            "selection": r.selection,
            "american_odds": r.american_odds,
            "line": r.line,
            "captured_at": r.captured_at.isoformat(),
        }
        for r in rows
    ]


@app.get("/games/{game_id}/weather")
def game_weather(game_id: int, db: Session = Depends(_get_db)):
    """Return the most recent weather snapshot for a game."""
    from sqlalchemy import desc
    from app.models.odds import WeatherSnapshotRow
    row = db.execute(
        select(WeatherSnapshotRow)
        .where(WeatherSnapshotRow.game_id == game_id)
        .order_by(desc(WeatherSnapshotRow.captured_at))
        .limit(1)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, f"No weather data for game {game_id}")
    return {
        "game_id": row.game_id,
        "temperature_f": row.temperature_f,
        "wind_speed_mph": row.wind_speed_mph,
        "wind_direction_deg": row.wind_direction_deg,
        "precipitation_chance": row.precipitation_chance,
        "humidity_pct": row.humidity_pct,
        "is_dome": row.is_dome,
        "captured_at": row.captured_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# LLM polish (optional — stubs if key missing)
# ---------------------------------------------------------------------------

@app.post("/report/polish")
def polish_report_endpoint(body: dict):
    """Polish a raw Markdown report with Claude.

    Returns {markdown, polished: bool, method: str}.
    polished=False means no LLM was applied (no API key and no CLI found).
    """
    raw = body.get("markdown", "")
    if not raw:
        raise HTTPException(400, "Field 'markdown' is required.")
    from app.config import get_settings
    from app.llm.claude_client import polish_report
    markdown, was_polished = polish_report(raw)
    if not was_polished:
        method = "none"
    elif get_settings().anthropic_api_key:
        method = "sdk"
    else:
        method = "cli"
    return {"markdown": markdown, "polished": was_polished, "method": method}
