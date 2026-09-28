"""`evra record SECONDS`: a 1:1 call → live, stored, labelled transcript (M3a, D18)."""

from __future__ import annotations

import argparse
import contextlib
import signal
import sys
import threading
import time
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from datetime import datetime

from evra.asr.parakeet import PARAKEET_ID
from evra.audio.frames import Frames
from evra.audio.vad import SpeechSegmenter, silero_vad
from evra.capture.session import CaptureHealth, CaptureSession
from evra.capture.sources import CaptureError
from evra.logging_setup import configure_logging
from evra.modelstore import ModelError
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.migrate import migrate
from evra.transcribe.cli import ensure_speech_models, format_ms
from evra.transcribe.live import LiveTranscriber, TranscriberStats
from evra.workers.asr import AsrClient
from evra.workers.protocol import WorkerCrashed, WorkerError

LABELS = {0: "You", 1: "Them"}  # 1:1 mode: mic = owner, system = the other person


@dataclass(frozen=True)
class RecordingResult:
    meeting_id: str
    utterances: int
    health: CaptureHealth | None
    stats: TranscriberStats
    interrupted: bool


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
    session: CaptureSession,
    segmenters: Mapping[int, SpeechSegmenter],
    transcriber: LiveTranscriber,
    store: MeetingStore,
    meeting_id: str,
    *,
    seconds: float,
    sleep: Callable[[float], None] = time.sleep,
) -> RecordingResult:
    def on_frames(frames: Frames) -> None:  # runs on the capture pipeline thread
        for segment in segmenters[frames.channel].accept(frames):
            transcriber.submit(segment)

    interrupted = False
    health: CaptureHealth | None = None
    state = "ready"
    transcriber.start()
    try:
        try:
            session.start(on_frames)
        except BaseException:
            state = "failed"
            raise
        try:
            sleep(seconds)
        except KeyboardInterrupt:
            interrupted = True
        finally:
            with ignore_ctrl_c():
                health = session.stop()
                for segmenter in segmenters.values():
                    for segment in segmenter.flush():
                        transcriber.submit(segment)
    finally:
        with ignore_ctrl_c():  # a second Ctrl+C must not lose queued speech or the meeting
            stats = transcriber.stop()
            store.finish_meeting(meeting_id, state=state)
    return RecordingResult(meeting_id, stats.utterances, health, stats, interrupted)


def _print_utterance(utterance: Utterance) -> None:
    label = LABELS.get(utterance.channel, f"Channel {utterance.channel}")
    print(f"[{format_ms(utterance.start_ms)}] {label}: {utterance.text}", flush=True)


def record_command(args: argparse.Namespace, paths: AppPaths) -> int:
    from evra.capture.mic import MicSource
    from evra.capture.windows import DefaultOutputWatcher, LoopbackSource

    paths.ensure()
    configure_logging(paths.log_dir, debug=False)
    conn = connect(paths.db_path)
    migrate(conn)
    store = MeetingStore(conn)
    asr = AsrClient.for_models(paths.models_dir)
    try:
        models = ensure_speech_models(paths)
        print("Loading speech recognition...", flush=True)
        asr.warm_up()
        vad_path = models["silero-vad"] / "silero_vad.onnx"
        segmenters = {ch: SpeechSegmenter(ch, silero_vad(vad_path)) for ch in (0, 1)}
        device: int | str | None = int(args.mic) if args.mic and args.mic.isdigit() else args.mic
        session = CaptureSession(
            MicSource(device), LoopbackSource(), watcher_factory=DefaultOutputWatcher
        )
        meeting_id = store.create_meeting(  # only once everything needed has loaded
            title=f"Recording {datetime.now():%Y-%m-%d %H:%M}",
            mode="one_on_one",
            situation=args.situation,
            template="one_on_one",
        )
        version_id = store.create_transcript_version(meeting_id, kind="live", model=PARAKEET_ID)
        live = LiveTranscriber(asr, paths.db_path, meeting_id=meeting_id, version_id=version_id)
        live.add_listener(_print_utterance)
        print(f"Recording for {args.seconds:.0f} s (Ctrl+C to stop early)...", flush=True)
        result = run_recording(session, segmenters, live, store, meeting_id, seconds=args.seconds)
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
            asr.stop()
            conn.close()
    for line in summary_lines(result):
        print(line)
    return 0


def summary_lines(result: RecordingResult) -> list[str]:
    stats = result.stats
    capture = "ok" if result.health and result.health.ok else "had problems"
    lines = []
    if result.utterances == 0:
        lines.append("-- no speech detected")
    lines.append(
        f"-- {result.utterances} utterances, {stats.failures} failed segments,"
        f" ASR real-time factor {stats.rtf:.3f}; capture {capture}; meeting {result.meeting_id}"
    )
    if result.health is not None:
        lines += [f"   hint: {hint}" for hint in result.health.hints]
    return lines
