"""Who spoke in a meeting (BUILD.md §8.2). In 1:1 mode a meeting has two speakers from its mode,
no voices needed: the owner in the room ("You", linked to the owner's `person`) and the other
person on the call ("Them"), linked to a person once the owner says who the 1:1 was with. M4's
identity work later fills the same rows from voiceprints."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from evra.store.db import writing
from evra.store.meetings import new_id
from evra.store.people import OWNER_NAME, Person, PersonStore

THEM = "Them"  # the other person's label in a 1:1, on their speaker row and in the transcript
# A meeting's remote "Them" speaker, with the person the owner said it was.
_NAMED = (
    "SELECT s.meeting_id, p.id, p.display_name FROM speaker s JOIN person p ON p.id = s.person_id"
    " WHERE s.namespace = 'remote' AND s.label = ? AND p.is_owner = 0"
)


def names_for(person: Person | None) -> dict[str, str]:
    """The labels a 1:1 shows, mapped to who they stand for: {"Them": "Priya"} once the owner
    has said who it was with, else none."""
    return {} if person is None else {THEM: person.name}


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
        with writing(self._conn):
            return self._pair(meeting_id)

    def set_person(self, meeting_id: str, person_id: str | None) -> None:
        """Say who the 1:1 was with: its remote speaker ("Them") stands for that person from now
        on, in the transcript, the note and every prompt about the meeting; None says no one.
        KeyError for an unknown meeting, or a person the owner never named (the owner too)."""
        with writing(self._conn):
            meeting = self._conn.execute("SELECT 1 FROM meeting WHERE id = ?", (meeting_id,))
            if meeting.fetchone() is None:
                raise KeyError(meeting_id)
            if person_id is not None and not PersonStore(self._conn).exists(person_id):
                raise KeyError(person_id)
            them = self._pair(meeting_id).them
            self._conn.execute("UPDATE speaker SET person_id = ? WHERE id = ?", (person_id, them))

    def person_for(self, meeting_id: str) -> Person | None:
        """Who the 1:1 was with, once the owner has said; a read, it makes no speakers."""
        row = self._conn.execute(
            f"{_NAMED} AND s.meeting_id = ? ORDER BY s.rowid LIMIT 1", (THEM, meeting_id)
        ).fetchone()
        return None if row is None else Person(row["id"], row["display_name"])

    def people_by_meeting(self) -> dict[str, Person]:
        """Who each 1:1 was with, for every meeting whose person the owner has said."""
        found: dict[str, Person] = {}
        for row in self._conn.execute(f"{_NAMED} ORDER BY s.rowid", (THEM,)).fetchall():
            found.setdefault(row["meeting_id"], Person(row["id"], row["display_name"]))
        return found

    def _pair(self, meeting_id: str) -> OneOnOne:
        return OneOnOne(
            you=self._speaker(meeting_id, "room", "You", self._owner()),
            them=self._speaker(meeting_id, "remote", THEM, None),
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
