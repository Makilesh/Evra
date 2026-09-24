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
from evra.capture.sources import MIC_PRIVACY_HINT, AudioSource

log = structlog.get_logger(__name__)

DRIFT_LIMIT_MS = 30.0
SILENT_DBFS = -60.0
SILENCE_FLOOR_DBFS = -120.0  # peak of pure digital zeros (what a privacy-blocked mic delivers)
STALL_TOLERANCE_S = 0.5  # channels may differ this much in length before one counts as stalled
WatcherFactory = Callable[[Callable[[str | None], None]], Any]


@dataclass(frozen=True)
class ChannelHealth:
    device: str
    overflows: int
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
    stream_restarts: int
    hints: list[str]
    ok: bool


def _channel_health(source: AudioSource, stats: ChannelStats) -> ChannelHealth:
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
    return ChannelHealth(device=source.name, overflows=source.overflows, **fields)


class CaptureSession:
    def __init__(
        self,
        mic: AudioSource,
        system: AudioSource,
        *,
        watcher_factory: WatcherFactory | None = None,
        now_ns: Callable[[], int] = time.monotonic_ns,
        tick_s: float = 0.01,
        liveness_s: float = 2.0,
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
        self.stream_restarts = 0
        self._liveness_s = liveness_s

    def start(self, on_frames: Callable[[Frames], None]) -> None:
        mic, system = self._sources[MIC], self._sources[SYSTEM]
        start_ns = self._now()  # before opening devices, so early audio has a place (I3)
        mic.start()
        try:
            system.start()
        except BaseException:
            mic.stop()
            raise
        self._pipeline = CapturePipeline(
            self._sources, on_frames, start_ns=start_ns, now_ns=self._now
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
        mic = _channel_health(self._sources[MIC], self._pipeline.stats(MIC))
        system = _channel_health(self._sources[SYSTEM], self._pipeline.stats(SYSTEM))
        drift = round(abs(mic.drift_ms - system.drift_ms), 2)
        hints: list[str] = []
        problems = 0
        if mic.seconds > 0 and mic.peak_dbfs <= SILENCE_FLOOR_DBFS:
            hints.append(f"Microphone delivered pure digital silence. {MIC_PRIVACY_HINT}")
            problems += 1
        elif mic.seconds > 0 and mic.rms_dbfs < SILENT_DBFS:
            hints.append(
                "Microphone looks silent: wrong device, muted, or blocked in privacy settings?"
            )
        if system.seconds > 0 and system.padded_ms >= system.seconds * 1000 * 0.95:
            hints.append("No system audio arrived: nothing playing, or a different output device?")
        longest = max(mic.seconds, system.seconds)
        for label, ch in (("microphone", mic), ("system", system)):
            if longest - ch.seconds > STALL_TOLERANCE_S:
                hints.append(f"The {label} channel stopped delivering audio at {ch.seconds:.1f} s.")
                problems += 1
        if mic.overflows + system.overflows:
            hints.append("An audio device overflowed (input lost): the computer was too busy.")
        if self._failure is not None:
            hints.append(f"Capture stopped early ({self._failure}); details are in the log.")
        problems += (
            int(self._failure is not None)
            + mic.overflows
            + system.overflows
            + (
                mic.dropped_chunks
                + system.dropped_chunks
                + sum(g["cause"] == "dropout" for c in (mic, system) for g in c.gaps)
            )
        )
        return CaptureHealth(
            channels={"mic": mic, "system": system},
            inter_channel_drift_ms=drift,
            device_changes=self.device_changes,
            stream_restarts=self.stream_restarts,
            hints=hints,
            ok=problems == 0 and drift < DRIFT_LIMIT_MS,
        )

    def _run(self) -> None:
        assert self._pipeline is not None
        next_check = time.monotonic() + self._liveness_s
        while not self._stop.wait(self._tick):
            try:
                self._pipeline.step()
            except Exception as exc:  # never let the capture thread die silently
                self._fail(exc)
                return
            if time.monotonic() >= next_check:
                next_check = time.monotonic() + self._liveness_s
                self._restart_dead_streams()

    def _restart_dead_streams(self) -> None:
        """A stream can die while the device id stays the same (Bluetooth reconnect,
        format change, another app taking exclusive mode): reopen it."""
        assert self._pipeline is not None
        for channel, source in self._sources.items():
            if source.is_active():
                continue
            try:
                self._pipeline.swap_source(channel, cause="stream_restart")
                self.stream_restarts += 1
                log.info("capture_stream_restarted", channel=channel)
            except Exception as exc:  # still gone: try again at the next check
                log.warning("capture_stream_restart_failed", error=type(exc).__name__)

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
        except Exception as exc:  # the system channel pads silence until the next change
            log.warning("loopback_reopen_failed", error=type(exc).__name__)
