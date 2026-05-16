"""Recent-form engine.

Computes Season / L20 / L10 / L5 windows for teams and hitters, and the
starter-specific (L10/L5 starts) and reliever-specific (L20/L10/L5
appearances) variants. Assigns a `TrendLabel` per window by comparing
the window's primary metric to the entity's season baseline.

Design:
- Pure stat aggregators (`aggregate_hitter`, `aggregate_pitcher`,
  `aggregate_team`) take raw counters and return rate-stat dicts. No I/O.
- `classify_trend` is a pure function over (window_metric, season_metric,
  sample_size). No state.
- DB-backed builders (`build_*_form_window`) compose the raw counters via
  SQL, call the pure helpers, and return a frozen contract dataclass.
- Loaders (`load_*_form_window`) read previously persisted rows. Track B
  uses these.

The dataclass shapes returned here are exactly the contracts in
`app.contracts` — that's the seam with Track B.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Integer, and_, func, select
from sqlalchemy.orm import Session

from app.contracts import (
    BullpenState,
    PitcherFormWindow,
    PlayerFormWindow,
    RelieverFormWindow,
    RelieverRole,
    RelieverUsage,
    TeamFormWindow,
    TrendLabel,
    WindowKey,
)
from app.models.entities import Player, Team
from app.models.games import PitcherGameLog, PlayerGameLog, TeamGameLog
from app.models.players import (
    PitcherFormWindowRow,
    PlayerFormWindowRow,
    RelieverFormWindowRow,
    TeamFormWindowRow,
)


# --- Tuning constants -------------------------------------------------------

# A window is "moving" vs season baseline if the relative delta exceeds this.
HEATING_DELTA = 0.10
# Above this, the deviation is extreme enough that mean reversion is the prior.
REGRESSION_DELTA = 0.30

# Minimum sample sizes before we trust a window (else label as SMALL_SAMPLE_WARN).
MIN_SAMPLE = {
    WindowKey.L5: 3,
    WindowKey.L10: 6,
    WindowKey.L20: 12,
    WindowKey.LAST_5_STARTS: 3,
    WindowKey.LAST_10_STARTS: 6,
    WindowKey.SEASON: 1,
}

# Default weights for combining windows into a single estimate.
# See PROJECT_BRIEF.md "MVP weighting".
DEFAULT_WINDOW_WEIGHTS = {
    WindowKey.SEASON: 0.50,
    WindowKey.L20: 0.25,
    WindowKey.L10: 0.15,
    WindowKey.L5: 0.10,
}

# "Strong" baselines used to distinguish Stable Strong vs Stable Weak.
TEAM_STRONG_RUNS_PER_GAME = 4.7
HITTER_STRONG_OPS = 0.740
PITCHER_STRONG_ERA = 3.80  # lower is better
FIP_CONSTANT = 3.10


# --- Pure: trend classifier -------------------------------------------------

def classify_trend(
    *,
    window_metric: float,
    season_metric: float,
    sample_size: int,
    min_sample: int,
    higher_is_better: bool = True,
    strong_threshold: Optional[float] = None,
) -> TrendLabel:
    """Compare a window's primary metric to its season baseline.

    `higher_is_better=True` is for offense (OPS, runs/game). For ERA/WHIP
    set `higher_is_better=False` so a *lower* window value is "heating up".
    """
    if sample_size < min_sample:
        return TrendLabel.SMALL_SAMPLE_WARN
    if season_metric == 0:
        return TrendLabel.SMALL_SAMPLE_WARN

    delta = (window_metric - season_metric) / abs(season_metric)
    if not higher_is_better:
        delta = -delta

    if abs(delta) >= REGRESSION_DELTA:
        return TrendLabel.REGRESSION_RISK
    if delta >= HEATING_DELTA:
        return TrendLabel.HEATING_UP
    if delta <= -HEATING_DELTA:
        return TrendLabel.COOLING_OFF

    # Stable — pick strong vs weak based on absolute baseline.
    if strong_threshold is None:
        return TrendLabel.STABLE_STRONG
    season_is_strong = (
        season_metric >= strong_threshold
        if higher_is_better
        else season_metric <= strong_threshold
    )
    return TrendLabel.STABLE_STRONG if season_is_strong else TrendLabel.STABLE_WEAK


# --- Pure: stat aggregators -------------------------------------------------

def _safe_div(num: float, den: float) -> float:
    return num / den if den else 0.0


def aggregate_hitter(
    *,
    games: int,
    plate_appearances: int,
    at_bats: int,
    hits: int,
    doubles: int,
    triples: int,
    home_runs: int,
    walks: int,
    hit_by_pitch: int,
    sac_flies: int,
    strikeouts: int,
) -> dict[str, float]:
    """Compute rate stats from a hitter's summed counters."""
    singles = max(hits - doubles - triples - home_runs, 0)
    total_bases = singles + 2 * doubles + 3 * triples + 4 * home_runs
    obp_den = at_bats + walks + hit_by_pitch + sac_flies
    avg = _safe_div(hits, at_bats)
    obp = _safe_div(hits + walks + hit_by_pitch, obp_den)
    slg = _safe_div(total_bases, at_bats)
    ops = obp + slg
    return {
        "games": games,
        "plate_appearances": plate_appearances,
        "batting_avg": round(avg, 3),
        "on_base_pct": round(obp, 3),
        "slugging_pct": round(slg, 3),
        "ops": round(ops, 3),
        "home_runs": home_runs,
        "strikeouts": strikeouts,
        "walks": walks,
    }


def aggregate_pitcher(
    *,
    innings_pitched: float,
    batters_faced: int,
    hits_allowed: int,
    earned_runs: int,
    walks: int,
    strikeouts: int,
    home_runs_allowed: int,
    pitches: int,
    outings: int,
) -> dict[str, float]:
    """Common pitching rate stats. `outings` = starts or appearances."""
    era = _safe_div(9 * earned_runs, innings_pitched)
    whip = _safe_div(walks + hits_allowed, innings_pitched)
    k9 = _safe_div(9 * strikeouts, innings_pitched)
    bb9 = _safe_div(9 * walks, innings_pitched)
    hr9 = _safe_div(9 * home_runs_allowed, innings_pitched)
    fip = (
        ((13 * home_runs_allowed + 3 * walks - 2 * strikeouts) / innings_pitched)
        + FIP_CONSTANT
        if innings_pitched
        else 0.0
    )
    balls_in_play = batters_faced - strikeouts - walks - home_runs_allowed
    babip = _safe_div(hits_allowed - home_runs_allowed, balls_in_play)
    return {
        "innings_pitched": round(innings_pitched, 1),
        "era": round(era, 2),
        "fip": round(fip, 2),
        "babip": round(babip, 3) if balls_in_play > 0 else None,
        "whip": round(whip, 2),
        "k_per_9": round(k9, 1),
        "bb_per_9": round(bb9, 1),
        "hr_per_9": round(hr9, 1),
        "avg_innings_per_start": round(_safe_div(innings_pitched, outings), 2),
        "avg_pitches_per_start": round(_safe_div(pitches, outings), 1) if pitches else None,
    }


def aggregate_team(
    *,
    games: int,
    runs: int,
    runs_allowed: int,
    wins: int,
    losses: int,
    team_ops: float = 0.0,
) -> dict[str, float]:
    return {
        "games": games,
        "runs_per_game": round(_safe_div(runs, games), 2),
        "runs_allowed_per_game": round(_safe_div(runs_allowed, games), 2),
        "team_ops": round(team_ops, 3),
        "record_wins": wins,
        "record_losses": losses,
    }


def _estimated_woba_from_counts(
    *,
    at_bats: int,
    hits: int,
    doubles: int,
    triples: int,
    home_runs: int,
    walks: int,
    hit_by_pitch: int,
    sac_flies: int,
) -> Optional[float]:
    singles = max(hits - doubles - triples - home_runs, 0)
    denom = at_bats + walks + hit_by_pitch + sac_flies
    if denom == 0:
        return None
    return (
        0.69 * walks
        + 0.72 * hit_by_pitch
        + 0.89 * singles
        + 1.27 * doubles
        + 1.62 * triples
        + 2.10 * home_runs
    ) / denom


# --- Pure: weighted form metric --------------------------------------------

def weighted_form_metric(
    metrics_by_window: dict[WindowKey, float],
    weights: dict[WindowKey, float] | None = None,
) -> float:
    """Combine per-window metrics into a single estimate via the
    Season/L20/L10/L5 weighting from PROJECT_BRIEF.md. Windows missing
    from `metrics_by_window` have their weight redistributed proportionally
    across the windows that ARE present.
    """
    weights = weights or DEFAULT_WINDOW_WEIGHTS
    available = {w: weights[w] for w in metrics_by_window if w in weights}
    total_weight = sum(available.values())
    if total_weight == 0:
        return 0.0
    return sum(metrics_by_window[w] * (available[w] / total_weight) for w in available)


# --- DB-backed builders -----------------------------------------------------

# Map non-season windows to (lookback game count) for team/hitter/reliever.
# Starters use a separate "last N starts" rule, applied after the query.
GAME_WINDOWS = {
    WindowKey.L5: 5,
    WindowKey.L10: 10,
    WindowKey.L20: 20,
}


def _window_date_range(
    session: Session,
    *,
    entity_filter,
    log_model,
    window: WindowKey,
    as_of_date: date,
) -> tuple[Optional[date], Optional[date]]:
    """Determine the inclusive (start, end) game-date range for a window.

    SEASON → (Jan 1 of as_of_date.year, as_of_date)
    L5/L10/L20 → the dates of the last N games <= as_of_date.
    Returns (None, None) if the entity has no games in range.
    """
    if window is WindowKey.SEASON:
        return date(as_of_date.year, 1, 1), as_of_date

    if window in GAME_WINDOWS:
        n = GAME_WINDOWS[window]
        stmt = (
            select(log_model.game_date)
            .where(entity_filter, log_model.game_date <= as_of_date)
            .order_by(log_model.game_date.desc())
            .limit(n)
        )
        dates = [d for (d,) in session.execute(stmt).all()]
        if not dates:
            return None, None
        return min(dates), max(dates)

    raise ValueError(f"Unsupported window for game-date range: {window}")


def build_team_form_window(
    session: Session,
    *,
    team_id: int,
    window: WindowKey,
    as_of_date: date,
) -> Optional[TeamFormWindow]:
    """Compute a team form window from team_game_logs. Returns None if
    the team has no logs in scope."""
    team = session.get(Team, team_id)
    if team is None:
        return None

    start, end = _window_date_range(
        session,
        entity_filter=TeamGameLog.team_id == team_id,
        log_model=TeamGameLog,
        window=window,
        as_of_date=as_of_date,
    )
    if start is None:
        return None

    stmt = select(
        func.count(TeamGameLog.id),
        func.coalesce(func.sum(TeamGameLog.runs), 0),
        func.coalesce(func.sum(TeamGameLog.runs_allowed), 0),
        func.coalesce(func.sum(func.cast(TeamGameLog.won, Integer)), 0),
    ).where(
        and_(
            TeamGameLog.team_id == team_id,
            TeamGameLog.game_date >= start,
            TeamGameLog.game_date <= end,
        )
    )
    games, runs, runs_allowed, wins = session.execute(stmt).one()
    losses = games - wins

    agg = aggregate_team(
        games=games, runs=runs, runs_allowed=runs_allowed, wins=wins, losses=losses
    )
    batting_rows = session.execute(
        select(PlayerGameLog).where(
            PlayerGameLog.team_id == team_id,
            PlayerGameLog.game_date >= start,
            PlayerGameLog.game_date <= end,
        )
    ).scalars().all()
    stolen_bases = sum(r.stolen_bases for r in batting_rows)
    caught_stealing = sum(r.caught_stealing for r in batting_rows)
    stolen_base_attempts = stolen_bases + caught_stealing
    stolen_base_success_rate = (
        round(_safe_div(stolen_bases, stolen_base_attempts), 3)
        if stolen_base_attempts
        else None
    )

    player_counts: dict[int, dict[str, int]] = {}
    for row in batting_rows:
        counts = player_counts.setdefault(
            row.player_id,
            dict(
                pa=0, ab=0, h=0, doubles=0, triples=0, hr=0,
                walks=0, hbp=0, sf=0,
            ),
        )
        counts["pa"] += row.plate_appearances
        counts["ab"] += row.at_bats
        counts["h"] += row.hits
        counts["doubles"] += row.doubles
        counts["triples"] += row.triples
        counts["hr"] += row.home_runs
        counts["walks"] += row.walks
        counts["hbp"] += row.hit_by_pitch
        counts["sf"] += row.sac_flies
    top_six = sorted(player_counts.values(), key=lambda c: c["pa"], reverse=True)[:6]
    top_wobas = [
        w
        for c in top_six
        if (w := _estimated_woba_from_counts(
            at_bats=c["ab"],
            hits=c["h"],
            doubles=c["doubles"],
            triples=c["triples"],
            home_runs=c["hr"],
            walks=c["walks"],
            hit_by_pitch=c["hbp"],
            sac_flies=c["sf"],
        )) is not None
    ]
    lineup_quality_score = (
        round(sum(top_wobas) / len(top_wobas), 3)
        if top_wobas
        else None
    )

    # Season baseline for trend comparison
    season_metric = agg["runs_per_game"]
    if window is not WindowKey.SEASON:
        season = build_team_form_window(
            session, team_id=team_id, window=WindowKey.SEASON, as_of_date=as_of_date
        )
        season_metric = season.runs_per_game if season else season_metric

    trend = classify_trend(
        window_metric=agg["runs_per_game"],
        season_metric=season_metric,
        sample_size=games,
        min_sample=MIN_SAMPLE[window],
        higher_is_better=True,
        strong_threshold=TEAM_STRONG_RUNS_PER_GAME,
    )

    return TeamFormWindow(
        team_id=team_id,
        team_abbr=team.abbr,
        window=window,
        games=games,
        runs_per_game=agg["runs_per_game"],
        runs_allowed_per_game=agg["runs_allowed_per_game"],
        team_ops=agg["team_ops"],
        record_wins=wins,
        record_losses=losses,
        trend_label=trend,
        as_of_date=as_of_date,
        team_woba=None,
        stolen_bases=stolen_bases,
        caught_stealing=caught_stealing,
        stolen_base_attempts=stolen_base_attempts,
        stolen_base_success_rate=stolen_base_success_rate,
        lineup_quality_score=lineup_quality_score,
        insufficient_sample=games < MIN_SAMPLE[window],
    )


def build_hitter_form_window(
    session: Session,
    *,
    player_id: int,
    window: WindowKey,
    as_of_date: date,
) -> Optional[PlayerFormWindow]:
    player = session.get(Player, player_id)
    if player is None:
        return None

    start, end = _window_date_range(
        session,
        entity_filter=PlayerGameLog.player_id == player_id,
        log_model=PlayerGameLog,
        window=window,
        as_of_date=as_of_date,
    )
    if start is None:
        return None

    stmt = select(
        func.count(PlayerGameLog.id),
        func.coalesce(func.sum(PlayerGameLog.plate_appearances), 0),
        func.coalesce(func.sum(PlayerGameLog.at_bats), 0),
        func.coalesce(func.sum(PlayerGameLog.hits), 0),
        func.coalesce(func.sum(PlayerGameLog.doubles), 0),
        func.coalesce(func.sum(PlayerGameLog.triples), 0),
        func.coalesce(func.sum(PlayerGameLog.home_runs), 0),
        func.coalesce(func.sum(PlayerGameLog.walks), 0),
        func.coalesce(func.sum(PlayerGameLog.hit_by_pitch), 0),
        func.coalesce(func.sum(PlayerGameLog.sac_flies), 0),
        func.coalesce(func.sum(PlayerGameLog.strikeouts), 0),
    ).where(
        and_(
            PlayerGameLog.player_id == player_id,
            PlayerGameLog.game_date >= start,
            PlayerGameLog.game_date <= end,
        )
    )
    games, pa, ab, h, d, t, hr, bb, hbp, sf, so = session.execute(stmt).one()

    agg = aggregate_hitter(
        games=games, plate_appearances=pa, at_bats=ab, hits=h,
        doubles=d, triples=t, home_runs=hr, walks=bb,
        hit_by_pitch=hbp, sac_flies=sf, strikeouts=so,
    )

    season_metric = agg["ops"]
    if window is not WindowKey.SEASON:
        season = build_hitter_form_window(
            session, player_id=player_id, window=WindowKey.SEASON, as_of_date=as_of_date
        )
        if season:
            season_metric = season.ops

    trend = classify_trend(
        window_metric=agg["ops"],
        season_metric=season_metric,
        sample_size=games,
        min_sample=MIN_SAMPLE[window],
        higher_is_better=True,
        strong_threshold=HITTER_STRONG_OPS,
    )

    team_id = (
        session.execute(
            select(PlayerGameLog.team_id)
            .where(PlayerGameLog.player_id == player_id)
            .order_by(PlayerGameLog.game_date.desc())
            .limit(1)
        ).scalar() or player.current_team_id or 0
    )

    return PlayerFormWindow(
        player_id=player_id,
        player_name=player.full_name,
        team_id=team_id,
        window=window,
        games=games,
        plate_appearances=pa,
        batting_avg=agg["batting_avg"],
        on_base_pct=agg["on_base_pct"],
        slugging_pct=agg["slugging_pct"],
        ops=agg["ops"],
        home_runs=hr,
        strikeouts=so,
        walks=bb,
        trend_label=trend,
        as_of_date=as_of_date,
        woba=None,
        insufficient_sample=games < MIN_SAMPLE[window],
    )


def _last_n_starter_dates(
    session: Session, pitcher_id: int, n: int, as_of_date: date
) -> list[date]:
    stmt = (
        select(PitcherGameLog.game_date)
        .where(
            PitcherGameLog.pitcher_id == pitcher_id,
            PitcherGameLog.started.is_(True),
            PitcherGameLog.game_date <= as_of_date,
        )
        .order_by(PitcherGameLog.game_date.desc())
        .limit(n)
    )
    return [d for (d,) in session.execute(stmt).all()]


def build_starter_form_window(
    session: Session,
    *,
    pitcher_id: int,
    window: WindowKey,
    as_of_date: date,
) -> Optional[PitcherFormWindow]:
    pitcher = session.get(Player, pitcher_id)
    if pitcher is None:
        return None

    if window is WindowKey.SEASON:
        start = date(as_of_date.year, 1, 1)
        end = as_of_date
    elif window in (WindowKey.LAST_10_STARTS, WindowKey.LAST_5_STARTS):
        n = 10 if window is WindowKey.LAST_10_STARTS else 5
        dates = _last_n_starter_dates(session, pitcher_id, n, as_of_date)
        if not dates:
            return None
        start, end = min(dates), max(dates)
    else:
        raise ValueError(f"build_starter_form_window: unsupported window {window}")

    stmt = select(
        func.count(PitcherGameLog.id),
        func.coalesce(func.sum(PitcherGameLog.innings_pitched), 0.0),
        func.coalesce(func.sum(PitcherGameLog.hits_allowed), 0),
        func.coalesce(func.sum(PitcherGameLog.earned_runs), 0),
        func.coalesce(func.sum(PitcherGameLog.walks), 0),
        func.coalesce(func.sum(PitcherGameLog.strikeouts), 0),
        func.coalesce(func.sum(PitcherGameLog.home_runs_allowed), 0),
        func.coalesce(func.sum(PitcherGameLog.pitches), 0),
        func.coalesce(func.sum(PitcherGameLog.batters_faced), 0),
    ).where(
        and_(
            PitcherGameLog.pitcher_id == pitcher_id,
            PitcherGameLog.started.is_(True),
            PitcherGameLog.game_date >= start,
            PitcherGameLog.game_date <= end,
        )
    )
    starts, ip, h, er, bb, k, hr, pitches, bf = session.execute(stmt).one()

    agg = aggregate_pitcher(
        innings_pitched=float(ip), batters_faced=bf, hits_allowed=h, earned_runs=er,
        walks=bb, strikeouts=k, home_runs_allowed=hr,
        pitches=pitches, outings=starts,
    )

    season_metric = agg["era"]
    if window is not WindowKey.SEASON:
        season = build_starter_form_window(
            session, pitcher_id=pitcher_id, window=WindowKey.SEASON, as_of_date=as_of_date
        )
        if season:
            season_metric = season.era

    trend = classify_trend(
        window_metric=agg["era"],
        season_metric=season_metric,
        sample_size=starts,
        min_sample=MIN_SAMPLE[window],
        higher_is_better=False,
        strong_threshold=PITCHER_STRONG_ERA,
    )

    team_id = (
        session.execute(
            select(PitcherGameLog.team_id)
            .where(PitcherGameLog.pitcher_id == pitcher_id)
            .order_by(PitcherGameLog.game_date.desc())
            .limit(1)
        ).scalar() or pitcher.current_team_id or 0
    )

    return PitcherFormWindow(
        pitcher_id=pitcher_id,
        pitcher_name=pitcher.full_name,
        team_id=team_id,
        window=window,
        starts=starts,
        innings_pitched=agg["innings_pitched"],
        era=agg["era"],
        fip=agg["fip"],
        babip=agg["babip"],
        whip=agg["whip"],
        k_per_9=agg["k_per_9"],
        bb_per_9=agg["bb_per_9"],
        hr_per_9=agg["hr_per_9"],
        avg_innings_per_start=agg["avg_innings_per_start"],
        trend_label=trend,
        as_of_date=as_of_date,
        avg_pitches_per_start=agg["avg_pitches_per_start"],
        insufficient_sample=starts < MIN_SAMPLE[window],
    )


def build_reliever_form_window(
    session: Session,
    *,
    pitcher_id: int,
    role: RelieverRole,
    window: WindowKey,
    as_of_date: date,
) -> Optional[RelieverFormWindow]:
    pitcher = session.get(Player, pitcher_id)
    if pitcher is None:
        return None

    start, end = _window_date_range(
        session,
        entity_filter=and_(
            PitcherGameLog.pitcher_id == pitcher_id,
            PitcherGameLog.started.is_(False),
        ),
        log_model=PitcherGameLog,
        window=window,
        as_of_date=as_of_date,
    )
    if start is None:
        return None

    stmt = select(
        func.count(PitcherGameLog.id),
        func.coalesce(func.sum(PitcherGameLog.innings_pitched), 0.0),
        func.coalesce(func.sum(PitcherGameLog.hits_allowed), 0),
        func.coalesce(func.sum(PitcherGameLog.earned_runs), 0),
        func.coalesce(func.sum(PitcherGameLog.walks), 0),
        func.coalesce(func.sum(PitcherGameLog.strikeouts), 0),
        func.coalesce(func.sum(PitcherGameLog.home_runs_allowed), 0),
    ).where(
        and_(
            PitcherGameLog.pitcher_id == pitcher_id,
            PitcherGameLog.started.is_(False),
            PitcherGameLog.game_date >= start,
            PitcherGameLog.game_date <= end,
        )
    )
    apps, ip, h, er, bb, k, hr = session.execute(stmt).one()

    agg = aggregate_pitcher(
        innings_pitched=float(ip), batters_faced=0, hits_allowed=h, earned_runs=er,
        walks=bb, strikeouts=k, home_runs_allowed=hr,
        pitches=0, outings=apps,
    )

    season_metric = agg["era"]
    if window is not WindowKey.SEASON:
        season = build_reliever_form_window(
            session, pitcher_id=pitcher_id, role=role,
            window=WindowKey.SEASON, as_of_date=as_of_date,
        )
        if season:
            season_metric = season.era

    trend = classify_trend(
        window_metric=agg["era"],
        season_metric=season_metric,
        sample_size=apps,
        min_sample=MIN_SAMPLE[window],
        higher_is_better=False,
        strong_threshold=PITCHER_STRONG_ERA,
    )

    team_id = (
        session.execute(
            select(PitcherGameLog.team_id)
            .where(PitcherGameLog.pitcher_id == pitcher_id)
            .order_by(PitcherGameLog.game_date.desc())
            .limit(1)
        ).scalar() or pitcher.current_team_id or 0
    )

    return RelieverFormWindow(
        pitcher_id=pitcher_id,
        pitcher_name=pitcher.full_name,
        team_id=team_id,
        role=role,
        window=window,
        appearances=apps,
        innings_pitched=agg["innings_pitched"],
        era=agg["era"],
        fip=agg["fip"],
        whip=agg["whip"],
        k_per_9=agg["k_per_9"],
        bb_per_9=agg["bb_per_9"],
        trend_label=trend,
        as_of_date=as_of_date,
        insufficient_sample=apps < MIN_SAMPLE[window],
    )


def build_bullpen_state(
    session: Session,
    *,
    team_id: int,
    as_of_date: date,
) -> Optional[BullpenState]:
    """Build a BullpenState from PitcherGameLog rows for the 5 days prior to as_of_date.

    back_to_back_relievers and three_in_four_relievers are List[int] pitcher_ids
    so the fatigue scorer can consume them directly without name lookups.
    """
    from datetime import timedelta

    team = session.get(Team, team_id)
    if team is None:
        return None

    yesterday = as_of_date - timedelta(days=1)
    four_days_ago = as_of_date - timedelta(days=4)
    five_days_ago = as_of_date - timedelta(days=5)

    # All reliever appearances in the last 5 days, newest first.
    stmt = (
        select(PitcherGameLog, Player)
        .join(Player, PitcherGameLog.pitcher_id == Player.id)
        .where(
            and_(
                PitcherGameLog.team_id == team_id,
                PitcherGameLog.started.is_(False),
                PitcherGameLog.game_date >= five_days_ago,
                PitcherGameLog.game_date < as_of_date,
            )
        )
        .order_by(PitcherGameLog.game_date.desc())
    )
    rows = session.execute(stmt).all()

    # Group appearances by date and by pitcher.
    by_date: dict[date, list[PitcherGameLog]] = {}
    by_pitcher: dict[int, list[date]] = {}
    pitcher_names: dict[int, str] = {}
    pitcher_roles: dict[int, str] = {}

    for log, player in rows:
        by_date.setdefault(log.game_date, []).append(log)
        by_pitcher.setdefault(log.pitcher_id, []).append(log.game_date)
        pitcher_names[log.pitcher_id] = player.full_name
        # Prefer the most specific role stored on the log; default to "middle".
        if log.pitcher_id not in pitcher_roles or log.game_date == yesterday:
            pitcher_roles[log.pitcher_id] = log.role if log.role not in ("starter", "reliever") else "middle"

    yesterday_logs = by_date.get(yesterday, [])

    # Yesterday totals.
    yesterday_total_innings = sum(lg.innings_pitched for lg in yesterday_logs)
    yesterday_total_pitches = sum(lg.pitches for lg in yesterday_logs)
    yesterday_relievers_used = len({lg.pitcher_id for lg in yesterday_logs})

    # closer / high-leverage yesterday (by pitcher_id).
    closer_ids = {
        lg.pitcher_id for lg in yesterday_logs
        if pitcher_roles.get(lg.pitcher_id) == "closer"
    }
    closer_pitched_yesterday = bool(closer_ids)

    high_leverage_pitched_yesterday = [
        lg.pitcher_id for lg in yesterday_logs
        if pitcher_roles.get(lg.pitcher_id) in ("closer", "high_leverage")
    ]

    # back-to-back: appeared yesterday AND day before.
    two_days_ago = as_of_date - timedelta(days=2)
    appeared_yesterday = {lg.pitcher_id for lg in yesterday_logs}
    appeared_day_before = {lg.pitcher_id for lg in by_date.get(two_days_ago, [])}
    back_to_back_relievers = sorted(appeared_yesterday & appeared_day_before)

    # three_in_four: appeared on 3+ of the 4 days ending yesterday.
    three_in_four_relievers = []
    for pid, dates in by_pitcher.items():
        recent_four = {d for d in dates if four_days_ago <= d <= yesterday}
        if len(recent_four) >= 3:
            three_in_four_relievers.append(pid)
    three_in_four_relievers.sort()

    # recent_usage: one RelieverUsage per (pitcher, game_date), newest first.
    recent_usage = [
        RelieverUsage(
            pitcher_id=log.pitcher_id,
            pitcher_name=pitcher_names.get(log.pitcher_id, ""),
            team_id=team_id,
            role=pitcher_roles.get(log.pitcher_id, "middle"),
            game_date=log.game_date,
            pitches=log.pitches,
            innings=log.innings_pitched,
            appeared=True,
        )
        for log, _ in sorted(rows, key=lambda r: r[0].game_date, reverse=True)
    ]

    # Build RelieverFormWindow for each reliever who appeared in the window.
    reliever_windows: list[RelieverFormWindow] = []
    for pid in by_pitcher:
        role: RelieverRole = pitcher_roles.get(pid, "middle")  # type: ignore[assignment]
        w = build_reliever_form_window(
            session, pitcher_id=pid, role=role,
            window=WindowKey.L20, as_of_date=as_of_date,
        )
        if w is not None:
            reliever_windows.append(w)

    return BullpenState(
        team_id=team_id,
        team_abbr=team.abbr,
        as_of_date=as_of_date,
        yesterday_total_innings=round(yesterday_total_innings, 1),
        yesterday_total_pitches=yesterday_total_pitches,
        yesterday_relievers_used=yesterday_relievers_used,
        closer_pitched_yesterday=closer_pitched_yesterday,
        high_leverage_pitched_yesterday=high_leverage_pitched_yesterday,
        back_to_back_relievers=back_to_back_relievers,
        three_in_four_relievers=three_in_four_relievers,
        relievers=reliever_windows,
        recent_usage=recent_usage,
    )


# --- Persistence ------------------------------------------------------------

def upsert_team_form_window(session: Session, w: TeamFormWindow) -> None:
    existing = session.scalar(
        select(TeamFormWindowRow).where(
            TeamFormWindowRow.team_id == w.team_id,
            TeamFormWindowRow.window == w.window.value,
            TeamFormWindowRow.as_of_date == w.as_of_date,
        )
    )
    fields = dict(
        games=w.games,
        runs_per_game=w.runs_per_game,
        runs_allowed_per_game=w.runs_allowed_per_game,
        team_ops=w.team_ops,
        team_woba=w.team_woba,
        stolen_bases=w.stolen_bases,
        caught_stealing=w.caught_stealing,
        stolen_base_attempts=w.stolen_base_attempts,
        stolen_base_success_rate=w.stolen_base_success_rate,
        lineup_quality_score=w.lineup_quality_score,
        record_wins=w.record_wins,
        record_losses=w.record_losses,
        trend_label=w.trend_label.value,
        insufficient_sample=w.insufficient_sample,
    )
    if existing is None:
        session.add(TeamFormWindowRow(
            team_id=w.team_id, window=w.window.value, as_of_date=w.as_of_date, **fields
        ))
    else:
        for k, v in fields.items():
            setattr(existing, k, v)


def upsert_hitter_form_window(session: Session, w: PlayerFormWindow) -> None:
    existing = session.scalar(
        select(PlayerFormWindowRow).where(
            PlayerFormWindowRow.player_id == w.player_id,
            PlayerFormWindowRow.window == w.window.value,
            PlayerFormWindowRow.as_of_date == w.as_of_date,
        )
    )
    fields = dict(
        games=w.games, plate_appearances=w.plate_appearances,
        batting_avg=w.batting_avg, on_base_pct=w.on_base_pct,
        slugging_pct=w.slugging_pct, ops=w.ops, woba=w.woba,
        home_runs=w.home_runs, strikeouts=w.strikeouts, walks=w.walks,
        trend_label=w.trend_label.value, insufficient_sample=w.insufficient_sample,
    )
    if existing is None:
        session.add(PlayerFormWindowRow(
            player_id=w.player_id, window=w.window.value, as_of_date=w.as_of_date, **fields
        ))
    else:
        for k, v in fields.items():
            setattr(existing, k, v)


# --- Loaders (Track B uses these) -------------------------------------------

def load_team_form_window(
    session: Session, *, team_id: int, window: WindowKey, as_of_date: date
) -> Optional[TeamFormWindow]:
    row = session.scalar(
        select(TeamFormWindowRow).where(
            TeamFormWindowRow.team_id == team_id,
            TeamFormWindowRow.window == window.value,
            TeamFormWindowRow.as_of_date == as_of_date,
        )
    )
    if row is None:
        return None
    team = session.get(Team, team_id)
    return TeamFormWindow(
        team_id=team_id,
        team_abbr=team.abbr if team else "",
        window=window,
        games=row.games,
        runs_per_game=row.runs_per_game,
        runs_allowed_per_game=row.runs_allowed_per_game,
        team_ops=row.team_ops,
        record_wins=row.record_wins,
        record_losses=row.record_losses,
        trend_label=TrendLabel(row.trend_label),
        as_of_date=row.as_of_date,
        team_woba=row.team_woba,
        stolen_bases=row.stolen_bases,
        caught_stealing=row.caught_stealing,
        stolen_base_attempts=row.stolen_base_attempts,
        stolen_base_success_rate=row.stolen_base_success_rate,
        lineup_quality_score=row.lineup_quality_score,
        insufficient_sample=row.insufficient_sample,
    )


def load_hitter_form_window(
    session: Session, *, player_id: int, window: WindowKey, as_of_date: date
) -> Optional[PlayerFormWindow]:
    row = session.scalar(
        select(PlayerFormWindowRow).where(
            PlayerFormWindowRow.player_id == player_id,
            PlayerFormWindowRow.window == window.value,
            PlayerFormWindowRow.as_of_date == as_of_date,
        )
    )
    if row is None:
        return None
    player = session.get(Player, player_id)
    return PlayerFormWindow(
        player_id=player_id,
        player_name=player.full_name if player else "",
        team_id=player.current_team_id if player and player.current_team_id else 0,
        window=window,
        games=row.games,
        plate_appearances=row.plate_appearances,
        batting_avg=row.batting_avg,
        on_base_pct=row.on_base_pct,
        slugging_pct=row.slugging_pct,
        ops=row.ops,
        home_runs=row.home_runs,
        strikeouts=row.strikeouts,
        walks=row.walks,
        trend_label=TrendLabel(row.trend_label),
        as_of_date=row.as_of_date,
        woba=row.woba,
        insufficient_sample=row.insufficient_sample,
    )
