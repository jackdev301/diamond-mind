"""Derived form-window tables.

These are recomputed by the Phase 5 engine; they're a cache of computed
features keyed by (entity_id, window, as_of_date). The dataclasses in
`app.contracts` are the in-memory equivalents — Track A's query helpers
load these rows and hydrate the dataclasses for Track B.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class TeamFormWindowRow(Base):
    __tablename__ = "team_form_windows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    window: Mapped[str] = mapped_column(String(24), index=True)  # WindowKey.value
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    games: Mapped[int] = mapped_column(default=0)
    runs_per_game: Mapped[float] = mapped_column(default=0.0)
    runs_allowed_per_game: Mapped[float] = mapped_column(default=0.0)
    team_ops: Mapped[float] = mapped_column(default=0.0)
    team_woba: Mapped[Optional[float]] = mapped_column()
    stolen_bases: Mapped[int] = mapped_column(default=0)
    caught_stealing: Mapped[int] = mapped_column(default=0)
    stolen_base_attempts: Mapped[int] = mapped_column(default=0)
    stolen_base_success_rate: Mapped[Optional[float]] = mapped_column()
    lineup_quality_score: Mapped[Optional[float]] = mapped_column()
    record_wins: Mapped[int] = mapped_column(default=0)
    record_losses: Mapped[int] = mapped_column(default=0)
    trend_label: Mapped[str] = mapped_column(String(32))
    insufficient_sample: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index("ix_team_form_team_window_date", "team_id", "window", "as_of_date", unique=True),
    )


class PlayerFormWindowRow(Base):
    __tablename__ = "player_form_windows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    window: Mapped[str] = mapped_column(String(24), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    games: Mapped[int] = mapped_column(default=0)
    plate_appearances: Mapped[int] = mapped_column(default=0)
    batting_avg: Mapped[float] = mapped_column(default=0.0)
    on_base_pct: Mapped[float] = mapped_column(default=0.0)
    slugging_pct: Mapped[float] = mapped_column(default=0.0)
    ops: Mapped[float] = mapped_column(default=0.0)
    woba: Mapped[Optional[float]] = mapped_column()
    home_runs: Mapped[int] = mapped_column(default=0)
    strikeouts: Mapped[int] = mapped_column(default=0)
    walks: Mapped[int] = mapped_column(default=0)
    trend_label: Mapped[str] = mapped_column(String(32))
    insufficient_sample: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index("ix_player_form_player_window_date", "player_id", "window", "as_of_date", unique=True),
    )


class PitcherFormWindowRow(Base):
    """Starter-shaped form windows. Relievers use `reliever_form_windows`."""

    __tablename__ = "pitcher_form_windows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pitcher_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    window: Mapped[str] = mapped_column(String(24), index=True)  # SEASON / LAST_10_STARTS / LAST_5_STARTS
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    starts: Mapped[int] = mapped_column(default=0)
    innings_pitched: Mapped[float] = mapped_column(default=0.0)
    era: Mapped[float] = mapped_column(default=0.0)
    fip: Mapped[Optional[float]] = mapped_column()
    xfip: Mapped[Optional[float]] = mapped_column()
    babip: Mapped[Optional[float]] = mapped_column()
    whip: Mapped[float] = mapped_column(default=0.0)
    k_per_9: Mapped[float] = mapped_column(default=0.0)
    bb_per_9: Mapped[float] = mapped_column(default=0.0)
    hr_per_9: Mapped[float] = mapped_column(default=0.0)
    avg_pitches_per_start: Mapped[Optional[float]] = mapped_column()
    avg_innings_per_start: Mapped[float] = mapped_column(default=0.0)
    trend_label: Mapped[str] = mapped_column(String(32))
    insufficient_sample: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index("ix_pitcher_form_pitcher_window_date", "pitcher_id", "window", "as_of_date", unique=True),
    )


class RelieverFormWindowRow(Base):
    """Reliever-shaped form windows. Distinct from starters because the
    field set (appearances vs starts, inherited runners) differs."""

    __tablename__ = "reliever_form_windows"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pitcher_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    window: Mapped[str] = mapped_column(String(24), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    appearances: Mapped[int] = mapped_column(default=0)
    innings_pitched: Mapped[float] = mapped_column(default=0.0)
    era: Mapped[float] = mapped_column(default=0.0)
    fip: Mapped[Optional[float]] = mapped_column()
    whip: Mapped[float] = mapped_column(default=0.0)
    k_per_9: Mapped[float] = mapped_column(default=0.0)
    bb_per_9: Mapped[float] = mapped_column(default=0.0)
    inherited_runners_scored_pct: Mapped[Optional[float]] = mapped_column()
    trend_label: Mapped[str] = mapped_column(String(32))
    insufficient_sample: Mapped[bool] = mapped_column(default=False)

    __table_args__ = (
        Index("ix_reliever_form_pitcher_window_date", "pitcher_id", "window", "as_of_date", unique=True),
    )
