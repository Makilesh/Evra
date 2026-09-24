"""`evra capture-test`: record both channels for N seconds, write WAVs + a health report (M1)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
import wave
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from evra.audio.frames import MIC, SAMPLE_RATE, SYSTEM, Int16Array
from evra.audio.keys import KeyringKeyStore, KeyStore, new_meeting_key
from evra.audio.spill import SpillWriter, read_channel
from evra.capture.fake import FakeSource
from evra.capture.mic import MicSource, list_input_devices
from evra.capture.session import DRIFT_LIMIT_MS, CaptureHealth, CaptureSession
from evra.capture.sources import CaptureError
from evra.constants import APP_NAME
from evra.logging_setup import configure_logging
from evra.paths import AppPaths


def write_wav(path: Path, pcm: Int16Array, rate: int = SAMPLE_RATE) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm.astype("<i2").tobytes())


def run_capture_test(
    session: CaptureSession,
    *,
    seconds: float,
    paths: AppPaths,
    keys: KeyStore,
    out_dir: Path,
    meeting_id: str,
    sleep: Callable[[float], None] = time.sleep,
) -> CaptureHealth:
    key = new_meeting_key()
    keys.set(meeting_id, key)
    spill_dir = paths.spill_dir / meeting_id
    try:
        writer = SpillWriter(spill_dir, meeting_id, key)
        session.start(writer.write)
        sleep(seconds)
        health = session.stop()
        writer.close()
        out_dir.mkdir(parents=True, exist_ok=True)
        write_wav(out_dir / "mic.wav", read_channel(spill_dir, key, MIC))
        write_wav(out_dir / "system.wav", read_channel(spill_dir, key, SYSTEM))
        report = json.dumps(asdict(health), indent=2)
        (out_dir / "health.json").write_text(report, encoding="utf-8")
        return health
    finally:
        shutil.rmtree(spill_dir, ignore_errors=True)
        keys.delete(meeting_id)


def format_summary(health: CaptureHealth, seconds: float, out_dir: Path) -> str:
    lines = [f"{APP_NAME} capture test: {seconds:.1f} s"]
    for label, ch in health.channels.items():
        lines.append(
            f"  {label:<7} {ch.device[:40]:<40} {ch.native_rate} Hz x{ch.native_channels}"
            f"  rms {ch.rms_dbfs:.1f} dBFS  peak {ch.peak_dbfs:.1f}"
            f"  drops {ch.dropped_chunks}  corrections {ch.corrections}"
            f"  drift {ch.drift_ms:+.1f} ms  gaps {len(ch.gaps)}"
        )
    lines.append(
        f"  inter-channel drift: {health.inter_channel_drift_ms:.1f} ms"
        f" (limit {DRIFT_LIMIT_MS:.0f})  device changes: {health.device_changes}"
    )
    lines += [f"  hint: {h}" for h in health.hints]
    lines.append(f"  result: {'PASS' if health.ok else 'FAIL'}")
    lines.append(f"  files: {out_dir}")
    return "\n".join(lines)


def _session(args: argparse.Namespace) -> CaptureSession:
    if args.fake_mic or args.fake_system:
        if not (args.fake_mic and args.fake_system):
            raise CaptureError("--fake-mic and --fake-system must be used together")
        mic = FakeSource.from_wav(Path(args.fake_mic))
        system = FakeSource.from_wav(Path(args.fake_system), pads_silence=True)
        return CaptureSession(mic, system)
    from evra.capture.windows import DefaultOutputWatcher, LoopbackSource

    device: int | str | None = int(args.mic) if args.mic and args.mic.isdigit() else args.mic
    return CaptureSession(MicSource(device), LoopbackSource(), watcher_factory=DefaultOutputWatcher)


def capture_test_command(
    args: argparse.Namespace, paths: AppPaths, keys: KeyStore | None = None
) -> int:
    paths.ensure()
    configure_logging(paths.log_dir, debug=False)
    if args.list_devices:
        for d in list_input_devices():
            print(f"  [{d['index']}] {d['name']} ({d['rate']:.0f} Hz)")
        return 0
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir = Path(args.out) if args.out else paths.data_dir / "capture-test" / stamp
    try:
        session = _session(args)
        health = run_capture_test(
            session,
            seconds=args.seconds,
            paths=paths,
            keys=keys or KeyringKeyStore(),
            out_dir=out_dir,
            meeting_id=f"capture-test-{stamp}",
        )
    except CaptureError as exc:
        print(f"{exc}", file=sys.stderr)
        if exc.hint:
            print(f"Fix: {exc.hint}", file=sys.stderr)
        return 2
    print(format_summary(health, args.seconds, out_dir))
    return 0 if health.ok else 1
