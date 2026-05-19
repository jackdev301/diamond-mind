"""Shared game-analysis data loader (Track B).

This module contains the data-loading logic that turns a `Game` row plus all
its dependent feature windows (starters, bullpens, team form, odds, weather)
into a `GameAnalysis` dataclass via `app.betting.game_analyzer.analyze_game`.

It was extracted verbatim from `app.api.routes._build_analysis` so that both
the FastAPI routes layer and the offline backtest engine
(`app.betting.backtest`) can call it without a circular import:

    routes.py  ─┐
                 ├─► analysis_builder.build_game_analysis ─► analyze_game
    backtest.py ─┘

`routes._build_analysis` now delegates here. Behavior is byte-identical to the
pre-refactor implementation: every model input is still computed
`as_of=as_of` exactly as before, so there is no look-ahead bias and every
existing endpoint returns the same result.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.contracts import PitcherFormWindow, TrendLabel, WindowKey
from app.features.recent_form import (
    build_bullpen_state,
    build_starter_form_window,
    build_team_form_window,
    load_team_form_window,
)
from app.features.bullpen_vulnerability import score_bullpen
from app.models.entities import Player, Team
from app.models.games import Game, PitcherGameLog, PlayerGameLog, TeamGameLog


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
        raise ValueError(f"Unsupported team window: {window.value}")
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
        raise ValueError(f"Unsupported pitcher window: {window.value}")
    return list(
        db.execute(stmt.order_by(PitcherGameLog.game_date.desc()).limit(limit)).scalars()
    )


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


def _starter_form_or_announced(
    db: Session,
    *,
    pitcher_id: Optional[int],
    window: WindowKey,
    as_of: date,
) -> Optional[PitcherFormWindow]:
    """Return starter form, or a name-only small-sample record for announced SPs."""
    if pitcher_id is None:
        return None
    window_data = build_starter_form_window(
        db,
        pitcher_id=pitcher_id,
        window=window,
        as_of_date=as_of,
    )
    if window_data is not None:
        return window_data

    pitcher = db.get(Player, pitcher_id)
    return PitcherFormWindow(
        pitcher_id=pitcher_id,
        pitcher_name=pitcher.full_name if pitcher is not None else f"Announced starter #{pitcher_id}",
        team_id=(pitcher.current_team_id if pitcher is not None else None) or 0,
        window=window,
        starts=0,
        innings_pitched=0.0,
        era=None,
        whip=None,
        k_per_9=None,
        bb_per_9=None,
        hr_per_9=None,
        avg_innings_per_start=None,
        trend_label=TrendLabel.SMALL_SAMPLE_WARN,
        as_of_date=as_of,
        insufficient_sample=True,
    )


def build_game_analysis(game_id: int, as_of: date, db: Session):
    """Load all data for a game and return a GameAnalysis dataclass (or None).

    Every feature lookup is computed `as_of=as_of`. This is the single source
    of truth for game analysis data loading — `routes._build_analysis`
    delegates here, and `app.betting.backtest.run_backtest` calls it directly
    with `as_of=game.game_date` to replay the model without look-ahead bias.
    """
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
        return _starter_form_or_announced(
            db,
            pitcher_id=pitcher_id,
            window=WindowKey.LAST_5_STARTS,
            as_of=as_of,
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
