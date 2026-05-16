"""Initialize the diamond-mind database.

Idempotent: creates any missing tables, leaves existing ones alone.
For a clean rebuild during development, pass --drop.

    python scripts/init_db.py
    python scripts/init_db.py --drop   # WARNING: drops all tables first
"""

from __future__ import annotations

import argparse
import sys

from app.config import get_settings
from app.database import Base, engine

# Side-effect import: registers every ORM model on Base.metadata.
import app.models  # noqa: F401


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize diamond-mind database.")
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop all tables before creating (DESTRUCTIVE).",
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"Database URL: {settings.database_url}")
    print(f"Tables registered: {len(Base.metadata.tables)}")

    if args.drop:
        confirm = input("Drop all tables? Type 'yes' to confirm: ").strip().lower()
        if confirm != "yes":
            print("Aborted.")
            return 1
        Base.metadata.drop_all(engine)
        print("Dropped existing tables.")

    Base.metadata.create_all(engine)
    print("Created tables:")
    for name in sorted(Base.metadata.tables.keys()):
        print(f"  - {name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
