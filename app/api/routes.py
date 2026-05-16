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


@app.get("/teams/{team_id}/batting")
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


@app.get("/pitchers/{pitcher_id}/advanced")
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
    return {"woba": woba, "iso": iso, "k_rate": k_rate}


def _estimated_woba_for_team(db: Session, *, team_id: int, as_of: date) -> Optional[float]:
    """Compute estimated wOBA from L10 batting logs for use in game analysis."""
    bounds = _last_team_game_dates(db, team_id=team_id, window=WindowKey.L10, as_of=as_of)
    if bounds is None:
        return None
    start, end = bounds
    rows = db.execute(
        select(PlayerGameLog).where(
            PlayerGameLog.team_id == team_id,
            PlayerGameLog.game_date >= start,
            PlayerGameLog.game_date <= end,
        )
    ).scalars().all()
    if not rows:
        return None
    walks = sum(r.walks for r in rows)
    hbp = sum(r.hit_by_pitch for r in rows)
    hits = sum(r.hits for r in rows)
    doubles = sum(r.doubles for r in rows)
    triples = sum(r.triples for r in rows)
    home_runs = sum(r.home_runs for r in rows)
    ab = sum(r.at_bats for r in rows)
    sac_flies = sum(r.sac_flies for r in rows)
    singles = hits - doubles - triples - home_runs
    denom = ab + walks + hbp + sac_flies
    return _safe_rate(
        0.69 * walks + 0.72 * hbp + 0.89 * singles
        + 1.27 * doubles + 1.62 * triples + 2.10 * home_runs,
        denom,
    )


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

    # Fetch batting aggregates for K% matchup edge and ISO power signal
    home_batting = _batting_stats_for_team(db, team_id=home_id, as_of=as_of)
    away_batting = _batting_stats_for_team(db, team_id=away_id, as_of=as_of)

    # Fetch actual odds if available
    from app.models.odds import OddsSnapshotRow
    from sqlalchemy import desc as _desc
    def _get_ml_odds(side: str) -> Optional[int]:
        row = db.execute(
            select(OddsSnapshotRow).where(
                OddsSnapshotRow.game_id == game_id,
                OddsSnapshotRow.market == "moneyline",
                OddsSnapshotRow.selection == side,
            ).order_by(_desc(OddsSnapshotRow.captured_at)).limit(1)
        ).scalar_one_or_none()
        return row.american_odds if row else None

    def _get_total_line() -> Optional[float]:
        row = db.execute(
            select(OddsSnapshotRow).where(
                OddsSnapshotRow.game_id == game_id,
                OddsSnapshotRow.market == "total",
                OddsSnapshotRow.selection == "over",
            ).order_by(_desc(OddsSnapshotRow.captured_at)).limit(1)
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
    )


@app.get("/games/{game_id}/analyze")
def game_analyze(
    game_id: int,
    as_of: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """Run the full deterministic model for a single game."""
    analysis = _build_analysis(game_id, as_of, db)
    if analysis is None:
        raise HTTPException(404, f"Game {game_id} not found")
    return _dc(analysis)


@app.get("/games/picks")
def daily_picks(
    game_date: date = Query(..., description="YYYY-MM-DD"),
    db: Session = Depends(_get_db),
):
    """Run the analyzer across all games on a date and return picks ranked by edge."""
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
        analysis = _build_analysis(game.id, game_date, db)
        if analysis is not None:
            d = _dc(analysis)
            d["game_date"] = game.game_date.isoformat()
            d["venue"] = game.venue
            results.append(d)

    # Sort: STRONG LEAN first, then LEAN, then PASS, then AVOID
    tier_order = {"STRONG LEAN": 0, "LEAN": 1, "PASS": 2, "AVOID": 3}
    results.sort(key=lambda r: (tier_order.get(r.get("ml_tier", "PASS"), 2), -r.get("ml_confidence", 0)))
    return results


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
