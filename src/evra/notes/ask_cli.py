"""`evra ask QUESTION`: ask the latest (or a chosen) meeting one question. The answer prints to
the owner's own console; logs get counts, never text."""

from __future__ import annotations

import argparse
import sqlite3
import sys

from evra.config import load_settings
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import LlmError, LlmModelMissing, LlmProvider
from evra.logging_setup import configure_logging
from evra.notes.ask import NOT_DISCUSSED, ask_meeting, ask_settings, clean_question
from evra.notes.cli import FALLBACK_MODEL, cite_marks
from evra.notes.errors import NoteError
from evra.notes.job import failure_reason
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.questions import QuestionStore, StoredQuestion

# the same sentences as the window's askExcerpt and askExcerptNothing
EXCERPT_PARTS = (
    "This call is too long to read whole, so Evra read the parts that match your question."
)
EXCERPT_NOTHING = (
    "This call is too long to read whole, and no part of it matches the words of your question."
)

FAILURES = {
    "ollama_down": "Ollama is not running. Start it (it lives in the system tray) and try again.",
    "model_missing": "The model {model} is not installed. Run: ollama pull {model}",
    "cloud_model": "That is a cloud model. Evra only uses models that run on this computer.",
    "timeout": "The model took too long. Try again, or a smaller model with --model.",
    "too_long": "This question needs more room than the model's settings allow.",
    "cut_off": "The model ran out of output room. Try again.",
    "invalid": "The model did not return a usable answer, even after one repair. Try --model.",
    "no_transcript": "This meeting has no transcript to ask about.",
    "llm_error": "The model failed. Try again.",
}


def _err(message: str) -> None:
    print(message, file=sys.stderr)


def ask_command(
    args: argparse.Namespace, paths: AppPaths, *, provider: LlmProvider | None = None
) -> int:
    paths.ensure()
    configure_logging(paths.log_dir, debug=False)
    conn = connect(paths.db_path)
    try:
        migrate(conn)
        return _run(args, conn, paths, provider)
    finally:
        conn.close()


def _run(
    args: argparse.Namespace,
    conn: sqlite3.Connection,
    paths: AppPaths,
    provider: LlmProvider | None,
) -> int:
    question = clean_question(args.question)
    if question is None:
        _err("Write a question of up to 500 characters.")
        return 2
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
        _err("This meeting has no transcript to ask about.")
        return 2
    llm = load_settings(paths.settings_file).llm
    model = args.model or llm.model
    settings = ask_settings(llm)
    questions = QuestionStore(conn)
    stored: StoredQuestion | None = None
    try:
        llm_provider = provider or OllamaProvider(settings)
        if not model:
            installed = llm_provider.installed_models()
            example = installed[0] if installed else FALLBACK_MODEL
            _err(f"No model chosen yet. Pick one, e.g.: evra ask --model {example} ...")
            return 2
        stored = questions.add(meeting_id, question)
        result = ask_meeting(
            llm_provider,
            model=model,
            meeting=meeting,
            utterances=utterances,
            question=question,
            settings=settings,
            history=questions.history(meeting_id),
        )
        questions.answer(stored.id, result, transcript_version_id=version_id)
    except KeyboardInterrupt:
        if stored is not None:
            questions.fail(stored.id, "interrupted")
        _err("Stopped.")
        return 130
    except Exception as exc:  # a failed question never stays "asking"
        reason = failure_reason(exc) if isinstance(exc, LlmError | NoteError) else "llm_error"
        if stored is not None:
            questions.fail(stored.id, reason)
        named = exc.model if isinstance(exc, LlmModelMissing) else model
        _err(FAILURES.get(reason, FAILURES["llm_error"]).format(model=named))
        return 1
    starts = {u.id: u.start_ms for u in utterances}
    if result.state == "answered":
        for point in result.points:
            print(f"- {point.text} {cite_marks(point.citations, starts)}".rstrip())
        if result.excerpt:
            print(EXCERPT_PARTS)
    elif result.state == "unchecked":
        _err("The model answered, but nothing could be checked against the transcript.")
        if result.excerpt:
            _err(EXCERPT_PARTS)
        return 1
    else:
        print(NOT_DISCUSSED)
        if result.excerpt:
            print(EXCERPT_NOTHING)
    return 0
