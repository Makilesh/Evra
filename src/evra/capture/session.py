"""Two-channel capture session: sources + pipeline thread + output watcher (BUILD.md §5)."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any

import structlog

from evra.audio.frames import MIC, SAMPLE_RATE, SYSTEM, Channel, Frames
from evra.audio.pipeline import CapturePipeline, ChannelStats
from evra.capture.sources import AudioSource, CaptureError

log = structlog.get_logger(__name__)

DRIFT_LIMIT_MS = 30.0
SILENT_DBFS = -60.0
WatcherFactory = Callable[[Callable[[str | None], None]], Any]


@dataclass(frozen=True)
class ChannelHealth:
    device: str
    native_rate: int
    native_channels: int
    seconds: float
    rms_dbfs: float
    peak_dbfs: float
    dropped_chunks: int
    corrections: int
    inserted_ms: float
    dropped_ms: float
    padded_ms: float
    drift_ms: float
    gaps: list[dict[str, Any]]


@dataclass(frozen=True)
class CaptureHealth:
    channels: dict[str, ChannelHealth]
    inter_channel_drift_ms: float
    device_changes: int
    hints: list[str]
    ok: bool


def _channel_health(device: str, stats: ChannelStats) -> ChannelHealth:
    fields = asdict(stats)
    fields.pop("channel")
    fields["gaps"] = [
        {
            "start_ms": g.start * 1000 // SAMPLE_RATE,
            "duration_ms": g.length * 1000 // SAMPLE_RATE,
            "cause": g.cause,
        }
        for g in stats.gaps
    ]
    return ChannelHealth(device=device, **fields)


class CaptureSession:
    def __init__(
        self,
        mic: AudioSource,
        system: AudioSource,
        *,
        watcher_factory: WatcherFactory | None = None,
        now_ns: Callable[[], int] = time.monotonic_ns,
        tick_s: float = 0.01,
    ) -> None:
        self._sources: dict[Channel, AudioSource] = {MIC: mic, SYSTEM: system}
        self._watcher_factory = watcher_factory
        self._now = now_ns
        self._tick = tick_s
        self._pipeline: CapturePipeline | None = None
        self._watcher: Any = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._failure: str | None = None  # exception type that stopped the pipeline thread
        self.device_changes = 0

    def start(self, on_frames: Callable[[Frames], None]) -> None:
        mic, system = self._sources[MIC], self._sources[SYSTEM]
        mic.start()
        try:
            system.start()
        except CaptureError:
            mic.stop()
            raise
        self._pipeline = CapturePipeline(
            self._sources, on_frames, start_ns=self._now(), now_ns=self._now
        )
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="capture-pipeline", daemon=True)
        self._thread.start()
        if self._watcher_factory is not None:
            self._watcher = self._watcher_factory(self._on_output_changed)
            self._watcher.start()
        log.info("capture_started", mic=mic.name, system=system.name)

    def stop(self) -> CaptureHealth:
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        for source in self._sources.values():
            source.stop()
        if self._pipeline is not None and self._failure is None:
            try:
                self._pipeline.flush()
            except Exception as exc:  # the frame consumer failed while flushing
                self._fail(exc)
        health = self.health()
        log.info("capture_stopped", ok=health.ok, drift_ms=health.inter_channel_drift_ms)
        return health

    def health(self) -> CaptureHealth:
        if self._pipeline is None:
            raise RuntimeError("capture has not started")
        mic = _channel_health(self._sources[MIC].name, self._pipeline.stats(MIC))
        system = _channel_health(self._sources[SYSTEM].name, self._pipeline.stats(SYSTEM))
        drift = round(abs(mic.drift_ms - system.drift_ms), 2)
        hints: list[str] = []
        if mic.seconds > 0 and mic.rms_dbfs < SILENT_DBFS:
            hints.append(
                "Microphone looks silent: wrong device, muted, or blocked in privacy settings?"
            )
        if system.seconds > 0 and system.padded_ms >= system.seconds * 1000 * 0.95:
            hints.append("No system audio arrived: nothing playing, or a different output device?")
        if self._failure is not None:
            hints.append(f"Capture stopped early ({self._failure}); details are in the log.")
        problems = int(self._failure is not None) + (
            mic.dropped_chunks
            + system.dropped_chunks
            + sum(g["cause"] == "dropout" for c in (mic, system) for g in c.gaps)
        )
        return CaptureHealth(
            channels={"mic": mic, "system": system},
            inter_channel_drift_ms=drift,
            device_changes=self.device_changes,
            hints=hints,
            ok=problems == 0 and drift < DRIFT_LIMIT_MS,
        )

    def _run(self) -> None:
        assert self._pipeline is not None
        while not self._stop.wait(self._tick):
            try:
                self._pipeline.step()
            except Exception as exc:  # never let the capture thread die silently
                self._fail(exc)
                return

    def _fail(self, exc: BaseException) -> None:
        self._failure = type(exc).__name__
        log.error("capture_pipeline_failed", error=self._failure)

    def _on_output_changed(self, device_id: str | None) -> None:
        self.device_changes += 1
        log.info("output_device_changed", has_device=device_id is not None)
        if self._pipeline is None:
            return
        try:
            self._pipeline.swap_source(SYSTEM)
        except CaptureError as exc:
            log.warning("loopback_reopen_failed", hint=exc.hint)
