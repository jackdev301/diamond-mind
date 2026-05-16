"""Reasoning / evaluation / memory tables.

- ModelRun: each pipeline invocation (morning, postgame, backfill).
- BetEvaluation: persisted output of the market verification step.
- ObsidianExport: tracks which markdown files were written and when.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ModelRun(Base):
    __tablename__ = "model_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_type: Mapped[str] = mapped_column(String(32), index=True)  # "daily" | "pregame" | "postgame" | "backfill"
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(16), default="running")  # running | ok | failed
    notes: Mapped[Optional[str]] = mapped_column(Text)


class BetEvaluationRow(Base):
    __tablename__ = "bet_evaluations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    game_id: Mapped[int] = mapped_column(ForeignKey("games.id"), index=True)
    model_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("model_runs.id"), index=True)
    market: Mapped[str] = mapped_column(String(24))
    selection: Mapped[str] = mapped_column(String(32))
    current_odds: Mapped[int] = mapped_column()
    implied_probability: Mapped[float] = mapped_column()
    estimated_probability: Mapped[float] = mapped_column()
    edge: Mapped[float] = mapped_column()
    confidence_score: Mapped[float] = mapped_column()
    evidence_quality_score: Mapped[float] = mapped_column()
    recommendation: Mapped[str] = mapped_column(String(24), index=True)
    supporting_factors: Mapped[Optional[str]] = mapped_column(Text)   # JSON list
    opposing_factors: Mapped[Optional[str]] = mapped_column(Text)     # JSON list
    uncertainty_flags: Mapped[Optional[str]] = mapped_column(Text)    # JSON list
    what_would_change_the_answer: Mapped[Optional[str]] = mapped_column(Text)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # Postgame grading (filled in later by evaluation pipeline)
    settled_result: Mapped[Optional[str]] = mapped_column(String(16))  # win | loss | push | void
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))


class ObsidianExportRow(Base):
    __tablename__ = "obsidian_exports"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    file_path: Mapped[str] = mapped_column(String(512), index=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)  # "daily" | "game" | "team" | "player" | "bullpen" | "bet" | "model_eval"
    entity_ref: Mapped[Optional[str]] = mapped_column(String(128))  # e.g. team_abbr, player_id, "YYYY-MM-DD"
    model_run_id: Mapped[Optional[int]] = mapped_column(ForeignKey("model_runs.id"), index=True)
    exported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    __table_args__ = (
        Index("ix_obsidian_kind_entity", "kind", "entity_ref"),
    )
