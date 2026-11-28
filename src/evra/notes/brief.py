"""The prep brief (A13, Plan C): before the next 1:1 with someone, a few points from the notes of
their recent 1:1s: what is still open between them, what they said they would come back to and
what changed since the meeting before. One call. It is not about one meeting, so it has no A0:
its system message holds the notes as <notes> blocks, m:1 the newest, and A13 is the user
message. Every point must cite the notes it comes from (m:<n>) and is checked against them as a
note's point is against its lines, with the person's name known (RC3). Nothing here logs a
name, a note or a point."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

import structlog

from evra.config import LlmSettings
from evra.llm.prompt_files import load_prompt
from evra.llm.provider import ChatMessage, ChatResult, LlmProvider
from evra.llm.schemas import PrepBrief
from evra.notes.ask import output_tokens
from evra.notes.context import as_data, estimate_tokens
from evra.notes.errors import NoteTooLong
from evra.notes.structured import chat_structured
from evra.notes.validate import CheckedBullet, Grounder

log = structlog.get_logger(__name__)

BRIEF_MEETINGS = 3  # the notes a brief reads: the person's newest 1:1s that have one
NONE_OPEN = "none"
BriefState = Literal["written", "unchecked"]


@dataclass(frozen=True)
class BriefSource:
    alias: str  # "m:1" is the most recent
    meeting_id: str
    title: str
    started_at: int  # epoch ms
    note_text: str  # the note's points as lines, then its records still open (as `Decision: …`)


@dataclass(frozen=True)
class BriefResult:
    state: BriefState  # "unchecked": no point passed the check, so there is none to show
    points: tuple[CheckedBullet, ...]  # each cites its sources by alias ("m:1")
    sources: tuple[BriefSource, ...]
    model: str
    prompt_version: str
    seconds: float


def brief_settings(llm: LlmSettings) -> LlmSettings:
    """A brief needs a short reply (the note's room when the model thinks), and it holds the slot
    asking shares, so it gives up as soon as a question would. The model, its context size and
    its keep-alive stay the note's, so Ollama never reloads the model for it."""
    return llm.model_copy(
        update={
            "max_output_tokens": output_tokens(llm),
            "timeout_s": min(llm.timeout_s, llm.ask_timeout_s),
        }
    )


def _one_line(text: str) -> str:
    return " ".join(as_data(text).split())


def _notes(sources: Sequence[BriefSource]) -> str:
    """Each meeting's note as a <notes> block headed "[m:k] {title} · {date}"."""
    blocks = []
    for source in sources:
        day = datetime.fromtimestamp(source.started_at / 1000).date().isoformat()
        head = f"[{source.alias}] {_one_line(source.title)} · {day}"
        blocks.append(f"<notes>\n{head}\n{as_data(source.note_text)}\n</notes>")
    return "\n\n".join(blocks)


def brief_messages(
    person: str, sources: Sequence[BriefSource], open_items: Sequence[str]
) -> tuple[list[ChatMessage], str]:
    """The brief's system and user messages, and its prompt version. The name, the notes and the
    open promises are data: they go through `as_data`."""
    prompt = load_prompt("a13_brief")
    system, user = prompt.render(
        person=_one_line(person),
        notes=_notes(sources),
        open_items="; ".join(_one_line(item) for item in open_items) or NONE_OPEN,
        schema=json.dumps(PrepBrief.model_json_schema(), separators=(",", ":")),
    )
    return [ChatMessage("system", system), ChatMessage("user", user)], prompt.version


def write_brief(
    provider: LlmProvider,
    *,
    model: str,
    person: str,
    sources: Sequence[BriefSource],
    open_items: Sequence[str],
    settings: LlmSettings,
) -> BriefResult:
    """The brief for the next 1:1 with `person`, from `sources` (newest first) and the owner's
    `open_items` with them ("You: …", "{person}: …"). One call (a cut-off reply raises
    NoteCutOff, invalid JSON gets one A9 repair); a prompt too long for `settings` raises
    NoteTooLong. "unchecked" when no point passes the check."""
    if not sources:
        raise ValueError("a brief needs the note of at least one 1:1")
    messages, version = brief_messages(person, sources, open_items)
    room = settings.num_ctx - settings.max_output_tokens
    limit = min(settings.context_budget, room)
    needed = estimate_tokens(messages[0].content + messages[1].content)
    if needed > limit:
        raise NoteTooLong(needed, limit)

    def too_long(first: ChatResult) -> None:
        if first.tokens_in >= room:  # Ollama cut the prompt to fit its context window
            raise NoteTooLong(first.tokens_in, room)

    reply = chat_structured(
        provider,
        model,
        messages,
        PrepBrief,
        max_output_tokens=settings.max_output_tokens,
        invalid_event="brief_json_invalid",
        after_first=too_long,
    )
    if reply.repair_version:
        version = f"{version}+{reply.repair_version}"
    grounder = Grounder(
        aliases={source.alias: source.alias for source in sources},
        utterance_text={source.alias: source.note_text for source in sources},
        people=(person,),  # a note written before the person was linked says "Them" (RC3)
        nearby=0,  # m:1 and m:2 are two meetings, not two lines of one conversation
    )
    kept: list[CheckedBullet] = []
    dropped: Counter[str] = Counter()
    for checked, reason in grounder.check_all(reply.value.points):
        if checked is None:
            dropped[reason] += 1
        else:
            kept.append(checked)
    state: BriefState = "written" if kept else "unchecked"
    log.info(
        "brief_written",
        state=state,
        kept=len(kept),
        dropped=sum(dropped.values()),
        reasons=dict(dropped),
        meetings=len(sources),
        seconds=round(reply.seconds, 1),
    )
    return BriefResult(state, tuple(kept), tuple(sources), model, version, reply.seconds)
