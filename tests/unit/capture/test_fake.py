import wave
from pathlib import Path

import numpy as np

from evra.capture.fake import FakeEvent, FakeSource


class VirtualTime:
    def __init__(self) -> None:
        self.t = 0

    def now(self) -> int:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += int(seconds * 1e9)


def _run(src: FakeSource) -> list[np.ndarray]:
    src.start()
    assert src.finished.wait(5)
    src.stop()
    return [c.data for c in src.ring.drain()]


def test_replays_all_audio_in_10ms_chunks() -> None:
    vt = VirtualTime()
    audio = np.linspace(-0.5, 0.5, 16_000, dtype=np.float32)  # 1 s at 16 kHz
    chunks = _run(FakeSource(audio, 16_000, now_ns=vt.now, sleep=vt.sleep))
    assert len(chunks) == 100 and all(c.shape == (160, 1) for c in chunks)
    np.testing.assert_array_equal(np.concatenate(chunks)[:, 0], audio)


def test_dropout_delivers_nothing_and_silence_delivers_zeros() -> None:
    vt = VirtualTime()
    audio = np.full(16_000, 0.25, dtype=np.float32)
    events = [FakeEvent("dropout", 0.2, 0.1), FakeEvent("silence", 0.5, 0.1)]
    chunks = _run(FakeSource(audio, 16_000, events=events, now_ns=vt.now, sleep=vt.sleep))
    assert len(chunks) == 90
    zeros = [c for c in chunks if not c.any()]
    assert len(zeros) == 10


def test_from_wav(tmp_path: Path) -> None:
    path = tmp_path / "a.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48_000)
        w.writeframes(np.full((480, 2), 16384, dtype=np.int16).tobytes())
    src = FakeSource.from_wav(path)
    assert (src.native_rate, src.native_channels) == (48_000, 2)
    assert np.allclose(src.audio, 0.5)
