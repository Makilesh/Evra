import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from evra.asr.engine import Segment
from evra.audio.vad import SpeechSegmenter
from evra.capture.fake import FakeSource
from evra.capture.session import CaptureSession
from evra.capture.sources import MicUnavailableError
from evra.config import LlmSettings, Settings, load_settings
from evra.llm.provider import ChatMessage, ChatResult, LlmModelMissing, LlmProvider, LlmUnavailable
from evra.modelstore import ModelError
from evra.paths import AppPaths
from evra.services.meetings import MeetingService
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.migrate import migrate
from evra.store.notes import NoteStore
from evra.transcribe.recording import LiveRecording
from tests.unit.audio.test_vad import FakeVad
from tests.unit.notes.fakes import FakeProvider

GOOD = json.dumps(
    {"summary": [{"text": "Some words were said.", "citations": ["u:1"]}], "sections": []}
)


class NumberAsr:
    def transcribe(self, pcm: np.ndarray) -> list[Segment]:
        return [Segment(0, len(pcm) * 1000 // 16_000, "words", ())]


class FakeKit:
    def __init__(
        self,
        paths: AppPaths,
        *,
        speech: bool = True,
        mic_error: Exception | None = None,
        prepare_error: Exception | None = None,
        prepare_delay: float = 0.0,
    ) -> None:
        self.paths, self.speech = paths, speech
        self.mic_error, self.prepare_error, self.prepare_delay = (
            mic_error,
            prepare_error,
            prepare_delay,
        )
        self.mics: list[object] = []
        self.closed = False
        self.releases = 0

    def prepare(self) -> None:
        time.sleep(self.prepare_delay)
        if self.prepare_error is not None:
            raise self.prepare_error

    def new_recording(
        self,
        mic: int | str | None,
        *,
        title: str,
        situation: str,
        on_utterance: Callable[[Utterance], None] | None = None,
        on_level: Callable[[int, float], None] | None = None,
    ) -> LiveRecording:
        self.mics.append(mic)
        if self.mic_error is not None:
            raise self.mic_error
        tone = (0.3 * np.sin(np.arange(16_000 * 3) / 5)).astype(np.float32)
        session = CaptureSession(
            FakeSource(tone, 16_000, name="mic"),
            FakeSource(tone, 16_000, name="out", pads_silence=True),
        )
        script = [(3_200, 9_600)] if self.speech else []
        segmenters = {
            0: SpeechSegmenter(0, FakeVad(script=script)),
            1: SpeechSegmenter(1, FakeVad(script=[])),
        }
        return LiveRecording(
            session=session,
            segmenters=segmenters,
            asr=NumberAsr(),
            db_path=self.paths.db_path,
            title=title,
            situation=situation,
            on_utterance=on_utterance,
            on_level=on_level,
        )

    def release_if_idle(self) -> bool:
        self.releases += 1
        return True

    def close(self) -> None:
        self.closed = True


class Events:
    def __init__(self) -> None:
        self.items: list[tuple[str, dict[str, Any]]] = []
        self._cond = threading.Condition()

    def __call__(self, name: str, payload: Mapping[str, Any]) -> bool:
        with self._cond:
            self.items.append((name, dict(payload)))
            self._cond.notify_all()
        return True

    def wait_for(self, name: str, timeout: float = 10.0, **match: Any) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                for n, p in self.items:
                    if n == name and all(p.get(k) == v for k, v in match.items()):
                        return p
                left = deadline - time.monotonic()
                if left <= 0:
                    raise AssertionError(f"no {name} {match}; got {[n for n, _ in self.items]}")
                self._cond.wait(left)

    def names(self) -> list[str]:
        with self._cond:
            return [n for n, _ in self.items]

    def states(self) -> list[str]:
        with self._cond:
            return [p["state"] for n, p in self.items if n == "recording.state"]


class Down(FakeProvider):
    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        raise LlmUnavailable("down")


class NoModel(FakeProvider):
    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        raise LlmModelMissing(model)


def make(
    tmp_path: Path,
    provider: Callable[[LlmSettings], LlmProvider] | None = None,
    idle_check_s: float = 60.0,
    **kit: Any,
) -> tuple[MeetingService, Events, FakeKit, AppPaths]:
    paths = AppPaths.under(tmp_path)
    paths.ensure()
    conn = connect(paths.db_path)
    migrate(conn)
    conn.close()
    events, fake_kit = Events(), FakeKit(paths, **kit)
    service = MeetingService(
        paths=paths,
        settings=Settings(),
        emit=events,
        kit=fake_kit,
        provider_factory=provider or (lambda settings: FakeProvider([GOOD])),
        level_interval_s=0.02,
        idle_check_s=idle_check_s,
    )
    return service, events, fake_kit, paths


def _db(paths: AppPaths) -> tuple[MeetingStore, NoteStore, Callable[[], None]]:
    conn = connect(paths.db_path)
    return MeetingStore(conn), NoteStore(conn), conn.close


def test_a_full_run_streams_the_transcript_and_writes_the_note(tmp_path: Path) -> None:
    service, events, kit, paths = make(tmp_path)
    reply = service.start("")
    assert reply["ok"] is True
    mid = reply["meeting_id"]
    line = events.wait_for("transcript.utterance")
    assert (line["meeting_id"], line["speaker"], line["text"]) == (mid, "You", "words")
    assert service.stop() == {"ok": True}
    events.wait_for("note.ready", meeting_id=mid)
    events.wait_for("recording.state", state="idle")
    assert events.states() == ["loading", "recording", "stopping", "processing", "idle"]
    finished = events.wait_for("recording.finished")
    assert finished["meeting_id"] == mid and finished["utterances"] >= 1
    names = events.names()
    assert names.index("note.stage") < names.index("note.ready")
    meetings, notes, close = _db(paths)
    try:
        assert meetings.get_meeting(mid)["state"] == "ready"
        assert notes.current_note(mid) is not None
    finally:
        close()
    assert kit.mics == [None]


def test_levels_are_pushed_only_while_recording(tmp_path: Path) -> None:
    service, events, _, _ = make(tmp_path)
    service.start("")
    deadline = time.monotonic() + 5  # capture warms up for 200 ms before frames flow
    while not any(p["you"] > 0 for n, p in list(events.items) if n == "recording.levels"):
        assert time.monotonic() < deadline, "no level above zero arrived"
        time.sleep(0.02)
    levels = [p for n, p in list(events.items) if n == "recording.levels"]
    assert all(0.0 <= p["you"] <= 1.0 and 0.0 <= p["them"] <= 1.0 for p in levels)
    service.stop()
    events.wait_for("recording.state", state="idle")
    count = events.names().count("recording.levels")
    time.sleep(0.1)
    assert events.names().count("recording.levels") == count


def test_a_missing_mic_fails_before_any_meeting_exists(tmp_path: Path) -> None:
    error = MicUnavailableError("microphone 'Headset' is not connected", "Pick it again.")
    service, events, _, paths = make(tmp_path, mic_error=error)
    assert service.start("Headset") == {
        "ok": False,
        "error": "microphone 'Headset' is not connected",
        "hint": "Pick it again.",
    }
    assert events.states() == ["loading", "idle"]
    meetings, _, close = _db(paths)
    try:
        assert meetings.latest_meeting_id() is None
    finally:
        close()


def test_a_model_that_will_not_load_is_explained(tmp_path: Path) -> None:
    service, events, _, _ = make(tmp_path, prepare_error=ModelError("checksum mismatch"))
    reply = service.start("")
    assert reply["ok"] is False and "ModelError" in reply["error"]
    assert events.states() == ["loading", "idle"]


def test_record_twice_and_stop_while_idle_are_refused(tmp_path: Path) -> None:
    service, events, _, _ = make(tmp_path)
    assert service.stop() == {"ok": False}
    assert events.states() == ["idle"]
    assert service.start("")["ok"] is True
    assert service.start("") == {"ok": False, "reason": "busy"}
    assert events.states()[-1] == "recording"
    events.wait_for("transcript.utterance")  # let one line through, so a note is written
    service.stop()
    events.wait_for("note.ready")


def test_two_record_clicks_at_once_make_one_recording(tmp_path: Path) -> None:
    service, events, kit, _ = make(tmp_path, prepare_delay=0.2)
    replies: list[dict[str, Any]] = []
    threads = [threading.Thread(target=lambda: replies.append(service.start(""))) for _ in "ab"]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(r["ok"] for r in replies) == [False, True]
    assert len(kit.mics) == 1
    events.wait_for("transcript.utterance")  # let one line through, so a note is written
    service.stop()
    events.wait_for("note.ready")


def test_a_failed_note_keeps_the_transcript_and_says_why(tmp_path: Path) -> None:
    service, events, _, paths = make(tmp_path, provider=lambda s: Down([]))
    mid = service.start("")["meeting_id"]
    events.wait_for("transcript.utterance")
    service.stop()
    assert events.wait_for("note.failed") == {"meeting_id": mid, "reason": "ollama_down"}
    events.wait_for("recording.state", state="idle")
    meetings, notes, close = _db(paths)
    try:
        assert meetings.get_meeting(mid)["state"] == "ready"
        version = meetings.current_transcript_version(mid)
        assert version is not None and meetings.utterances(version)
        assert notes.current_note(mid) is None
    finally:
        close()


def test_a_missing_model_is_named(tmp_path: Path) -> None:
    service, events, _, _ = make(tmp_path, provider=lambda s: NoModel([]))
    service.start("")
    events.wait_for("transcript.utterance")
    service.stop()
    failed = events.wait_for("note.failed")
    assert (failed["reason"], failed["model"]) == ("model_missing", "gemma4:12b")


def test_retry_writes_the_note_for_a_finished_meeting(tmp_path: Path) -> None:
    providers: list[LlmProvider] = [Down([]), FakeProvider([GOOD])]
    service, events, _, _ = make(tmp_path, provider=lambda s: providers.pop(0))
    mid = service.start("")["meeting_id"]
    events.wait_for("transcript.utterance")
    service.stop()
    events.wait_for("note.failed")
    events.wait_for("recording.state", state="idle")
    assert service.write_note(mid) == {"ok": True}
    events.wait_for("note.ready", meeting_id=mid)


def test_no_speech_means_no_note(tmp_path: Path) -> None:
    service, events, _, _ = make(tmp_path, speech=False)
    mid = service.start("")["meeting_id"]
    time.sleep(0.3)
    service.stop()
    assert events.wait_for("note.failed") == {"meeting_id": mid, "reason": "no_transcript"}


def test_closing_the_window_while_recording_saves_the_meeting(tmp_path: Path) -> None:
    service, events, kit, paths = make(tmp_path)
    mid = service.start("")["meeting_id"]
    events.wait_for("transcript.utterance")
    service.shutdown()
    assert kit.closed
    assert "note.stage" not in events.names()
    assert service.start("") == {"ok": False, "reason": "closing"}
    meetings, _, close = _db(paths)
    try:
        assert meetings.get_meeting(mid)["state"] == "ready"
        version = meetings.current_transcript_version(mid)
        assert version is not None and meetings.utterances(version)
    finally:
        close()


def test_closing_while_loading_starts_nothing(tmp_path: Path) -> None:
    service, _, kit, paths = make(tmp_path, prepare_delay=0.3)
    replies: list[dict[str, Any]] = []
    thread = threading.Thread(target=lambda: replies.append(service.start("")))
    thread.start()
    time.sleep(0.1)
    service.shutdown()
    thread.join()
    assert replies == [{"ok": False, "reason": "closing"}]
    assert kit.mics == []
    meetings, _, close = _db(paths)
    try:
        assert meetings.latest_meeting_id() is None
    finally:
        close()


def test_the_chosen_mic_is_remembered(tmp_path: Path) -> None:
    service, events, kit, paths = make(tmp_path)
    service.start("Headset (realme Buds Air7)")
    assert kit.mics == ["Headset (realme Buds Air7)"]
    assert service.mic_name == "Headset (realme Buds Air7)"
    assert load_settings(paths.settings_file).mic_name == "Headset (realme Buds Air7)"
    events.wait_for("transcript.utterance")  # let one line through, so a note is written
    service.stop()
    events.wait_for("note.ready")


def test_the_mic_list_is_refreshed_only_while_nothing_records(tmp_path: Path) -> None:
    from evra.capture.devices import MicList

    refreshed: list[bool] = []
    service, events, _, _ = make(tmp_path)
    service._refresh_devices = lambda: refreshed.append(True)  # type: ignore[method-assign]
    service._list_mics = lambda: MicList("Array", ("Array", "Headset"))  # type: ignore[method-assign]
    assert service.list_mics() == MicList("Array", ("Array", "Headset"))
    assert refreshed == [True]
    service.start("")
    service.list_mics()  # an open stream must never be cut by re-enumerating devices
    assert refreshed == [True]
    events.wait_for("transcript.utterance")
    service.stop()
    events.wait_for("note.ready")


def test_an_unexpected_start_error_returns_to_idle(tmp_path: Path) -> None:
    service, events, kit, _ = make(tmp_path, mic_error=RuntimeError("onnxruntime failed"))
    assert service.start("") == {
        "ok": False,
        "error": "Could not start recording (RuntimeError).",
        "hint": "",
    }
    assert events.states() == ["loading", "idle"]
    kit.mic_error = None
    assert service.start("")["ok"] is True  # not stuck in "loading"
    events.wait_for("transcript.utterance")
    service.stop()
    events.wait_for("note.ready")


def test_choosing_a_mic_keeps_settings_edited_while_the_app_runs(tmp_path: Path) -> None:
    from evra.config import save_settings

    service, events, _, paths = make(tmp_path)
    save_settings(paths.settings_file, Settings(llm=LlmSettings(model="qwen3.5:9b")))
    service.start("Headset (realme Buds Air7)")
    saved = load_settings(paths.settings_file)
    assert (saved.mic_name, saved.llm.model) == ("Headset (realme Buds Air7)", "qwen3.5:9b")
    events.wait_for("transcript.utterance")
    service.stop()
    events.wait_for("note.ready")


def test_speech_recognition_is_unloaded_only_while_idle(tmp_path: Path) -> None:
    service, events, kit, _ = make(tmp_path, idle_check_s=0.03)
    time.sleep(0.2)
    assert kit.releases > 0  # idle: the worker may go after its idle timeout (BUILD.md §4.2)
    service.start("")
    events.wait_for("transcript.utterance")
    during = kit.releases
    time.sleep(0.2)
    assert kit.releases == during  # never while recording
    service.stop()
    events.wait_for("note.ready")
    service.shutdown()
    after = kit.releases
    time.sleep(0.15)
    assert kit.releases == after  # and never after the window closed
