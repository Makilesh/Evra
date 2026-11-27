"""Meeting titles (BUILD.md §7.4, A8). A meeting is called "Recording <date> <time>" until it
has a note; then the local model names it from that note, the way chat apps name a chat.
A name the user gave is never replaced. Titles are meeting content: logs get reasons and
counts, never the title.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterable, Sequence
from datetime import datetime

import structlog
from pydantic import ValidationError

from evra.config import LlmSettings
from evra.llm.prompt_files import load_part
from evra.llm.provider import ChatMessage, LlmProvider
from evra.llm.schemas import MeetingTitle
from evra.notes.context import MeetingContext, as_data, estimate_tokens
from evra.notes.errors import NoTranscript
from evra.notes.user_notes import meeting_context
from evra.notes.writer import prompt_limit
from evra.store.items import ItemStore, StoredItem
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
# A call too long for one prompt is named from its note alone (RB46), as A3 writes its note.
LONG_CALL_NOTE = (
    "This meeting is long: its note is in <note> below; the lines themselves are not shown.\n"
)
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


def as_lines(texts: Iterable[str], limit: int) -> str:
    """Texts as "- " lines, whole lines only, at most `limit` characters: how a note is read
    into a prompt (the title here, a person's brief in `services.people`)."""
    lines: list[str] = []
    used = 0
    for text in texts:
        line = "- " + " ".join(text.split())
        if used + len(line) > limit:
            break
        lines.append(line)
        used += len(line) + 1  # and its newline
    return "\n".join(lines)


def note_text(note: StoredNote, limit: int = NOTE_CHARS) -> str:
    """The note's points as lines, summary first (its stored order), whole points only."""
    return as_lines((block.text for block in note.blocks), limit)


def items_text(items: Sequence[StoredItem], limit: int = NOTE_CHARS) -> str:
    """A note with no points of its own (its lists alone, when A1 failed): its action items,
    decisions and open questions as lines, a dismissed one left out."""
    return as_lines((item.text for item in items if item.status != "dismissed"), limit)


def title_messages(context: MeetingContext, text: str) -> tuple[list[ChatMessage], str]:
    """The title call's messages on the meeting's shared context, and the prompt version. The note
    text is data: it goes through `as_data`."""
    task = load_part("a8_title")
    messages = [
        ChatMessage("system", context.system),
        ChatMessage("user", task.render(note=as_data(text))),
    ]
    return messages, f"{context.version}+{task.version}"


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
    conn: sqlite3.Connection,
    meeting_id: str,
    *,
    provider: LlmProvider,
    model: str,
    settings: LlmSettings | None = None,
) -> str | None:
    """Name a meeting from its note if it still has the placeholder title. Returns the new
    title, or None when the title stays (named already, no note, or no usable reply).
    `settings` are the title call's (`title_settings`; the defaults' when not given): a call
    whose whole transcript and the task would not fit them is named on a context with none of
    its lines (its notes stay), and one that would not fit even then keeps its placeholder.

    LLM errors reach the caller. A rename the user makes while the model thinks wins: the
    title is replaced only if it is still the placeholder that was read."""
    store = MeetingStore(conn)
    current = str(store.get_meeting(meeting_id)["title"])
    if not has_placeholder_title(current):
        return None
    note = NoteStore(conn).current_note(meeting_id)
    text = ""
    if note is not None and note.blocks:
        text = note_text(note)
    elif note is not None:  # a note of its lists alone is named from its items
        text = items_text(ItemStore(conn).for_generation(note.generation_id))
    if not text:
        return None
    # The same system message the note was written with (the meeting's shared context, its
    # notes included), so Ollama keeps the meeting's processed prompt for the first question
    # (BUILD.md 7.4). A call too long for one prompt is named from its note alone: the whole
    # call would not fit (RB46), and when even that does not, it is not named.
    try:
        context, _ = meeting_context(conn, meeting_id)
    except NoTranscript:
        return None
    messages, version = title_messages(context, text)
    limit = prompt_limit(settings or title_settings(LlmSettings()))
    if estimate_tokens(context.system + messages[1].content) > limit:
        context, _ = meeting_context(conn, meeting_id, only=(), note=LONG_CALL_NOTE)
        messages, version = title_messages(context, text)
        if estimate_tokens(context.system + messages[1].content) > limit:
            log.info("meeting_not_named", reason="too_long")
            return None
    reply = provider.chat_json(model, messages, MeetingTitle.model_json_schema())
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
    log.info(
        "meeting_named",
        model=model,
        words=len(title.split()),
        prompt=version,
    )
    return title
