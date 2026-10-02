from pathlib import Path

import numpy as np
import pytest

from evra.paths import AppPaths
from evra.transcribe.recording import RecordingKit, frame_level


def test_frame_level_maps_minus_60_to_0_dbfs_onto_0_to_1() -> None:
    assert frame_level(np.zeros(160, dtype=np.int16)) == 0.0
    assert frame_level(np.full(160, 32767, dtype=np.int16)) == pytest.approx(1.0, abs=1e-3)
    assert frame_level(np.full(160, 3277, dtype=np.int16)) == pytest.approx(40 / 60, abs=1e-3)
    assert frame_level(np.zeros(0, dtype=np.int16)) == 0.0


class FakeAsr:
    def __init__(self) -> None:
        self.warmups = 0
        self.stopped = False

    def warm_up(self) -> None:
        self.warmups += 1

    def stop(self) -> None:
        self.stopped = True


def test_the_kit_loads_once_and_stops_the_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[AppPaths] = []

    def fake_models(paths: AppPaths) -> dict[str, Path]:
        calls.append(paths)
        return {"silero-vad": tmp_path}

    monkeypatch.setattr("evra.transcribe.recording.ensure_speech_models", fake_models)
    asr = FakeAsr()
    kit = RecordingKit(AppPaths.under(tmp_path), asr=asr)  # type: ignore[arg-type]
    kit.prepare()
    kit.prepare()
    assert len(calls) == 1 and asr.warmups == 1
    kit.close()
    assert asr.stopped
