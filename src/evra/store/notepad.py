"""The owner's notepad lines for a meeting (BUILD.md §7.1, §8.2 `note_block`). The window saves
the whole pad each time; a line keeps the first time it was typed (`captured_at_ms`, from the
meeting's start) however often it is saved again. A long paste is context, never linked to the
transcript; the other lines typed during the call are linked by the note job (`evra.notes.align`)
and keep those links until the next note. Line ids are the window's own, unique within a
meeting. Note-line text is content: it goes to the owner's window and the prompts, never a log."""

from __future__ import annotations

import json
import re
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from evra.store.meetings import MeetingStore

MAX_LINES, MAX_LINE_CHARS, CONTEXT_CHARS = 2000, 4000, 500
LINE_ID = re.compile(r"[A-Za-z0-9-]{1,64}")

Phase = Literal["before", "during", "after"]


@dataclass(frozen=True)
class LineIn:
    """A line as the window sends it."""

    id: str
    text: str
    captured_at: int | None  # epoch ms: when the line first got a character
    pasted: bool  # it arrived as a paste of more than CONTEXT_CHARS


@dataclass(frozen=True)
class NoteLine:
    id: str
    position: int  # 0, 1, ... in the pad's order
    text: str
    captured_at_ms: int | None  # from the meeting's start; negative before it
    phase: Phase
    is_context: bool
    aligned: tuple[tuple[str, float], ...]  # (utterance id, score), best first


def _phase(captured_at: int | None, meeting: Mapping[str, Any]) -> Phase:
    """`during` while the meeting runs or before it ended, `after` once it has, `before` only
    for a time before it started. A line with no time cannot be placed in the call: after."""
    if captured_at is None:
        return "after"
    if captured_at < int(meeting["started_at"]):
        return "before"
    ended = meeting["ended_at"]
    return "during" if ended is None or captured_at < int(ended) else "after"


def _checked(lines: Sequence[LineIn]) -> None:
    if len(lines) > MAX_LINES:
        raise ValueError(f"more than {MAX_LINES} lines")
    ids = [line.id for line in lines]
    if len(set(ids)) != len(ids):
        raise ValueError("a line id is repeated")
    for line in lines:
        if not LINE_ID.fullmatch(line.id):
            raise ValueError("a line id is not 1-64 letters, digits or hyphens")
        if len(line.text) > MAX_LINE_CHARS:
            raise ValueError(f"a line is longer than {MAX_LINE_CHARS} characters")


class NotepadStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def replace(self, meeting_id: str, lines: Sequence[LineIn]) -> list[NoteLine]:
        """The pad as it is now, saved in one transaction: blank lines are dropped, and a line
        keeps its first typed time and its links. ValueError for a pad past the limits or with
        a bad id; KeyError for an unknown meeting."""
        _checked(lines)
        self._conn.execute("BEGIN IMMEDIATE")  # read and write as one, against a parallel save
        try:
            meeting = MeetingStore(self._conn).get_meeting(meeting_id)
            started = int(meeting["started_at"])
            earlier = {line.id: line for line in self.lines(meeting_id)}
            saved: list[NoteLine] = []
            for line in lines:
                if not line.text.strip():
                    continue
                old = earlier.get(line.id)
                at_ms = old.captured_at_ms if old is not None else None
                if at_ms is None and line.captured_at is not None:
                    at_ms = line.captured_at - started
                phase = _phase(None if at_ms is None else started + at_ms, meeting)
                is_context = line.pasted and len(line.text) > CONTEXT_CHARS
                linkable = phase == "during" and not is_context
                aligned = old.aligned if old is not None and linkable else ()
                saved.append(
                    NoteLine(line.id, len(saved), line.text, at_ms, phase, is_context, aligned)
                )
            self._conn.execute("DELETE FROM note_block WHERE meeting_id = ?", (meeting_id,))
            for note in saved:
                self._conn.execute(
                    "INSERT INTO note_block (id, meeting_id, position, text, captured_at_ms,"
                    " phase, is_context, aligned_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        _row_id(meeting_id, note.id),
                        meeting_id,
                        note.position,
                        note.text,
                        note.captured_at_ms,
                        note.phase,
                        int(note.is_context),
                        _aligned_json(note.aligned),
                    ),
                )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return saved

    def has_lines(self, meeting_id: str) -> bool:
        """Whether the owner typed anything for the meeting (blank lines are never stored)."""
        found = self._conn.execute(
            "SELECT 1 FROM note_block WHERE meeting_id = ? LIMIT 1", (meeting_id,)
        ).fetchone()
        return found is not None

    def lines(self, meeting_id: str) -> list[NoteLine]:
        rows = self._conn.execute(
            "SELECT * FROM note_block WHERE meeting_id = ? ORDER BY position", (meeting_id,)
        ).fetchall()
        prefix = _row_id(meeting_id, "")
        return [
            NoteLine(
                str(r["id"]).removeprefix(prefix),
                r["position"],
                r["text"],
                r["captured_at_ms"],
                r["phase"],
                bool(r["is_context"]),
                tuple(
                    (str(a["utterance_id"]), float(a["score"]))
                    for a in json.loads(r["aligned_json"] or "[]")
                ),
            )
            for r in rows
        ]

    def set_alignment(
        self, meeting_id: str, aligned: Mapping[str, Sequence[tuple[str, float]]]
    ) -> None:
        """The links of one linking run: each named line gets its own, every other line of the
        meeting none."""
        self._conn.execute("BEGIN")
        try:
            self._conn.execute(
                "UPDATE note_block SET aligned_json = NULL WHERE meeting_id = ?", (meeting_id,)
            )
            for line_id, links in aligned.items():
                self._conn.execute(
                    "UPDATE note_block SET aligned_json = ? WHERE id = ? AND meeting_id = ?",
                    (_aligned_json(links), _row_id(meeting_id, line_id), meeting_id),
                )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise


def _row_id(meeting_id: str, line_id: str) -> str:
    """`note_block.id` is unique across meetings and a window's line ids only within one."""
    return f"{meeting_id}:{line_id}"


def _aligned_json(links: Sequence[tuple[str, float]]) -> str | None:
    if not links:
        return None
    return json.dumps([{"utterance_id": uid, "score": score} for uid, score in links])
