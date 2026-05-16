"""Market and weather context — point-in-time snapshots."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class OddsSnapshotRow(Base):
    """One row per (game, bookmaker, market, selection) capture. Append-only."""

    __tablename__ = "odds_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    bookmaker: Mapped[str] = mapped_column(String(32))
    market: Mapped[str] = mapped_column(String(24))
    selection: Mapped[str] = mapped_column(String(32))
    line: Mapped[Optional[float]] = mapped_column()
    american_odds: Mapped[int] = mapped_column()
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        Index("ix_odds_game_market_time", "game_id", "market", "captured_at"),
    )


class WeatherSnapshotRow(Base):
    __tablename__ = "weather_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    temperature_f: Mapped[Optional[float]] = mapped_column()
    wind_speed_mph: Mapped[Optional[float]] = mapped_column()
    wind_direction_deg: Mapped[Optional[int]] = mapped_column()
    precipitation_chance: Mapped[Optional[float]] = mapped_column()
    humidity_pct: Mapped[Optional[float]] = mapped_column()
    is_dome: Mapped[bool] = mapped_column(default=False)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
