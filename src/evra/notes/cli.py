"""`evra note [MEETING_ID]`: write a cited note for a recorded meeting (M3b). `evra titles`:
name the meetings that have a note but still their placeholder title (A8). Notes and titles
print to the user's own console only; logs get counts, never text."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Mapping
from typing import Any

from evra.config import LlmSettings, load_settings
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import (
    LlmConfigError,
    LlmError,
    LlmModelMissing,
    LlmProvider,
    LlmTimeout,
    LlmUnavailable,
)
from evra.logging_setup import configure_logging
from evra.notes.job import NothingSupported, write_and_save
from evra.notes.semantic import Embedder, SemanticCheck
from evra.notes.templates import load_template, template_ids
from evra.notes.title import has_placeholder_title, name_meeting, title_settings
from evra.notes.writer import NoteCutOff, NoteInvalid, NoteTooLong
from evra.paths import AppPaths
from evra.services.views import note_view
from evra.store.db import connect
from evra.store.items import ItemStore
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notepad import NotepadStore
from evra.store.notes import NoteStore
from evra.transcribe.cli import format_ms

FALLBACK_MODEL = "gemma4:12b"


def cite_marks(citations: tuple[str, ...], starts: Mapping[str, int]) -> str:
    marks = []
    for citation in citations:
        if citation in starts:
            marks.append(f"[{format_ms(starts[citation])}]")
        elif citation == "user":
            marks.append("[your notes]")
    return " ".join(marks)


def render_note(view: Mapping[str, Any]) -> list[str]:
    """The note as the window shows it (`note_view`): each section's points, its action items,
    decisions and open questions among them, with the times of the lines they cite, and under a
    point from the owner's notes the typed line it quotes, on one line."""
    lines: list[str] = []
    for section in view["sections"]:
        lines += ["", f"## {section['title']}"]
        for block in section["blocks"]:
            marks = " ".join(f"[{format_ms(int(c['start_ms']))}]" for c in block["citations"])
            lines.append(f"- {block['text']} {marks}".rstrip())
            if "user_quote" in block:
                typed = " ".join(str(block["user_quote"]["text"]).split())
                lines.append(f'  From your notes: "{typed}"')
    return lines[1:]


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def note_command(
    args: argparse.Namespace, paths: AppPaths, *, provider: LlmProvider | None = None
) -> int:
    paths.ensure()
    configure_logging(paths.log_dir, debug=False)
    settings = load_settings(paths.settings_file).llm
    if args.think is not None:
        settings = settings.model_copy(update={"think": args.think})
    conn = connect(paths.db_path)
    try:
        migrate(conn)
        return _run(args, conn, settings, provider)
    finally:
        conn.close()


def _run(
    args: argparse.Namespace,
    conn: sqlite3.Connection,
    settings: LlmSettings,
    provider: LlmProvider | None,
) -> int:
    meetings = MeetingStore(conn)
    meeting_id = args.meeting_id or meetings.latest_meeting_id()
    if meeting_id is None:
        _err("No meetings yet. Record one with: evra record 60")
        return 2
    try:
        meeting = meetings.get_meeting(meeting_id)
    except KeyError:
        _err(f"No meeting with id {meeting_id}.")
        return 2
    version_id = meetings.current_transcript_version(meeting_id)
    utterances = meetings.utterances(version_id) if version_id else []
    if version_id is None or not utterances:
        _err("This meeting has no transcript to write a note from.")
        return 2
    template_id = args.template or meeting["template"]
    try:
        template = load_template(template_id)
    except KeyError:
        _err(f"Unknown template {template_id!r}. Available: {', '.join(template_ids())}")
        return 2
    model = args.model or settings.model
    try:
        llm = provider or OllamaProvider(settings)
        if not model:
            installed = llm.installed_models()
            example = installed[0] if installed else FALLBACK_MODEL
            _err(f"No note model chosen yet. Pick one, e.g.: evra note --model {example}")
            if installed:
                _err("Installed: " + ", ".join(installed))
            return 2
        print(f"Writing the note with {model}...", flush=True)
        saved = write_and_save(
            conn,
            meeting=meeting,
            version_id=version_id,
            utterances=utterances,
            template=template,
            provider=llm,
            model=model,
            settings=settings,
            semantic=SemanticCheck(Embedder(llm, settings.embedding_model)),  # as the window does
        )
    except KeyboardInterrupt:
        _err("Stopped; nothing saved.")
        return 130
    except LlmUnavailable:
        _err("Ollama is not running. Start it (it lives in the system tray) and try again.")
        return 2
    except LlmModelMissing as exc:
        _err(f"The model {exc.model} is not installed. Run: ollama pull {exc.model}")
        return 2
    except LlmConfigError as exc:
        _err(str(exc))
        return 2
    except LlmTimeout as exc:
        _err(f"The model took too long ({exc}). Try again, or a smaller model with --model.")
        return 1
    except NoteTooLong as exc:  # even in parts: the parts' digests together do not fit
        _err(f"This meeting is too long for a note. You can still ask about it. ({exc})")
        return 1
    except NoteCutOff as exc:
        _err(
            f"The model ran out of output room ({exc}). Turn off --think, or raise"
            " llm.max_output_tokens in settings."
        )
        return 1
    except NoteInvalid:
        _err(f"{model} did not return a valid note, even after one repair. Try --model.")
        return 1
    except NothingSupported as exc:  # never replace a usable note with an empty one
        _err(
            f"Nothing in the note could be checked against the transcript"
            f" ({exc.dropped} points dropped); nothing saved, any earlier note is kept."
            " Try another model with --model."
        )
        return 1
    except LlmError as exc:
        _err(f"The LLM failed: {exc}")
        return 1
    result, extraction = saved.result, saved.extraction
    stored = NoteStore(conn).current_note(meeting_id)
    assert stored is not None
    items = ItemStore(conn).for_generation(saved.generation_id)
    typed = NotepadStore(conn).lines(meeting_id)
    print(f"# {meeting['title']}")
    for line in render_note(note_view(stored, utterances, items, lines=typed)):
        print(line)
    if result.items_only:
        print(
            f"-- {model} did not return a valid note, even after one repair: this note holds"
            " only the action items, decisions and open questions"
        )
    repaired = ", after one JSON repair" if result.repaired else ""
    kept = result.note.kept + len(extraction.items)
    dropped = result.note.dropped + extraction.dropped
    print(
        f"-- note written in {result.seconds + extraction.seconds:.1f} s by {result.model};"
        f" {kept} points kept, {dropped} dropped as unsupported{repaired};"
        f" generation {saved.generation_id}"
    )
    return 0


def titles_command(
    args: argparse.Namespace, paths: AppPaths, *, provider: LlmProvider | None = None
) -> int:
    """Name each meeting the way the window names a new one once its note is written; meetings
    recorded before that, or noted with `evra note`, are named here."""
    paths.ensure()
    configure_logging(paths.log_dir, debug=False)
    settings = title_settings(load_settings(paths.settings_file).llm)
    model = args.model or settings.model
    conn = connect(paths.db_path)
    try:
        migrate(conn)
        todo = [
            m
            for m in MeetingStore(conn).list_meetings()
            if m["has_note"] and has_placeholder_title(str(m["title"]))
        ]
        if not todo:
            print("Every meeting with a note has a name already.")
            return 0
        named = 0
        try:
            llm = provider or OllamaProvider(settings)
            for meeting in todo:
                title = name_meeting(
                    conn, str(meeting["id"]), provider=llm, model=model, settings=settings
                )
                if title is None:
                    print(f"{meeting['title']}: kept, no usable title came back")
                else:
                    print(f"{meeting['title']} -> {title}")
                    named += 1
        except LlmUnavailable:
            _err("Ollama is not running. Start it (it lives in the system tray) and try again.")
            return 2
        except LlmModelMissing as exc:
            _err(f"The model {exc.model} is not installed. Run: ollama pull {exc.model}")
            return 2
        except LlmConfigError as exc:
            _err(str(exc))
            return 2
        except LlmError as exc:
            _err(f"The LLM failed: {exc}")
            return 1
        print(f"-- {named} of {len(todo)} named")
        return 0
    finally:
        conn.close()
