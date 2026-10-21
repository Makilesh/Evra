"""Parakeet TDT 0.6B v3 int8 via sherpa-onnx, on CPU (BUILD.md D8). Runs inside the ASR worker."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np

from evra.asr.engine import Segment, Word
from evra.audio.frames import SAMPLE_RATE, Int16Array

PARAKEET_ID = "parakeet-tdt-0.6b-v3-int8"


def words_from_tokens(
    tokens: Sequence[str], starts_s: Sequence[float], total_ms: int
) -> list[Word]:
    """Join BPE tokens into words: a token starting with a space begins a new word.
    Each word ends where the next begins; the last one ends with the audio."""
    spans: list[tuple[int, str]] = []
    for token, start in zip(tokens, starts_s, strict=True):
        if token.startswith(" ") or not spans:
            spans.append((round(start * 1000), token.strip()))
        else:
            begin, text = spans[-1]
            spans[-1] = (begin, text + token)
    return [
        Word(begin, spans[i + 1][0] if i + 1 < len(spans) else total_ms, text)
        for i, (begin, text) in enumerate(spans)
        if text
    ]


def _load(model_dir: Path, num_threads: int) -> Any:
    import sherpa_onnx

    return sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(model_dir / "encoder.int8.onnx"),
        decoder=str(model_dir / "decoder.int8.onnx"),
        joiner=str(model_dir / "joiner.int8.onnx"),
        tokens=str(model_dir / "tokens.txt"),
        num_threads=num_threads,
        model_type="nemo_transducer",
        provider="cpu",
    )


class ParakeetEngine:
    name = PARAKEET_ID
    languages = frozenset({"en"})  # Phase 1 is English-only (D3); the model covers 25 languages

    def __init__(self, model_dir: Path, *, num_threads: int = 4, recognizer: Any = None) -> None:
        self._recognizer = recognizer or _load(model_dir, num_threads)

    def transcribe(
        self, pcm16k: Int16Array, language: str = "en", keywords: list[str] | None = None
    ) -> list[Segment]:
        if len(pcm16k) == 0:
            return []
        total_ms = len(pcm16k) * 1000 // SAMPLE_RATE
        stream = self._recognizer.create_stream()
        stream.accept_waveform(SAMPLE_RATE, pcm16k.astype(np.float32) / 32768.0)
        self._recognizer.decode_stream(stream)
        result = stream.result
        text = str(result.text).strip()
        if not text:
            return []
        words = words_from_tokens(list(result.tokens), list(result.timestamps), total_ms)
        return [Segment(0, total_ms, text, tuple(words))]
