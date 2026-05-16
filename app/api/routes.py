"""FastAPI routes — data query layer for the Streamlit dashboard.

All endpoints are read-only. They query the DB via Track A's form helpers
and return dataclass-compatible JSON. The Streamlit frontend (Track B)
consumes these instead of directly importing ORM models.

Run with:
    uvicorn app.api.routes:app --reload --port 8000
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
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
from app.models.entities import Team
from app.models.games import Game

app = FastAPI(
    title="diamond-mind API",
    description="Data query layer for the MLB intelligence system.",
    version="0.1.0",
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
    """Return all games scheduled for a date."""
    rows = db.execute(
        select(Game).where(Game.game_date == game_date)
    ).scalars().all()
    return [
        {
            "game_id": g.id,
            "game_date": g.game_date.isoformat(),
            "status": g.status,
            "home_team_id": g.home_team_id,
            "away_team_id": g.away_team_id,
            "venue": g.venue,
            "is_doubleheader": g.is_doubleheader,
            "game_number": g.game_number,
            "home_probable_starter_id": g.home_probable_starter_id,
            "away_probable_starter_id": g.away_probable_starter_id,
        }
        for g in rows
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
    return _dc(state)


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
# LLM polish (optional — stubs if key missing)
# ---------------------------------------------------------------------------

@app.post("/report/polish")
def polish_report_endpoint(body: dict):
    """Polish a raw Markdown report with Claude. Returns raw if key missing."""
    raw = body.get("markdown", "")
    if not raw:
        raise HTTPException(400, "Field 'markdown' is required.")
    from app.llm.claude_client import polish_report
    polished = polish_report(raw)
    return {"markdown": polished}
