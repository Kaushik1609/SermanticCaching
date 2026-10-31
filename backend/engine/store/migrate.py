"""Tiny migration runner for CacheIQ.

Reads DATABASE_URL from environment, connects via psycopg, and executes
the SQL migration file at backend/migrations/001_init.sql.
"""

import os
from pathlib import Path

import psycopg
from dotenv import load_dotenv


def run_migration() -> None:
    load_dotenv()

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set in environment or .env file")

    migration_file = Path(__file__).resolve().parents[2] / "migrations" / "001_init.sql"
    if not migration_file.exists():
        raise FileNotFoundError(f"Migration file not found: {migration_file}")

    sql = migration_file.read_text(encoding="utf-8")

    try:
        with psycopg.connect(database_url) as conn:
            conn.execute(sql)
            conn.commit()
        print("Migration 001_init.sql applied successfully.")
    except Exception as exc:
        print(f"Migration failed: {exc}")
        raise


if __name__ == "__main__":
    run_migration()
