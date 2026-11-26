"""Asking a meeting a question from the window (Ask a meeting, task 6): one question at a time,
answered on a daemon thread, announced with `question.updated`. A prefill warms the model with
the meeting's shared system message while the owner types.

Nothing slow, and no event, runs while holding the lock. Question and answer text go only to the
owner's window and the database; logs get codes and counts.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any, Literal

import structlog

from evra.config import LlmSettings
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import ChatMessage, LlmError, LlmProvider
from evra.notes.ask import (
    MAX_QUESTION_CHARS,
    ask_meeting,
    ask_settings,
    build_ask_messages,
    clean_question,
    whole_meeting_fits,
)
from evra.notes.context import build_context, estimate_tokens
from evra.notes.errors import NoteError
from evra.notes.job import failure_reason
from evra.paths import AppPaths
from evra.services.meetings import Emit
from evra.services.views import question_view
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.questions import QuestionStore, StoredQuestion

log = structlog.get_logger(__name__)

AskRefusal = Literal["invalid", "busy", "recording", "no_transcript"]
PREPARE_EVERY_S = 240.0
PREFILL_USER = 'Reply with {"ready": true}.'
PREFILL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"ready": {"type": "boolean"}},
    "required": ["ready"],
}


class AskService:
    def __init__(
        self,
        *,
        paths: AppPaths,
        llm: Callable[[], LlmSettings],
        emit: Emit,
        recording_busy: Callable[[], bool],
        provider_factory: Callable[[LlmSettings], LlmProvider] = OllamaProvider,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._paths = paths
        self._llm = llm
        self._emit = emit
        self._recording_busy = recording_busy
        self._provider_factory = provider_factory
        self._clock = clock
        self._lock = threading.Lock()
        self._pending = False
        self._preparing = False
        self._closing = False
        self._prepared: dict[str, float] = {}

    def ask(self, meeting_id: object, question: object) -> dict[str, Any]:
        cleaned = clean_question(question) if isinstance(question, str) else None
        if not isinstance(meeting_id, str) or cleaned is None:
            return {"ok": False, "reason": "invalid"}
        if self._recording_busy():
            return {"ok": False, "reason": "recording"}
        with self._lock:
            if self._pending or self._closing:
                return {"ok": False, "reason": "busy"}
            self._pending = True
        stored: StoredQuestion | None = None
        try:
            conn = connect(self._paths.db_path)
            try:
                if not _has_lines(MeetingStore(conn), meeting_id):
                    self._release()
                    return {"ok": False, "reason": "no_transcript"}
                stored = QuestionStore(conn).add(meeting_id, cleaned)
            finally:
                conn.close()
            threading.Thread(
                target=self._answer, args=(stored,), name="ask-answer", daemon=True
            ).start()
        except Exception as exc:  # e.g. a busy database or no thread: stay usable
            log.warning("question_not_started", error=type(exc).__name__)
            if stored is not None:
                self._fail(stored, "llm_error")  # never leave an asking row without a thread
            self._release()
            return {"ok": False, "reason": "busy"}
        return {"ok": True, "question": question_view(stored, {})}

    def prepare(self, meeting_id: object) -> dict[str, Any]:
        if not isinstance(meeting_id, str) or self._recording_busy():
            return {"ok": False}
        with self._lock:
            if self._pending or self._closing or self._preparing:
                return {"ok": False}
            last = self._prepared.get(meeting_id)
            if last is not None and self._clock() - last < PREPARE_EVERY_S:
                return {"ok": False}
            self._prepared[meeting_id] = self._clock()
            self._preparing = True  # one pre-read at a time
        try:
            system = self._prefill_system(meeting_id)
            if system is not None:
                threading.Thread(
                    target=self._prefill, args=(system,), name="ask-prepare", daemon=True
                ).start()
        except Exception as exc:
            log.warning("prefill_not_started", error=type(exc).__name__)
            system = None
        if system is None:
            with self._lock:
                self._prepared.pop(meeting_id, None)
                self._preparing = False
            return {"ok": False}
        return {"ok": True}

    def recover(self) -> int:
        conn = connect(self._paths.db_path)
        try:
            return QuestionStore(conn).interrupted()
        finally:
            conn.close()

    def shutdown(self) -> None:
        with self._lock:
            self._closing = True

    # --- internals -------------------------------------------------------------------------

    def _release(self) -> None:
        with self._lock:
            self._pending = False

    def _prefill_system(self, meeting_id: str) -> str | None:
        """The meeting's shared system message, when the whole meeting still fits one prompt
        with a 500-character question and the history asked so far; otherwise asking would take
        the excerpt path and a whole-meeting prefill would not be the cache it reuses."""
        conn = connect(self._paths.db_path)
        try:
            meetings = MeetingStore(conn)
            if not _has_lines(meetings, meeting_id):
                return None
            version_id = meetings.current_transcript_version(meeting_id)
            assert version_id is not None
            context = build_context(
                meeting=meetings.get_meeting(meeting_id),
                utterances=meetings.utterances(version_id),
            )
            history = QuestionStore(conn).history(meeting_id)
        finally:
            conn.close()
        user = build_ask_messages(context, "x" * MAX_QUESTION_CHARS, history)[0][1].content
        if not whole_meeting_fits(context, estimate_tokens(user), ask_settings(self._llm())):
            return None
        return context.system

    def _prefill(self, system: str) -> None:
        llm = ask_settings(self._llm())
        try:
            self._provider_factory(llm).chat_json(
                llm.model,
                [ChatMessage("system", system), ChatMessage("user", PREFILL_USER)],
                PREFILL_SCHEMA,
            )
        except Exception as exc:  # a warm-up only: the real question reports its own errors
            log.info("prefill_failed", error=type(exc).__name__)
        finally:
            with self._lock:
                self._preparing = False

    def _answer(self, stored: StoredQuestion) -> None:
        outcome: tuple[StoredQuestion, Mapping[str, int]] | None = None
        reason = "llm_error"
        try:
            outcome = self._answer_and_store(stored)
        except (LlmError, NoteError) as exc:
            reason = failure_reason(exc)
            log.info("question_failed", reason=reason)
        except Exception as exc:  # never leave the question asking
            log.warning("question_job_failed", error=type(exc).__name__)
        try:
            if outcome is None:
                outcome = (self._fail(stored, reason), {})
        finally:
            self._release()
        self._emit(
            "question.updated",
            {"meeting_id": stored.meeting_id, "question": question_view(*outcome)},
        )

    def _answer_and_store(self, asked: StoredQuestion) -> tuple[StoredQuestion, Mapping[str, int]]:
        llm = self._llm()
        settings = ask_settings(llm)
        conn = connect(self._paths.db_path)
        try:
            meetings, questions = MeetingStore(conn), QuestionStore(conn)
            version_id = meetings.current_transcript_version(asked.meeting_id)
            utterances = meetings.utterances(version_id) if version_id else []
            result = ask_meeting(
                self._provider_factory(settings),
                model=llm.model,
                meeting=meetings.get_meeting(asked.meeting_id),
                utterances=utterances,
                question=asked.text,
                settings=settings,
                history=questions.history(asked.meeting_id),
            )
            assert version_id is not None  # ask_meeting raised NoTranscript otherwise
            stored = questions.answer(asked.id, result, transcript_version_id=version_id)
            return stored, {u.id: u.start_ms for u in utterances}
        finally:
            conn.close()

    def _fail(self, asked: StoredQuestion, reason: str) -> StoredQuestion:
        """Store the failure; if even that cannot be written, still say it in memory so the
        window hears back."""
        try:
            conn = connect(self._paths.db_path)
            try:
                return QuestionStore(conn).fail(asked.id, reason)
            finally:
                conn.close()
        except Exception as exc:
            log.warning("question_not_marked", error=type(exc).__name__)
            return replace(asked, state="failed", reason=reason)


def _has_lines(meetings: MeetingStore, meeting_id: str) -> bool:
    try:
        meetings.get_meeting(meeting_id)
    except KeyError:
        return False
    version_id = meetings.current_transcript_version(meeting_id)
    return version_id is not None and meetings.has_utterances(version_id)
