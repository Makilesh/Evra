"""The lines an owner might type during the 60-minute synthetic call
(`tests/fixtures/notes/one_on_one_60min_notes.json`, synthetic), each labelled with the transcript
lines it was written about: for `tools/eval_alignment.py`, and for `tools/bakeoff_notes.py
--notes`, which links them as the note job does, writes the note from them and counts the [user]
points written and kept."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from evra.llm.schemas import NoteDraft
from evra.notes.align import align
from evra.notes.extract import Extraction
from evra.notes.semantic import Embedder
from evra.notes.structured import parse_reply
from evra.notes.user_notes import NO_NOTES, NotesInput, notes_input
from evra.notes.writer import NoteResult
from evra.store.meetings import Utterance
from evra.store.notepad import NoteLine
from tools.bakeoff_parts import LONG_FIXTURE

if TYPE_CHECKING:  # tools.bakeoff_notes imports this module
    from tools.bakeoff_notes import Case

NOTES_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "tests"
    / "fixtures"
    / "notes"
    / "one_on_one_60min_notes.json"
)
NOTES_SUFFIX = "_notes"  # a fixture of typed notes, not a call of its own
# a citation of the typed notes as a model writes it: "user", and the note's own label, which
# gemma4 also writes ("user.3", "n:3"); in a citation list, or in brackets in the point's text
_NOTES_CITED = re.compile(r"^(?:user|(?:user|n)[.:]\d+)$|\[[^\]]*\b(?:user|n:\d+)\b[^\]]*\]")


@dataclass(frozen=True)
class TypedNotes:
    lines: tuple[NoteLine, ...]  # typed during the call, not yet linked
    about: Mapping[str, frozenset[str]]  # line id -> the utterance ids it was written about


def load_notes(path: Path, utterances: Sequence[Utterance]) -> TypedNotes:
    """The fixture's lines; `about` names the call's utterances by their index in its file (of
    a call cut short, the ones it still has)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = [u.id for u in sorted(utterances, key=lambda u: u.seq)]
    lines = tuple(
        NoteLine(n["id"], k, n["text"], int(n["captured_ms"]), "during", False, ())
        for k, n in enumerate(data["lines"])
    )
    about = {n["id"]: frozenset(ids[i] for i in n["about"] if i < len(ids)) for n in data["lines"]}
    return TypedNotes(lines, about)


def with_notes(case: Case) -> Case:
    """The 60-minute call with its typed notes (those typed before a cut); others as they are."""
    if not case.name.startswith(Path(LONG_FIXTURE).stem):
        return case
    end = max((u.end_ms for u in case.utterances), default=0)
    typed = load_notes(NOTES_FIXTURE, case.utterances).lines
    return replace(case, notes=tuple(n for n in typed if (n.captured_at_ms or 0) <= end))


def linked_notes(case: Case, embedder: Embedder | None) -> NotesInput:
    """The case's typed notes linked as the note job links them: its one batch before the
    chats, on the embedder its check then uses."""
    if not case.notes:
        return NO_NOTES
    links = align(case.notes, case.utterances, embedder=embedder)
    return notes_input([replace(n, aligned=tuple(links.get(n.id, ()))) for n in case.notes])


def user_points(reply: str, result: NoteResult, extraction: Extraction) -> tuple[int, int, int]:
    """Points citing the typed notes in the model's note reply (A1's or A3's), in any form it
    wrote them; those the check kept in the note (as [user]); and the records citing them."""
    draft, _ = parse_reply(NoteDraft, reply)
    groups = [] if draft is None else [draft.summary, *(s.bullets for s in draft.sections)]
    written = [b for bullets in groups for b in bullets]
    kept = [*result.note.summary, *(b for s in result.note.sections for b in s.bullets)]
    return (
        sum(any(_NOTES_CITED.search(c) for c in [*b.citations, b.text]) for b in written),
        sum("user" in b.citations for b in kept),
        sum("user" in i.citations for i in extraction.items),
    )
