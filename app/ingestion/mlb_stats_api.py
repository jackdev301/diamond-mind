"""MLB Stats API client and ingestion helpers.

Fetches schedule, teams, players, games, box scores, and pitcher usage
from the free MLB Stats API (statsapi.mlb.com) and upserts into the DB.

All network calls go through MLBStatsClient, which is injectable for
testing — pass a stub client to bypass HTTP.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.entities import Player, Team
from app.models.games import Game, PitcherGameLog, PlayerGameLog, TeamGameLog

log = logging.getLogger(__name__)

SPORT_ID = 1  # MLB


# ---------------------------------------------------------------------------
# HTTP client
# ---------------------------------------------------------------------------

class MLBStatsClient:
    """Thin wrapper around the MLB Stats API."""

    def __init__(self, base_url: str | None = None, timeout: float = 30.0):
        self._base = (base_url or get_settings().mlb_stats_api_base).rstrip("/")
        self._http = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> MLBStatsClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def _get(self, path: str, **params: Any) -> dict:
        url = f"{self._base}{path}"
        r = self._http.get(url, params=params)
        r.raise_for_status()
        return r.json()

    # -- schedule -----------------------------------------------------------

    def fetch_schedule(self, game_date: date) -> dict:
        return self._get(
            "/schedule",
            sportId=SPORT_ID,
            date=game_date.isoformat(),
            hydrate="probablePitcher,venue,team",
        )

    # -- teams --------------------------------------------------------------

    def fetch_teams(self) -> dict:
        return self._get("/teams", sportId=SPORT_ID, activeStatus="Y")

    # -- players ------------------------------------------------------------

    def fetch_roster(self, team_id: int) -> dict:
        return self._get(f"/teams/{team_id}/roster", rosterType="40Man")

    def fetch_player(self, player_id: int) -> dict:
        return self._get(f"/people/{player_id}", hydrate="currentTeam")

    # -- box score / live feed ----------------------------------------------

    def fetch_boxscore(self, game_pk: int) -> dict:
        return self._get(f"/game/{game_pk}/boxscore")

    def fetch_live(self, game_pk: int) -> dict:
        return self._get(f"/game/{game_pk}/feed/live")


# ---------------------------------------------------------------------------
# Parse helpers
# ---------------------------------------------------------------------------

@dataclass
class _ScheduledGame:
    game_pk: int
    game_date: date
    status: str
    home_team_id: int
    away_team_id: int
    venue_name: str
    double_header: str   # "N", "Y", "S"
    game_number: int
    home_probable_pitcher_id: Optional[int]
    away_probable_pitcher_id: Optional[int]


def parse_schedule(payload: dict) -> list[_ScheduledGame]:
    games: list[_ScheduledGame] = []
    for date_entry in payload.get("dates", []):
        gdate = date.fromisoformat(date_entry["date"])
        for g in date_entry.get("games", []):
            teams = g.get("teams", {})
            home = teams.get("home", {})
            away = teams.get("away", {})

            def _probable(side: dict) -> Optional[int]:
                pp = side.get("probablePitcher") or {}
                return pp.get("id")

            games.append(_ScheduledGame(
                game_pk=g["gamePk"],
                game_date=gdate,
                status=g.get("status", {}).get("detailedState", ""),
                home_team_id=home.get("team", {}).get("id", 0),
                away_team_id=away.get("team", {}).get("id", 0),
                venue_name=g.get("venue", {}).get("name", ""),
                double_header=g.get("doubleHeader", "N"),
                game_number=g.get("gameNumber", 1),
                home_probable_pitcher_id=_probable(home),
                away_probable_pitcher_id=_probable(away),
            ))
    return games


def parse_teams(payload: dict) -> list[dict]:
    out = []
    for t in payload.get("teams", []):
        out.append({
            "id": t["id"],
            "abbr": t.get("abbreviation", ""),
            "name": t.get("teamName", t.get("name", "")),
            "league": t.get("league", {}).get("name"),
            "division": t.get("division", {}).get("name"),
        })
    return out


def parse_roster(payload: dict) -> list[dict]:
    out = []
    for entry in payload.get("roster", []):
        p = entry.get("person", {})
        pos = entry.get("position", {})
        out.append({
            "id": p["id"],
            "full_name": p.get("fullName", ""),
            "primary_position": pos.get("abbreviation", ""),
        })
    return out


def parse_player_detail(payload: dict) -> dict:
    people = payload.get("people", [])
    if not people:
        return {}
    p = people[0]
    return {
        "id": p["id"],
        "full_name": p.get("fullName", ""),
        "primary_position": p.get("primaryPosition", {}).get("abbreviation", ""),
        "bats": p.get("batSide", {}).get("code"),
        "throws": p.get("pitchHand", {}).get("code"),
        "current_team_id": p.get("currentTeam", {}).get("id"),
    }


# ---------------------------------------------------------------------------
# Box-score parsing
# ---------------------------------------------------------------------------

@dataclass
class _BoxTeamStats:
    team_id: int
    runs: int
    hits: int
    errors: int
    won: bool


@dataclass
class _BatterLine:
    player_id: int
    team_id: int
    plate_appearances: int
    at_bats: int
    hits: int
    doubles: int
    triples: int
    home_runs: int
    walks: int
    hit_by_pitch: int
    sac_flies: int
    strikeouts: int
    stolen_bases: int
    caught_stealing: int


@dataclass
class _PitcherLine:
    player_id: int
    team_id: int
    role: str           # "starter" or "reliever"
    started: bool
    innings_pitched: float
    batters_faced: int
    hits_allowed: int
    earned_runs: int
    walks: int
    strikeouts: int
    home_runs_allowed: int
    pitches: int


def _parse_ip(ip_str: str) -> float:
    """Convert '6.1' (6 innings + 1 out) to decimal innings (6.333...)."""
    try:
        whole, outs = str(ip_str).split(".")
        return int(whole) + int(outs) / 3
    except (ValueError, AttributeError):
        try:
            return float(ip_str)
        except (ValueError, TypeError):
            return 0.0


def parse_boxscore(
    payload: dict,
    game_pk: int,
    game_date: date,
) -> tuple[list[_BatterLine], list[_PitcherLine], _BoxTeamStats, _BoxTeamStats]:
    """Return (batters, pitchers, home_stats, away_stats)."""
    teams = payload.get("teams", {})
    batters: list[_BatterLine] = []
    pitchers: list[_PitcherLine] = []

    home_runs = teams.get("home", {}).get("teamStats", {}).get("batting", {}).get("runs", 0)
    away_runs = teams.get("away", {}).get("teamStats", {}).get("batting", {}).get("runs", 0)
    home_id = teams.get("home", {}).get("team", {}).get("id", 0)
    away_id = teams.get("away", {}).get("team", {}).get("id", 0)

    home_stats = _BoxTeamStats(
        team_id=home_id, runs=home_runs,
        hits=teams.get("home", {}).get("teamStats", {}).get("batting", {}).get("hits", 0),
        errors=teams.get("home", {}).get("teamStats", {}).get("fielding", {}).get("errors", 0),
        won=home_runs > away_runs,
    )
    away_stats = _BoxTeamStats(
        team_id=away_id, runs=away_runs,
        hits=teams.get("away", {}).get("teamStats", {}).get("batting", {}).get("hits", 0),
        errors=teams.get("away", {}).get("teamStats", {}).get("fielding", {}).get("errors", 0),
        won=away_runs > home_runs,
    )

    for side_key, team_id in [("home", home_id), ("away", away_id)]:
        side = teams.get(side_key, {})
        players = side.get("players", {})
        batting_order = side.get("battingOrder", [])
        pitching_ids: set[int] = set()
        for pid_str, pdata in players.items():
            s = pdata.get("stats", {})

            # --- pitcher ---
            pit = s.get("pitching", {})
            if pit.get("gamesPlayed", 0) or pit.get("inningsPitched"):
                pid = pdata["person"]["id"]
                pitching_ids.add(pid)
                started = pid_str.lstrip("ID") in [str(x) for x in (batting_order[:1] or [])]
                # More reliable: check gamesPitched / gamesStarted sub-keys
                gs = pit.get("gamesStarted", 0)
                pitchers.append(_PitcherLine(
                    player_id=pid,
                    team_id=team_id,
                    role="starter" if gs else "reliever",
                    started=bool(gs),
                    innings_pitched=_parse_ip(pit.get("inningsPitched", "0.0")),
                    batters_faced=pit.get("battersFaced", 0),
                    hits_allowed=pit.get("hits", 0),
                    earned_runs=pit.get("earnedRuns", 0),
                    walks=pit.get("baseOnBalls", 0),
                    strikeouts=pit.get("strikeOuts", 0),
                    home_runs_allowed=pit.get("homeRuns", 0),
                    pitches=pit.get("numberOfPitches", 0),
                ))

            # --- batter ---
            bat = s.get("batting", {})
            if bat.get("plateAppearances", 0):
                pid = pdata["person"]["id"]
                if pid not in pitching_ids:
                    batters.append(_BatterLine(
                        player_id=pid,
                        team_id=team_id,
                        plate_appearances=bat.get("plateAppearances", 0),
                        at_bats=bat.get("atBats", 0),
                        hits=bat.get("hits", 0),
                        doubles=bat.get("doubles", 0),
                        triples=bat.get("triples", 0),
                        home_runs=bat.get("homeRuns", 0),
                        walks=bat.get("baseOnBalls", 0),
                        hit_by_pitch=bat.get("hitByPitch", 0),
                        sac_flies=bat.get("sacFlies", 0),
                        strikeouts=bat.get("strikeOuts", 0),
                        stolen_bases=bat.get("stolenBases", 0),
                        caught_stealing=bat.get("caughtStealing", 0),
                    ))

    return batters, pitchers, home_stats, away_stats


# ---------------------------------------------------------------------------
# DB upsert helpers
# ---------------------------------------------------------------------------

def upsert_team(session: Session, data: dict) -> None:
    existing = session.get(Team, data["id"])
    if existing:
        existing.abbr = data["abbr"]
        existing.name = data["name"]
        if data.get("league"):
            existing.league = data["league"]
        if data.get("division"):
            existing.division = data["division"]
    else:
        session.add(Team(**{k: v for k, v in data.items() if v is not None or k == "id"}))


def upsert_player(session: Session, data: dict) -> None:
    if not data.get("id"):
        return
    existing = session.get(Player, data["id"])
    if existing:
        for k, v in data.items():
            if k != "id" and v is not None:
                setattr(existing, k, v)
    else:
        session.add(Player(**{k: v for k, v in data.items() if v is not None or k == "id"}))


def upsert_game(session: Session, g: _ScheduledGame) -> Game:
    existing = session.get(Game, g.game_pk)
    if existing:
        existing.status = g.status
        existing.home_probable_starter_id = g.home_probable_pitcher_id
        existing.away_probable_starter_id = g.away_probable_pitcher_id
        return existing
    obj = Game(
        id=g.game_pk,
        game_date=g.game_date,
        status=g.status,
        home_team_id=g.home_team_id,
        away_team_id=g.away_team_id,
        venue=g.venue_name,
        is_doubleheader=g.double_header != "N",
        game_number=g.game_number,
        home_probable_starter_id=g.home_probable_pitcher_id,
        away_probable_starter_id=g.away_probable_pitcher_id,
    )
    session.add(obj)
    return obj


def upsert_team_game_log(
    session: Session,
    game_id: int,
    game_date: date,
    stats: _BoxTeamStats,
    runs_allowed: int,
    is_home: bool,
) -> None:
    from sqlalchemy import select
    existing = session.execute(
        select(TeamGameLog).where(
            TeamGameLog.game_id == game_id,
            TeamGameLog.team_id == stats.team_id,
        )
    ).scalar_one_or_none()
    if existing:
        existing.runs = stats.runs
        existing.runs_allowed = runs_allowed
        existing.won = stats.won
        return
    session.add(TeamGameLog(
        game_id=game_id,
        team_id=stats.team_id,
        game_date=game_date,
        runs=stats.runs,
        runs_allowed=runs_allowed,
        won=stats.won,
        is_home=is_home,
    ))


def upsert_player_game_log(
    session: Session,
    game_id: int,
    game_date: date,
    b: _BatterLine,
) -> None:
    from sqlalchemy import select
    existing = session.execute(
        select(PlayerGameLog).where(
            PlayerGameLog.game_id == game_id,
            PlayerGameLog.player_id == b.player_id,
        )
    ).scalar_one_or_none()
    if existing:
        return  # box score data is final; don't re-write
    session.add(PlayerGameLog(
        game_id=game_id,
        player_id=b.player_id,
        team_id=b.team_id,
        game_date=game_date,
        plate_appearances=b.plate_appearances,
        at_bats=b.at_bats,
        hits=b.hits,
        doubles=b.doubles,
        triples=b.triples,
        home_runs=b.home_runs,
        walks=b.walks,
        hit_by_pitch=b.hit_by_pitch,
        sac_flies=b.sac_flies,
        strikeouts=b.strikeouts,
        stolen_bases=b.stolen_bases,
        caught_stealing=b.caught_stealing,
    ))


def upsert_pitcher_game_log(
    session: Session,
    game_id: int,
    game_date: date,
    p: _PitcherLine,
) -> None:
    from sqlalchemy import select
    existing = session.execute(
        select(PitcherGameLog).where(
            PitcherGameLog.game_id == game_id,
            PitcherGameLog.pitcher_id == p.player_id,
        )
    ).scalar_one_or_none()
    if existing:
        return
    session.add(PitcherGameLog(
        game_id=game_id,
        pitcher_id=p.player_id,
        team_id=p.team_id,
        game_date=game_date,
        role=p.role,
        started=p.started,
        innings_pitched=p.innings_pitched,
        batters_faced=p.batters_faced,
        hits_allowed=p.hits_allowed,
        earned_runs=p.earned_runs,
        walks=p.walks,
        strikeouts=p.strikeouts,
        home_runs_allowed=p.home_runs_allowed,
        pitches=p.pitches,
    ))


# ---------------------------------------------------------------------------
# High-level ingestion entry points
# ---------------------------------------------------------------------------

def ingest_teams(session: Session, client: MLBStatsClient) -> int:
    payload = client.fetch_teams()
    teams = parse_teams(payload)
    for t in teams:
        upsert_team(session, t)
    session.flush()
    log.info("Upserted %d teams", len(teams))
    return len(teams)


def ingest_roster(session: Session, client: MLBStatsClient, team_id: int) -> int:
    payload = client.fetch_roster(team_id)
    players = parse_roster(payload)
    for p in players:
        # Minimal upsert from roster; fetch_player fills bats/throws.
        upsert_player(session, {**p, "current_team_id": team_id})
    session.flush()
    return len(players)


def ingest_player(session: Session, client: MLBStatsClient, player_id: int) -> None:
    payload = client.fetch_player(player_id)
    data = parse_player_detail(payload)
    if data:
        upsert_player(session, data)
        session.flush()


def ingest_schedule(
    session: Session,
    client: MLBStatsClient,
    game_date: date,
) -> list[int]:
    """Upsert games for a date; return list of game_pks."""
    payload = client.fetch_schedule(game_date)
    scheduled = parse_schedule(payload)
    pks = []
    for g in scheduled:
        upsert_game(session, g)
        pks.append(g.game_pk)
    session.flush()
    log.info("Upserted %d games for %s", len(pks), game_date)
    return pks


def ingest_boxscore(
    session: Session,
    client: MLBStatsClient,
    game_pk: int,
    game_date: date,
) -> None:
    """Parse and upsert a completed game's box score."""
    payload = client.fetch_boxscore(game_pk)
    batters, pitchers, home_stats, away_stats = parse_boxscore(payload, game_pk, game_date)

    upsert_team_game_log(
        session, game_pk, game_date, home_stats,
        runs_allowed=away_stats.runs, is_home=True,
    )
    upsert_team_game_log(
        session, game_pk, game_date, away_stats,
        runs_allowed=home_stats.runs, is_home=False,
    )
    for b in batters:
        upsert_player_game_log(session, game_pk, game_date, b)
    for p in pitchers:
        upsert_pitcher_game_log(session, game_pk, game_date, p)

    session.flush()
    log.info(
        "Ingested box score game=%d: %d batters, %d pitchers",
        game_pk, len(batters), len(pitchers),
    )
