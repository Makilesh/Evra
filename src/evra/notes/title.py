"""Meeting titles (BUILD.md §7.4, A8). A meeting is called "Recording <date> <time>" until it
has a note; then the local model names it from that note, the way chat apps name a chat.
A name the user gave is never replaced. Titles are meeting content: logs get reasons and
counts, never the title.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import datetime

import structlog
from pydantic import ValidationError

from evra.config import LlmSettings
from evra.llm.prompt_files import load_prompt
from evra.llm.provider import ChatMessage, LlmProvider
from evra.llm.schemas import MeetingTitle
from evra.store.meetings import MeetingStore
from evra.store.notes import NoteStore, StoredNote

log = structlog.get_logger(__name__)

_PLACEHOLDER = re.compile(r"Recording \d{4}-\d{2}-\d{2} \d{2}:\d{2}")
# The prompt asks for at most 8 words; a few more is still a usable name, a paragraph is not.
MAX_WORDS = 12
# The note text a title is written from: plenty for "what was this about", and a short prompt
# keeps the call quick.
NOTE_CHARS = 4000
# The model is still loaded from writing the note, so a title takes seconds.
TITLE_TIMEOUT_S = 60.0
TITLE_OUTPUT_TOKENS = 256  # the least LlmSettings allows; a title needs about 20
_QUOTES = "\"'`\u2018\u2019\u201c\u201d"
_TRAILING = ".,;:!?\u2026 "


def placeholder_title(when: datetime) -> str:
    """What a meeting is called until it has a name: "Recording 2026-11-11 15:25"."""
    return f"Recording {when:%Y-%m-%d %H:%M}"


def has_placeholder_title(title: str) -> bool:
    return _PLACEHOLDER.fullmatch(title) is not None


def title_settings(llm: LlmSettings) -> LlmSettings:
    """The note's settings with a short wait and a short reply. Model, context size and
    thinking stay the same, so Ollama reuses the model the note just loaded."""
    return llm.model_copy(
        update={"timeout_s": TITLE_TIMEOUT_S, "max_output_tokens": TITLE_OUTPUT_TOKENS}
    )


def note_text(note: StoredNote, limit: int = NOTE_CHARS) -> str:
    """The note's points as lines, summary first (its stored order), whole points only."""
    lines: list[str] = []
    used = 0
    for block in note.blocks:
        line = "- " + " ".join(block.text.split())
        if used + len(line) > limit:
            break
        lines.append(line)
        used += len(line) + 1  # and its newline
    return "\n".join(lines)


def clean_generated_title(raw: str) -> str | None:
    """The model's title without wrapping quotes or trailing punctuation; None if it is not a
    usable name (empty, too long, or the placeholder again). `MeetingTitle` already capped
    its length at 120 characters."""
    title = " ".join(raw.split()).strip(_QUOTES).rstrip(_TRAILING).strip(_QUOTES).strip()
    if not any(c.isalnum() for c in title) or len(title.split()) > MAX_WORDS:
        return None
    if has_placeholder_title(title):
        return None
    return title


def name_meeting(
    conn: sqlite3.Connection, meeting_id: str, *, provider: LlmProvider, model: str
) -> str | None:
    """Name a meeting from its note if it still has the placeholder title. Returns the new
    title, or None when the title stays (named already, no note, or no usable reply).

    LLM errors reach the caller. A rename the user makes while the model thinks wins: the
    title is replaced only if it is still the placeholder that was read."""
    store = MeetingStore(conn)
    current = str(store.get_meeting(meeting_id)["title"])
    if not has_placeholder_title(current):
        return None
    note = NoteStore(conn).current_note(meeting_id)
    text = note_text(note) if note is not None else ""
    if not text:
        return None
    prompt = load_prompt("a8_title")
    system, user = prompt.render(note=text)
    reply = provider.chat_json(
        model,
        [ChatMessage("system", system), ChatMessage("user", user)],
        MeetingTitle.model_json_schema(),
    )
    if reply.truncated:
        log.info("meeting_not_named", reason="cut_off")
        return None
    try:
        draft = MeetingTitle.model_validate_json(reply.content)
    except ValidationError:
        log.info("meeting_not_named", reason="invalid")
        return None
    title = clean_generated_title(draft.title)
    if title is None:
        log.info("meeting_not_named", reason="unusable")
        return None
    if not store.rename_meeting_if(meeting_id, title, expected=current):
        log.info("meeting_not_named", reason="renamed_meanwhile")
        return None
    log.info("meeting_named", model=model, words=len(title.split()), prompt=prompt.version)
    return title
