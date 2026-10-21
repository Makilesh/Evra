"""The speech-to-text worker (BUILD.md §4, D6, D8): Parakeet runs in its own process."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import numpy as np

from evra.asr.engine import Segment, segment_from_dict, segment_to_dict
from evra.asr.parakeet import PARAKEET_ID
from evra.audio.frames import Int16Array
from evra.workers.protocol import Handler
from evra.workers.supervisor import Worker


def make_asr_handler(model_dir: str, num_threads: int = 4) -> Handler:
    """Runs inside the worker process: load the model once, then answer requests."""
    from evra.asr.parakeet import ParakeetEngine

    engine = ParakeetEngine(Path(model_dir), num_threads=num_threads)

    def handle(op: str, payload: Any) -> Any:
        if op == "ping":
            return "pong"
        if op == "transcribe":
            pcm = np.frombuffer(payload["pcm"], dtype="<i2").astype(np.int16)
            return [segment_to_dict(s) for s in engine.transcribe(pcm, payload["language"])]
        raise ValueError(f"unknown op {op!r}")

    return handle


class Transcriber(Protocol):
    def transcribe(self, pcm: Int16Array) -> list[Segment]: ...


class AsrClient:
    """App-side handle to the ASR worker."""

    def __init__(self, worker: Worker) -> None:
        self._worker = worker

    @classmethod
    def for_models(
        cls, models_dir: Path, *, num_threads: int = 4, idle_timeout_s: float = 300.0
    ) -> AsrClient:
        config = {"model_dir": str(models_dir / PARAKEET_ID), "num_threads": num_threads}
        worker = Worker(
            "asr", "evra.workers.asr:make_asr_handler", config, idle_timeout_s=idle_timeout_s
        )
        return cls(worker)

    def warm_up(self, timeout_s: float = 120.0) -> None:
        """Start the worker and load the model before audio arrives."""
        self._worker.call("ping", None, timeout_s)

    def transcribe(self, pcm: Int16Array, *, timeout_s: float = 60.0) -> list[Segment]:
        payload = {"pcm": pcm.astype("<i2").tobytes(), "language": "en"}
        return [segment_from_dict(d) for d in self._worker.call("transcribe", payload, timeout_s)]

    def stop_if_idle(self) -> bool:
        return self._worker.stop_if_idle()

    def stop(self) -> None:
        self._worker.stop()
