"""Action items, decisions and open questions (BUILD.md §7.5-7.6, A4-A6): one focused call per
kind over the same meeting context, then every item is checked like a note point.

Order inside a job (§8.3): the three chat calls run back to back, then one `check_all` covers
every item, so its embedding request comes after the model's replies. A long call's items come
from its parts' digests instead (`evra.notes.mapreduce`), through the same steps: `check_items`,
then `settle_items`. Nothing here logs or raises with item or transcript text."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
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
# the template section each kind fills (a section with `source: extraction`, BUILD.md §7.6)
ITEM_SECTIONS: Mapping[ItemKind, str] = MappingProxyType(
    {"action_item": "action_items", "decision": "decisions", "open_question": "open_questions"}
)
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
    prompt_versions: tuple[str, ...]  # per successful kind: "a4-v2", "a5-v2+a9-v1", ...
    tokens_in: int
    tokens_out: int
    cached_tokens: int
    seconds: float
    failed_kinds: tuple[ItemKind, ...]
    tasks_as_decisions: int = 0  # decisions left out as repeats of an action item (not drops)
    # a long call's items that A3 removed (RB27), not drops: repeats of an earlier one, and
    # questions the meeting answers later
    repeats_removed: int = 0
    answered_removed: int = 0


@dataclass(frozen=True)
class RawItem:
    """An item as a model listed it, before the check: it cites prompt ids (u:3)."""

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


def join_citations(first: Sequence[str], more: Sequence[str]) -> tuple[str, ...]:
    """The citations of both, in order, each once."""
    return tuple(dict.fromkeys([*first, *more]))


def _parse(kind: ItemKind, value: BaseModel) -> list[RawItem]:
    if isinstance(value, ActionItems):
        return [
            RawItem(kind, i.text, tuple(i.citations), i.owner, i.due, i.confidence)
            for i in value.items
        ]
    if isinstance(value, Decisions):
        return [
            RawItem(kind, d.statement, tuple(d.citations), d.made_by, None, None)
            for d in value.items
        ]
    assert isinstance(value, OpenQuestions)
    return [
        RawItem(kind, q.question, tuple(q.citations), q.raised_by, None, None) for q in value.items
    ]


def _without_restated_tasks(kept: Sequence[CheckedItem]) -> tuple[list[CheckedItem], int]:
    """A decision that repeats a kept action item ("You will send the quote by Friday") is that
    task, already listed: it is left out and counted, not dropped (RB20)."""
    tasks = [k for k in kept if k.kind == "action_item"]
    left: list[CheckedItem] = []
    restated = 0
    for item in kept:
        if item.kind == "decision" and any(
            is_repeat(t.text, t.citations, item.text, item.citations) for t in tasks
        ):
            restated += 1
            continue
        left.append(item)
    return left, restated


def _claim(item: RawItem) -> str:
    """What the check reads: an action item's due phrase is part of the claim."""
    text = f"{item.text} {item.due}" if item.due else item.text
    return text[:MAX_CLAIM_CHARS]


def check_items(
    raw: Sequence[RawItem],
    *,
    grounder: Grounder,
    names: Mapping[str, str] | None,
    reasons: Counter[str],
) -> list[CheckedItem | None]:
    """Each item's owner, then one check of every item (its one embedding batch, RB8): in
    order, the item checked, or None for one dropped, its reason counted."""
    labels = names or {}
    owners = [normalise_owner(item.owner, names=labels) for item in raw]
    verdicts = grounder.check_all(
        [NoteBullet(text=_claim(i), citations=list(i.citations)) for i in raw]
    )
    checked: list[CheckedItem | None] = []
    for item, owner, (bullet, reason) in zip(raw, owners, verdicts, strict=True):
        if bullet is None:
            reasons[reason] += 1
            checked.append(None)
            continue
        checked.append(
            CheckedItem(item.kind, item.text, bullet.citations, owner, item.due, item.confidence)
        )
    return checked


def settle_items(
    items: Sequence[CheckedItem], reasons: Counter[str]
) -> tuple[list[CheckedItem], int]:
    """Repeats within a kind are kept once: the earliest, citing its repeats' lines too (RB11,
    RB24; each repeat counts as a "duplicate" drop). Then a decision that restates a kept task
    is left to the task (RB20). Returns the items and how many decisions were left out."""
    kept: list[CheckedItem] = []
    for item in items:
        for n, earlier in enumerate(kept):
            if earlier.kind == item.kind and is_repeat(
                earlier.text, earlier.citations, item.text, item.citations
            ):
                kept[n] = replace(
                    earlier, citations=join_citations(earlier.citations, item.citations)
                )
                reasons["duplicate"] += 1
                break
        else:
            kept.append(item)
    return _without_restated_tasks(kept)


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
    raw: list[RawItem] = []
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
    checked = check_items(raw, grounder=grounder, names=names, reasons=reasons)
    kept, tasks_as_decisions = settle_items([c for c in checked if c is not None], reasons)
    dropped = sum(reasons.values())
    log.info(
        "items_extracted",
        kept=len(kept),
        dropped=dropped,
        reasons=dict(reasons),
        failed=failed,
        tasks_as_decisions=tasks_as_decisions,
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
        tasks_as_decisions=tasks_as_decisions,
    )
