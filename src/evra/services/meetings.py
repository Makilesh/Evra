"""The window's meeting flow (M3c spec §3.1): one recording at a time, then its note
(BUILD.md §7.3, D16).

Bridge calls arrive on their own threads (pywebview), so the state lives under one lock and
nothing slow, and no event, runs while holding it. Events carry transcript text only to the
user's own window; logs get codes and counts.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Literal, Protocol

import structlog

from evra.capture.devices import MicList, list_mics, refresh_devices
from evra.capture.sources import CaptureError
from evra.config import LlmSettings, Settings, load_settings, save_settings
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import LlmError, LlmModelMissing, LlmProvider
from evra.modelstore import ModelError
from evra.notes.job import failure_reason, write_and_save
from evra.notes.templates import load_template
from evra.notes.writer import NoteError, NoTranscript
from evra.paths import AppPaths
from evra.services.views import utterance_view
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.transcribe.recording import RecordingResult
from evra.workers.protocol import WorkerCrashed, WorkerError

log = structlog.get_logger(__name__)

State = Literal["idle", "loading", "recording", "stopping", "processing"]
Emit = Callable[[str, Mapping[str, Any]], object]


class Recording(Protocol):
    meeting_id: str | None
    started_at_ms: int | None

    def start(self) -> str: ...

    def stop(self, *, state: str = "ready") -> RecordingResult: ...


class Kit(Protocol):
    def prepare(self) -> None: ...

    def new_recording(
        self,
        mic: int | str | None,
        *,
        title: str,
        situation: str,
        on_utterance: Callable[[Utterance], None] | None = None,
        on_level: Callable[[int, float], None] | None = None,
    ) -> Recording: ...

    def close(self) -> None: ...


class MeetingService:
    def __init__(
        self,
        *,
        paths: AppPaths,
        settings: Settings,
        emit: Emit,
        kit: Kit,
        provider_factory: Callable[[LlmSettings], LlmProvider] = OllamaProvider,
        level_interval_s: float = 0.1,
        mic_lister: Callable[[], MicList] = list_mics,
        device_refresher: Callable[[], None] = refresh_devices,
    ) -> None:
        self._paths = paths
        self._settings = settings
        self._emit = emit
        self._kit = kit
        self._provider_factory = provider_factory
        self._level_interval = level_interval_s
        self._list_mics = mic_lister
        self._refresh_devices = device_refresher
        self._lock = threading.Lock()
        self._state: State = "idle"
        self._meeting_id: str | None = None
        self._started_at: int | None = None
        self._recording: Recording | None = None
        self._closing = False
        self._levels = [0.0, 0.0]
        self._ticker_stop = threading.Event()
        self._ticker: threading.Thread | None = None

    @property
    def mic_name(self) -> str:
        return self._settings.mic_name

    def state(self) -> dict[str, Any]:
        with self._lock:
            return self._payload()

    def list_mics(self) -> MicList:
        """The mics as they are now. Devices are enumerated again only while nothing records:
        re-enumerating closes open streams, so the lock keeps a Record from starting meanwhile."""
        with self._lock:
            if self._state == "idle" and not self._closing:
                try:
                    self._refresh_devices()
                except Exception as exc:
                    log.warning("devices_not_refreshed", error=type(exc).__name__)
        return self._list_mics()

    # --- recording -------------------------------------------------------------------------

    def start(self, mic_name: str) -> dict[str, Any]:
        with self._lock:
            refused = "closing" if self._closing else "" if self._state == "idle" else "busy"
            payload = self._payload() if refused else self._set("loading")
        self._announce(payload)
        if refused:
            return {"ok": False, "reason": refused}
        try:
            self._kit.prepare()
            if self._is_closing():  # the window closed while speech recognition loaded
                return self._back_to_idle({"ok": False, "reason": "closing"})
            recording = self._kit.new_recording(
                mic_name or None,
                title=f"Recording {datetime.now():%Y-%m-%d %H:%M}",
                situation=self._settings.default_situation,
                on_utterance=self._on_utterance,
                on_level=self._on_level,
            )
            meeting_id = recording.start()
        except CaptureError as exc:
            log.info("recording_not_started", error=type(exc).__name__)
            return self._back_to_idle({"ok": False, "error": str(exc), "hint": exc.hint})
        except (ModelError, WorkerError, WorkerCrashed, OSError) as exc:
            log.warning("recording_not_started", error=type(exc).__name__)
            message = f"Could not start recording ({type(exc).__name__}): {exc}"
            return self._back_to_idle({"ok": False, "error": message, "hint": ""})
        except Exception as exc:  # anything else must not leave the service stuck in "loading"
            log.warning("recording_not_started", error=type(exc).__name__)
            message = f"Could not start recording ({type(exc).__name__})."
            return self._back_to_idle({"ok": False, "error": message, "hint": ""})
        with self._lock:
            closing = self._closing
            if not closing:
                self._recording = recording
                payload = self._set("recording", meeting_id, recording.started_at_ms)
        if closing:  # the window closed while capture was opening: keep what exists
            recording.stop(state="ready")
            return self._back_to_idle({"ok": False, "reason": "closing"})
        self._remember_mic(mic_name)
        self._start_ticker()
        self._announce(payload)
        return {"ok": True, "meeting_id": meeting_id}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            recording = self._recording if self._state == "recording" else None
            if recording is not None:
                payload = self._set("stopping", self._meeting_id, self._started_at)
            else:
                payload = self._payload()
        self._announce(payload)
        if recording is None:
            return {"ok": False}
        self._stop_ticker()
        try:
            result = recording.stop(state="processing")
        except Exception as exc:  # capture failed while closing: the meeting is still kept
            log.warning("recording_stop_failed", error=type(exc).__name__)
            if recording.meeting_id is not None:
                self._finish(recording.meeting_id)
            with self._lock:
                self._recording = None
            return self._back_to_idle({"ok": False})
        with self._lock:
            self._recording = None
        hints = list(result.health.hints) if result.health is not None else []
        self._emit(
            "recording.finished",
            {
                "meeting_id": result.meeting_id,
                "utterances": result.utterances,
                "failed_segments": result.stats.failures,
                "hints": hints,
            },
        )
        with self._lock:
            closing = self._closing
            if not closing:
                payload = self._set("processing", result.meeting_id)
        if closing:  # never write a note while the app shuts down
            self._finish(result.meeting_id)
            return self._back_to_idle({"ok": True})
        self._announce(payload)
        self._start_note_job(result.meeting_id)
        return {"ok": True}

    # --- notes -----------------------------------------------------------------------------

    def write_note(self, meeting_id: str) -> dict[str, Any]:
        with self._lock:
            allowed = self._state == "idle" and not self._closing
            payload = self._set("processing", meeting_id) if allowed else self._payload()
        self._announce(payload)
        if not allowed:
            return {"ok": False}
        self._start_note_job(meeting_id)
        return {"ok": True}

    def _start_note_job(self, meeting_id: str) -> None:
        self._emit("note.stage", {"meeting_id": meeting_id, "stage": "writing"})
        threading.Thread(
            target=self._note_job, args=(meeting_id,), name="note-writer", daemon=True
        ).start()

    def _note_job(self, meeting_id: str) -> None:
        try:
            conn = connect(self._paths.db_path)
            try:
                event = self._write(conn, meeting_id)
                MeetingStore(conn).finish_meeting(meeting_id, state="ready")
            finally:
                conn.close()
        except Exception as exc:  # e.g. the database is busy: say so and stay usable
            log.warning("note_job_failed", error=type(exc).__name__)
            event = ("note.failed", {"meeting_id": meeting_id, "reason": "llm_error"})
        with self._lock:
            payload = self._set("idle")
        self._emit(*event)
        self._announce(payload)

    def _write(self, conn: sqlite3.Connection, meeting_id: str) -> tuple[str, dict[str, Any]]:
        store = MeetingStore(conn)
        meeting = store.get_meeting(meeting_id)
        version_id = store.current_transcript_version(meeting_id)
        utterances = store.utterances(version_id) if version_id else []
        llm = self._settings.llm
        try:
            if version_id is None or not utterances:
                raise NoTranscript("no transcript")
            write_and_save(
                conn,
                meeting=meeting,
                version_id=version_id,
                utterances=utterances,
                template=load_template(str(meeting["template"])),
                provider=self._provider_factory(llm),
                model=llm.model,
                settings=llm,
            )
        except (LlmError, NoteError) as exc:
            reason = failure_reason(exc)
            log.info("note_not_written", reason=reason)
            failed: dict[str, Any] = {"meeting_id": meeting_id, "reason": reason}
            if isinstance(exc, LlmModelMissing):
                failed["model"] = exc.model
            return "note.failed", failed
        return "note.ready", {"meeting_id": meeting_id}

    # --- shutdown --------------------------------------------------------------------------

    def shutdown(self) -> None:
        """The window closed: save a running recording (no note), then stop the ASR worker."""
        with self._lock:
            self._closing = True
            recording = self._recording if self._state == "recording" else None
            self._recording = None
        self._stop_ticker()
        if recording is not None:
            try:
                recording.stop(state="ready")
            except Exception as exc:
                log.warning("recording_stop_failed", error=type(exc).__name__)
            with self._lock:
                self._set("idle")
        self._kit.close()

    # --- helpers ---------------------------------------------------------------------------

    def _payload(self) -> dict[str, Any]:  # the caller holds the lock
        payload: dict[str, Any] = {"state": self._state}
        if self._meeting_id is not None:
            payload["meeting_id"] = self._meeting_id
            payload["started_at"] = self._started_at
        return payload

    def _set(
        self, state: State, meeting_id: str | None = None, started_at: int | None = None
    ) -> dict[str, Any]:  # the caller holds the lock
        self._state, self._meeting_id, self._started_at = state, meeting_id, started_at
        return self._payload()

    def _announce(self, payload: dict[str, Any]) -> None:
        self._emit("recording.state", payload)

    def _back_to_idle(self, reply: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = self._set("idle")
        self._announce(payload)
        return reply

    def _is_closing(self) -> bool:
        with self._lock:
            return self._closing

    def _finish(self, meeting_id: str) -> None:
        try:
            conn = connect(self._paths.db_path)
            try:
                MeetingStore(conn).finish_meeting(meeting_id, state="ready")
            finally:
                conn.close()
        except Exception as exc:
            log.warning("meeting_not_finished", error=type(exc).__name__)

    def _remember_mic(self, mic_name: str) -> None:
        if mic_name == self._settings.mic_name:
            return
        # read the file again: settings edited while the app runs must not be overwritten
        current = load_settings(self._paths.settings_file)
        self._settings = current.model_copy(update={"mic_name": mic_name})
        try:
            save_settings(self._paths.settings_file, self._settings)
        except OSError as exc:
            log.warning("settings_not_saved", error=type(exc).__name__)

    def _on_utterance(self, utterance: Utterance) -> None:  # the transcriber's thread
        self._emit(
            "transcript.utterance",
            {"meeting_id": utterance.meeting_id, **utterance_view(utterance)},
        )

    def _on_level(self, channel: int, level: float) -> None:  # the capture thread
        if channel in (0, 1):
            self._levels[channel] = level

    def _start_ticker(self) -> None:
        self._levels = [0.0, 0.0]
        self._ticker_stop.clear()
        self._ticker = threading.Thread(target=self._tick, name="level-meter", daemon=True)
        self._ticker.start()

    def _tick(self) -> None:
        while not self._ticker_stop.wait(self._level_interval):
            you, them = self._levels
            self._emit("recording.levels", {"you": round(you, 3), "them": round(them, 3)})

    def _stop_ticker(self) -> None:
        self._ticker_stop.set()
        ticker, self._ticker = self._ticker, None
        if ticker is not None:
            ticker.join(timeout=1)
