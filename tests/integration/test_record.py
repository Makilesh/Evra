from pathlib import Path

import numpy as np

from evra.asr.engine import Segment
from evra.audio.vad import SpeechSegmenter
from evra.capture.fake import FakeSource
from evra.capture.session import CaptureSession
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.transcribe.live import LiveTranscriber
from evra.transcribe.record import LABELS, run_recording
from tests.unit.audio.test_vad import FakeVad


class NumberAsr:
    def transcribe(self, pcm: np.ndarray) -> list[Segment]:
        return [Segment(0, len(pcm) * 1000 // 16_000, "words", ())]


def _setup(tmp_path: Path) -> tuple[Path, MeetingStore, str, str]:
    db = tmp_path / "evra.db"
    conn = connect(db)
    migrate(conn)
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    return db, store, mid, vid


def _sources(seconds: float) -> tuple[FakeSource, FakeSource]:
    tone = (0.3 * np.sin(np.arange(int(16_000 * seconds)) / 5)).astype(np.float32)
    return (
        FakeSource(tone, 16_000, name="mic"),
        FakeSource(tone, 16_000, name="out", pads_silence=True),
    )


def test_speech_on_both_channels_becomes_labelled_utterances(tmp_path: Path) -> None:
    db, store, mid, vid = _setup(tmp_path)
    mic, system = _sources(1.5)
    segmenters = {
        0: SpeechSegmenter(0, FakeVad(script=[(3_200, 9_600)])),
        1: SpeechSegmenter(1, FakeVad(script=[(8_000, 14_400)])),
    }
    live = LiveTranscriber(NumberAsr(), db, meeting_id=mid, version_id=vid)
    result = run_recording(CaptureSession(mic, system), segmenters, live, store, mid, seconds=1.6)
    rows = store.utterances(vid)
    assert result.utterances == 2 and {r.channel for r in rows} == {0, 1}
    assert store.get_meeting(mid)["state"] == "ready"
    assert LABELS == {0: "You", 1: "Them"}


def test_silence_only_recording_says_no_speech(tmp_path: Path) -> None:
    db, store, mid, vid = _setup(tmp_path)
    mic, system = _sources(0.6)
    segmenters = {
        0: SpeechSegmenter(0, FakeVad(script=[])),
        1: SpeechSegmenter(1, FakeVad(script=[])),
    }
    live = LiveTranscriber(NumberAsr(), db, meeting_id=mid, version_id=vid)
    result = run_recording(CaptureSession(mic, system), segmenters, live, store, mid, seconds=0.7)
    assert result.utterances == 0 and store.get_meeting(mid)["state"] == "ready"


def test_interrupt_still_finishes_the_meeting(tmp_path: Path) -> None:
    db, store, mid, vid = _setup(tmp_path)
    mic, system = _sources(3.0)
    segmenters = {
        0: SpeechSegmenter(0, FakeVad(script=[(1_600, 6_400)])),
        1: SpeechSegmenter(1, FakeVad(script=[])),
    }
    live = LiveTranscriber(NumberAsr(), db, meeting_id=mid, version_id=vid)

    def interrupted_sleep(seconds: float) -> None:
        import time

        time.sleep(0.6)
        raise KeyboardInterrupt

    result = run_recording(
        CaptureSession(mic, system),
        segmenters,
        live,
        store,
        mid,
        seconds=30,
        sleep=interrupted_sleep,
    )
    assert result.interrupted and result.utterances == 1
    assert store.get_meeting(mid)["state"] == "ready"
    assert not mic.is_active() or mic._thread is None
