"""FastAPI routes — data query layer for the web frontend.

All endpoints are read-only. They query the DB via Track A's form helpers
and return dataclass-compatible JSON. The Next.js/React frontend (Track B)
consumes these via HTTP.

Run with:
    uvicorn app.api.routes:app --reload --port 8000
"""

from __future__ import annotations

import dataclasses
import time
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
from app.database import SessionLocal
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

    games = db.execute(
        select(TeamGameLog.game_id).where(
            TeamGameLog.team_id == team_id,
            TeamGameLog.game_date >= start,
            TeamGameLog.game_date <= end,
        )
    ).all()
    game_count = len(games)

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

    def _bullpen(team_id: int):
        state = build_bullpen_state(db, team_id=team_id, as_of_date=as_of)
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
        "home_bullpen": _bullpen(home_id),
        "away_bullpen": _bullpen(away_id),
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

    def _bp(team_id):
        state = build_bullpen_state(db, team_id=team_id, as_of_date=as_of)
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

    # Fetch actual odds if available — prefer DraftKings, fall back to any bookmaker
    from app.models.odds import OddsSnapshotRow
    from sqlalchemy import desc as _desc
    _preferred = get_settings().preferred_bookmaker

    def _get_ml_odds(side: str) -> Optional[int]:
        base_where = [
            OddsSnapshotRow.game_id == game_id,
            OddsSnapshotRow.market == "moneyline",
            OddsSnapshotRow.selection == side,
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

    def _get_total_line() -> Optional[float]:
        base_where = [
            OddsSnapshotRow.game_id == game_id,
            OddsSnapshotRow.market == "total",
            OddsSnapshotRow.selection == "over",
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
        return row.line if row else None

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
        home_bullpen=_bp(home_id),
        away_bullpen=_bp(away_id),
        home_form=_form(home_id),
        away_form=_form(away_id),
        weather=weather,
        home_ml_odds=_get_ml_odds("home"),
        away_ml_odds=_get_ml_odds("away"),
        total_line=_get_total_line(),
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

    def _bullpen_dict(team_id: int):
        state = build_bullpen_state(db, team_id=team_id, as_of_date=game_date)
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
            "home_bullpen": _bullpen_dict(game.home_team_id),
            "away_bullpen": _bullpen_dict(game.away_team_id),
            "analysis": analysis,
        })

    return output


# ---------------------------------------------------------------------------
# LLM polish (optional — stubs if key missing)
# ---------------------------------------------------------------------------


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
