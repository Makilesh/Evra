from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from evra.asr.engine import Segment
from evra.audio.vad import SpeechSegmenter
from evra.capture.fake import FakeSource
from evra.capture.session import CaptureSession
from evra.capture.sources import CaptureError
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.migrate import migrate
from evra.transcribe.labels import LABELS
from evra.transcribe.record import run_recording
from evra.transcribe.recording import LiveRecording
from tests.unit.audio.test_vad import FakeVad


class NumberAsr:
    def transcribe(self, pcm: np.ndarray) -> list[Segment]:
        return [Segment(0, len(pcm) * 1000 // 16_000, "words", ())]


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "evra.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    return db


def _sources(seconds: float) -> tuple[FakeSource, FakeSource]:
    tone = (0.3 * np.sin(np.arange(int(16_000 * seconds)) / 5)).astype(np.float32)
    return (
        FakeSource(tone, 16_000, name="mic"),
        FakeSource(tone, 16_000, name="out", pads_silence=True),
    )


def _recording(
    db: Path,
    mic: FakeSource,
    system: FakeSource,
    scripts: Sequence[Sequence[tuple[int, int]]] = ((), ()),
    **kwargs: Any,
) -> LiveRecording:
    segmenters = {
        channel: SpeechSegmenter(channel, FakeVad(script=list(script)))
        for channel, script in enumerate(scripts)
    }
    return LiveRecording(
        session=CaptureSession(mic, system),
        segmenters=segmenters,
        asr=NumberAsr(),
        db_path=db,
        title="t",
        situation="call_headphones",
        **kwargs,
    )


def _stored(db: Path, meeting_id: str) -> tuple[dict[str, Any], list[Utterance]]:
    conn = connect(db)
    try:
        store = MeetingStore(conn)
        version = store.current_transcript_version(meeting_id)
        return store.get_meeting(meeting_id), store.utterances(version) if version else []
    finally:
        conn.close()


def test_speech_on_both_channels_becomes_labelled_utterances(tmp_path: Path) -> None:
    db = _db(tmp_path)
    mic, system = _sources(1.5)
    heard: list[Utterance] = []
    recording = _recording(
        db, mic, system, ([(3_200, 9_600)], [(8_000, 14_400)]), on_utterance=heard.append
    )
    result = run_recording(recording, seconds=1.6)
    meeting, rows = _stored(db, result.meeting_id)
    assert result.utterances == 2 and {r.channel for r in rows} == {0, 1}
    assert meeting["state"] == "ready" and meeting["mode"] == "one_on_one"
    assert len(heard) == 2
    assert LABELS == {0: "You", 1: "Them"}


def test_silence_only_recording_says_no_speech(tmp_path: Path) -> None:
    db = _db(tmp_path)
    mic, system = _sources(0.6)
    result = run_recording(_recording(db, mic, system), seconds=0.7)
    meeting, _ = _stored(db, result.meeting_id)
    assert result.utterances == 0 and meeting["state"] == "ready"


def test_interrupt_still_finishes_the_meeting(tmp_path: Path) -> None:
    db = _db(tmp_path)
    mic, system = _sources(3.0)

    def interrupted_sleep(seconds: float) -> None:
        import time

        time.sleep(0.6)
        raise KeyboardInterrupt

    recording = _recording(db, mic, system, ([(1_600, 6_400)], []))
    result = run_recording(recording, seconds=30, sleep=interrupted_sleep)
    meeting, _ = _stored(db, result.meeting_id)
    assert result.interrupted and result.utterances == 1
    assert meeting["state"] == "ready"
    assert not mic.is_active() or mic._thread is None


def test_ctrl_c_is_held_off_while_wrapping_up() -> None:
    import signal

    from evra.transcribe.record import ignore_ctrl_c

    before = signal.getsignal(signal.SIGINT)
    with ignore_ctrl_c():
        assert signal.getsignal(signal.SIGINT) == signal.SIG_IGN
    assert signal.getsignal(signal.SIGINT) == before


def test_capture_start_failure_creates_no_meeting(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _, system = _sources(0.5)

    class BrokenMic(FakeSource):
        def start(self) -> None:
            raise CaptureError("no microphone", "plug one in")

    mic = BrokenMic(np.zeros((1600, 1), dtype=np.float32), 16_000)
    with pytest.raises(CaptureError):
        run_recording(_recording(db, mic, system), seconds=1)
    conn = connect(db)
    try:
        assert MeetingStore(conn).latest_meeting_id() is None
    finally:
        conn.close()


def test_levels_are_reported_for_both_channels(tmp_path: Path) -> None:
    db = _db(tmp_path)
    mic, system = _sources(0.6)
    levels: dict[int, list[float]] = {0: [], 1: []}
    recording = _recording(db, mic, system, on_level=lambda ch, v: levels[ch].append(v))
    run_recording(recording, seconds=0.7)
    assert levels[0] and levels[1]
    assert max(levels[0]) > 0.5
    assert all(0.0 <= v <= 1.0 for v in levels[0] + levels[1])


def test_summary_only_claims_no_speech_when_none_was_detected() -> None:
    from evra.transcribe.live import TranscriberStats
    from evra.transcribe.record import RecordingResult, summary_lines

    silent = RecordingResult("m", 0, None, TranscriberStats(0, 0, 0, 0, 0), False)
    failed = RecordingResult("m", 0, None, TranscriberStats(3, 0, 3, 3000, 10), False)
    leftover = RecordingResult(
        "m", 2, None, TranscriberStats(5, 2, 0, 5000, 10, unprocessed=3, drained=False), False
    )
    assert "no speech detected" in "\n".join(summary_lines(silent))
    failed_text = "\n".join(summary_lines(failed))
    assert "no speech detected" not in failed_text and "3 failed" in failed_text
    assert "3 segments were still waiting" in "\n".join(summary_lines(leftover))
