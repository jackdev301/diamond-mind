"""Team and Player identity tables.

These use the upstream MLB Stats API IDs as primary keys (not surrogate
auto-increments) so cross-references with external data are unambiguous.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)  # MLB Stats API team id
    abbr: Mapped[str] = mapped_column(String(4), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    league: Mapped[Optional[str]] = mapped_column(String(2))   # "AL" / "NL"
    division: Mapped[Optional[str]] = mapped_column(String(16))


class Player(Base):
    __tablename__ = "players"

    id: Mapped[int] = mapped_column(primary_key=True)  # MLB Stats API player id
    full_name: Mapped[str] = mapped_column(String(128), index=True)
    primary_position: Mapped[Optional[str]] = mapped_column(String(8))
    bats: Mapped[Optional[str]] = mapped_column(String(1))   # L / R / S
    throws: Mapped[Optional[str]] = mapped_column(String(1)) # L / R
    current_team_id: Mapped[Optional[int]] = mapped_column(index=True)
