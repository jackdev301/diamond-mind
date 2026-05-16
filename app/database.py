"""SQLAlchemy engine + session factory.

The DB is the source of truth. SQLite for local MVP; the URL-based config
means swapping to PostgreSQL later is a `.env` change.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models. Imported by `app/models/*`."""


def _build_engine() -> Engine:
    settings = get_settings()
    connect_args = {}
    if settings.database_url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(settings.database_url, future=True, connect_args=connect_args)


engine: Engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


def _ensure_sqlite_compat_columns() -> None:
    """Best-effort schema compatibility for MVP SQLite databases.

    We do not have Alembic in the MVP. These additive ALTERs let existing local
    DBs survive contract/cache-field additions without requiring a destructive
    drop/re-init.
    """
    if engine.dialect.name != "sqlite":
        return

    additions = {
        "player_game_logs": [
            ("caught_stealing", "INTEGER NOT NULL DEFAULT 0"),
        ],
        "team_form_windows": [
            ("stolen_bases", "INTEGER NOT NULL DEFAULT 0"),
            ("caught_stealing", "INTEGER NOT NULL DEFAULT 0"),
            ("stolen_base_attempts", "INTEGER NOT NULL DEFAULT 0"),
            ("stolen_base_success_rate", "FLOAT"),
            ("lineup_quality_score", "FLOAT"),
        ],
        "pitcher_form_windows": [
            ("babip", "FLOAT"),
        ],
    }

    with engine.begin() as conn:
        tables = {
            row[0]
            for row in conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        for table, columns in additions.items():
            if table not in tables:
                continue
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, ddl in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


_ensure_sqlite_compat_columns()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transactional session context. Commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
