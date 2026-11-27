"""JSON-ready views of meetings for the window (M3c spec §3.3). Their text goes only to the
user's own window, never to logs."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from evra.notes.extract import ITEM_SECTIONS
from evra.notes.templates import load_template
from evra.store.items import ItemStore, StoredItem
from evra.store.meetings import MeetingStore, Utterance
from evra.store.notepad import NoteLine, NotepadStore
from evra.store.notes import SUMMARY, NoteStore, StoredNote
from evra.store.questions import QuestionStore, StoredQuestion
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


def item_text(kind: str, owner: str | None, text: str, due: str | None) -> str:
    """An item as the note shows it. A task names its owner first, and its due date once:
    "You: Send the vendor quote (by Friday)". A decision or a question stands alone; who made
    or raised it stays in the record."""
    shown = f"{owner}: {text}" if owner and kind == "action_item" else text
    if due and due.casefold() not in text.casefold():
        shown = f"{shown} ({due})"
    return shown


def note_view(
    note: StoredNote, utterances: Sequence[Utterance], items: Sequence[StoredItem] = ()
) -> dict[str, Any]:
    """The summary, then the template's sections in order: the note's own points, and in the
    sections the records fill, the generation's items (a dismissed one is left out). An older
    note kept its lists as points, so those still show."""
    try:
        known = load_template(note.template).sections
    except KeyError:
        known = ()
    titles = {SUMMARY: "Summary", **{s.id: s.title for s in known}}
    starts = {u.id: u.start_ms for u in utterances}

    def cited(citations: Sequence[str]) -> list[dict[str, Any]]:
        return [{"utterance_id": c, "start_ms": starts[c]} for c in citations if c in starts]

    blocks: dict[str, list[dict[str, Any]]] = {}
    for block in note.blocks:
        blocks.setdefault(block.section, []).append(
            {"text": block.text, "citations": cited(block.citations)}
        )
    for item in items:
        if item.status == "dismissed":
            continue
        blocks.setdefault(ITEM_SECTIONS[item.kind], []).append(
            {
                "text": item_text(item.kind, item.owner, item.text, item.due),
                "citations": cited(item.citations),
                "item": {
                    "id": item.id,
                    "kind": item.kind,
                    "status": item.status,
                    "owner": item.owner,
                    "due": item.due,
                },
            }
        )
    order = [SUMMARY, *(s.id for s in known)]
    order += [sid for sid in blocks if sid not in order]  # a section the template doesn't name
    sections = [
        {
            "id": sid,
            "title": titles.get(sid) or sid.replace("_", " ").capitalize(),
            "blocks": blocks[sid],
        }
        for sid in order
        if blocks.get(sid)
    ]
    return {"model": note.model, "sections": sections}


def question_view(question: StoredQuestion, starts: Mapping[str, int]) -> dict[str, Any]:
    view: dict[str, Any] = {
        "id": question.id,
        "text": question.text,
        "asked_at": question.asked_at,
        "state": question.state,
        "points": [
            {
                "text": p.text,
                "citations": [
                    {"utterance_id": c, "start_ms": starts[c]} for c in p.citations if c in starts
                ],
            }
            for p in question.points
        ],
        "excerpt": question.excerpt,
    }
    if question.state == "failed":
        view["reason"] = question.reason
    if question.state == "answered" and question.model is not None:
        view["model"] = question.model
    return view


def note_line_view(line: NoteLine, started_at: int, starts: Mapping[str, int]) -> dict[str, Any]:
    """A typed line as the My notes tab reads it (RB2): when it was typed (epoch ms, and ms into
    the call), whether it was a long paste, and the transcript lines it is linked to, in the
    call's order (a line the transcript no longer has is left out)."""
    linked = sorted((starts[uid], uid) for uid, _ in line.aligned if uid in starts)
    at_ms = line.captured_at_ms
    return {
        "id": line.id,
        "text": line.text,
        "captured_at": None if at_ms is None else started_at + at_ms,
        "pasted": line.is_context,
        "captured_ms": at_ms,
        "phase": line.phase,
        "aligned": [{"utterance_id": uid, "start_ms": start} for start, uid in linked],
    }


def meeting_detail(conn: sqlite3.Connection, meeting_id: str) -> dict[str, Any] | None:
    store = MeetingStore(conn)
    try:
        meeting = store.get_meeting(meeting_id)
    except KeyError:
        return None
    version = store.current_transcript_version(meeting_id)
    utterances = store.utterances(version) if version else []
    note = NoteStore(conn).current_note(meeting_id)
    starts = {u.id: u.start_ms for u in utterances}
    items = ItemStore(conn).for_generation(note.generation_id) if note is not None else []
    started_at = int(meeting["started_at"])
    return {
        "meeting": meeting_summary({**meeting, "has_note": note is not None}),
        "utterances": [utterance_view(u) for u in utterances],
        "note": note_view(note, utterances, items) if note is not None else None,
        "questions": [
            question_view(q, starts) for q in QuestionStore(conn).for_meeting(meeting_id)
        ],
        "notes": [
            note_line_view(line, started_at, starts)
            for line in NotepadStore(conn).lines(meeting_id)
        ],
    }


def clean_title(title: str) -> str | None:
    cleaned = " ".join(title.split())
    return cleaned if 1 <= len(cleaned) <= MAX_TITLE else None
