"""JSON-ready views of meetings for the window (M3c spec §3.3). Their text goes only to the
user's own window, never to logs."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from evra.notes.templates import load_template
from evra.store.meetings import MeetingStore, Utterance
from evra.store.notes import SUMMARY, NoteStore, StoredNote
from evra.transcribe.labels import speaker_label

MAX_TITLE = 200


def meeting_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    ended = row.get("ended_at")
    return {
        "id": row["id"],
        "title": row["title"],
        "started_at": row["started_at"],
        "duration_ms": None if ended is None else int(ended) - int(row["started_at"]),
        "state": row["state"],
        "has_note": bool(row.get("has_note", False)),
    }


def utterance_view(utterance: Utterance) -> dict[str, Any]:
    return {
        "id": utterance.id,
        "channel": utterance.channel,
        "speaker": speaker_label(utterance.channel),
        "start_ms": utterance.start_ms,
        "end_ms": utterance.end_ms,
        "text": utterance.text,
    }


def note_view(note: StoredNote, utterances: Sequence[Utterance]) -> dict[str, Any]:
    try:
        titles = {s.id: s.title for s in load_template(note.template).sections}
    except KeyError:
        titles = {}
    titles[SUMMARY] = "Summary"
    starts = {u.id: u.start_ms for u in utterances}
    sections: list[dict[str, Any]] = []
    for block in note.blocks:
        if not sections or sections[-1]["id"] != block.section:
            title = titles.get(block.section) or block.section.replace("_", " ").capitalize()
            sections.append({"id": block.section, "title": title, "blocks": []})
        citations = [
            {"utterance_id": c, "start_ms": starts[c]} for c in block.citations if c in starts
        ]
        sections[-1]["blocks"].append({"text": block.text, "citations": citations})
    return {"model": note.model, "sections": sections}


def meeting_detail(conn: sqlite3.Connection, meeting_id: str) -> dict[str, Any] | None:
    store = MeetingStore(conn)
    try:
        meeting = store.get_meeting(meeting_id)
    except KeyError:
        return None
    version = store.current_transcript_version(meeting_id)
    utterances = store.utterances(version) if version else []
    note = NoteStore(conn).current_note(meeting_id)
    return {
        "meeting": meeting_summary({**meeting, "has_note": note is not None}),
        "utterances": [utterance_view(u) for u in utterances],
        "note": note_view(note, utterances) if note is not None else None,
    }


def clean_title(title: str) -> str | None:
    cleaned = " ".join(title.split())
    return cleaned if 1 <= len(cleaned) <= MAX_TITLE else None
