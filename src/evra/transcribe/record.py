"""`evra record SECONDS`: a 1:1 call -> live, stored, labelled transcript (M3a, D18).
The recording itself is `LiveRecording`, shared with the window (M3c)."""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import signal
import sys
import threading
import time
from collections.abc import Callable, Iterator
from datetime import datetime

from evra.capture.sources import CaptureError
from evra.logging_setup import configure_logging
from evra.modelstore import ModelError
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import Utterance
from evra.store.migrate import migrate
from evra.transcribe.cli import format_ms
from evra.transcribe.labels import speaker_label
from evra.transcribe.recording import LiveRecording, RecordingKit, RecordingResult
from evra.workers.protocol import WorkerCrashed, WorkerError

__all__ = ["RecordingResult", "ignore_ctrl_c", "record_command", "run_recording", "summary_lines"]


@contextlib.contextmanager
def ignore_ctrl_c() -> Iterator[None]:
    """Hold off Ctrl+C while a recording is wrapped up (main thread only: signals live there)."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    previous = signal.signal(signal.SIGINT, signal.SIG_IGN)
    try:
        yield
    finally:
        signal.signal(signal.SIGINT, previous)


def run_recording(
    recording: LiveRecording, *, seconds: float, sleep: Callable[[float], None] = time.sleep
) -> RecordingResult:
    recording.start()  # a missing or busy mic fails here, before any meeting exists
    interrupted = False
    try:
        sleep(seconds)
    except KeyboardInterrupt:
        interrupted = True
    finally:
        with ignore_ctrl_c():  # a second Ctrl+C must not lose queued speech or the meeting
            result = recording.stop()
    return dataclasses.replace(result, interrupted=interrupted)


def _print_utterance(utterance: Utterance) -> None:
    label = speaker_label(utterance.channel)
    print(f"[{format_ms(utterance.start_ms)}] {label}: {utterance.text}", flush=True)


def record_command(args: argparse.Namespace, paths: AppPaths) -> int:
    paths.ensure()
    configure_logging(paths.log_dir, debug=False)
    conn = connect(paths.db_path)
    try:
        migrate(conn)
    finally:
        conn.close()
    kit = RecordingKit(paths)
    try:
        print("Loading speech recognition...", flush=True)
        kit.prepare()
        mic: int | str | None = int(args.mic) if args.mic and args.mic.isdigit() else args.mic
        recording = kit.new_recording(
            mic,
            title=f"Recording {datetime.now():%Y-%m-%d %H:%M}",
            situation=args.situation,
            on_utterance=_print_utterance,
        )
        print(f"Recording for {args.seconds:.0f} s (Ctrl+C to stop early)...", flush=True)
        result = run_recording(recording, seconds=args.seconds)
    except KeyboardInterrupt:  # during setup; run_recording handles Ctrl+C while recording
        print("Cancelled.", file=sys.stderr)
        return 130
    except CaptureError as exc:
        print(f"{exc}", file=sys.stderr)
        if exc.hint:
            print(f"Fix: {exc.hint}", file=sys.stderr)
        return 2
    except (ModelError, WorkerError, WorkerCrashed, OSError) as exc:
        print(f"Could not start recording ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 2
    finally:
        with ignore_ctrl_c():
            kit.close()
    for line in summary_lines(result):
        print(line)
    return 0


def summary_lines(result: RecordingResult) -> list[str]:
    stats = result.stats
    capture = "ok" if result.health and result.health.ok else "had problems"
    lines = []
    if stats.segments == 0:
        lines.append("-- no speech detected")
    elif result.utterances == 0:
        lines.append(f"-- speech was detected but not transcribed ({stats.failures} failed)")
    if not stats.drained:
        lines.append(f"-- {stats.unprocessed} segments were still waiting when recording stopped")
    lines.append(
        f"-- {result.utterances} utterances, {stats.failures} failed segments,"
        f" ASR real-time factor {stats.rtf:.3f}; capture {capture}; meeting {result.meeting_id}"
    )
    if result.health is not None:
        lines += [f"   hint: {hint}" for hint in result.health.hints]
    return lines
