import json
import wave
from pathlib import Path

import numpy as np
import pytest

from evra.__main__ import main
from evra.audio.keys import MemoryKeyStore
from evra.capture.capture_test import run_capture_test, write_wav
from evra.capture.fake import FakeSource
from evra.capture.session import CaptureSession
from evra.paths import AppPaths


def _wav(path: Path, rate: int, channels: int, seconds: float) -> Path:
    t = np.arange(int(rate * seconds)) / rate
    mono = (0.3 * 32767 * np.sin(2 * np.pi * 300 * t)).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.repeat(mono[:, None], channels, axis=1).tobytes())
    return path


def test_run_capture_test_writes_wavs_and_health_and_cleans_up(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path / "home")
    paths.ensure()
    keys = MemoryKeyStore()
    mic = FakeSource.from_wav(_wav(tmp_path / "m.wav", 44_100, 1, 1.2))
    system = FakeSource.from_wav(_wav(tmp_path / "s.wav", 48_000, 2, 1.2), pads_silence=True)
    out = tmp_path / "out"
    health = run_capture_test(
        CaptureSession(mic, system),
        seconds=1.0,
        paths=paths,
        keys=keys,
        out_dir=out,
        meeting_id="t1",
    )
    assert health.ok
    for name in ("mic.wav", "system.wav"):
        with wave.open(str(out / name), "rb") as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16_000, 1, 2)
            assert w.getnframes() >= 15_000
    report = json.loads((out / "health.json").read_text(encoding="utf-8"))
    assert report["ok"] is True and "mic" in report["channels"]
    assert not (paths.spill_dir / "t1").exists()  # temporary audio deleted
    assert keys.get("t1") is None  # key deleted


def test_cli_with_fake_sources(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("evra.capture.capture_test.KeyringKeyStore", MemoryKeyStore)
    mic = _wav(tmp_path / "m.wav", 16_000, 1, 1.5)
    system = _wav(tmp_path / "s.wav", 48_000, 2, 1.5)
    out = tmp_path / "out"
    code = main(
        [
            "capture-test",
            "1.0",
            "--fake-mic",
            str(mic),
            "--fake-system",
            str(system),
            "--data-dir",
            str(tmp_path / "home"),
            "--out",
            str(out),
        ]
    )
    text = capsys.readouterr().out
    assert code == 0 and "PASS" in text
    assert (out / "health.json").exists()


def test_cli_reports_capture_error_with_hint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from evra.capture import capture_test
    from evra.capture.sources import MIC_PRIVACY_HINT, MicUnavailableError

    def broken_mic(*args: object, **kwargs: object) -> None:
        raise MicUnavailableError("could not open microphone 'X'", MIC_PRIVACY_HINT)

    monkeypatch.setattr(capture_test, "MicSource", broken_mic)
    code = main(["capture-test", "1", "--data-dir", str(tmp_path / "home")])
    err = capsys.readouterr().err
    assert code == 2
    assert "could not open microphone" in err and "ms-settings:privacy-microphone" in err


def test_write_wav_round_trip(tmp_path: Path) -> None:
    pcm = np.arange(-100, 100, dtype=np.int16)
    write_wav(tmp_path / "x.wav", pcm)
    with wave.open(str(tmp_path / "x.wav"), "rb") as w:
        assert np.array_equal(np.frombuffer(w.readframes(200), dtype="<i2"), pcm)
