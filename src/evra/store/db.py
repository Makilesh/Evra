"""SQLite connections (BUILD.md §8.2): WAL, foreign keys, one connection per thread."""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Iterator
from pathlib import Path

BUSY_TIMEOUT_MS = 5000


@contextlib.contextmanager
def writing(conn: sqlite3.Connection) -> Iterator[None]:
    """One write: inside the caller's transaction when there is one, otherwise its own, begun
    IMMEDIATE so what it reads cannot change before it writes."""
    if conn.in_transaction:
        yield
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield
        conn.execute("COMMIT")
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database in autocommit mode; callers manage transactions explicitly."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn
