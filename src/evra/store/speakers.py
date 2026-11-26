"""Who spoke in a meeting (BUILD.md §8.2). In 1:1 mode a meeting has two speakers from its mode,
no voices needed: the owner in the room ("You", linked to the owner's `person`) and the other
person on the call ("Them"). M4's identity work later fills the same rows from voiceprints."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from evra.store.meetings import new_id

OWNER_NAME = "You"


@dataclass(frozen=True)
class OneOnOne:
    you: str  # speaker ids
    them: str


class SpeakerStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def one_on_one(self, meeting_id: str) -> OneOnOne:
        """The meeting's two speakers, created the first time they are needed. Inside the caller's
        transaction when there is one; otherwise in its own, so two callers never make two."""
        if self._conn.in_transaction:
            return self._pair(meeting_id)
        self._conn.execute("BEGIN IMMEDIATE")
        try:
            pair = self._pair(meeting_id)
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return pair

    def _pair(self, meeting_id: str) -> OneOnOne:
        return OneOnOne(
            you=self._speaker(meeting_id, "room", "You", self._owner()),
            them=self._speaker(meeting_id, "remote", "Them", None),
        )

    def _owner(self) -> str:
        """The one owner `person` of the whole database."""
        row = self._conn.execute(
            "SELECT id FROM person WHERE is_owner = 1 ORDER BY rowid LIMIT 1"
        ).fetchone()
        if row is not None:
            return str(row["id"])
        person_id = new_id()
        self._conn.execute(
            "INSERT INTO person (id, display_name, is_owner) VALUES (?, ?, 1)",
            (person_id, OWNER_NAME),
        )
        return person_id

    def _speaker(self, meeting_id: str, namespace: str, label: str, person_id: str | None) -> str:
        row = self._conn.execute(
            "SELECT id FROM speaker WHERE meeting_id = ? AND namespace = ? AND label = ?"
            " ORDER BY rowid LIMIT 1",
            (meeting_id, namespace, label),
        ).fetchone()
        if row is not None:
            return str(row["id"])
        speaker_id = new_id()
        self._conn.execute(
            "INSERT INTO speaker (id, meeting_id, namespace, label, person_id, source)"
            " VALUES (?, ?, ?, ?, ?, 'mode')",
            (speaker_id, meeting_id, namespace, label, person_id),
        )
        return speaker_id
