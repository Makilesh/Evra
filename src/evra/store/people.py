"""People the owner names (BUILD.md §6.5, D14). A person exists only because the owner said who a
1:1 was with; the owner's own person ("You", made with a meeting's speakers) is not one of them,
and no one else can take that name. Two spellings of one name ("priya", "Priya ") are one person.
No voiceprints here (M4). A name is content: it goes to the owner's window and the prompts about
their meetings, never to a log."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Literal

from evra.store.db import writing
from evra.store.meetings import new_id

MAX_NAME = 80
OWNER_NAME = "You"  # the owner's own person: how Evra shows them, which no one else can take

NameRefusal = Literal["invalid", "reserved"]
Renamed = Literal["ok", "taken", "invalid", "unknown", "reserved"]


@dataclass(frozen=True)
class Person:
    id: str
    name: str


class NameRefused(ValueError):
    """A name no one can be given: empty or too long ("invalid"), or the owner's ("reserved")."""

    def __init__(self, reason: NameRefusal) -> None:
        super().__init__(reason)
        self.reason: NameRefusal = reason


def clean_name(name: str) -> str | None:
    """The name with its whitespace collapsed, or None when that leaves nothing or more than
    MAX_NAME characters."""
    cleaned = " ".join(name.split())
    return cleaned if 1 <= len(cleaned) <= MAX_NAME else None


def is_reserved(name: str) -> bool:
    """ "You" is how Evra shows the owner, ignoring case and spaces."""
    return "".join(name.split()).casefold() == OWNER_NAME.casefold()


def _checked(name: str) -> str:
    cleaned = clean_name(name)
    if cleaned is None:
        raise NameRefused("invalid")
    if is_reserved(cleaned):
        raise NameRefused("reserved")
    return cleaned


class PersonStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def list_people(self) -> list[Person]:
        """Everyone the owner has named, by name; never the owner."""
        rows = self._conn.execute(
            "SELECT id, display_name FROM person WHERE is_owner = 0"
        ).fetchall()
        people = [Person(r["id"], r["display_name"]) for r in rows]
        return sorted(people, key=lambda p: (p.name.casefold(), p.name, p.id))

    def find_or_create(self, name: str) -> Person:
        """The person with this name, whatever its case or spacing, else a new one with the
        name as typed (tidied). NameRefused for an invalid or reserved name. Inside the
        caller's transaction when there is one, so a refused link leaves no one behind."""
        cleaned = _checked(name)
        with writing(self._conn):
            found = self._named(cleaned)
            if found is not None:
                return found
            person = Person(new_id(), cleaned)
            self._conn.execute(
                "INSERT INTO person (id, display_name, is_owner) VALUES (?, ?, 0)",
                (person.id, person.name),
            )
            return person

    def rename(self, person_id: str, name: str) -> Renamed:
        """Give a person another name: "taken" when someone else has it (whatever its case or
        spacing), "reserved" for "You", "invalid" for an empty or too long name, "unknown" for
        no such person (the owner included)."""
        cleaned = clean_name(name)
        if cleaned is None:
            return "invalid"
        if is_reserved(cleaned):
            return "reserved"
        with writing(self._conn):
            if not self.exists(person_id):
                return "unknown"
            other = self._named(cleaned)
            if other is not None and other.id != person_id:
                return "taken"
            self._conn.execute(
                "UPDATE person SET display_name = ? WHERE id = ?", (cleaned, person_id)
            )
        return "ok"

    def remove(self, person_id: str) -> bool:
        """Forget a person: their meetings go back to "Them", then the person goes (and,
        through the schema, whatever belongs only to them). False for no such person."""
        with writing(self._conn):
            if not self.exists(person_id):
                return False
            self._conn.execute(
                "UPDATE speaker SET person_id = NULL WHERE person_id = ?", (person_id,)
            )
            self._conn.execute("DELETE FROM person WHERE id = ?", (person_id,))
        return True

    def exists(self, person_id: str) -> bool:
        """One of the people the owner named (never the owner)."""
        row = self._conn.execute(
            "SELECT 1 FROM person WHERE id = ? AND is_owner = 0", (person_id,)
        ).fetchone()
        return row is not None

    def _named(self, cleaned: str) -> Person | None:
        """The person whose name matches, ignoring case (names are stored tidied)."""
        key = cleaned.casefold()
        return next((p for p in self.list_people() if p.name.casefold() == key), None)
