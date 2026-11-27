"""The owner's typed notes in every prompt about a meeting (BUILD.md §7.4, A0's <user_notes>), and
the meeting's one shared context (RB1). The note job, the title (A8) and asking all build A0 with
`notes_context`, from the same transcript and the same stored lines and links, so Ollama can
reuse the prompt it already processed; `meeting_context` builds it for a stored meeting.

A note is `[n:k] (mm:ss) text || aligned: u:3, u:4` (before or after the call in place of the
time, and `(context)` for a long paste), k counting every note of the meeting in the pad's order,
so a part of a long call that shows some of them numbers them as every other prompt does."""

from __future__ import annotations

import sqlite3
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evra.notes.context import NONE, MeetingContext, as_data, build_context, line_aliases
from evra.notes.errors import NoTranscript
from evra.store.meetings import MeetingStore, Utterance
from evra.store.notepad import NoteLine, NotepadStore
from evra.transcribe.cli import format_ms


@dataclass(frozen=True)
class NotesInput:
    """A meeting's typed lines, for its prompts and its checks."""

    lines: tuple[NoteLine, ...]  # in the pad's order, with their links
    user_notes: str  # what a [user] citation is checked against (`notes_text`)


NO_NOTES = NotesInput((), "")


def _in_pad_order(lines: Sequence[NoteLine]) -> list[NoteLine]:
    return sorted(lines, key=lambda line: line.position)


def notes_text(lines: Sequence[NoteLine]) -> str:
    """Every line's text, one a line: the Grounder's `user_notes`."""
    return "\n".join(line.text for line in _in_pad_order(lines))


def notes_input(lines: Sequence[NoteLine]) -> NotesInput:
    ordered = tuple(_in_pad_order(lines))
    return NotesInput(ordered, notes_text(ordered))


def format_user_notes(
    lines: Sequence[NoteLine],
    aliases: Mapping[str, str],
    *,
    only: Collection[str] | None = None,
) -> str:
    """A0's <user_notes>: one line per note in the pad's order, its text made inert and kept on
    one line; with `only`, just those notes (by id), still numbered among all of them. A link to
    a line the transcript no longer has is left out. NONE when there is nothing to show."""
    numbers = {uid: int(alias.removeprefix("u:")) for alias, uid in aliases.items()}
    rows: list[str] = []
    for k, line in enumerate(_in_pad_order(lines), start=1):
        if only is not None and line.id not in only:
            continue
        text = " ".join(as_data(line.text).split())
        if line.is_context:
            rows.append(f"[n:{k}] (context) {text}")
            continue
        when: str = line.phase
        if line.phase == "during" and line.captured_at_ms is not None:
            when = format_ms(line.captured_at_ms)
        row = f"[n:{k}] ({when}) {text}"
        linked = sorted({numbers[uid] for uid, _ in line.aligned if uid in numbers})
        if linked:
            row += " || aligned: " + ", ".join(f"u:{n}" for n in linked)
        rows.append(row)
    return "\n".join(rows) or NONE


def notes_context(
    *,
    meeting: Mapping[str, Any],
    utterances: Sequence[Utterance],
    notes: NotesInput = NO_NOTES,
    gaps: Sequence[Mapping[str, Any]] = (),
    only: Collection[str] | None = None,
    note: str | None = None,
    shown_notes: Collection[str] | None = None,
) -> MeetingContext:
    """The meeting's A0 with its notes, linked on the whole meeting's u:1..u:N. `only` and
    `note` are build_context's (the lines printed, and the text before them); `shown_notes`
    limits the notes shown, by id."""
    user_notes = format_user_notes(notes.lines, line_aliases(utterances), only=shown_notes)
    return build_context(
        meeting=meeting,
        utterances=utterances,
        gaps=gaps,
        user_notes=user_notes,
        only=only,
        note=note,
    )


def meeting_context(
    conn: sqlite3.Connection,
    meeting_id: str,
    *,
    only: Collection[str] | None = None,
    note: str | None = None,
) -> tuple[MeetingContext, NotesInput]:
    """A stored meeting's shared context: its current transcript, and its typed lines with the
    links the last note stored. KeyError for an unknown meeting, NoTranscript for one with no
    lines."""
    store = MeetingStore(conn)
    meeting = store.get_meeting(meeting_id)
    version_id = store.current_transcript_version(meeting_id)
    utterances = store.utterances(version_id) if version_id else []
    if not utterances:
        raise NoTranscript("no transcript")
    notes = notes_input(NotepadStore(conn).lines(meeting_id))
    context = notes_context(
        meeting=meeting, utterances=utterances, notes=notes, only=only, note=note
    )
    return context, notes
