import sqlite3
from pathlib import Path

import pytest

from evra.store.db import connect
from evra.store.migrate import Migration, bundled_migrations, current_version, migrate

EXPECTED_TABLES = {
    "meeting",
    "audio_segment",
    "gap",
    "transcript_version",
    "utterance",
    "person",
    "voiceprint",
    "speaker",
    "note_block",
    "generation",
    "output_block",
    "action_item",
    "decision",
    "open_question",
    "topic",
    "job",
}


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows}


def test_fresh_database_gets_phase1_schema(tmp_path: Path) -> None:
    conn = connect(tmp_path / "evra.db")
    assert migrate(conn) == 1
    assert current_version(conn) == 1
    assert _tables(conn) == EXPECTED_TABLES
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"utt_meeting", "job_ready"} <= indexes


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "evra.db")
    migrate(conn)
    assert migrate(conn) == 1


def test_connection_pragmas(tmp_path: Path) -> None:
    conn = connect(tmp_path / "evra.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_deleting_meeting_cascades_to_dependents(tmp_path: Path) -> None:
    conn = connect(tmp_path / "evra.db")
    migrate(conn)
    conn.execute(
        "INSERT INTO meeting (id, title, started_at, template, state, created_at, updated_at)"
        " VALUES ('m1', 'Sync', 0, 'one_on_one', 'ready', 0, 0)"
    )
    conn.execute(
        "INSERT INTO transcript_version (id, meeting_id, kind, model, created_at)"
        " VALUES ('v1', 'm1', 'live', 'parakeet', 0)"
    )
    conn.execute(
        "INSERT INTO utterance (id, version_id, meeting_id, seq, channel, start_ms, end_ms, text)"
        " VALUES ('u1', 'v1', 'm1', 0, 0, 0, 1000, 'hello')"
    )
    conn.execute(
        "INSERT INTO note_block (id, meeting_id, position, text, phase)"
        " VALUES ('n1', 'm1', 0, 'budget?', 'during')"
    )
    conn.execute("DELETE FROM meeting WHERE id = 'm1'")
    for table in ("transcript_version", "utterance", "note_block"):
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_failed_migration_rolls_back_and_keeps_version(tmp_path: Path) -> None:
    conn = connect(tmp_path / "evra.db")
    good = Migration(1, "good", "CREATE TABLE a (x INTEGER);")
    bad = Migration(2, "bad", "CREATE TABLE b (y INTEGER); THIS IS NOT SQL;")
    with pytest.raises(sqlite3.Error):
        migrate(conn, [good, bad])
    assert current_version(conn) == 1
    assert "b" not in _tables(conn)
    assert not conn.in_transaction


def test_reader_not_blocked_by_open_write_transaction(tmp_path: Path) -> None:
    db = tmp_path / "evra.db"
    writer = connect(db)
    migrate(writer)
    reader = connect(db)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO person (id, display_name) VALUES ('p1', 'Asha')")
    assert reader.execute("SELECT count(*) FROM person").fetchone()[0] == 0
    writer.execute("COMMIT")
    assert reader.execute("SELECT count(*) FROM person").fetchone()[0] == 1


def test_bundled_migrations_are_numbered_without_gaps() -> None:
    versions = [m.version for m in bundled_migrations()]
    assert versions == list(range(1, len(versions) + 1))
