"""Audio callback → pipeline hand-off (BUILD.md §5.2).

Single producer (the audio callback), single consumer (the pipeline thread). `put` never
blocks: a full ring discards its oldest chunk (deque with maxlen; append/popleft are atomic
under the GIL). The consumer counts discarded chunks from gaps in the sequence numbers.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

from evra.audio.frames import Float32Array


@dataclass(frozen=True)
class Chunk:
    seq: int
    data: Float32Array  # (frames, channels) at the device's native rate
    t_callback_ns: int  # time.monotonic_ns() when the callback ran


class ChunkRing:
    def __init__(self, max_chunks: int) -> None:
        if max_chunks < 1:
            raise ValueError("max_chunks must be >= 1")
        self._items: deque[Chunk] = deque(maxlen=max_chunks)
        self._next_seq = 0  # producer only
        self._expected_seq = 0  # consumer only
        self.dropped_chunks = 0  # consumer only

    @classmethod
    def for_duration(cls, seconds: float, chunk_seconds: float) -> ChunkRing:
        return cls(math.ceil(seconds / chunk_seconds))

    def put(self, data: Float32Array, t_callback_ns: int) -> None:
        self._items.append(Chunk(self._next_seq, data, t_callback_ns))
        self._next_seq += 1

    def drain(self) -> list[Chunk]:
        out: list[Chunk] = []
        while True:
            try:
                chunk = self._items.popleft()
            except IndexError:
                return out
            if chunk.seq > self._expected_seq:
                self.dropped_chunks += chunk.seq - self._expected_seq
            self._expected_seq = chunk.seq + 1
            out.append(chunk)
