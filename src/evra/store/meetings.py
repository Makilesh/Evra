"""Meetings, transcript versions and utterances (BUILD.md §8.2). One store per connection."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from evra.asr.engine import Word


def new_id() -> str:
    return uuid.uuid4().hex


def now_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True)
class Utterance:
    id: str
    version_id: str
    meeting_id: str
    seq: int
    channel: int
    speaker_id: str | None
    start_ms: int
    end_ms: int
    text: str
    words: tuple[Word, ...]
    confidence: float | None


class MeetingStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create_meeting(
        self,
        *,
        title: str,
        mode: str,
        situation: str,
        template: str,
        started_at_ms: int | None = None,
    ) -> str:
        meeting_id, now = new_id(), now_ms()
        self._conn.execute(
            "INSERT INTO meeting (id, title, started_at, mode, situation, template, state,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'recording', ?, ?)",
            (meeting_id, title, started_at_ms or now, mode, situation, template, now, now),
        )
        return meeting_id

    def finish_meeting(self, meeting_id: str, *, state: str = "ready") -> None:
        now = now_ms()
        self._conn.execute(
            "UPDATE meeting SET ended_at = COALESCE(ended_at, ?), state = ?, updated_at = ?"
            " WHERE id = ?",
            (now, state, now, meeting_id),
        )

    def get_meeting(self, meeting_id: str) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM meeting WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            raise KeyError(meeting_id)
        return dict(row)

    def latest_meeting_id(self) -> str | None:
        row = self._conn.execute(
            "SELECT id FROM meeting ORDER BY started_at DESC, created_at DESC LIMIT 1"
        ).fetchone()
        return None if row is None else str(row["id"])

    def current_transcript_version(self, meeting_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT id FROM transcript_version WHERE meeting_id = ? AND is_current = 1",
            (meeting_id,),
        ).fetchone()
        return None if row is None else str(row["id"])

    def create_transcript_version(self, meeting_id: str, *, kind: str, model: str) -> str:
        version_id = new_id()
        self._conn.execute("BEGIN")
        try:
            self._conn.execute(
                "UPDATE transcript_version SET is_current = 0 WHERE meeting_id = ?", (meeting_id,)
            )
            self._conn.execute(
                "INSERT INTO transcript_version (id, meeting_id, kind, model, created_at,"
                " is_current) VALUES (?, ?, ?, ?, ?, 1)",
                (version_id, meeting_id, kind, model, now_ms()),
            )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return version_id

    def add_utterance(
        self,
        *,
        version_id: str,
        meeting_id: str,
        channel: int,
        start_ms: int,
        end_ms: int,
        text: str,
        words: Sequence[Word] = (),
        confidence: float | None = None,
        speaker_id: str | None = None,
    ) -> Utterance:
        utterance_id = new_id()
        seq = self._conn.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 FROM utterance WHERE version_id = ?", (version_id,)
        ).fetchone()[0]
        words_json = json.dumps([[w.start_ms, w.end_ms, w.text] for w in words]) if words else None
        self._conn.execute(
            "INSERT INTO utterance (id, version_id, meeting_id, seq, channel, speaker_id,"
            " start_ms, end_ms, text, words_json, confidence)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                utterance_id,
                version_id,
                meeting_id,
                seq,
                channel,
                speaker_id,
                start_ms,
                end_ms,
                text,
                words_json,
                confidence,
            ),
        )
        return Utterance(
            utterance_id,
            version_id,
            meeting_id,
            seq,
            channel,
            speaker_id,
            start_ms,
            end_ms,
            text,
            tuple(words),
            confidence,
        )

    def utterances(self, version_id: str) -> list[Utterance]:
        rows = self._conn.execute(
            "SELECT * FROM utterance WHERE version_id = ? ORDER BY start_ms, seq", (version_id,)
        ).fetchall()
        return [
            Utterance(
                r["id"],
                r["version_id"],
                r["meeting_id"],
                r["seq"],
                r["channel"],
                r["speaker_id"],
                r["start_ms"],
                r["end_ms"],
                r["text"],
                tuple(Word(*w) for w in json.loads(r["words_json"])) if r["words_json"] else (),
                r["confidence"],
            )
            for r in rows
        ]
