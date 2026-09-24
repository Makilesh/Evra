"""SQLite connections (BUILD.md §8.2): WAL, foreign keys, one connection per thread."""

from __future__ import annotations

import sqlite3
from pathlib import Path

BUSY_TIMEOUT_MS = 5000


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database in autocommit mode; callers manage transactions explicitly."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn
