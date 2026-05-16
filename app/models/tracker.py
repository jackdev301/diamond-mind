"""BetRecord — picks performance tracker model.

Each row represents a single tracked bet (moneyline or total).
Result is null until settled. units_returned is computed on settlement.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class BetRecord(Base):
    __tablename__ = "bet_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    game_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    market: Mapped[str] = mapped_column(String(16), nullable=False)        # "moneyline" | "total"
    selection: Mapped[str] = mapped_column(String(32), nullable=False)     # team abbr (ML) or "OVER"/"UNDER"
    american_odds: Mapped[int] = mapped_column(Integer, nullable=False)
    units: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    result: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)        # "WIN"|"LOSS"|"PUSH"|null
    units_returned: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # null until settled
    tier: Mapped[str] = mapped_column(String(16), nullable=False)          # "STRONG LEAN"|"LEAN"
    home_team_abbr: Mapped[str] = mapped_column(String(8), nullable=False)
    away_team_abbr: Mapped[str] = mapped_column(String(8), nullable=False)
    total_line: Mapped[Optional[float]] = mapped_column(Float, nullable=True)       # for O/U picks
    projected_total: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # model projection
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


def decimal_odds(american_odds: int) -> float:
    """Convert American odds to decimal odds."""
    if american_odds >= 0:
        return 1.0 + american_odds / 100.0
    return 1.0 + 100.0 / abs(american_odds)


def compute_units_returned(result: str, units: float, american_odds: int) -> float:
    """Compute units returned for a settled bet."""
    if result == "WIN":
        return units * (decimal_odds(american_odds) - 1.0)
    if result == "LOSS":
        return -units
    if result == "PUSH":
        return 0.0
    raise ValueError(f"Unknown result: {result!r}")
