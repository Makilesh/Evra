"""The People pages (Plan C Task 3): everyone the owner has named, with their last 1:1; a
person's page; and their prep brief (A13), written on a daemon thread and announced with
`brief.updated`. A brief takes the slot asking takes (`JobSlot`): one question or brief at a
time. A person's open promises are the window's own list (RC7), so their page leaves them out.

Names, notes, promises and briefs go only to the owner's window and the prompt; logs get codes
and counts.
"""

from __future__ import annotations

import re
import sqlite3
import threading
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

import structlog

from evra.config import LlmSettings
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import LlmError, LlmProvider
from evra.notes.brief import BRIEF_MEETINGS, BriefSource, brief_settings, write_brief
from evra.notes.errors import NoteError
from evra.notes.extract import ALL_KINDS, ITEM_SECTIONS, ItemKind
from evra.notes.job import failure_reason
from evra.notes.templates import load_template
from evra.notes.title import NOTE_CHARS, as_lines, note_text
from evra.paths import AppPaths
from evra.services.ask import JobSlot
from evra.services.meetings import Emit
from evra.services.views import meeting_summary, note_view
from evra.store.briefs import BriefStore, StoredBrief
from evra.store.db import connect
from evra.store.items import ItemStore, Promise, StoredItem
from evra.store.meetings import MeetingStore
from evra.store.notes import NoteStore
from evra.store.people import OWNER_NAME, Person, PersonStore
from evra.store.speakers import THEM, SpeakerStore, names_for

log = structlog.get_logger(__name__)

BriefRefusal = Literal["unknown", "no_notes"]
# how a decision and a question read among a note's lines for a brief (RC8)
_RECORD_LEADS: dict[ItemKind, str] = {"decision": "Decision", "open_question": "Open question"}


@dataclass(frozen=True)
class _Job:
    person: Person
    sources: tuple[BriefSource, ...]
    open_items: tuple[str, ...]


def _person(conn: sqlite3.Connection, person_id: str) -> Person | None:
    return next((p for p in PersonStore(conn).list_people() if p.id == person_id), None)


def _meetings_with(conn: sqlite3.Connection, person: Person) -> list[dict[str, Any]]:
    """The person's 1:1s, newest first, as `list_meetings` reads them."""
    people = SpeakerStore(conn).people_by_meeting()
    return [
        row
        for row in MeetingStore(conn).list_meetings()
        if (found := people.get(row["id"])) is not None and found.id == person.id
    ]


def people_list(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Everyone the owner has named, by name, with when their newest 1:1 started (`last_met`,
    epoch ms; null when no 1:1 is linked to them now)."""
    people = SpeakerStore(conn).people_by_meeting()
    last: dict[str, int] = {}
    for row in MeetingStore(conn).list_meetings():  # newest first
        person = people.get(row["id"])
        if person is not None:
            last.setdefault(person.id, int(row["started_at"]))
    return [
        {"id": p.id, "name": p.name, "last_met": last.get(p.id)}
        for p in PersonStore(conn).list_people()
    ]


def _last(
    conn: sqlite3.Connection, person: Person, meetings: Sequence[dict[str, Any]]
) -> dict[str, Any] | None:
    """From the newest of their 1:1s that has a note: what was left for next time, and the
    questions still open, as its note shows them (cited lines and all)."""
    row = next((m for m in meetings if m["has_note"]), None)
    note = None if row is None else NoteStore(conn).current_note(row["id"])
    if row is None or note is None:
        return None
    store = MeetingStore(conn)
    version = store.current_transcript_version(row["id"])
    utterances = store.utterances(version) if version else []
    items = ItemStore(conn).for_generation(note.generation_id)
    view = note_view(note, utterances, items, names=names_for(person))
    blocks = {section["id"]: section["blocks"] for section in view["sections"]}
    return {
        "meeting_id": row["id"],
        "title": row["title"],
        "started_at": row["started_at"],
        "next_time": blocks.get("next_time", []),
        "open_questions": blocks.get("open_questions", []),
    }


def brief_view(conn: sqlite3.Connection, brief: StoredBrief | None) -> dict[str, Any] | None:
    """A brief as the window shows it: each point with the meetings it cites, by their names
    today (a meeting deleted since is left out)."""
    if brief is None:
        return None
    meetings = {row["id"]: row for row in MeetingStore(conn).list_meetings()}
    return {
        "created_at": brief.created_at,
        "points": [
            {
                "text": point.text,
                "meetings": [
                    {
                        "id": mid,
                        "title": meetings[mid]["title"],
                        "started_at": meetings[mid]["started_at"],
                    }
                    for mid in point.meetings
                    if mid in meetings
                ],
            }
            for point in brief.points
        ],
    }


def person_view(conn: sqlite3.Connection, person_id: str) -> dict[str, Any] | None:
    """A person's page: who they are, their last 1:1's points for next time and its open
    questions, their brief, and their 1:1s, newest first. None for no such person."""
    person = _person(conn, person_id)
    if person is None:
        return None
    meetings = _meetings_with(conn, person)
    return {
        "person": {"id": person.id, "name": person.name},
        "last": _last(conn, person, meetings),
        "brief": brief_view(conn, BriefStore(conn).latest(person.id)),
        "meetings": [meeting_summary({**row, "with_name": person.name}) for row in meetings],
    }


def owed(text: str, owner: str | None, due: str | None, *, names: Iterable[str] = ()) -> str:
    """A task as one line: led once by who owes it ("You: …", "Them: …" or a name), in place of
    a "You:", "Them:" or `names` lead the text already has, then its due date when the text
    doesn't already say it. A task no one took on has no lead."""
    line = text
    if owner:
        labels = sorted({OWNER_NAME, THEM, owner, *names}, key=len, reverse=True)
        lead = re.compile(rf"^(?:{'|'.join(re.escape(n) for n in labels)})\s*:\s*", re.IGNORECASE)
        line = f"{owner}: {lead.sub('', text)}"
    if due and due.casefold() not in text.casefold():
        line = f"{line} (due {due})"
    return line


def _record_kinds(template_id: str) -> list[ItemKind]:
    """The kinds of record in the order the note's template shows their sections."""
    try:
        sections = [section.id for section in load_template(template_id).sections]
    except KeyError:  # a template since removed: the kinds' own order
        sections = []

    def place(kind: ItemKind) -> int:
        section = ITEM_SECTIONS[kind]
        return sections.index(section) if section in sections else len(sections)

    return sorted(ALL_KINDS, key=place)


def open_records_text(items: Sequence[StoredItem], template_id: str) -> str:
    """A note's records still open (RC8), as lines in the order the note shows them: "Decision:
    …", a task led by its stored owner ("You: …" or "Them: …", the notes' own words) with its due
    date, "Open question: …". A task done or set aside is left out. They get their own room
    (whole lines, NOTE_CHARS), so the note's points are never cut for them."""
    lines: list[str] = []
    for kind in _record_kinds(template_id):
        for item in items:
            if item.kind != kind or item.status != "open":
                continue
            if kind == "action_item":
                lines.append(owed(item.text, item.owner, item.due))
            else:
                lines.append(f"{_RECORD_LEADS[kind]}: {item.text}")
    return as_lines(lines, NOTE_CHARS)


def brief_sources(
    conn: sqlite3.Connection, person: Person, limit: int = BRIEF_MEETINGS
) -> list[BriefSource]:
    """The notes of the person's newest 1:1s that have one, m:1 the latest. Each is read as the
    title reads a note (its points), then its records still open: what a brief asks about."""
    notes, items = NoteStore(conn), ItemStore(conn)
    sources: list[BriefSource] = []
    for row in _meetings_with(conn, person):
        note = notes.current_note(row["id"]) if row["has_note"] else None
        if note is None:
            continue
        records = open_records_text(items.for_generation(note.generation_id), note.template)
        text = "\n".join(part for part in (note_text(note), records) if part)
        if not text:
            continue
        alias = f"m:{len(sources) + 1}"
        sources.append(
            BriefSource(alias, row["id"], str(row["title"]), int(row["started_at"]), text)
        )
        if len(sources) == limit:
            break
    return sources


def open_items(promises: Sequence[Promise], person: Person) -> list[str]:
    """The person's open promises both ways, each as `owed` leads it: by "You" or their name (in
    place of a "Them:" or name the text already starts with), with its due date."""
    names = (person.name, *person.name.split())
    return [
        owed(
            promise.text,
            OWNER_NAME if promise.owner == "You" else person.name,
            promise.due,
            names=names,
        )
        for promise in promises
        if promise.person is not None and promise.person.id == person.id
    ]


class PeopleService:
    def __init__(
        self,
        *,
        paths: AppPaths,
        llm: Callable[[], LlmSettings],
        emit: Emit,
        recording_busy: Callable[[], bool],
        slot: JobSlot,
        provider_factory: Callable[[LlmSettings], LlmProvider] = OllamaProvider,
    ) -> None:
        self._paths = paths
        self._llm = llm
        self._emit = emit
        self._recording_busy = recording_busy  # asking's rule too (app.py)
        self._slot = slot  # asking's: one question or brief at a time
        self._provider_factory = provider_factory

    def person_page(self, person_id: object) -> dict[str, Any] | None:
        if not isinstance(person_id, str):
            return None
        conn = connect(self._paths.db_path)
        try:
            return person_view(conn, person_id)
        finally:
            conn.close()

    def write_brief(self, person_id: object) -> dict[str, Any]:
        """Start the person's brief: {"ok": True} at once, the brief later as `brief.updated`.
        Refused, in asking's order: while a recording loads, runs or stops ("recording", RC9);
        while a question or another brief is being written, or the app closes ("busy"); for no
        such person ("unknown"), or someone with no note from a 1:1 yet ("no_notes")."""
        if not isinstance(person_id, str):
            return {"ok": False, "reason": "invalid"}
        if self._recording_busy():
            return {"ok": False, "reason": "recording"}
        if not self._slot.take():
            return {"ok": False, "reason": "busy"}
        try:
            job = self._job(person_id)
            if isinstance(job, str):  # nothing to write from: the slot is free again
                self._slot.release()
                return {"ok": False, "reason": job}
            threading.Thread(
                target=self._write, args=(job,), name="brief-writer", daemon=True
            ).start()
        except Exception as exc:  # e.g. a busy database or no thread: stay usable
            log.warning("brief_not_started", error=type(exc).__name__)
            self._slot.release()
            return {"ok": False, "reason": "busy"}
        log.info("brief_started", meetings=len(job.sources), open_items=len(job.open_items))
        return {"ok": True}

    # --- internals -------------------------------------------------------------------------

    def _job(self, person_id: str) -> _Job | BriefRefusal:
        """Who the brief is for, the notes it is read from and their open promises both ways;
        or why there is none to write."""
        conn = connect(self._paths.db_path)
        try:
            person = _person(conn, person_id)
            if person is None:
                return "unknown"
            sources = brief_sources(conn, person)
            if not sources:  # no note from a 1:1 with them yet: nothing to call the model on
                return "no_notes"
            promises = ItemStore(conn).open_promises()
            return _Job(person, tuple(sources), tuple(open_items(promises, person)))
        finally:
            conn.close()

    def _write(self, job: _Job) -> None:
        event: dict[str, Any] = {
            "person_id": job.person.id,
            "state": "failed",
            "reason": "llm_error",
        }
        try:
            event = self._write_and_store(job)
        except (LlmError, NoteError) as exc:
            event["reason"] = failure_reason(exc)
            log.info("brief_failed", reason=event["reason"])
        except Exception as exc:  # never leave the slot taken
            log.warning("brief_job_failed", error=type(exc).__name__)
        finally:
            self._slot.release()
        self._emit("brief.updated", event)

    def _write_and_store(self, job: _Job) -> dict[str, Any]:
        llm = self._llm()
        settings = brief_settings(llm)
        result = write_brief(
            self._provider_factory(settings),
            model=llm.model,
            person=job.person.name,
            sources=job.sources,
            open_items=job.open_items,
            settings=settings,
        )
        if result.state == "unchecked":  # no point passed the check: none to show, none kept
            return {"person_id": job.person.id, "state": "unchecked"}
        conn = connect(self._paths.db_path)
        try:
            stored = BriefStore(conn).save(job.person.id, result)
            if stored is None:  # forgotten while it was written
                log.info("brief_not_kept", reason="unknown")
                return {"person_id": job.person.id, "state": "failed", "reason": "unknown"}
            return {
                "person_id": job.person.id,
                "state": "written",
                "brief": brief_view(conn, stored),
            }
        finally:
            conn.close()
