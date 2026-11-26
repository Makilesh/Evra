"""Action items, decisions and open questions (BUILD.md §7.5-7.6, A4-A6): one focused call per
kind over the same meeting context, then every item is checked like a note point.

Order inside a job (§8.3): the three chat calls run back to back, then one `check_all` covers
every item, so its embedding request comes after the model's replies. Nothing here logs or
raises with item or transcript text."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from difflib import SequenceMatcher
from types import MappingProxyType
from typing import Literal

import structlog
from pydantic import BaseModel

from evra.config import LlmSettings
from evra.llm.prompt_files import load_part
from evra.llm.provider import ChatMessage, LlmProvider
from evra.llm.schemas import (
    ActionItems,
    Decisions,
    NoteBullet,
    OpenQuestions,
)
from evra.notes.context import MeetingContext
from evra.notes.errors import NoteCutOff, NoteInvalid
from evra.notes.structured import chat_structured
from evra.notes.validate import Grounder

log = structlog.get_logger(__name__)

ItemKind = Literal["action_item", "decision", "open_question"]
ALL_KINDS: tuple[ItemKind, ...] = ("action_item", "decision", "open_question")
MIN_CONFIDENCE = 0.5
SAME_TEXT = 0.9  # two items this alike repeat each other
SAME_TEXT_AND_LINE = 0.6  # ...or this alike when they cite a common line
MAX_CLAIM_CHARS = 600  # NoteBullet's limit

_PROMPTS: dict[ItemKind, tuple[str, type[BaseModel]]] = {
    "action_item": ("a4_actions", ActionItems),
    "decision": ("a5_decisions", Decisions),
    "open_question": ("a6_questions", OpenQuestions),
}
_YOU = {"you", "me", "i", "owner"}
_THEM = {"them", "they"}


@dataclass(frozen=True)
class CheckedItem:
    kind: ItemKind
    text: str
    citations: tuple[str, ...]  # utterance ids, and "user"
    owner: str | None
    due: str | None
    confidence: float | None


@dataclass(frozen=True)
class Extraction:
    items: tuple[CheckedItem, ...]
    dropped: int
    drop_reasons: Mapping[str, int]
    prompt_versions: tuple[str, ...]  # per successful kind: "a4-v1", "a5-v1+a9-v1", ...
    tokens_in: int
    tokens_out: int
    cached_tokens: int
    seconds: float
    failed_kinds: tuple[ItemKind, ...]


@dataclass(frozen=True)
class _Raw:
    kind: ItemKind
    text: str
    citations: tuple[str, ...]
    owner: str | None
    due: str | None
    confidence: float | None


def normalise_owner(
    owner: str | None, *, names: Mapping[str, str] = MappingProxyType({})
) -> str | None:
    """ "You", "Them" or None: a name the model made up becomes None (BUILD.md §7.5.5)."""
    if owner is None:
        return None
    word = " ".join(owner.split()).casefold()
    if word in _YOU:
        return "You"
    if word in _THEM:
        return "Them"
    for label, display in names.items():
        if display and word == " ".join(display.split()).casefold():
            return label
    return None


def is_repeat(
    a_text: str, a_citations: Sequence[str], b_text: str, b_citations: Sequence[str]
) -> bool:
    """Two items of one kind say the same thing: near-identical words, or similar words about a
    common line. A shared line alone is not enough: one line often holds two tasks."""
    ratio = SequenceMatcher(None, a_text.lower(), b_text.lower()).ratio()
    if ratio >= SAME_TEXT:
        return True
    return ratio >= SAME_TEXT_AND_LINE and bool(set(a_citations) & set(b_citations))


def _parse(kind: ItemKind, value: BaseModel) -> list[_Raw]:
    if isinstance(value, ActionItems):
        return [
            _Raw(kind, i.text, tuple(i.citations), i.owner, i.due, i.confidence)
            for i in value.items
        ]
    if isinstance(value, Decisions):
        return [
            _Raw(kind, d.statement, tuple(d.citations), d.made_by, None, None) for d in value.items
        ]
    assert isinstance(value, OpenQuestions)
    return [
        _Raw(kind, q.question, tuple(q.citations), q.raised_by, None, None) for q in value.items
    ]


def _claim(item: _Raw) -> str:
    """What the check reads: an action item's due phrase is part of the claim."""
    text = f"{item.text} {item.due}" if item.due else item.text
    return text[:MAX_CLAIM_CHARS]


def extract_items(
    provider: LlmProvider,
    *,
    model: str,
    context: MeetingContext,
    settings: LlmSettings,
    grounder: Grounder,
    kinds: Sequence[ItemKind] = ALL_KINDS,
    names: Mapping[str, str] | None = None,
) -> Extraction:
    reasons: Counter[str] = Counter()
    versions: list[str] = []
    failed: list[ItemKind] = []
    raw: list[_Raw] = []
    tokens_in = tokens_out = cached = 0
    seconds = 0.0
    for kind in kinds:  # the chat calls, back to back
        prompt_id, model_cls = _PROMPTS[kind]
        part = load_part(prompt_id)
        user = part.render(schema=json.dumps(model_cls.model_json_schema(), separators=(",", ":")))
        try:
            reply = chat_structured(
                provider,
                model,
                [ChatMessage("system", context.system), ChatMessage("user", user)],
                model_cls,
                max_output_tokens=settings.max_output_tokens,
                invalid_event="extraction_json_invalid",
            )
        except (NoteCutOff, NoteInvalid) as exc:
            reason = "cut_off" if isinstance(exc, NoteCutOff) else "invalid"
            log.info("extraction_kind_failed", kind=kind, reason=reason)
            failed.append(kind)
            continue
        version = part.version + (f"+{reply.repair_version}" if reply.repair_version else "")
        versions.append(version)
        tokens_in += reply.tokens_in
        tokens_out += reply.tokens_out
        cached += reply.cached_tokens
        seconds += reply.seconds
        for item in _parse(kind, reply.value):
            if item.kind == "action_item" and (item.confidence or 0.0) < MIN_CONFIDENCE:
                reasons["low_confidence"] += 1
                continue
            raw.append(item)
    labels = names or {}
    owners = [normalise_owner(item.owner, names=labels) for item in raw]
    verdicts = grounder.check_all(
        [NoteBullet(text=_claim(i), citations=list(i.citations)) for i in raw]
    )
    kept: list[CheckedItem] = []
    for item, owner, (checked, reason) in zip(raw, owners, verdicts, strict=True):
        if checked is None:
            reasons[reason] += 1
            continue
        if any(
            k.kind == item.kind and is_repeat(k.text, k.citations, item.text, checked.citations)
            for k in kept
        ):
            reasons["duplicate"] += 1
            continue
        kept.append(
            CheckedItem(item.kind, item.text, checked.citations, owner, item.due, item.confidence)
        )
    dropped = sum(reasons.values())
    log.info(
        "items_extracted",
        kept=len(kept),
        dropped=dropped,
        reasons=dict(reasons),
        failed=failed,
    )
    return Extraction(
        items=tuple(kept),
        dropped=dropped,
        drop_reasons=dict(reasons),
        prompt_versions=tuple(versions),
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cached_tokens=cached,
        seconds=seconds,
        failed_kinds=tuple(failed),
    )
