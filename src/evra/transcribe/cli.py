"""`evra models` and `evra transcribe WAV` (M3a)."""

from __future__ import annotations

import argparse
import time
import wave
from pathlib import Path

import numpy as np

from evra.asr.parakeet import PARAKEET_ID
from evra.audio.convert import ToMono16k
from evra.audio.frames import FRAME_SAMPLES, Frames
from evra.audio.vad import SpeechSegmenter, VadBackend, silero_vad
from evra.logging_setup import configure_logging
from evra.modelstore import ensure_model, is_ready, load_catalog
from evra.paths import AppPaths
from evra.workers.asr import AsrClient, Transcriber

SPEECH_MODELS = ("silero-vad", PARAKEET_ID)


def format_ms(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def ensure_speech_models(paths: AppPaths) -> dict[str, Path]:
    catalogue = load_catalog()
    found: dict[str, Path] = {}
    for model_id in SPEECH_MODELS:
        spec = catalogue[model_id]
        if not is_ready(spec, paths.models_dir):
            print(f"Downloading {model_id} ({spec.size_mb} MB)...", flush=True)
        found[model_id] = ensure_model(spec, paths.models_dir)
    return found


def transcribe_file(path: Path, *, asr: Transcriber, vad: VadBackend) -> list[tuple[int, int, str]]:
    with wave.open(str(path), "rb") as w:
        if w.getsampwidth() != 2:
            raise ValueError(f"{path.name}: only 16-bit PCM WAV is supported")
        rate, channels = w.getframerate(), w.getnchannels()
        raw = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").reshape(-1, channels)
    pcm = ToMono16k(rate, channels).process((raw / 32768.0).astype(np.float32))
    segmenter = SpeechSegmenter(0, vad)
    segments = []
    for start in range(0, len(pcm), FRAME_SAMPLES):
        chunk = pcm[start : start + FRAME_SAMPLES]
        segments += segmenter.accept(Frames(0, chunk, 0, start))
    segments += segmenter.flush()
    lines: list[tuple[int, int, str]] = []
    for segment in segments:
        for result in asr.transcribe(segment.pcm):
            if result.text:
                lines.append(
                    (
                        segment.start_ms + result.start_ms,
                        segment.start_ms + result.end_ms,
                        result.text,
                    )
                )
    return lines


def models_command(args: argparse.Namespace, paths: AppPaths) -> int:
    paths.ensure()
    for model_id, spec in load_catalog().items():
        if args.download:
            ensure_model(spec, paths.models_dir)
        state = "ready" if is_ready(spec, paths.models_dir) else "missing"
        print(f"  {model_id:<32} {spec.licence:<10} {spec.size_mb:>5} MB  {state}")
    return 0


def transcribe_command(args: argparse.Namespace, paths: AppPaths) -> int:
    paths.ensure()
    configure_logging(paths.log_dir, debug=False)
    models = ensure_speech_models(paths)
    asr = AsrClient.for_models(paths.models_dir)
    try:
        started = time.perf_counter()
        vad = silero_vad(models["silero-vad"] / "silero_vad.onnx")
        lines = transcribe_file(Path(args.wav), asr=asr, vad=vad)
        elapsed = time.perf_counter() - started
    finally:
        asr.stop()
    for start, _end, text in lines:
        print(f"[{format_ms(start)}] {text}")
    print(f"-- {len(lines)} lines in {elapsed:.1f} s (includes loading the model)")
    return 0
