"""Encrypted temporary audio (BUILD.md §5.5).

File layout: MAGIC | header length (4 bytes, big-endian) | JSON header | nonce (12) | ciphertext.
The magic + header are the AES-GCM associated data, so metadata cannot be altered either.
Files are written to a .tmp name and renamed, so a crash never leaves a half segment.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from evra.audio.frames import SAMPLE_RATE, Frames, Int16Array

MAGIC = b"EVRASPL1"
SEGMENT_SECONDS = 30
_NONCE = 12


class SpillError(RuntimeError):
    pass


@dataclass(frozen=True)
class SpillSegment:
    channel: int
    index: int
    start_ms: int
    end_ms: int
    path: Path


class SpillWriter:
    def __init__(
        self,
        directory: Path,
        meeting_id: str,
        key: bytes,
        *,
        segment_samples: int = SEGMENT_SECONDS * SAMPLE_RATE,
    ) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        self._dir = directory
        self._meeting_id = meeting_id
        self._aead = AESGCM(key)
        self._segment_samples = segment_samples
        self._pending: dict[int, list[Int16Array]] = {}
        self._pending_len: dict[int, int] = {}
        self._start: dict[int, int] = {}
        self._next_index: dict[int, int] = {}
        self.segments: list[SpillSegment] = []

    def write(self, frames: Frames) -> None:
        ch = frames.channel
        if ch not in self._pending:
            self._pending[ch], self._pending_len[ch] = [], 0
            self._start[ch], self._next_index[ch] = frames.index, 0
        self._pending[ch].append(frames.pcm)
        self._pending_len[ch] += len(frames.pcm)
        if self._pending_len[ch] >= self._segment_samples:
            self._flush(ch)

    def close(self) -> list[SpillSegment]:
        for ch in list(self._pending):
            if self._pending_len[ch]:
                self._flush(ch)
        return self.segments

    def _flush(self, ch: int) -> None:
        pcm = np.concatenate(self._pending[ch])
        start = self._start[ch]
        index = self._next_index[ch]
        start_ms = start * 1000 // SAMPLE_RATE
        end_ms = (start + len(pcm)) * 1000 // SAMPLE_RATE
        header = json.dumps(
            {
                "v": 1,
                "meeting_id": self._meeting_id,
                "channel": ch,
                "index": index,
                "start_ms": start_ms,
                "end_ms": end_ms,
                "sample_rate": SAMPLE_RATE,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
        prefix = MAGIC + len(header).to_bytes(4, "big") + header
        nonce = os.urandom(_NONCE)
        body = self._aead.encrypt(nonce, pcm.astype("<i2").tobytes(), prefix)
        path = self._dir / f"{ch}_{index:05d}.spill"
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(prefix + nonce + body)
        tmp.replace(path)
        self.segments.append(SpillSegment(ch, index, start_ms, end_ms, path))
        self._pending[ch], self._pending_len[ch] = [], 0
        self._start[ch] = start + len(pcm)
        self._next_index[ch] = index + 1


def read_segment(path: Path, key: bytes) -> tuple[dict[str, Any], Int16Array]:
    raw = path.read_bytes()
    if not raw.startswith(MAGIC) or len(raw) < len(MAGIC) + 4:
        raise SpillError(f"not a spill file: {path.name}")
    size = int.from_bytes(raw[len(MAGIC) : len(MAGIC) + 4], "big")
    prefix_end = len(MAGIC) + 4 + size
    prefix = raw[:prefix_end]
    nonce = raw[prefix_end : prefix_end + _NONCE]
    try:
        plain = AESGCM(key).decrypt(nonce, raw[prefix_end + _NONCE :], prefix)
    except (InvalidTag, ValueError) as exc:
        raise SpillError(f"spill segment {path.name} failed authentication") from exc
    header: dict[str, Any] = json.loads(prefix[len(MAGIC) + 4 :])
    return header, np.frombuffer(plain, dtype="<i2").astype(np.int16)


def read_channel(directory: Path, key: bytes, channel: int) -> Int16Array:
    parts = [read_segment(p, key)[1] for p in sorted(directory.glob(f"{channel}_*.spill"))]
    return np.concatenate(parts) if parts else np.zeros(0, dtype=np.int16)
