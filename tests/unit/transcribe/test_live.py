from pathlib import Path

import numpy as np
import pytest

from evra.asr.engine import Segment, Word
from evra.audio.vad import SpeechSegment
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.migrate import migrate
from evra.transcribe.live import LiveTranscriber
from evra.workers.protocol import WorkerCrashed


class FakeAsr:
    def __init__(self, fail_first: int = 0, crash_once: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first
        self.crash_once = crash_once

    def transcribe(self, pcm: np.ndarray) -> list[Segment]:
        self.calls += 1
        if self.crash_once:
            self.crash_once = False
            raise WorkerCrashed("asr")
        if self.fail_first:
            self.fail_first -= 1
            raise TimeoutError
        end = len(pcm) * 1000 // 16_000
        return [Segment(0, end, f"text {int(pcm[0])}", (Word(0, end, f"w{int(pcm[0])}"),))]


@pytest.fixture
def db(tmp_path: Path) -> tuple[Path, str, str]:
    path = tmp_path / "evra.db"
    conn = connect(path)
    migrate(conn)
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    conn.close()
    return path, mid, vid


def _seg(channel: int, start_s: float, marker: int) -> SpeechSegment:
    return SpeechSegment(channel, int(start_s * 16_000), np.full(16_000, marker, dtype=np.int16))


def _stored(path: Path, vid: str) -> list[Utterance]:
    conn = connect(path)
    try:
        return MeetingStore(conn).utterances(vid)
    finally:
        conn.close()


def test_segments_are_stored_in_order_with_absolute_times(db) -> None:  # type: ignore[no-untyped-def]
    path, mid, vid = db
    seen: list[Utterance] = []
    live = LiveTranscriber(FakeAsr(), path, meeting_id=mid, version_id=vid)
    live.add_listener(seen.append)
    live.start()
    for i, (ch, t) in enumerate([(0, 1.0), (1, 2.5), (0, 20.0), (0, 21.0)]):
        live.submit(_seg(ch, t, i + 1))
    stats = live.stop()
    rows = _stored(path, vid)
    assert [r.text for r in rows] == ["text 1", "text 2", "text 3", "text 4"]
    assert [(r.channel, r.start_ms, r.end_ms) for r in rows][:2] == [
        (0, 1000, 2000),
        (1, 2500, 3500),
    ]
    assert rows[0].words[0].start_ms == 1000  # word times are absolute too
    assert [u.text for u in seen] == [r.text for r in rows]
    assert stats.segments == 4 and stats.utterances == 4 and stats.failures == 0


def test_failed_segment_is_counted_and_later_segments_still_work(db) -> None:  # type: ignore[no-untyped-def]
    path, mid, vid = db
    asr = FakeAsr(fail_first=2)  # the first try and its retry both fail
    live = LiveTranscriber(asr, path, meeting_id=mid, version_id=vid)
    live.start()
    live.submit(_seg(0, 1.0, 1))
    live.submit(_seg(0, 3.0, 2))
    stats = live.stop()
    assert stats.failures == 1
    assert [r.text for r in _stored(path, vid)] == ["text 2"]


def test_a_worker_crash_is_retried_once(db) -> None:  # type: ignore[no-untyped-def]
    path, mid, vid = db
    asr = FakeAsr(crash_once=True)
    live = LiveTranscriber(asr, path, meeting_id=mid, version_id=vid)
    live.start()
    live.submit(_seg(0, 1.0, 7))
    stats = live.stop()
    assert asr.calls == 2 and stats.failures == 0
    assert [r.text for r in _stored(path, vid)] == ["text 7"]


def test_a_listener_error_does_not_stop_transcription(db) -> None:  # type: ignore[no-untyped-def]
    path, mid, vid = db
    live = LiveTranscriber(FakeAsr(), path, meeting_id=mid, version_id=vid)

    def broken(u: Utterance) -> None:
        raise RuntimeError("ui gone")

    live.add_listener(broken)
    live.start()
    live.submit(_seg(0, 1.0, 1))
    live.submit(_seg(0, 2.0, 2))
    assert live.stop().utterances == 2


def test_a_timeout_is_retried_once(db) -> None:  # type: ignore[no-untyped-def]
    path, mid, vid = db
    asr = FakeAsr(fail_first=1)
    live = LiveTranscriber(asr, path, meeting_id=mid, version_id=vid)
    live.start()
    live.submit(_seg(0, 1.0, 5))
    stats = live.stop()
    assert asr.calls == 2 and stats.failures == 0
    assert [r.text for r in _stored(path, vid)] == ["text 5"]


def test_a_database_error_is_counted_and_later_segments_still_work(db, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import sqlite3

    path, mid, vid = db
    real_add = MeetingStore.add_utterance
    calls = {"n": 0}

    def flaky_add(self, **kwargs):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_add(self, **kwargs)

    monkeypatch.setattr(MeetingStore, "add_utterance", flaky_add)
    live = LiveTranscriber(FakeAsr(), path, meeting_id=mid, version_id=vid)
    live.start()
    live.submit(_seg(0, 1.0, 1))
    live.submit(_seg(0, 2.0, 2))
    stats = live.stop()
    assert stats.failures == 1 and stats.utterances == 1


def test_an_unreachable_database_fails_segments_instead_of_dying(tmp_path: Path) -> None:
    folder = tmp_path / "not-a-database"
    folder.mkdir()
    live = LiveTranscriber(FakeAsr(), folder, meeting_id="m", version_id="v")
    live.start()
    live.submit(_seg(0, 1.0, 1))
    stats = live.stop(timeout_s=10)
    assert stats.drained and stats.failures == 1 and stats.utterances == 0


def test_stop_that_times_out_reports_leftovers_and_stops_writing(db) -> None:  # type: ignore[no-untyped-def]
    import time

    path, mid, vid = db

    class SlowAsr(FakeAsr):
        def transcribe(self, pcm: np.ndarray) -> list[Segment]:
            time.sleep(0.4)
            return super().transcribe(pcm)

    live = LiveTranscriber(SlowAsr(), path, meeting_id=mid, version_id=vid)
    live.start()
    for i in range(6):
        live.submit(_seg(0, float(i), i + 1))
    stats = live.stop(timeout_s=0.5)
    assert not stats.drained and stats.unprocessed >= 3
    written = len(_stored(path, vid))
    time.sleep(1.5)
    assert len(_stored(path, vid)) <= written + 1  # at most the one already in progress
