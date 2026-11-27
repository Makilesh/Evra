"""A person's prep brief (Plan C, A13): one kept per person, the newest. Each point keeps the
meetings it cites, and the brief the meetings it was written from. Forgetting the person deletes
it, through the schema (`brief.person_id ... ON DELETE CASCADE`, D14). A brief is content: it
goes to the owner's window only, never to a log."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from evra.notes.brief import BriefResult
from evra.store.db import writing
from evra.store.meetings import new_id, now_ms
from evra.store.people import PersonStore


@dataclass(frozen=True)
class BriefPoint:
    text: str
    meetings: tuple[str, ...]  # the meetings it cites, by id, in its order


@dataclass(frozen=True)
class StoredBrief:
    id: str
    person_id: str
    created_at: int
    points: tuple[BriefPoint, ...]
    meetings: tuple[str, ...]  # what it was written from, newest first
    model: str | None
    prompt_version: str | None


def _stored(row: sqlite3.Row) -> StoredBrief:
    return StoredBrief(
        id=row["id"],
        person_id=row["person_id"],
        created_at=row["created_at"],
        points=tuple(
            BriefPoint(p["text"], tuple(p["meetings"])) for p in json.loads(row["points_json"])
        ),
        meetings=tuple(json.loads(row["meetings_json"])),
        model=row["llm_model"],
        prompt_version=row["prompt_version"],
    )


class BriefStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, person_id: str, result: BriefResult) -> StoredBrief | None:
        """Keep a written brief in place of the person's earlier one, each m:<n> it cites turned
        into the meeting it stood for. None when the person was forgotten meanwhile."""
        meeting_of = {source.alias: source.meeting_id for source in result.sources}
        points = [
            {"text": p.text, "meetings": [meeting_of[c] for c in p.citations if c in meeting_of]}
            for p in result.points
        ]
        brief_id = new_id()
        with writing(self._conn):
            if not PersonStore(self._conn).exists(person_id):
                return None
            self._conn.execute("DELETE FROM brief WHERE person_id = ?", (person_id,))
            self._conn.execute(
                "INSERT INTO brief (id, person_id, created_at, points_json, meetings_json,"
                " llm_model, prompt_version) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    brief_id,
                    person_id,
                    now_ms(),
                    json.dumps(points),
                    json.dumps([source.meeting_id for source in result.sources]),
                    result.model,
                    result.prompt_version,
                ),
            )
        return self.latest(person_id)

    def latest(self, person_id: str) -> StoredBrief | None:
        row = self._conn.execute(
            "SELECT * FROM brief WHERE person_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1",
            (person_id,),
        ).fetchone()
        return None if row is None else _stored(row)
