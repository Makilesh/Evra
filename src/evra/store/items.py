"""Action items, decisions and open questions as records (BUILD.md §8.2, Plan B), each kept with
the generation that found it. An action item also has a status the owner sets: open, done or
dismissed. When the note is written again, a new action item that repeats one of the meeting's
earlier ones keeps that one's status, so a Done tick survives a rewrite. Item text is content: it
goes to the owner's window only, never to a log."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from evra.notes.extract import ALL_KINDS, CheckedItem, ItemKind, is_repeat
from evra.store.meetings import new_id, now_ms
from evra.store.speakers import OneOnOne, SpeakerStore

ItemStatus = Literal["open", "done", "dismissed"]
STATUSES: tuple[ItemStatus, ...] = ("open", "done", "dismissed")
# each kind's table and the column naming who owns, made or raised it
_TABLES: dict[ItemKind, tuple[str, str]] = {
    "action_item": ("action_item", "owner_speaker_id"),
    "decision": ("decision", "made_by_speaker_id"),
    "open_question": ("open_question", "raised_by_speaker_id"),
}


@dataclass(frozen=True)
class StoredItem:
    id: str
    kind: ItemKind
    text: str
    owner: str | None  # the speaker's label: "You" or "Them"
    due: str | None
    citations: tuple[str, ...]  # utterance ids, and "user"
    status: str  # open | done | dismissed; a decision or a question is always open


@dataclass(frozen=True)
class _Earlier:
    text: str
    citations: tuple[str, ...]
    status: str
    changed_at: int | None


def _speaker(pair: OneOnOne | None, owner: str | None) -> str | None:
    if pair is None or owner is None:
        return None
    return {"You": pair.you, "Them": pair.them}.get(owner)


def _carried(earlier: Sequence[_Earlier], item: CheckedItem) -> tuple[str, int | None]:
    """The status of the earlier action item this one repeats, the newest note's first (the same
    words, or similar words about a common line: one line can hold two tasks)."""
    for old in earlier:
        if is_repeat(old.text, old.citations, item.text, item.citations):
            return old.status, old.changed_at
    return "open", None


class ItemStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, *, meeting_id: str, generation_id: str, items: Sequence[CheckedItem]) -> None:
        """Runs inside the caller's transaction: a note and its items are saved together."""
        unknown = sorted({str(i.kind) for i in items if i.kind not in _TABLES})
        if unknown:
            raise ValueError(f"unknown item kinds: {unknown}")
        owned = any(i.owner is not None for i in items)
        pair = SpeakerStore(self._conn).one_on_one(meeting_id) if owned else None
        earlier = self._earlier_actions(meeting_id, generation_id)
        for item in items:
            owner = _speaker(pair, item.owner)
            citations = json.dumps(list(item.citations))
            if item.kind == "action_item":
                status, changed_at = _carried(earlier, item)
                self._conn.execute(
                    "INSERT INTO action_item (id, meeting_id, generation_id, text,"
                    " owner_speaker_id, due, status, confidence, citations_json,"
                    " status_changed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        new_id(),
                        meeting_id,
                        generation_id,
                        item.text,
                        owner,
                        item.due,
                        status,
                        item.confidence,
                        citations,
                        changed_at,
                    ),
                )
                continue
            table, column = _TABLES[item.kind]
            self._conn.execute(
                f"INSERT INTO {table} (id, meeting_id, generation_id, text, {column},"
                " citations_json) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id(), meeting_id, generation_id, item.text, owner, citations),
            )

    def for_generation(self, generation_id: str) -> list[StoredItem]:
        """A generation's items: action items, then decisions, then open questions, each in the
        order they were found."""
        found: list[StoredItem] = []
        for kind in ALL_KINDS:
            table, column = _TABLES[kind]
            due, status = ("i.due", "i.status") if kind == "action_item" else ("NULL", "'open'")
            rows = self._conn.execute(
                f"SELECT i.id, i.text, i.citations_json, {due} AS due, {status} AS status,"
                f" s.label AS owner FROM {table} i LEFT JOIN speaker s ON s.id = i.{column}"
                " WHERE i.generation_id = ? ORDER BY i.rowid",
                (generation_id,),
            ).fetchall()
            found += [
                StoredItem(
                    r["id"],
                    kind,
                    r["text"],
                    r["owner"],
                    r["due"],
                    tuple(json.loads(r["citations_json"])),
                    r["status"],
                )
                for r in rows
            ]
        return found

    def set_status(self, item_id: str, status: str) -> bool:
        """Tick an action item done, dismiss it, or open it again. Only those three values, and
        only action items; the time of the change is kept."""
        if status not in STATUSES:
            return False
        cursor = self._conn.execute(
            "UPDATE action_item SET status = ?, status_changed_at = ? WHERE id = ?",
            (status, now_ms(), item_id),
        )
        return cursor.rowcount == 1

    def _earlier_actions(self, meeting_id: str, generation_id: str) -> list[_Earlier]:
        rows = self._conn.execute(
            "SELECT a.text, a.citations_json, a.status, a.status_changed_at FROM action_item a"
            " JOIN generation g ON g.id = a.generation_id"
            " WHERE a.meeting_id = ? AND a.generation_id != ?"
            " ORDER BY g.created_at DESC, g.rowid DESC, a.rowid",
            (meeting_id, generation_id),
        ).fetchall()
        return [
            _Earlier(
                r["text"],
                tuple(json.loads(r["citations_json"])),
                r["status"],
                r["status_changed_at"],
            )
            for r in rows
        ]
