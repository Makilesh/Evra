"""`evra note [MEETING_ID]`: write a cited note for a recorded meeting (M3b). The note prints
to the user's own console only; logs get counts, never text."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from collections.abc import Mapping

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
from evra.notes.templates import load_template, template_ids
from evra.notes.writer import NoteCutOff, NoteInvalid, NoteTooLong
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import SUMMARY, NoteStore, StoredNote
from evra.transcribe.cli import format_ms

FALLBACK_MODEL = "gemma4:12b"


def _cite(citations: tuple[str, ...], starts: Mapping[str, int]) -> str:
    marks = []
    for citation in citations:
        if citation in starts:
            marks.append(f"[{format_ms(starts[citation])}]")
        elif citation == "user":
            marks.append("[your notes]")
    return " ".join(marks)


def render_note(
    note: StoredNote, *, titles: Mapping[str, str], starts: Mapping[str, int]
) -> list[str]:
    lines: list[str] = []
    current: str | None = None
    for block in note.blocks:
        if block.section != current:
            current = block.section
            title = titles.get(current) or current.replace("_", " ").capitalize()
            lines += ["", f"## {title}"]
        lines.append(f"- {block.text} {_cite(block.citations, starts)}".rstrip())
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
    except NoteTooLong as exc:
        _err(
            f"This meeting is too long for one pass ({exc}). Notes for long meetings are not"
            " supported yet."
        )
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
    result, generation_id = saved.result, saved.generation_id
    notes = NoteStore(conn)
    stored = notes.current_note(meeting_id)
    assert stored is not None
    titles = {SUMMARY: "Summary", **{s.id: s.title for s in template.sections}}
    print(f"# {meeting['title']}")
    for line in render_note(stored, titles=titles, starts={u.id: u.start_ms for u in utterances}):
        print(line)
    repaired = ", after one JSON repair" if result.repaired else ""
    print(
        f"-- note written in {result.seconds:.1f} s by {result.model}; {result.note.kept} points"
        f" kept, {result.note.dropped} dropped as unsupported{repaired}; generation {generation_id}"
    )
    return 0
