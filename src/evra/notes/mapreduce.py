"""A long call's note in parts (BUILD.md §7.4, A2/A3; spec §4.6). Each ~10-minute window of the
call is summarised on its own (A2, a `WindowDigest` per part); one call then writes the note from
every part's digest (A3). The digests' decisions, commitments and questions become the note's
records through the same steps as A4-A6's items (`evra.notes.extract`), merged across parts.

Order (§8.3, RB30): every A2 call, then A3, then one check of every item (one embedding batch),
A3's pruning, then the note's own check. A part whose reply fails is left out (RB28). Nothing
here logs or raises with transcript, digest, note or item text."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

import structlog

from evra.config import LlmSettings
from evra.llm.prompt_files import PromptPart, load_part
from evra.llm.provider import ChatMessage, LlmProvider
from evra.llm.schemas import CombinedNote, WindowDigest, WindowPoint
from evra.notes.context import (
    ELLIPSIS,
    EN_DASH,
    MeetingContext,
    as_data,
    build_context,
    estimate_tokens,
)
from evra.notes.errors import NoteCutOff, NoteError, NoteInvalid, NoteTooLong
from evra.notes.extract import (
    ALL_KINDS,
    CheckedItem,
    Extraction,
    ItemKind,
    RawItem,
    check_items,
    is_repeat,
    join_citations,
    settle_items,
)
from evra.notes.prompt_input import combine_prompt
from evra.notes.structured import Structured, chat_structured
from evra.notes.templates import Template
from evra.notes.validate import Grounder
from evra.notes.windows import Window, split_windows
from evra.notes.writer import (
    DraftedNote,
    NoteResult,
    check_drafted,
    cut_to_fit,
    lists_only,
    prompt_limit,
)
from evra.store.meetings import Utterance
from evra.transcribe.cli import format_ms

log = structlog.get_logger(__name__)

COMBINE_NOTE = (
    "This meeting is long: its parts are summarised in <digests> below; the lines themselves"
    " are not shown.\n"
)
COMBINE_ROOM = 2  # A3's reply may use twice the usual room (RB45), if it overshoots its bound
# the digest points that become records, and the record each becomes
RECORDS: Mapping[str, ItemKind] = MappingProxyType(
    {"commitment": "action_item", "decision": "decision", "question": "open_question"}
)


@dataclass(frozen=True)
class _Part:
    window: Window
    reply: Structured[WindowDigest]
    task_version: str  # A2's, "a2-v1"


def part_note(window: Window, parts: int) -> str:
    """What a part's transcript starts with: which part it is, and when, on the lines' clock."""
    when = f"{format_ms(window.start_ms)}{EN_DASH}{format_ms(window.end_ms)}"
    return (
        f"This is part {window.index} of {parts} of the meeting ({when});"
        f" {ELLIPSIS} marks lines left out.\n"
    )


def _fits(prompt_tokens: int, settings: LlmSettings, *, reply: int | None = None) -> None:
    limit = prompt_limit(settings, reply=reply)
    if prompt_tokens > limit:
        raise NoteTooLong(prompt_tokens, limit)


def _reason(exc: NoteError) -> str:
    if isinstance(exc, NoteCutOff):
        return "cut_off"
    return "too_long" if isinstance(exc, NoteTooLong) else "invalid"


def _read_part(
    provider: LlmProvider,
    *,
    model: str,
    task: PromptPart,
    context: MeetingContext,
    window: Window,
    settings: LlmSettings,
) -> Structured[WindowDigest]:
    """A2 on one part. The part's number in the prompt is the code's; so is the one used after."""
    schema = json.dumps(WindowDigest.model_json_schema(), separators=(",", ":"))
    user = task.render(window_index=str(window.index), schema=schema)
    _fits(estimate_tokens(context.system + user), settings)
    return chat_structured(
        provider,
        model,
        [ChatMessage("system", context.system), ChatMessage("user", user)],
        WindowDigest,
        max_output_tokens=settings.max_output_tokens,
        invalid_event="digest_json_invalid",
        after_first=cut_to_fit(settings),
    )


def digests_text(parts: Sequence[_Part]) -> tuple[str, list[tuple[str, WindowPoint]]]:
    """The parts' digests as JSON for A3, one part a line, made inert; every point carries an
    id p1, p2, ... numbered across the parts in order (RB27). Also returns the points by id."""
    rows: list[str] = []
    numbered: list[tuple[str, WindowPoint]] = []
    for part in parts:
        points: list[dict[str, Any]] = []
        for point in part.reply.value.points:
            pid = f"p{len(numbered) + 1}"
            numbered.append((pid, point))
            points.append({"id": pid, **point.model_dump(exclude_none=True)})
        row = {
            "window_index": part.window.index,
            "points": points,
            "supports_notes": part.reply.value.supports_notes,
        }
        rows.append(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
    return as_data("[\n" + ",\n".join(rows) + "\n]"), numbered


def _records(numbered: Sequence[tuple[str, WindowPoint]]) -> tuple[list[RawItem], list[str]]:
    """The points that become records, as items not yet checked, and their ids. A digest gives
    no confidence, and only a commitment has a due date."""
    raw: list[RawItem] = []
    ids: list[str] = []
    for pid, point in numbered:
        kind = RECORDS.get(point.kind)
        if kind is None:
            continue
        due = point.due if kind == "action_item" else None
        raw.append(RawItem(kind, point.text, tuple(point.citations), point.owner, due, None))
        ids.append(pid)
    return raw, ids


def prune(
    checked: Sequence[CheckedItem | None], ids: Sequence[str], combined: CombinedNote
) -> tuple[list[CheckedItem | None], int, int]:
    """A3's lists applied to the checked items (RB27); they only ever remove one. A question
    listed in `answered` goes, with every kept question that repeats it (the same question read
    in two parts). A listed repeat goes when both are still kept, of one kind, and the one it
    repeats is earlier: its lines join that one's. Anything else listed is ignored. Returns the
    items (None where removed), and how many repeats and answered questions were removed."""
    items = list(checked)
    at = {pid: n for n, pid in enumerate(ids)}
    answered = 0
    for pid in combined.answered:
        n = at.get(pid)
        question = None if n is None else items[n]
        if question is None or question.kind != "open_question":
            continue
        for m, other in enumerate(items):
            if other is None or other.kind != "open_question":
                continue
            if m == n or is_repeat(question.text, question.citations, other.text, other.citations):
                items[m] = None
                answered += 1
    repeats = 0
    for pair in combined.repeats:
        later_at, earlier_at = at.get(pair.id), at.get(pair.of)
        if later_at is None or earlier_at is None or earlier_at >= later_at:
            continue
        later, earlier = items[later_at], items[earlier_at]
        if later is None or earlier is None or later.kind != earlier.kind:
            continue
        items[earlier_at] = replace(
            earlier, citations=join_citations(earlier.citations, later.citations)
        )
        items[later_at] = None
        repeats += 1
    return items, repeats, answered


def _read_parts(
    provider: LlmProvider,
    *,
    model: str,
    meeting: Mapping[str, Any],
    utterances: Sequence[Utterance],
    settings: LlmSettings,
    user_notes: str,
    on_stage: Callable[[str], None],
) -> list[_Part]:
    """A2 on every window, back to back. A part that fails is left out (a retry at temperature 0
    repeats it); when every part fails, the first error is raised."""
    windows = split_windows(utterances)
    task = load_part("a2_digest")
    parts: list[_Part] = []
    first_error: NoteError | None = None
    for window in windows:
        on_stage(f"part:{window.index}:{len(windows)}")
        context = build_context(
            meeting=meeting,
            utterances=utterances,
            user_notes=user_notes,
            only=frozenset(window.ids),
            note=part_note(window, len(windows)),
        )
        try:
            reply = _read_part(
                provider, model=model, task=task, context=context, window=window, settings=settings
            )
        except (NoteCutOff, NoteInvalid, NoteTooLong) as exc:
            log.info("note_part_failed", index=window.index, reason=_reason(exc))
            first_error = first_error or exc
            continue
        log.info(
            "note_part_read",
            index=window.index,
            points=len(reply.value.points),
            seconds=round(reply.seconds, 2),
        )
        parts.append(_Part(window, reply, task.version))
    if not parts:
        assert first_error is not None
        raise first_error
    log.info("note_parts_read", parts=len(windows), failed=len(windows) - len(parts))
    return parts


def _part_version(parts: Sequence[_Part]) -> str:
    """a2-v1, with "+a9-v1" when any part needed a repair."""
    repairs = [p.reply.repair_version for p in parts if p.reply.repair_version]
    return "+".join([parts[0].task_version, *repairs[:1]])


def _extraction(
    parts: Sequence[_Part],
    numbered: Sequence[tuple[str, WindowPoint]],
    *,
    grounder: Grounder,
    names: Mapping[str, str] | None,
    combined: CombinedNote | None,
) -> Extraction:
    """The digests' records through extract.py's steps (RB25): owners, one check of them all,
    A3's pruning (only when its reply is used), the repeats across parts, the restated tasks.
    The records carry the parts' calls only when there is no A3 note to carry them (RB29)."""
    raw, ids = _records(numbered)
    reasons: Counter[str] = Counter()
    checked = check_items(raw, grounder=grounder, names=names, reasons=reasons)
    repeats = answered = 0
    if combined is not None:
        checked, repeats, answered = prune(checked, ids, combined)
    kept, restated = settle_items([c for c in checked if c is not None], reasons)
    items = tuple(sorted(kept, key=lambda i: ALL_KINDS.index(i.kind)))  # stable: earliest first
    dropped = sum(reasons.values())
    log.info(
        "items_extracted",
        kept=len(items),
        dropped=dropped,
        reasons=dict(reasons),
        tasks_as_decisions=restated,
        repeats=repeats,
        answered=answered,
    )
    replies = [p.reply for p in parts] if combined is None else []
    return Extraction(
        items=items,
        dropped=dropped,
        drop_reasons=dict(reasons),
        prompt_versions=(_part_version(parts),) if combined is None else (),
        tokens_in=sum(r.tokens_in for r in replies),
        tokens_out=sum(r.tokens_out for r in replies),
        cached_tokens=sum(r.cached_tokens for r in replies),
        seconds=sum(r.seconds for r in replies),
        failed_kinds=(),
        tasks_as_decisions=restated,
        repeats_removed=repeats,
        answered_removed=answered,
    )


def write_long_note(
    provider: LlmProvider,
    *,
    model: str,
    meeting: Mapping[str, Any],
    utterances: Sequence[Utterance],
    template: Template,
    settings: LlmSettings,
    grounder: Grounder,
    user_notes: str,
    on_stage: Callable[[str], None],
    names: Mapping[str, str] | None = None,
) -> tuple[NoteResult, Extraction]:
    """The note's own sections (A3) and its records (from the digests), checked, not yet saved.
    Every part and the combining call see all of `user_notes` (A0's text). A3's reply has twice
    the usual room, inside the same context (RB45). When A3's JSON fails even after its repair,
    the records alone make the note (RB16); A3's NoteCutOff and NoteTooLong are raised, and so
    is every LlmError.

    The note's version is a0-v1+a2-v1+a3-v2 ("+a9-v1" after a part's or A3's repair) and its
    tokens and seconds are every call's; a note of the records alone has the A0 version, and
    its records carry a2-v1 and the parts' tokens and seconds (RB29)."""
    parts = _read_parts(
        provider,
        model=model,
        meeting=meeting,
        utterances=utterances,
        settings=settings,
        user_notes=user_notes,
        on_stage=on_stage,
    )
    digests, numbered = digests_text(parts)
    on_stage("combining")
    context = build_context(
        meeting=meeting, utterances=utterances, user_notes=user_notes, only=(), note=COMBINE_NOTE
    )
    prompt = combine_prompt(
        context, template=template, schema=CombinedNote.model_json_schema(), digests=digests
    )
    reply = COMBINE_ROOM * settings.max_output_tokens  # the context's size stays the same
    _fits(prompt.estimated_tokens, settings, reply=reply)
    combined: Structured[CombinedNote] | None = None
    invalid: NoteInvalid | None = None
    try:
        combined = chat_structured(
            provider,
            model,
            [ChatMessage("system", prompt.system), ChatMessage("user", prompt.user)],
            CombinedNote,
            max_output_tokens=reply,
            invalid_event="combine_json_invalid",
            after_first=cut_to_fit(settings, reply=reply),
            reply_tokens=reply,
        )
    except NoteInvalid as exc:  # the records can still make a note (§9.1)
        invalid = exc
    # every chat call is done: now the records' check (one batch), then the note's own
    extraction = _extraction(
        parts,
        numbered,
        grounder=grounder,
        names=names,
        combined=None if combined is None else combined.value,
    )
    if combined is None:
        assert invalid is not None
        if not extraction.items:
            raise invalid
        log.info("note_from_items", items=len(extraction.items))
        note = lists_only(model=model, prompt_version=context.version, template=template)
        return note, extraction
    task_version = prompt.prompt_version.removeprefix(f"{context.version}+")  # "a3-v2"
    if combined.repair_version:
        task_version = f"{task_version}+{combined.repair_version}"
    calls = [*(p.reply for p in parts), combined]
    drafted = DraftedNote(
        draft=combined.value,
        model=model,
        prompt_version=f"{context.version}+{_part_version(parts)}+{task_version}",
        tokens_in=sum(c.tokens_in for c in calls),
        tokens_out=sum(c.tokens_out for c in calls),
        seconds=sum(c.seconds for c in calls),
        repaired=any(c.repaired for c in calls),
    )
    result = check_drafted(drafted, context=context, template=template, semantic=grounder.semantic)
    return result, extraction
