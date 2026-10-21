import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from evra.asr.engine import Segment, Word, segment_from_dict, segment_to_dict
from evra.asr.parakeet import PARAKEET_ID, ParakeetEngine, words_from_tokens
from evra.audio.convert import ToMono16k
from evra.paths import REPO_ROOT, resolve_paths
from tests.conftest import requires_models


def test_words_are_built_from_bpe_tokens() -> None:
    tokens = [" A", "sk", " not", " what", ",", " co", "un", "try", "."]
    starts = [0.0, 0.24, 0.4, 0.64, 0.7, 0.8, 0.96, 1.04, 1.3]
    words = words_from_tokens(tokens, starts, total_ms=1500)
    assert [w.text for w in words] == ["Ask", "not", "what,", "country."]
    assert [(w.start_ms, w.end_ms) for w in words] == [
        (0, 400),
        (400, 640),
        (640, 800),
        (800, 1500),
    ]


def test_words_from_no_tokens() -> None:
    assert words_from_tokens([], [], 1000) == []


class FakeStream:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.accepted: tuple[int, np.ndarray] | None = None

    def accept_waveform(self, rate: int, samples: np.ndarray) -> None:
        self.accepted = (rate, samples)


class FakeRecognizer:
    def __init__(self, text: str) -> None:
        self.result = SimpleNamespace(text=text, tokens=[" Hello", " there"], timestamps=[0.1, 0.5])
        self.stream: FakeStream | None = None

    def create_stream(self) -> FakeStream:
        self.stream = FakeStream(self.result)
        return self.stream

    def decode_stream(self, stream: FakeStream) -> None: ...


def test_engine_wraps_the_recognizer() -> None:
    rec = FakeRecognizer(" Hello there ")
    engine = ParakeetEngine(Path("unused"), recognizer=rec)
    pcm = np.full(16_000, 16384, dtype=np.int16)
    [seg] = engine.transcribe(pcm)
    assert seg.text == "Hello there" and (seg.start_ms, seg.end_ms) == (0, 1000)
    assert [w.text for w in seg.words] == ["Hello", "there"]
    rate, samples = rec.stream.accepted  # type: ignore[union-attr, misc]
    assert rate == 16_000 and samples.dtype == np.float32 and abs(samples[0] - 0.5) < 1e-6


def test_empty_audio_and_empty_text_give_no_segments() -> None:
    engine = ParakeetEngine(Path("unused"), recognizer=FakeRecognizer("  "))
    assert engine.transcribe(np.zeros(0, dtype=np.int16)) == []
    assert engine.transcribe(np.zeros(1600, dtype=np.int16)) == []


def test_segment_dict_round_trip() -> None:
    seg = Segment(10, 90, "hi", (Word(10, 50, "hi"),))
    assert segment_from_dict(segment_to_dict(seg)) == seg


@requires_models(PARAKEET_ID)
def test_real_parakeet_transcribes_english() -> None:
    with wave.open(str(REPO_ROOT / "spikes" / "test_wavs" / "en.wav")) as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    audio16k = ToMono16k(rate, 1).process((pcm / 32768.0).astype(np.float32))
    engine = ParakeetEngine(resolve_paths().models_dir / PARAKEET_ID)
    [seg] = engine.transcribe(audio16k)
    assert "country" in seg.text.lower()
    assert seg.words and seg.words[0].start_ms < 500
