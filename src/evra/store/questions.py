"""Questions asked about a meeting and their checked answers (one `question` row each)."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from evra.notes.ask import HISTORY_TURNS, AskResult, Exchange
from evra.notes.validate import CheckedBullet
from evra.store.meetings import new_id, now_ms


@dataclass(frozen=True)
class StoredQuestion:
    id: str
    meeting_id: str
    asked_at: int
    text: str
    state: str  # asking | answered | not_found | unchecked | failed
    points: tuple[CheckedBullet, ...]
    reason: str | None
    excerpt: bool
    model: str | None


def _stored(row: sqlite3.Row) -> StoredQuestion:
    raw = json.loads(row["answer_json"]) if row["answer_json"] else []
    return StoredQuestion(
        id=row["id"],
        meeting_id=row["meeting_id"],
        asked_at=row["asked_at"],
        text=row["text"],
        state=row["state"],
        points=tuple(CheckedBullet(p["text"], tuple(p["citations"])) for p in raw),
        reason=row["reason"],
        excerpt=bool(row["excerpt"]),
        model=row["llm_model"],
    )


class QuestionStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def add(self, meeting_id: str, text: str) -> StoredQuestion:
        question_id = new_id()
        self._conn.execute(
            "INSERT INTO question (id, meeting_id, asked_at, text, state)"
            " VALUES (?, ?, ?, ?, 'asking')",
            (question_id, meeting_id, now_ms(), text),
        )
        return self.get(question_id)

    def answer(
        self, question_id: str, result: AskResult, *, transcript_version_id: str
    ) -> StoredQuestion:
        points = [{"text": p.text, "citations": list(p.citations)} for p in result.points]
        self._conn.execute(
            "UPDATE question SET state = ?, answer_json = ?, excerpt = ?, llm_model = ?,"
            " prompt_version = ?, transcript_version_id = ?, tokens_in = ?, tokens_out = ?,"
            " dropped_claims = ?, seconds = ? WHERE id = ?",
            (
                result.state,
                json.dumps(points),
                int(result.excerpt),
                result.model,
                result.prompt_version,
                transcript_version_id,
                result.tokens_in,
                result.tokens_out,
                result.dropped,
                result.seconds,
                question_id,
            ),
        )
        return self.get(question_id)

    def fail(self, question_id: str, reason: str) -> StoredQuestion:
        self._conn.execute(
            "UPDATE question SET state = 'failed', reason = ? WHERE id = ?", (reason, question_id)
        )
        return self.get(question_id)

    def get(self, question_id: str) -> StoredQuestion:
        row = self._conn.execute("SELECT * FROM question WHERE id = ?", (question_id,)).fetchone()
        if row is None:
            raise KeyError(question_id)
        return _stored(row)

    def for_meeting(self, meeting_id: str) -> list[StoredQuestion]:
        rows = self._conn.execute(
            "SELECT * FROM question WHERE meeting_id = ? ORDER BY asked_at, rowid", (meeting_id,)
        ).fetchall()
        return [_stored(r) for r in rows]

    def history(self, meeting_id: str, limit: int = HISTORY_TURNS) -> list[Exchange]:
        rows = self._conn.execute(
            "SELECT * FROM question WHERE meeting_id = ? AND state IN ('answered', 'not_found')"
            " ORDER BY asked_at DESC, rowid DESC LIMIT ?",
            (meeting_id, limit),
        ).fetchall()
        stored = [_stored(r) for r in reversed(rows)]
        return [Exchange(q.text, tuple(p.text for p in q.points)) for q in stored]

    def interrupted(self) -> int:
        cursor = self._conn.execute(
            "UPDATE question SET state = 'failed', reason = 'interrupted' WHERE state = 'asking'"
        )
        return cursor.rowcount
