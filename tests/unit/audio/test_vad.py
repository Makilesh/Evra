import itertools
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from evra.audio.frames import Frames
from evra.audio.vad import VAD_WINDOW, SpeechSegmenter, silero_vad
from evra.paths import resolve_paths
from tests.conftest import requires_models


@dataclass
class _Seg:
    start: int
    samples: np.ndarray


@dataclass
class FakeVad:
    """Emits scripted (start, end) segments once enough audio has been accepted."""

    script: list[tuple[int, int]]
    audio: list[np.ndarray] = field(default_factory=list)
    sizes: list[int] = field(default_factory=list)
    ready: list[_Seg] = field(default_factory=list)
    flushed: bool = False

    def accept_waveform(self, samples: np.ndarray) -> None:
        self.sizes.append(len(samples))
        self.audio.append(samples.copy())
        self._release()

    def _release(self) -> None:
        have = sum(len(a) for a in self.audio)
        while self.script and (self.script[0][1] <= have or self.flushed):
            start, end = self.script.pop(0)
            everything = np.concatenate(self.audio)
            self.ready.append(_Seg(start, everything[start:end]))

    def flush(self) -> None:
        self.flushed = True
        self._release()

    def empty(self) -> bool:
        return not self.ready

    def is_speech_detected(self) -> bool:
        return False  # scripted segments never trigger the forced 20 s cut

    @property
    def front(self) -> _Seg:
        return self.ready[0]

    def pop(self) -> None:
        self.ready.pop(0)


def _frames(audio: np.ndarray, first_index: int = 0, channel: int = 0) -> list[Frames]:
    return [
        Frames(channel, audio[i : i + 160], (first_index + i) * 62_500, first_index + i)  # type: ignore[arg-type]
        for i in range(0, len(audio), 160)
    ]


def _run(seg: SpeechSegmenter, audio: np.ndarray, first_index: int = 0) -> list:  # type: ignore[type-arg]
    out = []
    for f in _frames(audio, first_index):
        out += seg.accept(f)
    return out + seg.flush()


def test_vad_is_fed_512_sample_windows() -> None:
    vad = FakeVad(script=[])
    _run(SpeechSegmenter(0, vad), np.zeros(16_000, dtype=np.int16))
    assert all(s == VAD_WINDOW for s in vad.sizes[:-1]) and sum(vad.sizes) == 16_000


def test_segment_maps_to_timeline_with_pre_roll() -> None:
    audio = np.arange(48_000, dtype=np.int16) % 1000  # distinct values to check alignment
    vad = FakeVad(script=[(16_000, 32_000)])  # speech from 1.0 s to 2.0 s of what it was fed
    [s] = _run(SpeechSegmenter(1, vad), audio, first_index=8_000)
    assert s.channel == 1
    assert s.start_index == 8_000 + 16_000 - 4_800  # 300 ms of pre-roll
    assert len(s.pcm) == 16_000 + 4_800
    np.testing.assert_array_equal(s.pcm, audio[16_000 - 4_800 : 32_000])
    assert (s.start_ms, s.end_ms) == ((8_000 + 11_200) // 16, (8_000 + 32_000) // 16)


def test_pre_roll_is_clipped_at_the_start_of_the_channel() -> None:
    audio = np.ones(32_000, dtype=np.int16)
    vad = FakeVad(script=[(1_600, 16_000)])
    [s] = _run(SpeechSegmenter(0, vad), audio)
    assert s.start_index == 0 and len(s.pcm) == 16_000


def test_flush_releases_speech_still_in_progress() -> None:
    vad = FakeVad(script=[(0, 20_000)])
    segs = _run(SpeechSegmenter(0, vad), np.ones(16_000, dtype=np.int16))
    assert len(segs) == 1 and vad.flushed


@requires_models("silero-vad")
def test_real_silero_finds_the_speech() -> None:
    import wave

    from evra.audio.convert import ToMono16k
    from evra.paths import REPO_ROOT

    with wave.open(str(REPO_ROOT / "spikes" / "test_wavs" / "en.wav")) as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    speech = ToMono16k(rate, 1).process((pcm / 32768.0).astype(np.float32))
    audio = np.concatenate([np.zeros(16_000, np.int16), speech, np.zeros(16_000, np.int16)])
    model = resolve_paths().models_dir / "silero-vad" / "silero_vad.onnx"
    segs = _run(SpeechSegmenter(0, silero_vad(Path(model))), audio)
    assert len(segs) >= 1
    assert 500 <= segs[0].start_ms <= 1_100


@dataclass
class ContinuousVad:
    """Hears speech in everything; only a flush closes a segment (like one endless voice)."""

    fed: int = 0
    start: int = 0
    audio: list[np.ndarray] = field(default_factory=list)
    ready: list[_Seg] = field(default_factory=list)

    def accept_waveform(self, samples: np.ndarray) -> None:
        self.audio.append(samples.copy())
        self.fed += len(samples)

    def is_speech_detected(self) -> bool:
        return True

    def flush(self) -> None:
        if self.fed > self.start:
            everything = np.concatenate(self.audio)
            self.ready.append(_Seg(self.start, everything[self.start : self.fed]))
            self.start = self.fed

    def empty(self) -> bool:
        return not self.ready

    @property
    def front(self) -> _Seg:
        return self.ready[0]

    def pop(self) -> None:
        self.ready.pop(0)


def test_continuous_speech_is_cut_every_20_seconds_without_overlap() -> None:
    audio = (np.arange(16_000 * 50) % 2000 - 1000).astype(np.int16)
    segs = _run(SpeechSegmenter(0, ContinuousVad()), audio)
    assert len(segs) == 3
    assert all(len(s.pcm) <= 16_000 * 20 + 512 for s in segs)
    for before, after in itertools.pairwise(segs):
        assert after.start_index == before.start_index + len(before.pcm)  # no overlap, no gap
    np.testing.assert_array_equal(np.concatenate([s.pcm for s in segs]), audio)  # exact samples


@requires_models("silero-vad")
def test_real_silero_cuts_endless_speech() -> None:
    import wave

    from evra.audio.convert import ToMono16k
    from evra.paths import REPO_ROOT

    with wave.open(str(REPO_ROOT / "spikes" / "test_wavs" / "en.wav")) as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    speech = ToMono16k(rate, 1).process((pcm / 32768.0).astype(np.float32))
    loud = np.nonzero(np.abs(speech) > 600)[0]
    core = speech[loud[0] : loud[-1]]
    endless = np.tile(core, 40)[: 16_000 * 50]  # 50 s with no pauses
    model = resolve_paths().models_dir / "silero-vad" / "silero_vad.onnx"
    segs = _run(SpeechSegmenter(0, silero_vad(Path(model))), endless)
    assert len(segs) >= 3
    assert max(len(s.pcm) for s in segs) <= 16_000 * 21
