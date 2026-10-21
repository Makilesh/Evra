"""Generated notes (BUILD.md §7.7, §8.2): a `generation` row per note (the newest is current)
and one `output_block` per bullet, summary first. M5 adds editing and restoring."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from evra.notes.validate import CheckedBullet, CheckedNote
from evra.store.meetings import new_id, now_ms

SUMMARY = "summary"


@dataclass(frozen=True)
class OutputBlock:
    id: str
    section: str
    position: int
    text: str
    citations: tuple[str, ...]
    provenance: str  # generated | edited | user


@dataclass(frozen=True)
class StoredNote:
    generation_id: str
    model: str
    template: str
    prompt_version: str
    created_at: int
    dropped_claims: int
    blocks: tuple[OutputBlock, ...]


class NoteStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save_generation(
        self,
        *,
        meeting_id: str,
        transcript_version_id: str,
        note: CheckedNote,
        provider: str,
        model: str,
        prompt_version: str,
        template: str,
        tokens_in: int,
        tokens_out: int,
    ) -> str:
        generation_id = new_id()
        groups: list[tuple[str, tuple[CheckedBullet, ...]]] = [(SUMMARY, note.summary)]
        groups += [(s.section_id, s.bullets) for s in note.sections]
        self._conn.execute("BEGIN")
        try:
            self._conn.execute(
                "UPDATE generation SET is_current = 0 WHERE meeting_id = ?", (meeting_id,)
            )
            self._conn.execute(
                "INSERT INTO generation (id, meeting_id, created_at, llm_provider, llm_model,"
                " prompt_version, template, transcript_version_id, tokens_in, tokens_out,"
                " dropped_claims, is_current) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)",
                (
                    generation_id,
                    meeting_id,
                    now_ms(),
                    provider,
                    model,
                    prompt_version,
                    template,
                    transcript_version_id,
                    tokens_in,
                    tokens_out,
                    note.dropped,
                ),
            )
            position = 0
            for section, bullets in groups:
                for bullet in bullets:
                    self._conn.execute(
                        "INSERT INTO output_block (id, generation_id, meeting_id, section,"
                        " position, text, citations_json, provenance)"
                        " VALUES (?, ?, ?, ?, ?, ?, ?, 'generated')",
                        (
                            new_id(),
                            generation_id,
                            meeting_id,
                            section,
                            position,
                            bullet.text,
                            json.dumps(list(bullet.citations)),
                        ),
                    )
                    position += 1
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return generation_id

    def current_note(self, meeting_id: str) -> StoredNote | None:
        row = self._conn.execute(
            "SELECT * FROM generation WHERE meeting_id = ? AND is_current = 1", (meeting_id,)
        ).fetchone()
        if row is None:
            return None
        blocks = self._conn.execute(
            "SELECT * FROM output_block WHERE generation_id = ? ORDER BY position", (row["id"],)
        ).fetchall()
        return StoredNote(
            generation_id=row["id"],
            model=row["llm_model"],
            template=row["template"],
            prompt_version=row["prompt_version"],
            created_at=row["created_at"],
            dropped_claims=row["dropped_claims"] or 0,
            blocks=tuple(
                OutputBlock(
                    b["id"],
                    b["section"],
                    b["position"],
                    b["text"],
                    tuple(json.loads(b["citations_json"])),
                    b["provenance"],
                )
                for b in blocks
            ),
        )
