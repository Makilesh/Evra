import threading

import numpy as np

from evra.audio.ringbuffer import ChunkRing


def _data(v: float) -> np.ndarray:
    return np.full((4, 1), v, dtype=np.float32)


def test_drain_returns_chunks_in_order() -> None:
    ring = ChunkRing(10)
    for i in range(3):
        ring.put(_data(i), 100 + i)
    chunks = ring.drain()
    assert [c.seq for c in chunks] == [0, 1, 2]
    assert [c.t_callback_ns for c in chunks] == [100, 101, 102]
    assert ring.drain() == []
    assert ring.dropped_chunks == 0


def test_overflow_discards_oldest_and_counts_drops() -> None:
    ring = ChunkRing(4)
    for i in range(10):
        ring.put(_data(i), i)
    chunks = ring.drain()
    assert [c.seq for c in chunks] == [6, 7, 8, 9]
    assert ring.dropped_chunks == 6


def test_for_duration_sizes_the_ring() -> None:
    ring = ChunkRing.for_duration(2.0, 0.01)
    for i in range(201):
        ring.put(_data(i), i)
    assert len(ring.drain()) == 200
    assert ring.dropped_chunks == 1


def test_concurrent_producer_and_consumer_lose_nothing_silently() -> None:
    ring = ChunkRing(64)
    total = 20_000
    done = threading.Event()

    def produce() -> None:
        for i in range(total):
            ring.put(_data(i), i)
        done.set()

    received: list[int] = []
    producer = threading.Thread(target=produce)
    producer.start()
    while True:
        finished = done.is_set()  # read before draining, or the last chunks can be missed
        batch = ring.drain()
        received.extend(c.seq for c in batch)
        if finished and not batch:
            break
    producer.join()
    assert received == sorted(received)
    assert len(received) + ring.dropped_chunks == total
