"""Bullpen tables: per-appearance usage rows and computed daily fatigue."""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import Date, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RelieverUsageRow(Base):
    """One row per (reliever, game) appearance. Drives fatigue scoring."""

    __tablename__ = "reliever_usage"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pitcher_id: Mapped[int] = mapped_column(ForeignKey("players.id"), index=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    game_date: Mapped[date] = mapped_column(Date, index=True)
    role: Mapped[str] = mapped_column(String(16))
    pitches: Mapped[int] = mapped_column(default=0)
    innings: Mapped[float] = mapped_column(default=0.0)
    appeared: Mapped[bool] = mapped_column(default=True)

    __table_args__ = (
        Index("ix_reliever_usage_team_date", "team_id", "game_date"),
        Index("ix_reliever_usage_pitcher_date", "pitcher_id", "game_date"),
    )


class BullpenFatigueRow(Base):
    """Computed per (team, date). Source of truth for Track B's vulnerability inputs."""

    __tablename__ = "bullpen_fatigue"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    team_id: Mapped[int] = mapped_column(ForeignKey("teams.id"), index=True)
    as_of_date: Mapped[date] = mapped_column(Date, index=True)
    fatigue_score: Mapped[float] = mapped_column(default=0.0)
    overall_bullpen_quality: Mapped[Optional[float]] = mapped_column()
    available_bullpen_quality: Mapped[Optional[float]] = mapped_column()
    vulnerability_score: Mapped[Optional[float]] = mapped_column()
    notes: Mapped[Optional[str]] = mapped_column(Text)  # JSON blob: unavailable list, etc.

    __table_args__ = (
        Index("ix_bullpen_fatigue_team_date", "team_id", "as_of_date", unique=True),
    )
