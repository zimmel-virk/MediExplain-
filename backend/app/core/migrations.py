"""Automatic Alembic adoption/upgrade for existing and fresh project databases."""
# This file handles automatic database migration setup when MediExplain+ starts.
# It works with both fresh SQLite databases and older prototype databases that
# existed before Alembic version tracking was introduced. Older databases are
# first adopted at the baseline revision, then Alembic upgrades the schema to
# the latest available migration. After the schema is current, the legacy
# backfill runs so older consultation data is brought into the structures used
# by the final version of the application.

from pathlib import Path
import sqlite3
from alembic import command
from alembic.config import Config
from app.core.config import BASE_DIR, settings

BASELINE = "0001_baseline"

def _sqlite_path() -> Path:
    prefix = "sqlite+aiosqlite:///"
    if not settings.DATABASE_URL.startswith(prefix):
        raise RuntimeError("Automatic migration bootstrap currently supports SQLite only.")
    return Path(settings.DATABASE_URL[len(prefix):])

def _has_table(db: Path, table: str) -> bool:
    if not db.exists():
        return False
    con = sqlite3.connect(db)
    try:
        row = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
        ).fetchone()
        return bool(row)
    finally:
        con.close()

def ensure_database() -> None:
    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "alembic"))
    db = _sqlite_path()
    db.parent.mkdir(parents=True, exist_ok=True)

    # Existing prototype database: adopt it at the baseline revision first.
    if _has_table(db, "users") and not _has_table(db, "alembic_version"):
        command.stamp(cfg, BASELINE)

    command.upgrade(cfg, "head")

    from app.core.legacy_backfill import run_legacy_backfill
    run_legacy_backfill(db)
