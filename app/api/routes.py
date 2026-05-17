"""FastAPI routes — data query layer for the web frontend.

All endpoints are read-only. They query the DB via Track A's form helpers
and return dataclass-compatible JSON. The Next.js/React frontend (Track B)
consumes these via HTTP.

Run with:
    uvicorn app.api.routes:app --reload --port 8000
"""

from __future__ import annotations

import dataclasses
import logging
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import aliased
from sqlalchemy.orm import Session

from app.config import get_settings
from app.contracts import WindowKey
from app.database import SessionLocal, engine, Base
from app.ingestion.park_factors import get_park_factor
from app.features.recent_form import (
    FIP_CONSTANT,
    build_bullpen_state,
    build_hitter_form_window,
    build_starter_form_window,
    build_team_form_window,
    load_hitter_form_window,
    load_team_form_window,
)
from app.features.bullpen_vulnerability import score_bullpen
from app.models.entities import Player, Team
from app.models.games import Game, PitcherGameLog, PlayerGameLog, TeamGameLog
from app.models.tracker import BetRecord, compute_units_returned

# Import all models so Base.metadata knows about every table, then create
# any that don't exist yet (safe on both SQLite and Postgres — additive only).
import app.models.players  # noqa: F401
import app.models.bullpen  # noqa: F401
import app.models.odds     # noqa: F401
import app.models.reports  # noqa: F401
Base.metadata.create_all(engine)

app = FastAPI(
    title="Diamond Mind API",
    description=(
        "Deterministic MLB betting intelligence. All analysis is math-based — "
        "no LLM inference, no fabricated stats. Data sourced from MLB Stats API "
        "and The Odds API."
    ),
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Analysis result cache  (game_id, as_of_date) → (result_dict, expires_at)
# 5-minute TTL — analysis is deterministic given the DB snapshot, but odds
# and ingested stats can change, so we don't cache indefinitely.
# ---------------------------------------------------------------------------
_ANALYSIS_CACHE: Dict[Tuple[int, date], Tuple[Any, float]] = {}
_CACHE_TTL_SECONDS = 300

def _cache_get(game_id: int, as_of: date) -> Optional[Any]:
    entry = _ANALYSIS_CACHE.get((game_id, as_of))
    if entry and time.monotonic() < entry[1]:
        return entry[0]
    _ANALYSIS_CACHE.pop((game_id, as_of), None)
    return None

def _cache_set(game_id: int, as_of: date, value: Any) -> None:
    _ANALYSIS_CACHE[(game_id, as_of)] = (value, time.monotonic() + _CACHE_TTL_SECONDS)

def _cache_invalidate_all() -> int:
    count = len(_ANALYSIS_CACHE)
    _ANALYSIS_CACHE.clear()
    return count


# ---------------------------------------------------------------------------
# Timing middleware — adds X-Response-Time header to every response
# ---------------------------------------------------------------------------
@app.middleware("http")
async def add_timing_header(request: Request, call_next):
    t0 = time.perf_counter()
    response = await call_next(request)
    ms = (time.perf_counter() - t0) * 1000
    response.headers["X-Response-Time"] = f"{ms:.1f}ms"
    return response


@app.middleware("http")
async def add_cache_control(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path in ("/health", "/cache/clear"):
        response.headers["Cache-Control"] = "no-store"
    elif path == "/model/constants":
        response.headers["Cache-Control"] = "public, max-age=3600"
    elif path in ("/games/slate", "/games/picks") or path.endswith("/analyze") or path.endswith("/context"):
        response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=30"
    elif path.startswith("/games") or path.startswith("/teams") or path.startswith("/pitchers"):
        response.headers["Cache-Control"] = "public, max-age=30, stale-while-revalidate=15"
    return response


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


def _safe_rate(num: float, den: float) -> Optional[float]:
    if den == 0:
        return None
    return num / den


def _last_team_game_dates(
    db: Session,
    *,
    team_id: int,
    window: WindowKey,
    as_of: date,
) -> Optional[tuple[date, date]]:
    if window is WindowKey.SEASON:
        return date(as_of.year, 1, 1), as_of
    game_counts = {
        WindowKey.L5: 5,
        WindowKey.L10: 10,
        WindowKey.L20: 20,
    }
    if window not in game_counts:
        raise HTTPException(400, f"Unsupported team window: {window.value}")
    dates = [
        d
        for (d,) in db.execute(
            select(TeamGameLog.game_date)
            .where(TeamGameLog.team_id == team_id, TeamGameLog.game_date <= as_of)
            .order_by(TeamGameLog.game_date.desc())
            .limit(game_counts[window])
        ).all()
    ]
    if not dates:
        return None
    return min(dates), max(dates)


def _pitcher_rows_for_window(
    db: Session,
    *,
    pitcher_id: int,
    window: WindowKey,
    as_of: date,
) -> list[PitcherGameLog]:
    stmt = select(PitcherGameLog).where(
        PitcherGameLog.pitcher_id == pitcher_id,
        PitcherGameLog.game_date <= as_of,
    )
    if window is WindowKey.SEASON:
        return list(
            db.execute(
                stmt.where(PitcherGameLog.game_date >= date(as_of.year, 1, 1))
                .order_by(PitcherGameLog.game_date.desc())
            ).scalars()
        )
    if window is WindowKey.L5:
        limit = 5
    elif window is WindowKey.L10:
        limit = 10
    elif window is WindowKey.L20:
        limit = 20
    elif window is WindowKey.LAST_5_STARTS:
        limit = 5
        stmt = stmt.where(PitcherGameLog.started.is_(True))
    elif window is WindowKey.LAST_10_STARTS:
        limit = 10
        stmt = stmt.where(PitcherGameLog.started.is_(True))
    else:
        raise HTTPException(400, f"Unsupported pitcher window: {window.value}")
    return list(
        db.execute(stmt.order_by(PitcherGameLog.game_date.desc()).limit(limit)).scalars()
    )


@app.get("/health", tags=["meta"])
def health():
    """Fast liveness probe."""
    return {"status": "ok", "version": app.version}


@app.get("/health/detailed", tags=["meta"])
def health_detailed(db: Session = Depends(_get_db)):
    """DB record counts and data-freshness timestamps."""
    from app.models.games import Game, PitcherGameLog, PlayerGameLog, TeamGameLog
    from app.models.odds import OddsSnapshotRow, WeatherSnapshotRow

    def _count(model):
        return db.execute(select(func.count()).select_from(model)).scalar_one()

    def _latest_date(model, col):
        val = db.execute(select(func.max(col))).scalar_one()
        return val.isoformat() if val else None

    games_total      = _count(Game)
    pitcher_logs     = _count(PitcherGameLog)
    player_logs      = _count(PlayerGameLog)
    team_logs        = _count(TeamGameLog)
    odds_snapshots   = _count(OddsSnapshotRow)
    weather_snapshots = _count(WeatherSnapshotRow)

    latest_game      = _latest_date(Game, Game.game_date)
    latest_pitcher   = _latest_date(PitcherGameLog, PitcherGameLog.game_date)
    latest_odds      = db.execute(select(func.max(OddsSnapshotRow.captured_at))).scalar_one()

    return {
        "status": "ok",
        "version": app.version,
        "cache": {
            "entries": len(_ANALYSIS_CACHE),
            "ttl_seconds": _CACHE_TTL_SECONDS,
        },
        "records": {
            "games": games_total,
            "pitcher_logs": pitcher_logs,
            "player_logs": player_logs,
            "team_logs": team_logs,
            "odds_snapshots": odds_snapshots,
            "weather_snapshots": weather_snapshots,
        },
        "freshness": {
            "latest_game_date": latest_game,
            "latest_pitcher_log": latest_pitcher,
            "latest_odds_captured_at": latest_odds.isoformat() if latest_odds else None,
        },
    }


@app.post("/cache/clear", tags=["meta"])
def clear_cache():
    """Flush the analysis result cache (call after ingestion runs)."""
    evicted = _cache_invalidate_all()
    return {"evicted": evicted}


@app.get("/model/constants", tags=["meta"])
def model_constants():
    """Expose all model parameters so the frontend and users can verify the math."""
    from app.betting.game_analyzer import (
        HOME_ADVANTAGE, FIP_SCALE, FIP_CONSTANT, BULLPEN_VULN_SCALE,
        OFFENSE_SCALE, KELLY_FRACTION, WIND_OUT_THRESHOLD_MPH,
        WIND_OUT_DEGREES, REST_ADJ_SHORT, REST_ADJ_LONG,
        TREND_ADJUSTMENTS, RECOMMENDATION_TIERS, PARK_FACTORS,
    )
    return {
        "version": app.version,
        "win_probability": {
            "home_advantage": HOME_ADVANTAGE,
            "home_advantage_note": "2022-2024 MLB home win rate",
            "fip_scale": FIP_SCALE,
            "fip_scale_note": "win-prob shift per 1-run FIP advantage",
            "fip_constant": FIP_CONSTANT,
            "bullpen_vuln_scale": BULLPEN_VULN_SCALE,
            "offense_scale": OFFENSE_SCALE,
        },
        "kelly": {
            "fraction": KELLY_FRACTION,
            "note": "fractional Kelly multiplier (conservative risk management)",
        },
        "weather": {
            "wind_out_threshold_mph": WIND_OUT_THRESHOLD_MPH,
            "wind_out_degrees_range": list(WIND_OUT_DEGREES),
        },
        "rest": {
            "short_rest_days": "< 4",
            "short_rest_adj": REST_ADJ_SHORT,
            "long_rest_days": "≥ 8",
            "long_rest_adj": REST_ADJ_LONG,
            "normal_range": "4–6 days (no adjustment)",
        },
        "trend_adjustments": TREND_ADJUSTMENTS,
        "recommendation_tiers": [
            {"tier": t, "min_edge": me, "min_conf": mc}
            for t, me, mc in RECOMMENDATION_TIERS
        ],
        "park_factors": PARK_FACTORS,
    }


# ---------------------------------------------------------------------------
# Games
# ---------------------------------------------------------------------------

@app.get("/games", tags=["games"])
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

@app.get("/teams", tags=["teams"])
def list_teams(db: Session = Depends(_get_db)):
    teams = db.execute(select(Team)).scalars().all()
    return [
        {"id": t.id, "abbr": t.abbr, "name": t.name,
         "league": t.league, "division": t.division}
        for t in teams
    ]


@app.get("/teams/{team_id}/form", tags=["teams"])
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


@app.get("/teams/{team_id}/batting", tags=["teams"])
def team_batting(
    team_id: int,
    window: str = Query("l10", description="season|l20|l10|l5"),
    as_of: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """Aggregate team batting rates from hitter game logs.

    This is intentionally computed from stored box-score counters only. True
    handedness splits require per-PA handedness outcomes and are not available
    in the MVP schema.
    """
    try:
        wk = WindowKey(window)
    except ValueError:
        raise HTTPException(400, f"Unknown window: {window}")

    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(404, f"Team {team_id} not found")

    bounds = _last_team_game_dates(db, team_id=team_id, window=wk, as_of=as_of)
    if bounds is None:
        raise HTTPException(404, f"No batting data for team {team_id}")
    start, end = bounds

    rows = db.execute(
        select(PlayerGameLog).where(
            PlayerGameLog.team_id == team_id,
            PlayerGameLog.game_date >= start,
            PlayerGameLog.game_date <= end,
        )
    ).scalars().all()

    tgl_rows = db.execute(
        select(TeamGameLog.game_id, TeamGameLog.runs).where(
            TeamGameLog.team_id == team_id,
            TeamGameLog.game_date >= start,
            TeamGameLog.game_date <= end,
        )
    ).all()
    game_count = len(tgl_rows)
    total_runs = sum(r for _, r in tgl_rows if r is not None)
    runs_per_game = round(total_runs / game_count, 2) if game_count else None

    pa = sum(r.plate_appearances for r in rows)
    ab = sum(r.at_bats for r in rows)
    hits = sum(r.hits for r in rows)
    doubles = sum(r.doubles for r in rows)
    triples = sum(r.triples for r in rows)
    home_runs = sum(r.home_runs for r in rows)
    walks = sum(r.walks for r in rows)
    strikeouts = sum(r.strikeouts for r in rows)
    hbp = sum(r.hit_by_pitch for r in rows)
    sac_flies = sum(r.sac_flies for r in rows)
    stolen_bases = sum(r.stolen_bases for r in rows)
    caught_stealing = sum(r.caught_stealing for r in rows)
    stolen_base_attempts = stolen_bases + caught_stealing
    singles = hits - doubles - triples - home_runs
    total_bases = singles + 2 * doubles + 3 * triples + 4 * home_runs
    avg = _safe_rate(hits, ab)
    obp = _safe_rate(hits + walks + hbp, ab + walks + hbp + sac_flies)
    slg = _safe_rate(total_bases, ab)
    ops = (obp + slg) if obp is not None and slg is not None else None
    iso = (slg - avg) if slg is not None and avg is not None else None
    woba_denom = ab + walks + hbp + sac_flies
    estimated_woba = _safe_rate(
        0.69 * walks
        + 0.72 * hbp
        + 0.89 * singles
        + 1.27 * doubles
        + 1.62 * triples
        + 2.10 * home_runs,
        woba_denom,
    )
    min_games = 1 if wk is WindowKey.SEASON else 5

    return {
        "team_id": team_id,
        "team_abbr": team.abbr,
        "window": wk.value,
        "as_of_date": as_of.isoformat(),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "games": game_count,
        "runs_per_game": runs_per_game,
        "plate_appearances": pa,
        "at_bats": ab,
        "hits": hits,
        "doubles": doubles,
        "triples": triples,
        "home_runs": home_runs,
        "walks": walks,
        "strikeouts": strikeouts,
        "hit_by_pitch": hbp,
        "sac_flies": sac_flies,
        "stolen_bases": stolen_bases,
        "caught_stealing": caught_stealing,
        "stolen_base_attempts": stolen_base_attempts,
        "stolen_base_success_rate": _safe_rate(stolen_bases, stolen_base_attempts),
        "batting_avg": avg,
        "on_base_pct": obp,
        "slugging_pct": slg,
        "ops": ops,
        "iso": iso,
        "strikeout_rate": _safe_rate(strikeouts, pa),
        "walk_rate": _safe_rate(walks, pa),
        "estimated_woba": estimated_woba,
        "unsupported": {
            "true_woba": "not stored; estimated_woba uses static linear weights",
            "handedness_splits": "not stored in MVP box-score logs",
        },
        "insufficient_sample": game_count < min_games,
    }


@app.get("/teams/{team_id}/bullpen", tags=["teams"])
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

@app.get("/players/{player_id}/form", tags=["players"])
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

@app.get("/pitchers/{pitcher_id}/form", tags=["pitchers"])
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


@app.get("/pitchers/{pitcher_id}/advanced", tags=["pitchers"])
def pitcher_advanced(
    pitcher_id: int,
    window: str = Query("last_5_starts"),
    as_of: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """Aggregate pitcher advanced-ish rates from stored pitching logs.

    FIP uses the MVP constant from the recent-form engine. BABIP is approximate because the
    schema lacks sacrifice and batted-ball detail. Strand rate and true L/R
    splits are explicitly unavailable until richer play-by-play ingestion.
    """
    try:
        wk = WindowKey(window)
    except ValueError:
        raise HTTPException(400, f"Unknown window: {window}")

    pitcher = db.get(Player, pitcher_id)
    rows = _pitcher_rows_for_window(db, pitcher_id=pitcher_id, window=wk, as_of=as_of)
    if not rows:
        raise HTTPException(404, f"No pitching data for pitcher {pitcher_id}")

    appearances = len(rows)
    starts = sum(1 for r in rows if r.started)
    innings = sum(r.innings_pitched for r in rows)
    batters_faced = sum(r.batters_faced for r in rows)
    hits = sum(r.hits_allowed for r in rows)
    earned_runs = sum(r.earned_runs for r in rows)
    walks = sum(r.walks for r in rows)
    strikeouts = sum(r.strikeouts for r in rows)
    home_runs = sum(r.home_runs_allowed for r in rows)
    pitches = sum(r.pitches for r in rows)
    fip = ((13 * home_runs + 3 * walks - 2 * strikeouts) / innings + FIP_CONSTANT) if innings else None
    balls_in_play = batters_faced - strikeouts - walks - home_runs
    babip = _safe_rate(hits - home_runs, balls_in_play)

    return {
        "pitcher_id": pitcher_id,
        "pitcher_name": pitcher.full_name if pitcher else None,
        "throws": pitcher.throws if pitcher else None,
        "team_id": rows[0].team_id,
        "window": wk.value,
        "as_of_date": as_of.isoformat(),
        "start_date": min(r.game_date for r in rows).isoformat(),
        "end_date": max(r.game_date for r in rows).isoformat(),
        "appearances": appearances,
        "starts": starts,
        "innings_pitched": innings,
        "batters_faced": batters_faced,
        "hits_allowed": hits,
        "earned_runs": earned_runs,
        "walks": walks,
        "strikeouts": strikeouts,
        "home_runs_allowed": home_runs,
        "pitches": pitches,
        "era": (earned_runs * 9 / innings) if innings else None,
        "fip": fip,
        "fip_constant": FIP_CONSTANT,
        "babip": babip,
        "whip": _safe_rate(walks + hits, innings),
        "k_rate": _safe_rate(strikeouts, batters_faced),
        "bb_rate": _safe_rate(walks, batters_faced),
        "k_per_9": (strikeouts * 9 / innings) if innings else None,
        "bb_per_9": (walks * 9 / innings) if innings else None,
        "hr_per_9": (home_runs * 9 / innings) if innings else None,
        "avg_pitches_per_start": _safe_rate(pitches, starts),
        "unsupported": {
            "strand_rate": "not stored; needs baserunner/LOB or play-by-play state",
            "left_right_splits": "not stored; needs batter handedness outcomes per PA",
        },
        "insufficient_sample": appearances < 3 or innings < 10,
    }


# ---------------------------------------------------------------------------
# GameBundle — single-call composite for the frontend
# ---------------------------------------------------------------------------

@app.get("/games/{game_id}/bundle", tags=["games"])
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

    def _bullpen(team_id: int, probable_starter_id: Optional[int] = None):
        exclude = [probable_starter_id] if probable_starter_id else None
        state = build_bullpen_state(db, team_id=team_id, as_of_date=as_of, exclude_pitcher_ids=exclude)
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
        "home_bullpen": _bullpen(home_id, game.home_probable_starter_id),
        "away_bullpen": _bullpen(away_id, game.away_probable_starter_id),
        "park_factors": {
            "venue": game.venue,
            "runs": get_park_factor(game.venue).runs,
            "hr": get_park_factor(game.venue).hr,
            "hits": get_park_factor(game.venue).hits,
            "is_dome": get_park_factor(game.venue).is_dome,
        },
    }


@app.get("/games/{game_id}/context", tags=["games"])
def game_context(
    game_id: int,
    as_of: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """Bundle + analysis + weather in one call.

    Replaces the 4-request waterfall the detail page previously needed:
      bundle, weather, analyze, (batting fetched separately per team).
    Now the detail page only needs this call + one batting call per team.
    Analysis result is cache-backed.
    """
    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(404, f"Game {game_id} not found")

    from sqlalchemy import desc as _desc
    from app.models.odds import WeatherSnapshotRow

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

    def _bullpen(team_id: int, probable_starter_id: Optional[int] = None):
        exclude = [probable_starter_id] if probable_starter_id else None
        state = build_bullpen_state(db, team_id=team_id, as_of_date=as_of, exclude_pitcher_ids=exclude)
        if state is None:
            return None
        return _dc(score_bullpen(state))

    home_id = game.home_team_id
    away_id = game.away_team_id
    home_team = db.get(Team, home_id)
    away_team = db.get(Team, away_id)

    weather_row = db.execute(
        select(WeatherSnapshotRow)
        .where(WeatherSnapshotRow.game_id == game_id)
        .order_by(_desc(WeatherSnapshotRow.captured_at))
        .limit(1)
    ).scalar_one_or_none()

    weather = None
    if weather_row:
        weather = {
            "game_id": weather_row.game_id,
            "temperature_f": weather_row.temperature_f,
            "wind_speed_mph": weather_row.wind_speed_mph,
            "wind_direction_deg": weather_row.wind_direction_deg,
            "precipitation_chance": weather_row.precipitation_chance,
            "humidity_pct": weather_row.humidity_pct,
            "is_dome": weather_row.is_dome,
            "captured_at": weather_row.captured_at.isoformat(),
        }

    return {
        "game_id": game_id,
        "game_date": game.game_date.isoformat(),
        "status": game.status,
        "venue": game.venue,
        "home_team_id": home_id,
        "away_team_id": away_id,
        "home_team_abbr": home_team.abbr if home_team else None,
        "away_team_abbr": away_team.abbr if away_team else None,
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
        "home_bullpen": _bullpen(home_id, game.home_probable_starter_id),
        "away_bullpen": _bullpen(away_id, game.away_probable_starter_id),
        "weather": weather,
        "analysis": _build_analysis_cached(game_id, as_of, db),
    }


# ---------------------------------------------------------------------------
# Park factors
# ---------------------------------------------------------------------------

@app.get("/park-factors")
def park_factors_all():
    """Return park factors for all known venues."""
    from app.ingestion.park_factors import _PARK_FACTORS
    return [
        {"venue": pf.venue, "runs": pf.runs, "hr": pf.hr, "hits": pf.hits, "is_dome": pf.is_dome}
        for pf in _PARK_FACTORS
    ]


@app.get("/park-factors/venue")
def park_factors_venue(venue: str = Query(..., description="Venue name")):
    pf = get_park_factor(venue)
    return {"venue": pf.venue, "runs": pf.runs, "hr": pf.hr, "hits": pf.hits, "is_dome": pf.is_dome}


# ---------------------------------------------------------------------------
# Odds and weather
# ---------------------------------------------------------------------------

@app.get("/games/{game_id}/odds", tags=["games"])
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


@app.get("/games/{game_id}/weather", tags=["games"])
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
# Game Analysis — algorithmic betting intelligence
# ---------------------------------------------------------------------------

def _batting_stats_for_team(db: Session, *, team_id: int, as_of: date) -> dict:
    """Return estimated_woba, strikeout_rate, and ISO from L10 batting logs."""
    bounds = _last_team_game_dates(db, team_id=team_id, window=WindowKey.L10, as_of=as_of)
    if bounds is None:
        return {}
    start, end = bounds
    rows = db.execute(
        select(PlayerGameLog).where(
            PlayerGameLog.team_id == team_id,
            PlayerGameLog.game_date >= start,
            PlayerGameLog.game_date <= end,
        )
    ).scalars().all()
    if not rows:
        return {}
    walks = sum(r.walks for r in rows)
    hbp = sum(r.hit_by_pitch for r in rows)
    hits = sum(r.hits for r in rows)
    doubles = sum(r.doubles for r in rows)
    triples = sum(r.triples for r in rows)
    home_runs = sum(r.home_runs for r in rows)
    ab = sum(r.at_bats for r in rows)
    pa = sum(r.plate_appearances for r in rows)
    sac_flies = sum(r.sac_flies for r in rows)
    strikeouts = sum(r.strikeouts for r in rows)
    singles = hits - doubles - triples - home_runs
    total_bases = singles + 2 * doubles + 3 * triples + 4 * home_runs
    denom = ab + walks + hbp + sac_flies
    woba = _safe_rate(
        0.69 * walks + 0.72 * hbp + 0.89 * singles
        + 1.27 * doubles + 1.62 * triples + 2.10 * home_runs,
        denom,
    )
    slg = _safe_rate(total_bases, ab)
    avg = _safe_rate(hits, ab)
    iso = (slg - avg) if slg is not None and avg is not None else None
    k_rate = _safe_rate(strikeouts, pa)
    bb_rate = _safe_rate(walks, pa)
    return {"woba": woba, "iso": iso, "k_rate": k_rate, "bb_rate": bb_rate}


def _estimated_woba_for_team(db: Session, *, team_id: int, as_of: date) -> Optional[float]:
    """Compute estimated wOBA from L10 batting logs for use in game analysis."""
    return _batting_stats_for_team(db, team_id=team_id, as_of=as_of).get("woba")


def _build_analysis(game_id: int, as_of: date, db: Session):
    """Load all data for a game and return a GameAnalysis dataclass."""
    import dataclasses
    from sqlalchemy import desc
    from app.betting.game_analyzer import analyze_game
    from app.models.odds import WeatherSnapshotRow

    game = db.get(Game, game_id)
    if game is None:
        return None

    home_id = game.home_team_id
    away_id = game.away_team_id
    home_team = db.get(Team, home_id)
    away_team = db.get(Team, away_id)

    def _sp(pitcher_id):
        if pitcher_id is None:
            return None
        return build_starter_form_window(
            db, pitcher_id=pitcher_id,
            window=WindowKey.LAST_5_STARTS, as_of_date=as_of,
        )

    def _bp(team_id, probable_starter_id=None):
        exclude = [probable_starter_id] if probable_starter_id else None
        state = build_bullpen_state(db, team_id=team_id, as_of_date=as_of, exclude_pitcher_ids=exclude)
        return score_bullpen(state) if state else None

    def _form(team_id):
        w = load_team_form_window(db, team_id=team_id, window=WindowKey.L10, as_of_date=as_of)
        if w is None:
            w = build_team_form_window(db, team_id=team_id, window=WindowKey.L10, as_of_date=as_of)
        if w is None:
            return None
        # Inject estimated wOBA from batting logs if team_woba not already set
        if w.team_woba is None:
            woba = _estimated_woba_for_team(db, team_id=team_id, as_of=as_of)
            if woba is not None:
                w = dataclasses.replace(w, team_woba=woba)
        return w

    # Fetch batting aggregates for K%, ISO, and BB% signals
    home_batting = _batting_stats_for_team(db, team_id=home_id, as_of=as_of)
    away_batting = _batting_stats_for_team(db, team_id=away_id, as_of=as_of)

    # Head-to-head season record between these two teams
    def _h2h(team_id: int, opp_id: int) -> tuple[int, int]:
        """Return (wins, games_played) for team_id vs opp_id this season."""
        season_start = date(as_of.year, 1, 1)
        matchup_game_ids = [
            gid for (gid,) in db.execute(
                select(Game.id).where(
                    Game.game_date >= season_start,
                    Game.game_date <= as_of,
                    (
                        ((Game.home_team_id == team_id) & (Game.away_team_id == opp_id)) |
                        ((Game.home_team_id == opp_id) & (Game.away_team_id == team_id))
                    ),
                )
            ).all()
        ]
        if not matchup_game_ids:
            return 0, 0
        logs = db.execute(
            select(TeamGameLog.won).where(
                TeamGameLog.team_id == team_id,
                TeamGameLog.game_id.in_(matchup_game_ids),
            )
        ).scalars().all()
        won_count = sum(1 for w in logs if w)
        return won_count, len(logs)

    home_h2h = _h2h(home_id, away_id)
    away_h2h = _h2h(away_id, home_id)

    # Home/road splits — season win rate at home (for home team) and on road (for away team)
    def _split_record(team_id: int, is_home: bool) -> tuple[int, int]:
        season_start = date(as_of.year, 1, 1)
        logs = db.execute(
            select(TeamGameLog.won).where(
                TeamGameLog.team_id == team_id,
                TeamGameLog.game_date >= season_start,
                TeamGameLog.game_date <= as_of,
                TeamGameLog.is_home == is_home,
            )
        ).scalars().all()
        return sum(1 for w in logs if w), len(logs)

    home_home_record = _split_record(home_id, True)   # home team's home record
    away_road_record = _split_record(away_id, False)   # away team's road record

    # Pitcher BABIP from last 5 starts — high BABIP = getting unlucky (positive regression)
    def _sp_babip(pitcher_id: Optional[int]) -> Optional[float]:
        if pitcher_id is None:
            return None
        rows = _pitcher_rows_for_window(db, pitcher_id=pitcher_id, window=WindowKey.LAST_5_STARTS, as_of=as_of)
        if not rows or sum(r.innings_pitched for r in rows) < 10:
            return None
        hits = sum(r.hits_allowed for r in rows)
        hr = sum(r.home_runs_allowed for r in rows)
        bf = sum(r.batters_faced for r in rows)
        k = sum(r.strikeouts for r in rows)
        bb = sum(r.walks for r in rows)
        bip = bf - k - bb - hr
        return _safe_rate(hits - hr, bip)

    home_sp_babip = _sp_babip(game.home_probable_starter_id)
    away_sp_babip = _sp_babip(game.away_probable_starter_id)

    # Team stolen base rate this season (speed/pressure signal)
    def _sb_rate(team_id: int) -> Optional[float]:
        season_start = date(as_of.year, 1, 1)
        rows = db.execute(
            select(PlayerGameLog).where(
                PlayerGameLog.team_id == team_id,
                PlayerGameLog.game_date >= season_start,
                PlayerGameLog.game_date <= as_of,
            )
        ).scalars().all()
        if not rows:
            return None
        sb = sum(r.stolen_bases for r in rows)
        pa = sum(r.plate_appearances for r in rows)
        return _safe_rate(sb, pa)

    home_sb_rate = _sb_rate(home_id)
    away_sb_rate = _sb_rate(away_id)

    # Pitcher last-start pitch count (within 7 days)
    def _last_pitch_count(pitcher_id: Optional[int]) -> Optional[int]:
        if pitcher_id is None:
            return None
        from datetime import timedelta
        row = db.execute(
            select(PitcherGameLog.pitches).where(
                PitcherGameLog.pitcher_id == pitcher_id,
                PitcherGameLog.started.is_(True),
                PitcherGameLog.game_date < as_of,
                PitcherGameLog.game_date >= as_of - timedelta(days=7),
            ).order_by(PitcherGameLog.game_date.desc()).limit(1)
        ).scalar_one_or_none()
        return row

    # Pitcher days rest — most recent appearance before as_of
    def _days_rest(pitcher_id: Optional[int]) -> Optional[int]:
        if pitcher_id is None:
            return None
        last = db.execute(
            select(PitcherGameLog.game_date)
            .where(PitcherGameLog.pitcher_id == pitcher_id, PitcherGameLog.game_date < as_of)
            .order_by(PitcherGameLog.game_date.desc())
            .limit(1)
        ).scalar_one_or_none()
        if last is None:
            return None
        return (as_of - last).days

    # Fetch actual odds if available — prefer DraftKings, fall back to any bookmaker.
    # Selections are stored as lowercased team names from The Odds API (e.g. "new york mets"),
    # so we match by substring against the team's DB name rather than "home"/"away".
    from app.models.odds import OddsSnapshotRow
    from sqlalchemy import desc as _desc
    _preferred = get_settings().preferred_bookmaker

    def _team_name_fragment(team_id: int) -> str:
        t = db.get(Team, team_id)
        return t.name.lower() if t else ""

    _home_frag = _team_name_fragment(home_id)
    _away_frag = _team_name_fragment(away_id)

    def _get_ml_odds(side: str) -> Optional[int]:
        frag = _home_frag if side == "home" else _away_frag
        if not frag:
            return None
        base_where = [
            OddsSnapshotRow.game_id == game_id,
            OddsSnapshotRow.market == "moneyline",
            OddsSnapshotRow.selection.ilike(f"%{frag}%"),
        ]
        row = db.execute(
            select(OddsSnapshotRow).where(*base_where, OddsSnapshotRow.bookmaker == _preferred)
            .order_by(_desc(OddsSnapshotRow.captured_at)).limit(1)
        ).scalar_one_or_none()
        if row is None:
            row = db.execute(
                select(OddsSnapshotRow).where(*base_where)
                .order_by(_desc(OddsSnapshotRow.captured_at)).limit(1)
            ).scalar_one_or_none()
        return row.american_odds if row else None

    def _get_total_odds(selection: str) -> tuple[Optional[float], Optional[int]]:
        """Return (line, american_odds) for the given total selection ('over'/'under')."""
        base_where = [
            OddsSnapshotRow.game_id == game_id,
            OddsSnapshotRow.market == "total",
            OddsSnapshotRow.selection == selection,
        ]
        row = db.execute(
            select(OddsSnapshotRow).where(*base_where, OddsSnapshotRow.bookmaker == _preferred)
            .order_by(_desc(OddsSnapshotRow.captured_at)).limit(1)
        ).scalar_one_or_none()
        if row is None:
            row = db.execute(
                select(OddsSnapshotRow).where(*base_where)
                .order_by(_desc(OddsSnapshotRow.captured_at)).limit(1)
            ).scalar_one_or_none()
        return (row.line, row.american_odds) if row else (None, None)

    _total_line, _over_odds = _get_total_odds("over")
    _total_line_u, _under_odds = _get_total_odds("under")
    _total_line = _total_line or _total_line_u  # either row has the line
    # Sanity: MLB game totals should be between 5 and 15 runs.
    # Lines outside that range indicate mismatched odds (alternate lines, wrong sport).
    if _total_line is not None and not (5.0 <= _total_line <= 15.0):
        _total_line = None
        _over_odds = None
        _under_odds = None

    # Weather — best available snapshot
    weather_row = db.execute(
        select(WeatherSnapshotRow)
        .where(WeatherSnapshotRow.game_id == game_id)
        .order_by(desc(WeatherSnapshotRow.captured_at))
        .limit(1)
    ).scalar_one_or_none()

    weather = None
    if weather_row is not None:
        from app.contracts import WeatherSnapshot
        weather = WeatherSnapshot(
            game_id=weather_row.game_id,
            temperature_f=weather_row.temperature_f,
            wind_speed_mph=weather_row.wind_speed_mph,
            wind_direction_deg=weather_row.wind_direction_deg,
            precipitation_chance=weather_row.precipitation_chance,
            humidity_pct=weather_row.humidity_pct,
            is_dome=weather_row.is_dome,
            captured_at=weather_row.captured_at,
        )

    return analyze_game(
        game_id=game_id,
        home_abbr=home_team.abbr if home_team else "???",
        away_abbr=away_team.abbr if away_team else "???",
        home_sp=_sp(game.home_probable_starter_id),
        away_sp=_sp(game.away_probable_starter_id),
        home_bullpen=_bp(home_id, game.home_probable_starter_id),
        away_bullpen=_bp(away_id, game.away_probable_starter_id),
        home_form=_form(home_id),
        away_form=_form(away_id),
        weather=weather,
        home_ml_odds=_get_ml_odds("home"),
        away_ml_odds=_get_ml_odds("away"),
        total_line=_total_line,
        over_odds=_over_odds,
        under_odds=_under_odds,
        home_k_rate=home_batting.get("k_rate"),
        away_k_rate=away_batting.get("k_rate"),
        home_iso=home_batting.get("iso"),
        away_iso=away_batting.get("iso"),
        home_bb_rate=home_batting.get("bb_rate"),
        away_bb_rate=away_batting.get("bb_rate"),
        home_sp_days_rest=_days_rest(game.home_probable_starter_id),
        away_sp_days_rest=_days_rest(game.away_probable_starter_id),
        venue=game.venue,
        home_h2h=home_h2h,
        away_h2h=away_h2h,
        home_home_record=home_home_record,
        away_road_record=away_road_record,
        home_sp_last_pitch_count=_last_pitch_count(game.home_probable_starter_id),
        away_sp_last_pitch_count=_last_pitch_count(game.away_probable_starter_id),
        home_sp_babip=home_sp_babip,
        away_sp_babip=away_sp_babip,
        home_sb_rate=home_sb_rate,
        away_sb_rate=away_sb_rate,
    )


def _build_analysis_cached(game_id: int, as_of: date, db: Session) -> Optional[dict]:
    """Cache-wrapped version of _build_analysis. Returns a dict (already serialized)."""
    cached = _cache_get(game_id, as_of)
    if cached is not None:
        return cached
    result = _build_analysis(game_id, as_of, db)
    if result is None:
        return None
    serialized = _dc(result)
    _cache_set(game_id, as_of, serialized)
    return serialized


@app.get("/games/{game_id}/analyze", tags=["analysis"])
def game_analyze(
    game_id: int,
    as_of: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """Run the full deterministic model for a single game.

    Results are cached for 5 minutes per (game_id, as_of) pair.
    Call POST /cache/clear after an ingestion run to force a refresh.
    """
    result = _build_analysis_cached(game_id, as_of, db)
    if result is None:
        raise HTTPException(404, f"Game {game_id} not found")
    return result


@app.get("/games/{game_id}/analyze/f5", tags=["analysis"])
def game_analyze_f5(
    game_id: int,
    as_of: date = Query(..., description="YYYY-MM-DD"),
    home_f5_odds: Optional[int] = Query(None, description="American odds, home F5 ML"),
    away_f5_odds: Optional[int] = Query(None, description="American odds, away F5 ML"),
    db: Session = Depends(_get_db),
):
    """First-5-innings moneyline model — isolates starter skill, excludes bullpen.

    Projection-only unless both F5 odds are supplied (no invented line). Per
    Arnav's Track A/B split; platoon term is 0.0 until L/R splits land.
    """
    import dataclasses
    from app.betting.f5_model import analyze_f5_moneyline

    game = db.get(Game, game_id)
    if game is None:
        raise HTTPException(404, f"Game {game_id} not found")
    home_team = db.get(Team, game.home_team_id)
    away_team = db.get(Team, game.away_team_id)

    def _sp(pitcher_id):
        if pitcher_id is None:
            return None
        return build_starter_form_window(
            db, pitcher_id=pitcher_id, window=WindowKey.LAST_5_STARTS, as_of_date=as_of,
        )

    result = analyze_f5_moneyline(
        game_id=game_id,
        home_abbr=home_team.abbr if home_team else "HOM",
        away_abbr=away_team.abbr if away_team else "AWY",
        home_sp=_sp(game.home_probable_starter_id),
        away_sp=_sp(game.away_probable_starter_id),
        home_f5_odds=home_f5_odds,
        away_f5_odds=away_f5_odds,
    )
    return dataclasses.asdict(result)


@app.get("/quant/verify", tags=["analysis"])
def quant_verify(
    model_prob: float = Query(..., ge=0.01, le=0.99, description="model win prob for the side"),
    side_odds: int = Query(..., description="American odds for the side"),
    other_odds: int = Query(..., description="American odds for the opponent"),
    evidence_quality: float = Query(0.7, ge=0.0, le=1.0),
):
    """Run the live quant pipeline for an arbitrary line.

    Single source of truth for the Bet Verifier UI — Shin devig, Bayesian
    shrinkage, edge posterior, uncertainty-adjusted Kelly, log-growth.
    """
    from app.betting.quant import compute_quant_edge, quant_recommendation

    qe = compute_quant_edge(model_prob, side_odds, other_odds, evidence_quality)
    rec = quant_recommendation(qe, model_confidence=model_prob, evidence_quality=evidence_quality)
    return {**dataclasses.asdict(qe), "recommendation": rec}


@app.get("/nba/analyze", tags=["analysis"])
def nba_analyze(
    home_team: str = Query(...),
    away_team: str = Query(...),
    home_net_rating: float = Query(..., description="off_rtg - def_rtg, home"),
    away_net_rating: float = Query(..., description="off_rtg - def_rtg, away"),
    home_ml_odds: Optional[int] = Query(None),
    away_ml_odds: Optional[int] = Query(None),
    home_rest_days: Optional[int] = Query(None),
    away_rest_days: Optional[int] = Query(None),
    home_back_to_back: bool = Query(False),
    away_back_to_back: bool = Query(False),
    evidence_quality: float = Query(0.6, ge=0.0, le=1.0),
):
    """NBA moneyline — quant core ported to basketball.

    On-demand over explicit inputs (no NBA ingestion in this repo; no
    fabricated team data). Routes through the same Shin/Bayesian/Kelly
    pipeline as the MLB models.
    """
    import dataclasses
    from app.betting.nba_model import analyze_nba_game

    result = analyze_nba_game(
        home_team=home_team, away_team=away_team,
        home_net_rating=home_net_rating, away_net_rating=away_net_rating,
        home_ml_odds=home_ml_odds, away_ml_odds=away_ml_odds,
        home_rest_days=home_rest_days, away_rest_days=away_rest_days,
        home_back_to_back=home_back_to_back, away_back_to_back=away_back_to_back,
        evidence_quality=evidence_quality,
    )
    return dataclasses.asdict(result)


@app.get("/games/picks", tags=["analysis"])
def daily_picks(
    game_date: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """All games on a date, analyzed and ranked by model edge.

    STRONG LEAN → LEAN → PASS → AVOID, then by confidence descending.
    Analysis results are cached for 5 minutes.
    """
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

    results = []
    for game, _home, _away in rows:
        d = _build_analysis_cached(game.id, game_date, db)
        if d is not None:
            d = dict(d)
            d["game_date"] = game.game_date.isoformat()
            d["venue"] = game.venue
            results.append(d)

    tier_order = {"STRONG LEAN": 0, "LEAN": 1, "PASS": 2, "AVOID": 3}
    results.sort(key=lambda r: (tier_order.get(r.get("ml_tier", "PASS"), 2), -r.get("ml_confidence", 0)))
    return results


@app.get("/games/slate", tags=["analysis"])
def slate(
    game_date: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """Single-call slate endpoint — replaces N+1 frontend pattern.

    Returns every game on a date with home/away bullpen scores and model
    analysis bundled inline. One HTTP request replaces 1 + 3N requests
    (games list + bullpen×2 + analyze per game).

    Results are cached per (game_id, date).
    """
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

    def _bullpen_dict(team_id: int, probable_starter_id: Optional[int] = None):
        exclude = [probable_starter_id] if probable_starter_id else None
        state = build_bullpen_state(db, team_id=team_id, as_of_date=game_date, exclude_pitcher_ids=exclude)
        if state is None:
            return None
        return _dc(score_bullpen(state))

    output = []
    for game, home_t, away_t in rows:
        analysis = _build_analysis_cached(game.id, game_date, db)
        output.append({
            "game_id": game.id,
            "game_date": game.game_date.isoformat(),
            "status": game.status,
            "venue": game.venue,
            "home_team_id": game.home_team_id,
            "home_team_abbr": home_t.abbr,
            "away_team_id": game.away_team_id,
            "away_team_abbr": away_t.abbr,
            "home_probable_starter_id": game.home_probable_starter_id,
            "away_probable_starter_id": game.away_probable_starter_id,
            "home_bullpen": _bullpen_dict(game.home_team_id, game.home_probable_starter_id),
            "away_bullpen": _bullpen_dict(game.away_team_id, game.away_probable_starter_id),
            "analysis": analysis,
        })

    return output


# ---------------------------------------------------------------------------
# LLM polish (optional — stubs if key missing)
# ---------------------------------------------------------------------------


@app.get("/report", tags=["reports"])
def get_report(date: str = Query(..., description="YYYY-MM-DD")):
    """Serve the generated daily report markdown for a date.

    Reads obsidian_vault/Reports/Daily/{date}.md (written by
    scripts/run_daily_report.py). 404 if it hasn't been generated yet.
    """
    from pathlib import Path
    from fastapi.responses import PlainTextResponse

    repo_root = Path(__file__).resolve().parents[2]
    report_path = repo_root / "obsidian_vault" / "Reports" / "Daily" / f"{date}.md"
    if not report_path.is_file():
        raise HTTPException(
            404, f"No report for {date}. Run: python scripts/run_daily_report.py"
        )
    return PlainTextResponse(report_path.read_text(encoding="utf-8"))


@app.post("/report/polish", tags=["reports"])
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


# ---------------------------------------------------------------------------
# Tracker — picks performance log
# ---------------------------------------------------------------------------

# Tables are created at module load above (Base.metadata.create_all).


class _BetCreate(dict):
    """Thin typed wrapper — FastAPI will parse from JSON body."""


from pydantic import BaseModel as _BaseModel


class BetCreateBody(_BaseModel):
    game_id: int
    game_date: str          # "YYYY-MM-DD"
    market: str             # "moneyline" | "total"
    selection: str          # team abbr or "OVER"/"UNDER"
    american_odds: int
    units: float = 1.0
    tier: str               # "STRONG LEAN" | "LEAN"
    home_team_abbr: str
    away_team_abbr: str
    total_line: Optional[float] = None
    projected_total: Optional[float] = None


class BetSettleBody(_BaseModel):
    result: str                         # "WIN" | "LOSS" | "PUSH"
    units_returned: Optional[float] = None


def _bet_to_dict(b: BetRecord) -> dict:
    return {
        "id": b.id,
        "game_id": b.game_id,
        "game_date": b.game_date.isoformat(),
        "market": b.market,
        "selection": b.selection,
        "american_odds": b.american_odds,
        "units": b.units,
        "result": b.result,
        "units_returned": b.units_returned,
        "tier": b.tier,
        "home_team_abbr": b.home_team_abbr,
        "away_team_abbr": b.away_team_abbr,
        "total_line": b.total_line,
        "projected_total": b.projected_total,
        "created_at": b.created_at.isoformat() if b.created_at else None,
    }


@app.get("/tracker/bets", tags=["tracker"])
def list_bets(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    market: Optional[str] = Query(None),
    db: Session = Depends(_get_db),
):
    """Return tracked bets, optionally filtered by date range and market."""
    stmt = select(BetRecord)
    if date_from:
        stmt = stmt.where(BetRecord.game_date >= date_from)
    if date_to:
        stmt = stmt.where(BetRecord.game_date <= date_to)
    if market:
        stmt = stmt.where(BetRecord.market == market)
    stmt = stmt.order_by(BetRecord.game_date.desc(), BetRecord.id.desc())
    rows = db.execute(stmt).scalars().all()
    return [_bet_to_dict(b) for b in rows]


@app.post("/tracker/bets", tags=["tracker"], status_code=201)
def create_bet(body: BetCreateBody, db: Session = Depends(_get_db)):
    """Track a new bet. Returns the created record."""
    from datetime import date as _date
    gd = _date.fromisoformat(body.game_date)
    record = BetRecord(
        game_id=body.game_id,
        game_date=gd,
        market=body.market,
        selection=body.selection,
        american_odds=body.american_odds,
        units=body.units,
        tier=body.tier,
        home_team_abbr=body.home_team_abbr,
        away_team_abbr=body.away_team_abbr,
        total_line=body.total_line,
        projected_total=body.projected_total,
        result=None,
        units_returned=None,
        created_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _bet_to_dict(record)


@app.patch("/tracker/bets/{bet_id}", tags=["tracker"])
def settle_bet(bet_id: int, body: BetSettleBody, db: Session = Depends(_get_db)):
    """Settle a bet. Auto-computes units_returned if not provided."""
    record = db.get(BetRecord, bet_id)
    if record is None:
        raise HTTPException(404, f"Bet {bet_id} not found")
    valid = {"WIN", "LOSS", "PUSH"}
    if body.result not in valid:
        raise HTTPException(400, f"result must be one of {valid}")
    record.result = body.result
    if body.units_returned is not None:
        record.units_returned = body.units_returned
    else:
        record.units_returned = compute_units_returned(body.result, record.units, record.american_odds)
    db.commit()
    db.refresh(record)
    return _bet_to_dict(record)


@app.delete("/tracker/bets/{bet_id}", tags=["tracker"], status_code=204)
def delete_bet(bet_id: int, db: Session = Depends(_get_db)):
    """Remove a tracked bet."""
    record = db.get(BetRecord, bet_id)
    if record is None:
        raise HTTPException(404, f"Bet {bet_id} not found")
    db.delete(record)
    db.commit()
    return None


@app.get("/tracker/summary", tags=["tracker"])
def tracker_summary(
    date_from: Optional[date] = Query(None),
    date_to: Optional[date] = Query(None),
    db: Session = Depends(_get_db),
):
    """Return win/loss/units summary split by market and combined."""
    stmt = select(BetRecord)
    if date_from:
        stmt = stmt.where(BetRecord.game_date >= date_from)
    if date_to:
        stmt = stmt.where(BetRecord.game_date <= date_to)
    rows = db.execute(stmt).scalars().all()

    def _stats(bets):
        wins = sum(1 for b in bets if b.result == "WIN")
        losses = sum(1 for b in bets if b.result == "LOSS")
        pushes = sum(1 for b in bets if b.result == "PUSH")
        pending = sum(1 for b in bets if b.result is None)
        wagered = sum(b.units for b in bets)
        net = sum(b.units_returned for b in bets if b.units_returned is not None)
        return {
            "bets": len(bets),
            "wins": wins,
            "losses": losses,
            "pushes": pushes,
            "pending": pending,
            "units_wagered": round(wagered, 2),
            "units_net": round(net, 2),
        }

    ml = [b for b in rows if b.market == "moneyline"]
    total = [b for b in rows if b.market == "total"]
    return {
        "ml": _stats(ml),
        "total": _stats(total),
        "combined": _stats(rows),
    }


_ACTIONABLE_TIERS = {"STRONG LEAN", "LEAN"}
_MIN_UNITS = 0.5
_MAX_UNITS = 5.0


def _kelly_units(kelly_sized: float) -> float:
    """Convert a Kelly fraction to units (bankroll = 100u), clamped [0.5, 5.0]."""
    raw = round(kelly_sized * 100, 1)
    return max(_MIN_UNITS, min(_MAX_UNITS, raw))


@app.post("/tracker/auto-track", tags=["tracker"])
def auto_track(
    game_date: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """Automatically log all non-PASS picks for a date with Kelly-derived units.

    Idempotent — skips any (game_id, market) pair that already has a record.
    Returns a summary of how many bets were created vs already-tracked.
    """
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

    created = 0
    skipped = 0

    from app.models.odds import OddsSnapshotRow

    now_utc = datetime.utcnow()

    for game, home_t, away_t in rows:
        # Skip games that have already started — picks placed after first pitch
        # are not actionable and should not be tracked.
        if game.game_time_utc and game.game_time_utc <= now_utc:
            skipped += 1
            continue

        analysis = _build_analysis_cached(game.id, game_date, db)
        if analysis is None:
            continue

        home_abbr = home_t.abbr
        away_abbr = away_t.abbr

        # ── Moneyline ────────────────────────────────────────────────────────
        if analysis.get("ml_tier") in _ACTIONABLE_TIERS:
            existing = db.execute(
                select(BetRecord).where(
                    BetRecord.game_id == game.id,
                    BetRecord.market == "moneyline",
                )
            ).scalar_one_or_none()
            if existing is None:
                # ml_lean is "HOME" or "AWAY" (not team abbr)
                lean = analysis.get("ml_lean", "")
                if lean == "HOME" or lean == home_abbr:
                    selection = home_abbr
                    odds = analysis.get("ml_american_odds", 0)
                else:
                    selection = away_abbr
                    away_team = db.get(Team, game.away_team_id)
                    away_frag = away_team.name.lower() if away_team else away_abbr.lower()
                    away_odds_row = db.execute(
                        select(OddsSnapshotRow.american_odds)
                        .where(
                            OddsSnapshotRow.game_id == game.id,
                            OddsSnapshotRow.market == "h2h",
                            OddsSnapshotRow.selection.ilike(f"%{away_frag}%"),
                        )
                        .order_by(OddsSnapshotRow.captured_at.desc())
                        .limit(1)
                    ).scalar_one_or_none()
                    odds = away_odds_row if away_odds_row is not None else analysis.get("ml_american_odds", 0)

                units = _kelly_units(analysis.get("q_kelly_sized", 0.01))
                db.add(BetRecord(
                    game_id=game.id,
                    game_date=game_date,
                    market="moneyline",
                    selection=selection,
                    american_odds=int(odds),
                    units=units,
                    tier=analysis["ml_tier"],
                    home_team_abbr=home_abbr,
                    away_team_abbr=away_abbr,
                    total_line=None,
                    projected_total=None,
                    result=None,
                    units_returned=None,
                    created_at=datetime.utcnow(),
                ))
                created += 1
            else:
                skipped += 1

        # ── Total (over/under) ────────────────────────────────────────────────
        if analysis.get("total_tier") in _ACTIONABLE_TIERS:
            existing = db.execute(
                select(BetRecord).where(
                    BetRecord.game_id == game.id,
                    BetRecord.market == "total",
                )
            ).scalar_one_or_none()
            if existing is None:
                total_lean = analysis.get("total_lean", "OVER")
                if total_lean not in ("OVER", "UNDER"):
                    proj = analysis.get("projected_total")
                    line = analysis.get("total_line")
                    total_lean = "OVER" if (proj and line and proj > line) else "UNDER"

                side_frag = "over" if total_lean == "OVER" else "under"
                total_odds_row = db.execute(
                    select(OddsSnapshotRow.american_odds)
                    .where(
                        OddsSnapshotRow.game_id == game.id,
                        OddsSnapshotRow.market == "totals",
                        OddsSnapshotRow.selection.ilike(f"%{side_frag}%"),
                    )
                    .order_by(OddsSnapshotRow.captured_at.desc())
                    .limit(1)
                ).scalar_one_or_none()
                total_odds = int(total_odds_row) if total_odds_row is not None else -110

                units = _kelly_units(analysis.get("qt_kelly_sized", 0.01))
                db.add(BetRecord(
                    game_id=game.id,
                    game_date=game_date,
                    market="total",
                    selection=total_lean,
                    american_odds=total_odds,
                    units=units,
                    tier=analysis["total_tier"],
                    home_team_abbr=home_abbr,
                    away_team_abbr=away_abbr,
                    total_line=analysis.get("total_line"),
                    projected_total=analysis.get("projected_total"),
                    result=None,
                    units_returned=None,
                    created_at=datetime.utcnow(),
                ))
                created += 1
            else:
                skipped += 1

    db.commit()
    return {"created": created, "skipped": skipped, "date": game_date.isoformat()}


# ---------------------------------------------------------------------------
# Admin — server-side ingestion
# Runs run_pregame_update.py as a subprocess so it executes on the Render VM,
# eliminating the ~100ms-per-query network round-trip from local machines.
# ---------------------------------------------------------------------------

_INGESTION_JOBS: Dict[str, Dict] = {}   # job_id → {status, started_at, as_of, log_lines, error}
_INGESTION_LOCK = threading.Lock()


def _run_ingestion_subprocess(job_id: str, as_of: date) -> None:
    job = _INGESTION_JOBS[job_id]
    job["status"] = "running"
    try:
        script = os.path.join(os.path.dirname(__file__), "..", "..", "scripts", "run_pregame_update.py")
        script = os.path.abspath(script)
        cmd = [sys.executable, script, "--date", as_of.isoformat()]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        for line in proc.stdout:
            job["log_lines"].append(line.rstrip())
        proc.wait()
        if proc.returncode == 0:
            job["status"] = "done"
        else:
            job["status"] = "error"
            job["error"] = f"Process exited with code {proc.returncode}"
    except Exception as exc:
        job["status"] = "error"
        job["error"] = str(exc)
        logging.getLogger("admin.ingestion").exception("Ingestion job %s failed", job_id)


@app.post("/admin/run-ingestion")
def trigger_ingestion(game_date: Optional[date] = Query(default=None)):
    """
    Trigger a full pregame ingestion run server-side (runs on the Render VM).
    Returns a job_id immediately; poll /admin/ingestion-status/{job_id} for progress.
    Idempotent: if a job is already running for the same date, returns its job_id.
    """
    if game_date is None:
        game_date = date.today()

    with _INGESTION_LOCK:
        # Prevent double-starts for the same date if already in flight
        for jid, job in _INGESTION_JOBS.items():
            if job["as_of"] == game_date.isoformat() and job["status"] == "running":
                return {"job_id": jid, "as_of": game_date.isoformat(), "status": "already_running"}

        job_id = uuid.uuid4().hex[:12]
        _INGESTION_JOBS[job_id] = {
            "status": "queued",
            "started_at": datetime.utcnow().isoformat() + "Z",
            "as_of": game_date.isoformat(),
            "log_lines": [],
            "error": None,
        }

    t = threading.Thread(target=_run_ingestion_subprocess, args=(job_id, game_date), daemon=True)
    t.start()
    return {"job_id": job_id, "as_of": game_date.isoformat(), "status": "queued"}


@app.get("/admin/ingestion-status/{job_id}")
def ingestion_status(job_id: str, tail: int = Query(default=100, ge=1, le=2000)):
    """
    Check the status and recent log output of an ingestion job.
    tail=N returns the last N log lines (default 100).
    """
    job = _INGESTION_JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found. It may have expired.")
    return {
        "job_id": job_id,
        "status": job["status"],
        "started_at": job["started_at"],
        "as_of": job["as_of"],
        "error": job["error"],
        "log_lines_total": len(job["log_lines"]),
        "log_tail": job["log_lines"][-tail:],
    }


@app.get("/admin/ingestion-jobs")
def list_ingestion_jobs():
    """List all ingestion jobs (running, done, error) in this server process lifetime."""
    return [
        {
            "job_id": jid,
            "status": job["status"],
            "started_at": job["started_at"],
            "as_of": job["as_of"],
            "log_lines_total": len(job["log_lines"]),
            "error": job["error"],
        }
        for jid, job in _INGESTION_JOBS.items()
    ]
