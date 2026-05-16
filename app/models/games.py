"""Game-level tables: the Game itself and per-game performance logs.

Game logs are the raw inputs to recent-form calculations. One row per
(game, team) or (game, player). Pitcher logs distinguish starters from
relievers via `role`.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Game(Base):
    __tablename__ = "games"

    id: Mapped[int] = mapped_column(primary_key=True)  # MLB Stats API game id (gamePk)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    game_time_utc: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    home_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    away_team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    venue: Mapped[Optional[str]] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32), default="scheduled")
    home_score: Mapped[Optional[int]] = mapped_column()
    away_score: Mapped[Optional[int]] = mapped_column()
    is_doubleheader: Mapped[bool] = mapped_column(default=False)
    game_number: Mapped[int] = mapped_column(default=1)


class TeamGameLog(Base):
    __tablename__ = "team_game_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    runs: Mapped[int] = mapped_column(default=0)
    runs_allowed: Mapped[int] = mapped_column(default=0)
    hits: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
    is_home: Mapped[bool] = mapped_column(default=False)
    won: Mapped[Optional[bool]] = mapped_column()

    __table_args__ = (Index("ix_team_game_logs_team_date", "team_id", "game_date"),)


class PlayerGameLog(Base):
    """One row per hitter per game."""

    __tablename__ = "player_game_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    plate_appearances: Mapped[int] = mapped_column(default=0)
    at_bats: Mapped[int] = mapped_column(default=0)
    hits: Mapped[int] = mapped_column(default=0)
    doubles: Mapped[int] = mapped_column(default=0)
    triples: Mapped[int] = mapped_column(default=0)
    home_runs: Mapped[int] = mapped_column(default=0)
    rbis: Mapped[int] = mapped_column(default=0)
    walks: Mapped[int] = mapped_column(default=0)
    strikeouts: Mapped[int] = mapped_column(default=0)
    hit_by_pitch: Mapped[int] = mapped_column(default=0)
    sac_flies: Mapped[int] = mapped_column(default=0)
    stolen_bases: Mapped[int] = mapped_column(default=0)

    __table_args__ = (Index("ix_player_game_logs_player_date", "player_id", "game_date"),)


class PitcherGameLog(Base):
    """One row per pitcher per game. `role` separates starters from relievers."""

    __tablename__ = "pitcher_game_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    pitcher_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    role: Mapped[str] = mapped_column(String(16), index=True)  # "starter" or one of RelieverRole values
    started: Mapped[bool] = mapped_column(default=False)
    innings_pitched: Mapped[float] = mapped_column(default=0.0)
    batters_faced: Mapped[int] = mapped_column(default=0)
    hits_allowed: Mapped[int] = mapped_column(default=0)
    earned_runs: Mapped[int] = mapped_column(default=0)
    walks: Mapped[int] = mapped_column(default=0)
    strikeouts: Mapped[int] = mapped_column(default=0)
    home_runs_allowed: Mapped[int] = mapped_column(default=0)
    pitches: Mapped[int] = mapped_column(default=0)

    __table_args__ = (Index("ix_pitcher_game_logs_pitcher_date", "pitcher_id", "game_date"),)
