import wave
from pathlib import Path

import numpy as np
import pytest

from evra.__main__ import main
from evra.asr.engine import Segment
from evra.asr.parakeet import PARAKEET_ID
from evra.paths import REPO_ROOT
from evra.transcribe.cli import format_ms, transcribe_file
from tests.conftest import requires_models
from tests.unit.audio.test_vad import FakeVad


class EchoAsr:
    def transcribe(self, pcm: np.ndarray) -> list[Segment]:
        return [Segment(0, len(pcm) * 1000 // 16_000, "speech", ())]


def _wav(path: Path, rate: int, seconds: float) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.full(int(rate * seconds), 1000, dtype="<i2").tobytes())
    return path


def test_format_ms() -> None:
    assert (
        format_ms(0) == "00:00" and format_ms(83_400) == "01:23" and format_ms(3_600_000) == "60:00"
    )


def test_transcribe_file_resamples_segments_and_offsets(tmp_path: Path) -> None:
    wav = _wav(tmp_path / "a.wav", 48_000, 3.0)
    lines = transcribe_file(wav, asr=EchoAsr(), vad=FakeVad(script=[(16_000, 32_000)]))
    [(start, end, text)] = lines
    assert text == "speech" and 700 <= start <= 1000 and 1900 <= end <= 2100


def test_models_command_lists_catalogue(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["models", "--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "silero-vad" in out and PARAKEET_ID in out and "missing" in out


@requires_models(PARAKEET_ID, "silero-vad")
def test_real_transcribe_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["transcribe", str(REPO_ROOT / "spikes" / "test_wavs" / "en.wav")]) == 0
    assert "country" in capsys.readouterr().out.lower()
