"""The owner's notepad lines for a meeting (BUILD.md §7.1, §8.2 `note_block`)."""

import sqlite3
from pathlib import Path

import pytest

from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notepad import CONTEXT_CHARS, MAX_LINE_CHARS, MAX_LINES, LineIn, NotepadStore

STARTED = 1_790_600_000_000


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _meeting(conn: sqlite3.Connection) -> str:
    return MeetingStore(conn).create_meeting(
        title="Weekly 1:1",
        mode="one_on_one",
        situation="call_headphones",
        template="one_on_one",
        started_at_ms=STARTED,
    )


def _end(conn: sqlite3.Connection, meeting_id: str, after_ms: int) -> None:
    conn.execute("UPDATE meeting SET ended_at = ? WHERE id = ?", (STARTED + after_ms, meeting_id))


def typed(line_id: str, text: str, at_ms: int | None = 0, *, pasted: bool = False) -> LineIn:
    """A line as the window sends it: its first typed time in epoch ms, `at_ms` into the call."""
    return LineIn(line_id, text, None if at_ms is None else STARTED + at_ms, pasted)


def test_blank_lines_are_dropped(conn: sqlite3.Connection) -> None:
    mid = _meeting(conn)
    store = NotepadStore(conn)
    saved = store.replace(
        mid,
        [typed("a", "Budget approved", 5_000), typed("b", "  \n\t"), typed("c", "Dana", 9_000)],
    )
    assert [(line.id, line.position, line.text) for line in saved] == [
        ("a", 0, "Budget approved"),
        ("c", 1, "Dana"),
    ]
    assert store.lines(mid) == saved


def test_long_paste_is_context(conn: sqlite3.Connection) -> None:
    mid = _meeting(conn)
    long = "x" * (CONTEXT_CHARS + 1)
    saved = NotepadStore(conn).replace(
        mid,
        [
            typed("paste", long, pasted=True),
            typed("short", "x" * CONTEXT_CHARS, pasted=True),
            typed("typed", long),
        ],
    )
    assert [line.is_context for line in saved] == [True, False, False]


def test_first_capture_time_is_kept(conn: sqlite3.Connection) -> None:
    mid = _meeting(conn)
    store = NotepadStore(conn)
    store.replace(mid, [typed("a", "Budget", 12_000), typed("b", "Not timed yet", None)])
    a, b = store.replace(mid, [typed("a", "Budget approved", 50_000), typed("b", "Now", 61_000)])
    assert (a.text, a.captured_at_ms) == ("Budget approved", 12_000)  # a later save never moves it
    assert b.captured_at_ms == 61_000  # the first time it was given
    [b] = store.replace(mid, [typed("b", "Now", 99_000)])
    assert b.captured_at_ms == 61_000


def test_phase_from_meeting_times(conn: sqlite3.Connection) -> None:
    mid = _meeting(conn)
    store = NotepadStore(conn)
    lines = [typed("early", "Agenda", -60_000), typed("live", "Budget", 30_000)]
    lines.append(typed("untimed", "No time", None))  # cannot be placed in the call: after it
    saved = store.replace(mid, lines)  # the meeting has no end yet
    assert [line.phase for line in saved] == ["before", "during", "after"]
    assert saved[0].captured_at_ms == -60_000
    _end(conn, mid, 600_000)
    lines += [typed("late", "Follow up", 600_000), typed("last", "Wrap up", 599_999)]
    assert [(line.id, line.phase) for line in store.replace(mid, lines)] == [
        ("early", "before"),
        ("live", "during"),
        ("untimed", "after"),
        ("late", "after"),
        ("last", "during"),
    ]


def test_limits_raise(conn: sqlite3.Connection) -> None:
    mid = _meeting(conn)
    store = NotepadStore(conn)
    store.replace(mid, [typed("keep", "Kept")])
    refused = [
        [typed(f"l{i}", "x") for i in range(MAX_LINES + 1)],
        [typed("long", "x" * (MAX_LINE_CHARS + 1))],
        [typed("a b", "x")],
        [typed("", "x")],
        [typed("x" * 65, "x")],
        [typed("ü", "x")],
        [typed("twice", "x"), typed("twice", "y")],
    ]
    for lines in refused:
        with pytest.raises(ValueError):
            store.replace(mid, lines)
    assert [line.id for line in store.lines(mid)] == ["keep"]  # nothing was changed
    most = [typed(f"l-{i}", "x" * MAX_LINE_CHARS) for i in range(MAX_LINES)]
    assert len(store.replace(mid, most)) == MAX_LINES
    with pytest.raises(KeyError):
        store.replace("no-such-meeting", [typed("a", "x")])


def test_each_meeting_keeps_its_own_lines(conn: sqlite3.Connection) -> None:
    first, second = _meeting(conn), _meeting(conn)
    store = NotepadStore(conn)
    store.replace(first, [typed("1", "First meeting")])
    store.replace(second, [typed("1", "Second meeting")])
    assert [(line.id, line.text) for line in store.lines(first)] == [("1", "First meeting")]
    assert [(line.id, line.text) for line in store.lines(second)] == [("1", "Second meeting")]


def test_links_are_stored_and_kept_until_the_next_linking(conn: sqlite3.Connection) -> None:
    mid = _meeting(conn)
    store = NotepadStore(conn)
    store.replace(mid, [typed("a", "Budget", 30_000), typed("b", "Dana", 40_000)])
    store.set_alignment(mid, {"a": [("u7", 0.61), ("u6", 0.42)], "b": []})
    a, b = store.lines(mid)
    assert (a.aligned, b.aligned) == ((("u7", 0.61), ("u6", 0.42)), ())
    a, b = store.replace(mid, [typed("a", "Budget approved", 30_000), typed("b", "Dana", 40_000)])
    assert a.aligned == (("u7", 0.61), ("u6", 0.42))  # an edit keeps the line's links
    store.set_alignment(mid, {"b": [("u9", 0.5)]})
    assert [line.aligned for line in store.lines(mid)] == [(), (("u9", 0.5),)]  # a is unlinked
    long = "x" * (CONTEXT_CHARS + 1)
    [b] = store.replace(mid, [typed("b", long, 40_000, pasted=True)])
    assert (b.is_context, b.aligned) == (True, ())  # a paste is context: never linked
