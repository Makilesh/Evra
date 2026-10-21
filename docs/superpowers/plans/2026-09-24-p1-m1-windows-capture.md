# Phase 1 · M1 Windows Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record the microphone and the system output as two aligned 16 kHz mono channels on Windows, spill them to encrypted 30 s segments, and prove it with `evra capture-test SECONDS`, which writes two WAVs plus a health report.

**Architecture:**
- **Sources** (`MicSource` via sounddevice, `LoopbackSource` via PyAudioWPatch, `FakeSource` from WAV files) copy native float32 chunks into a non-blocking `ChunkRing` from their audio callbacks.
- A **pipeline thread** handles each channel every 10 ms:
  - drains the ring;
  - timestamps chunks with a `SourceClock`, which steadies jittery callback times using the device's own sample count;
  - converts the audio to 16 kHz mono int16 with a stateful libsamplerate resampler;
  - places it on a shared meeting timeline with `ChannelTimeline`, which fills gaps, corrects drift and pads loopback silence;
  - emits 10 ms `Frames`.
- A `CaptureSession` wires the sources, pipeline, and default-output watcher (pycaw) together and reports `CaptureHealth`.
- A `SpillWriter` encrypts frames into AES-GCM segments; the per-meeting key lives in Windows Credential Manager.

**Tech Stack:** numpy, samplerate (libsamplerate), sounddevice, PyAudioWPatch, pycaw + comtypes, cryptography (AESGCM), keyring (WinVault), stdlib `wave`.

**Spec:** `BUILD.md` §5.1, §5.2, §5.5 (spill part), §10 row M1, §10.1 HC1, §11.

## Global Constraints

- Everything from the M0 plan's Global Constraints still applies:
  - Python 3.12, uv-managed.
  - `mypy --strict`.
  - Files under ~500 lines.
  - No network listener.
  - Nothing logged above DEBUG may contain audio or transcript content.
  - D23: working files stay inside the repo (`.data/`, `spikes/`, `private/`).
  - D22: after each task, run `tools/check.py`, then commit and `git push` on branch **`windows-capture`**.
- Timeline format: **16 kHz, mono, int16, 10 ms frames (160 samples)**. Channel **0 = microphone, 1 = system output**. One monotonic clock (`time.monotonic_ns`).
- Capture callbacks never block and never log. They only copy the buffer and append to the ring.
- The ring holds about 2 s of audio. On overflow the oldest chunk is discarded and the drop is counted (§5.2).
- Correction thresholds:
  - drift correction when drift exceeds **20 ms**, checked about once per second, applied in **10 ms steps**;
  - a hole of **≥ 50 ms** is a gap and is filled with silence immediately;
  - loopback silence is padded once there has been **no loopback data for 50 ms**.
- Acceptance (DoD):
  - A 60-minute soak shows the two channels differing by **< 30 ms**, with **no dropped chunks**.
  - HC1 is passed.
- Spill:
  - AES-GCM with a random 256-bit key per meeting.
  - The key is stored in keyring: service `Evra`, username `meeting/<id>`.
  - Segments cover 30 s per channel and are written atomically.
  - The spill directory is `<data_dir>/spill/<meeting_id>/`.
- Windows-only packages (`pyaudiowpatch`, `pycaw`, `comtypes`) get the marker `sys_platform == 'win32'`.
- Tests that need real devices or the real credential store are marked `hardware` and excluded by default. Run them with `uv run pytest -m hardware`.

## Review Focus

1. **Bursty or late audio callbacks.** The spike measured mic callbacks at a 26 ms mean with 47 ms spikes. The jitter must not create false gaps or drift corrections. → Task 3 `test_jittery_callbacks_stay_within_2ms`, `test_bursty_delivery_is_smoothed`.
2. **Loopback that stops delivering while nothing plays, then resumes.** The system timeline must keep moving, and no real audio may be dropped on resume. → Task 5 `test_loopback_silence_is_padded_and_resume_keeps_alignment`.
3. **Default output device changes mid-meeting**, for example plugging in a headset, possibly to a new sample rate. The gap must be recorded with cause `device_change` and capture must continue at the new rate. → Task 5 `test_swap_source_records_device_change_gap_and_new_rate`.
4. **A crash mid-write, a tampered segment, or the wrong key.** Reading must fail loudly (`SpillError`), never return garbage audio. → Task 6 `test_tampered_segment_fails`, `test_wrong_key_fails`, `test_no_plaintext_on_disk`.
5. **Microphone blocked by Windows privacy settings, or no output device.** The user needs a clear message with the fix, not a traceback. → Task 7 `test_start_failure_maps_to_mic_unavailable_with_privacy_hint`, and Task 9 `test_cli_reports_capture_error_with_hint`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `src/evra/audio/__init__.py` | package |
| `src/evra/audio/frames.py` | `Frames`, `Channel`, rate/frame constants |
| `src/evra/audio/convert.py` | `ToMono16k` streaming downmix + resample; `float_to_int16` |
| `src/evra/audio/ringbuffer.py` | `Chunk`, `ChunkRing` (callback → pipeline hand-off) |
| `src/evra/audio/clock.py` | `SourceClock` (steady timestamps), `ChannelTimeline` (gaps, drift, padding), `Gap`, `TimelineStats` |
| `src/evra/audio/pipeline.py` | `CapturePipeline` (per-channel drain → clock → convert → place → emit), `ChannelStats` |
| `src/evra/audio/spill.py` | `SpillWriter`, `read_segment`, `read_channel`, `SpillError`, `SpillSegment` |
| `src/evra/audio/keys.py` | `KeyStore`, `KeyringKeyStore`, `MemoryKeyStore`, `new_meeting_key` |
| `src/evra/capture/__init__.py` | package |
| `src/evra/capture/sources.py` | `AudioSource` protocol, `CaptureError` + subclasses, hints |
| `src/evra/capture/fake.py` | `FakeSource`, `FakeEvent` |
| `src/evra/capture/mic.py` | `MicSource`, `list_input_devices` |
| `src/evra/capture/windows.py` | `LoopbackSource`, `default_output_id`, `DefaultOutputWatcher` |
| `src/evra/capture/session.py` | `CaptureSession`, `CaptureHealth`, `ChannelHealth` |
| `src/evra/capture/capture_test.py` | `run_capture_test`, `write_wav`, `capture_test_command`, summary printing |
| `src/evra/paths.py` | + `spill_dir` |
| `src/evra/__main__.py` | + `capture-test` subcommand |
| `tests/unit/audio/…`, `tests/unit/capture/…` | unit tests |
| `tests/integration/test_capture_test.py` | fake-source end-to-end |
| `tests/hardware/test_devices.py` | real devices + Credential Manager (`-m hardware`) |

---

### Task 1: Frames and the 16 kHz converter

**Files:**
- Create: `src/evra/audio/__init__.py`, `src/evra/audio/frames.py`, `src/evra/audio/convert.py`, `tests/unit/audio/__init__.py`, `tests/unit/audio/test_convert.py`
- Modify: `pyproject.toml` (deps, mypy overrides), `THIRD_PARTY_LICENSES.md` (regenerated), `DECISIONS.md`, `BUILD.md` §5.1

**Interfaces:**
- Produces:
  - `SAMPLE_RATE = 16_000`, `FRAME_MS = 10`, `FRAME_SAMPLES = 160`, `NS = 1_000_000_000`
  - `MIC: Final = 0`, `SYSTEM: Final = 1`, `Channel = Literal[0, 1]`
  - `Int16Array = npt.NDArray[np.int16]`, `Float32Array = npt.NDArray[np.float32]`
  - `Frames(channel: Channel, pcm: Int16Array, t_capture_ns: int, index: int)` (frozen dataclass; `index` = sample index of `pcm[0]` on the meeting timeline)
  - `float_to_int16(samples) -> Int16Array`
  - `ToMono16k(native_rate: int, channels: int, converter: str = "sinc_fastest")` with `.process(chunk: Float32Array) -> Int16Array`

- [ ] **Step 1: Add dependencies and mypy overrides**

```powershell
uv add numpy samplerate
```

In `pyproject.toml`, add a second overrides block below the existing `webview` one:

```toml
[[tool.mypy.overrides]]
module = ["samplerate", "sounddevice", "pyaudiowpatch", "pycaw", "pycaw.*", "comtypes", "comtypes.*"]
ignore_missing_imports = true
```

- [ ] **Step 2: Write failing tests** `tests/unit/audio/test_convert.py` (plus empty `tests/unit/audio/__init__.py`)

```python
import numpy as np
import numpy.typing as npt
import pytest

from evra.audio.convert import ToMono16k, float_to_int16


def _sine(rate: int, seconds: float, channels: int = 1, freq: float = 440.0) -> npt.NDArray[np.float32]:
    t = np.arange(int(rate * seconds)) / rate
    mono = (0.5 * np.sin(2 * np.pi * freq * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1)


def _peak_hz(x: npt.NDArray[np.int16], rate: int) -> float:
    spectrum = np.abs(np.fft.rfft(x.astype(np.float64)))
    return float(np.fft.rfftfreq(len(x), 1 / rate)[int(np.argmax(spectrum))])


def _stream(conv: ToMono16k, audio: npt.NDArray[np.float32], block: int) -> npt.NDArray[np.int16]:
    return np.concatenate([conv.process(audio[i : i + block]) for i in range(0, len(audio), block)])


def test_48k_stereo_in_10ms_chunks_becomes_16k_mono() -> None:
    out = _stream(ToMono16k(48_000, 2), _sine(48_000, 2.0, channels=2), 480)
    assert out.dtype == np.int16
    assert abs(len(out) - 32_000) < 200
    assert abs(_peak_hz(out[2000:], 16_000) - 440) < 5


def test_44k1_mono_rational_ratio() -> None:
    out = _stream(ToMono16k(44_100, 1), _sine(44_100, 2.0), 441)
    assert abs(len(out) - 32_000) < 200
    assert abs(_peak_hz(out[2000:], 16_000) - 440) < 5


def test_chunk_size_does_not_change_the_output() -> None:
    audio = _sine(48_000, 1.0, channels=2)
    a = _stream(ToMono16k(48_000, 2), audio, 480)
    b = _stream(ToMono16k(48_000, 2), audio, 1_111)
    n = min(len(a), len(b)) - 200
    assert np.max(np.abs(a[:n].astype(np.int32) - b[:n])) <= 2


def test_16k_mono_passes_through_exactly() -> None:
    audio = _sine(16_000, 0.1)
    np.testing.assert_array_equal(ToMono16k(16_000, 1).process(audio), float_to_int16(audio[:, 0]))


def test_downmix_averages_channels() -> None:
    chunk = np.array([[0.5, -0.5], [1.0, 0.0]], dtype=np.float32)
    np.testing.assert_array_equal(ToMono16k(16_000, 2).process(chunk), [0, 16384])


def test_clipping_and_rounding() -> None:
    np.testing.assert_array_equal(
        float_to_int16(np.array([2.0, -2.0, 0.5], dtype=np.float32)), [32767, -32767, 16384]
    )


def test_empty_chunk_gives_empty_output() -> None:
    assert len(ToMono16k(48_000, 2).process(np.zeros((0, 2), dtype=np.float32))) == 0


def test_wrong_channel_count_rejected() -> None:
    with pytest.raises(ValueError, match="channels"):
        ToMono16k(48_000, 2).process(np.zeros((10, 1), dtype=np.float32))
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/unit/audio -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.audio'`.

- [ ] **Step 4: Implement**

`src/evra/audio/__init__.py`: empty. `src/evra/audio/frames.py`:

```python
"""The meeting timeline format (BUILD.md §5.1): 16 kHz mono int16 in 10 ms frames."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

import numpy as np
import numpy.typing as npt

SAMPLE_RATE: Final = 16_000
FRAME_MS: Final = 10
FRAME_SAMPLES: Final = SAMPLE_RATE * FRAME_MS // 1000
NS: Final = 1_000_000_000
MIC: Final = 0
SYSTEM: Final = 1
Channel = Literal[0, 1]
Int16Array = npt.NDArray[np.int16]
Float32Array = npt.NDArray[np.float32]


@dataclass(frozen=True)
class Frames:
    channel: Channel
    pcm: Int16Array  # FRAME_SAMPLES samples
    t_capture_ns: int  # monotonic time of pcm[0]
    index: int  # sample index of pcm[0] on the meeting timeline
```

`src/evra/audio/convert.py`:

```python
"""Downmix + resample native capture audio to the 16 kHz mono int16 timeline (BUILD.md §5.1).

libsamplerate keeps filter state between calls, so a stream converted chunk by chunk has
no seams (D24).
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
import samplerate

from evra.audio.frames import SAMPLE_RATE, Float32Array, Int16Array


def float_to_int16(samples: npt.NDArray[np.floating]) -> Int16Array:
    return np.round(np.clip(samples, -1.0, 1.0) * 32767.0).astype(np.int16)


class ToMono16k:
    def __init__(self, native_rate: int, channels: int, converter: str = "sinc_fastest") -> None:
        if native_rate <= 0 or channels <= 0:
            raise ValueError(f"bad audio format: {native_rate} Hz, {channels} channels")
        self.native_rate = native_rate
        self.channels = channels
        self._ratio = SAMPLE_RATE / native_rate
        self._resampler = (
            None if native_rate == SAMPLE_RATE else samplerate.Resampler(converter, channels=1)
        )

    def process(self, chunk: Float32Array) -> Int16Array:
        data = np.asarray(chunk, dtype=np.float32)
        if data.ndim == 2:
            if data.shape[1] != self.channels:
                raise ValueError(f"expected {self.channels} channels, got {data.shape[1]}")
            mono = data.mean(axis=1, dtype=np.float32) if self.channels > 1 else data[:, 0]
        else:
            mono = data
        if len(mono) == 0:
            return np.zeros(0, dtype=np.int16)
        if self._resampler is not None:
            mono = self._resampler.process(np.ascontiguousarray(mono), self._ratio)
        return float_to_int16(mono)
```

- [ ] **Step 5: Run tests and tools**

Run: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`
Expected: all pass.

- [ ] **Step 6: Record the resampler decision**

Append to `DECISIONS.md`:

```markdown

## D24 — libsamplerate (`samplerate`) instead of scipy `resample_poly` (2026-09-24)
- **Context:** BUILD.md §5.1 named `scipy.signal.resample_poly`; capture arrives in 10–26 ms chunks at 44.1/48 kHz.
- **Evidence:** `resample_poly` is stateless, so per-chunk calls create seams at every boundary. A spike on the dev machine showed the default mic at 44.1 kHz (a rational 160/441 ratio) and 26 ms callbacks. `samplerate` 0.2.4 (MIT binding; libsamplerate BSD-2-Clause) streams statefully: 88 200 → 31 954 samples, ≈3 ms held in the filter.
- **Decision:** `ToMono16k` uses `samplerate.Resampler("sinc_fastest")`; scipy is not a dependency.
- **Consequences:** one fewer large dependency; the tiny constant filter delay is absorbed by the timeline.
```

In `BUILD.md` §5.1, replace `with \`scipy.signal.resample_poly\` (never ask WASAPI to convert; avoid \`soxr\`, which is LGPL)` with `with a stateful libsamplerate resampler (\`samplerate\`, D24) (never ask WASAPI to convert; avoid \`soxr\`, which is LGPL)`. Add D24 to the §2 table: `| D24 | Resampling | libsamplerate via \`samplerate\` (stateful, seamless across chunks) | 2026-09-24 |`.

- [ ] **Step 7: Licence register, commit, push**

Run: `uv run python tools/license_gate.py --write-register` and then `uv run python tools/license_gate.py`. The second run must report `0 problems`. If a new package fails, apply the Task 7 (M0) resolution rules.

Append to `PROGRESS.md` under a new heading `## 2026-09-24 — M1 Windows capture` (put it above the M0 heading): `- Task 1: Frames + ToMono16k streaming converter (libsamplerate, D24).`

```powershell
uv run python tools/check.py
git add pyproject.toml uv.lock src/evra/audio tests/unit/audio THIRD_PARTY_LICENSES.md DECISIONS.md BUILD.md PROGRESS.md
git commit -m "feat: 16 kHz timeline frames and streaming converter" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push -u origin windows-capture
```

---

### Task 2: ChunkRing (callback → pipeline hand-off)

**Files:**
- Create: `src/evra/audio/ringbuffer.py`, `tests/unit/audio/test_ringbuffer.py`

**Interfaces:**
- Produces:
  - `Chunk(seq: int, data: Float32Array, t_callback_ns: int)` (frozen)
  - `ChunkRing(max_chunks: int)` with `.put(data, t_callback_ns) -> None` (producer), `.drain() -> list[Chunk]` (consumer) and attribute `.dropped_chunks: int`
  - `ChunkRing.for_duration(seconds: float, chunk_seconds: float) -> ChunkRing`

- [ ] **Step 1: Write failing tests** `tests/unit/audio/test_ringbuffer.py`

```python
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
        batch = ring.drain()
        received.extend(c.seq for c in batch)
        if done.is_set() and not batch:
            break
    producer.join()
    assert received == sorted(received)
    assert len(received) + ring.dropped_chunks == total
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/audio/test_ringbuffer.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.audio.ringbuffer'`.

- [ ] **Step 3: Implement** `src/evra/audio/ringbuffer.py`

```python
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
```

- [ ] **Step 4: Run tests and tools**, then commit and push

Run: `uv run python tools/check.py`
Expected: all PASS. Append to `PROGRESS.md`: `- Task 2: ChunkRing — non-blocking callback hand-off, drops counted.`

```powershell
git add src/evra/audio/ringbuffer.py tests/unit/audio/test_ringbuffer.py PROGRESS.md
git commit -m "feat: non-blocking chunk ring for capture callbacks" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 3: SourceClock (steady timestamps from jittery callbacks)

**Files:**
- Create: `src/evra/audio/clock.py` (SourceClock part), `tests/unit/audio/test_source_clock.py`

**Interfaces:**
- Produces: `SourceClock(native_rate: int, *, latency_ns: int = 0, window: int = 100, jump_ns: int = 50_000_000, jump_chunks: int = 3)` with `.first_sample_ns(t_callback_ns: int, frames: int) -> int`.

**How it works:**
- Every chunk implies an anchor: `callback − latency − (all samples received so far) / rate`.
- Callbacks are only ever late, never early, so the **smallest anchor in the last `window` chunks** is the best estimate. That ignores jitter and bursts, and it follows slow clock drift.
- A jump larger than `jump_ns` that persists for `jump_chunks` chunks means samples really went missing (lost chunks, or a device that stopped delivering). In that case the anchor moves at once.

- [ ] **Step 1: Write failing tests** `tests/unit/audio/test_source_clock.py`

```python
import random

from evra.audio.clock import SourceClock

RATE = 48_000
FR = 480  # 10 ms
MS = 1_000_000


def test_steady_callbacks_give_exact_times() -> None:
    clock = SourceClock(RATE)
    for i in range(50):
        assert clock.first_sample_ns((i + 1) * 10 * MS, FR) == i * 10 * MS


def test_jittery_callbacks_stay_within_2ms() -> None:
    rng = random.Random(7)
    clock = SourceClock(RATE)
    for i in range(1_000):
        late = rng.uniform(0, 30) * MS
        t = clock.first_sample_ns(int((i + 1) * 10 * MS + late), FR)
        if i >= 50:
            assert abs(t - i * 10 * MS) < 2 * MS


def test_bursty_delivery_is_smoothed() -> None:
    clock = SourceClock(RATE)
    for i in range(500):
        callback = ((i // 5) + 1) * 50 * MS  # 5 chunks arrive together every 50 ms
        t = clock.first_sample_ns(callback, FR)
        if i >= 5:
            assert abs(t - i * 10 * MS) <= 1 * MS


def test_persistent_jump_moves_the_anchor() -> None:
    clock = SourceClock(RATE)
    for i in range(100):
        clock.first_sample_ns((i + 1) * 10 * MS, FR)
    stall = 2_000 * MS
    times = [clock.first_sample_ns((i + 1) * 10 * MS + stall, FR) for i in range(100, 110)]
    for i, t in zip(range(102, 110), times[2:], strict=True):
        assert abs(t - (i * 10 * MS + stall)) <= 1 * MS


def test_single_late_callback_is_not_a_jump() -> None:
    clock = SourceClock(RATE)
    for i in range(100):
        clock.first_sample_ns((i + 1) * 10 * MS, FR)
    clock.first_sample_ns(101 * 10 * MS + 200 * MS, FR)
    for i in range(101, 150):
        assert abs(clock.first_sample_ns((i + 1) * 10 * MS, FR) - i * 10 * MS) <= 1 * MS


def test_follows_a_fast_device_clock() -> None:
    clock = SourceClock(RATE)
    for i in range(10_000):
        wall = (i + 1) * 10 * MS / 1.001
        t = clock.first_sample_ns(round(wall), FR)
        assert abs(t - i * 10 * MS / 1.001) < 2 * MS


def test_follows_a_slow_device_clock() -> None:
    clock = SourceClock(RATE)
    for i in range(10_000):
        wall = (i + 1) * 10 * MS / 0.999
        t = clock.first_sample_ns(round(wall), FR)
        assert abs(t - i * 10 * MS / 0.999) < 2 * MS


def test_latency_is_subtracted() -> None:
    clock = SourceClock(RATE, latency_ns=20 * MS)
    assert clock.first_sample_ns(30 * MS, FR) == 0
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/audio/test_source_clock.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.audio.clock'`.

- [ ] **Step 3: Implement** the first part of `src/evra/audio/clock.py`

```python
"""Capture clocks (BUILD.md §5.2).

SourceClock: steady first-sample times for one device from jittery callback times.
ChannelTimeline: places a channel's samples on the shared meeting timeline.
"""

from __future__ import annotations

from collections import deque

from evra.audio.frames import NS


class SourceClock:
    def __init__(
        self,
        native_rate: int,
        *,
        latency_ns: int = 0,
        window: int = 100,
        jump_ns: int = 50_000_000,
        jump_chunks: int = 3,
    ) -> None:
        self._rate = native_rate
        self._latency_ns = latency_ns
        self._samples = 0
        self._recent: deque[float] = deque(maxlen=window)
        self._pending: list[float] = []
        self._anchor: float | None = None
        self._jump_ns = jump_ns
        self._jump_chunks = jump_chunks

    def first_sample_ns(self, t_callback_ns: int, frames: int) -> int:
        before = self._samples
        self._samples += frames
        implied = t_callback_ns - self._latency_ns - self._samples * NS / self._rate
        if self._anchor is None:
            self._anchor = implied
            self._recent.append(implied)
        elif implied - self._anchor > self._jump_ns:
            self._pending.append(implied)
            if len(self._pending) >= self._jump_chunks:
                self._anchor = min(self._pending)
                self._recent.clear()
                self._recent.extend(self._pending)
                self._pending.clear()
        else:
            self._pending.clear()
            self._recent.append(implied)
            self._anchor = min(self._recent)
        return round(self._anchor + before * NS / self._rate)
```

- [ ] **Step 4: Run tests and tools**, then commit and push

Run: `uv run python tools/check.py`
Expected: all PASS. Append to `PROGRESS.md`: `- Task 3: SourceClock — steady timestamps from jittery/bursty callbacks; follows drift; detects real jumps.`

```powershell
git add src/evra/audio/clock.py tests/unit/audio/test_source_clock.py PROGRESS.md
git commit -m "feat: source clock that steadies jittery capture callbacks" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 4: ChannelTimeline (gaps, drift correction, silence padding)

**Files:**
- Modify: `src/evra/audio/clock.py` (append)
- Create: `tests/unit/audio/test_timeline.py`

**Interfaces:**
- Consumes: `SAMPLE_RATE`, `FRAME_SAMPLES`, `NS`, `Int16Array` from Task 1.
- Produces:
  - `GAP_SAMPLES = 800`, `MAX_DRIFT_SAMPLES = 320`, `CHECK_EVERY_SAMPLES = 16_000`
  - `Gap(start: int, length: int, cause: str)` (frozen; samples)
  - `TimelineStats` (mutable dataclass) with fields `corrections`, `inserted`, `dropped`, `padded`, `drift` (samples; positive means the timeline is ahead of real time) and `gaps: list[Gap]`
  - `ChannelTimeline(start_ns: int)` with:
    - `.emitted: int`
    - `.stats: TimelineStats`
    - `.index_at(t_ns) -> int`
    - `.place(samples: Int16Array, t_first_ns: int, cause: str = "dropout") -> Int16Array`
    - `.pad_until(now_ns: int, margin_ns: int = 100_000_000) -> Int16Array`

- [ ] **Step 1: Write failing tests** `tests/unit/audio/test_timeline.py`

```python
import numpy as np

from evra.audio.clock import ChannelTimeline

MS = 1_000_000
CHUNK = 160  # 10 ms at 16 kHz


def _pcm(n: int = CHUNK, value: int = 1000) -> np.ndarray:
    return np.full(n, value, dtype=np.int16)


def test_on_time_chunks_pass_through_unchanged() -> None:
    tl = ChannelTimeline(0)
    for i in range(300):
        out = tl.place(_pcm(), i * 10 * MS)
        assert len(out) == CHUNK
    assert tl.emitted == 300 * CHUNK
    assert tl.stats.corrections == 0 and tl.stats.gaps == []
    assert tl.stats.drift == 0


def test_small_jitter_is_not_corrected() -> None:
    tl = ChannelTimeline(0)
    for i in range(500):
        jitter = (5 if i % 2 else -5) * MS
        tl.place(_pcm(), i * 10 * MS + jitter)
    assert tl.stats.corrections == 0
    assert tl.emitted == 500 * CHUNK


def test_hole_of_50ms_or_more_becomes_a_gap_filled_with_silence() -> None:
    tl = ChannelTimeline(0)
    for i in range(10):
        tl.place(_pcm(), i * 10 * MS)
    out = tl.place(_pcm(), 400 * MS)  # 300 ms hole after 100 ms of audio
    assert len(out) == 4800 + CHUNK
    assert not out[:4800].any()
    [gap] = tl.stats.gaps
    assert (gap.start, gap.length, gap.cause) == (1600, 4800, "dropout")


def test_gap_cause_is_recorded() -> None:
    tl = ChannelTimeline(0)
    tl.place(_pcm(), 0)
    tl.place(_pcm(), 500 * MS, cause="device_change")
    assert tl.stats.gaps[0].cause == "device_change"


def _simulate(speed: float, minutes: int) -> tuple[ChannelTimeline, int]:
    tl = ChannelTimeline(0)
    worst = 0
    for i in range(minutes * 60 * 100):
        tl.place(_pcm(), round(i * 10 * MS / speed))
        worst = max(worst, abs(tl.stats.drift))
    return tl, worst


def test_fast_device_is_corrected_by_dropping_in_10ms_steps() -> None:
    tl, worst = _simulate(speed=1.001, minutes=60)
    assert tl.stats.corrections > 0 and tl.stats.dropped > 0
    assert worst < 480  # < 30 ms at every point of a 60-minute run
    assert tl.stats.dropped % CHUNK == 0


def test_slow_device_is_corrected_by_inserting_silence() -> None:
    tl, worst = _simulate(speed=0.999, minutes=10)
    assert tl.stats.inserted > 0 and worst < 480


def test_pad_until_keeps_the_timeline_moving() -> None:
    tl = ChannelTimeline(0)
    fill = tl.pad_until(1_000 * MS)
    assert len(fill) == 14_400 and not fill.any()  # up to now − 100 ms
    assert tl.stats.padded == 14_400
    assert len(tl.pad_until(1_050 * MS)) == 800
    assert len(tl.pad_until(1_052 * MS)) == 0  # less than one frame missing
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/audio/test_timeline.py -q`
Expected: FAIL with `ImportError: cannot import name 'ChannelTimeline'`.

- [ ] **Step 3: Implement.** Append to `src/evra/audio/clock.py`; add `from dataclasses import dataclass, field`, `import numpy as np` and `from evra.audio.frames import FRAME_SAMPLES, SAMPLE_RATE, Int16Array` to its imports.

```python
GAP_SAMPLES = 800  # 50 ms: a hole this big is a gap, filled at once
MAX_DRIFT_SAMPLES = 320  # 20 ms of drift before correcting
CHECK_EVERY_SAMPLES = SAMPLE_RATE  # compare clocks about once per second of audio
STEP = FRAME_SAMPLES  # corrections move in 10 ms steps


@dataclass(frozen=True)
class Gap:
    start: int  # timeline sample index
    length: int  # samples of inserted silence
    cause: str  # dropout | device_change | silence


@dataclass
class TimelineStats:
    corrections: int = 0
    inserted: int = 0
    dropped: int = 0
    padded: int = 0
    drift: int = 0  # samples; positive = timeline ahead of real time
    gaps: list[Gap] = field(default_factory=list)


class ChannelTimeline:
    def __init__(self, start_ns: int) -> None:
        self._start_ns = start_ns
        self.emitted = 0
        self.stats = TimelineStats()
        self._since_check = 0
        self._owed_drop = 0

    def index_at(self, t_ns: int) -> int:
        return round((t_ns - self._start_ns) * SAMPLE_RATE / NS)

    def place(self, samples: Int16Array, t_first_ns: int, cause: str = "dropout") -> Int16Array:
        """What to append to this channel's timeline for a chunk whose first sample is at t."""
        delta = self.index_at(t_first_ns) - self.emitted  # > 0: timeline behind real time
        out = samples
        if delta >= GAP_SAMPLES:
            fill = delta // STEP * STEP
            self.stats.gaps.append(Gap(self.emitted, fill, cause))
            self.stats.inserted += fill
            out = np.concatenate([np.zeros(fill, dtype=np.int16), out])
            self._since_check = 0
            self._owed_drop = 0
        elif self._since_check >= CHECK_EVERY_SAMPLES:
            self._since_check = 0
            if abs(delta) > MAX_DRIFT_SAMPLES:
                amount = abs(delta) // STEP * STEP
                self.stats.corrections += 1
                if delta > 0:
                    self.stats.inserted += amount
                    out = np.concatenate([np.zeros(amount, dtype=np.int16), out])
                else:
                    self._owed_drop += amount
        if self._owed_drop and len(out):
            cut = min(self._owed_drop, len(out))
            out = out[cut:]
            self._owed_drop -= cut
            self.stats.dropped += cut
        self._since_check += len(samples)
        self.emitted += len(out)
        self.stats.drift = self.emitted - (self.index_at(t_first_ns) + len(samples))
        return out

    def pad_until(self, now_ns: int, margin_ns: int = 100_000_000) -> Int16Array:
        """Silence that keeps the timeline moving while a source delivers nothing."""
        missing = self.index_at(now_ns - margin_ns) - self.emitted
        if missing < STEP:
            return np.zeros(0, dtype=np.int16)
        fill = missing // STEP * STEP
        self.stats.padded += fill
        self.emitted += fill
        return np.zeros(fill, dtype=np.int16)
```

- [ ] **Step 4: Run tests and tools**, then commit and push

Run: `uv run python tools/check.py`
Expected: all PASS; the 60-minute simulation runs in a few seconds. Append to `PROGRESS.md`: `- Task 4: ChannelTimeline — ≥50 ms gaps filled, >20 ms drift corrected in 10 ms steps (60-min simulated drift < 30 ms), silence padding.`

```powershell
git add src/evra/audio/clock.py tests/unit/audio/test_timeline.py PROGRESS.md
git commit -m "feat: channel timeline with gap filling, drift correction and padding" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 5: CapturePipeline and the AudioSource protocol

**Files:**
- Create: `src/evra/capture/__init__.py`, `src/evra/capture/sources.py`, `src/evra/audio/pipeline.py`, `tests/unit/audio/test_pipeline.py`

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces (`capture/sources.py`):
  - `AudioSource` Protocol with attributes `name: str`, `ring: ChunkRing`, `native_rate: int`, `native_channels: int`, `latency_ns: int`, `pads_silence: bool`, and methods `start() -> None`, `stop() -> None`, `reopen() -> None`
  - `CaptureError(message: str, hint: str = "")` with attribute `.hint`; subclasses `MicUnavailableError`, `LoopbackUnavailableError`
  - `MIC_PRIVACY_HINT: str`, `NO_OUTPUT_HINT: str`
- Produces (`audio/pipeline.py`):
  - `SILENCE_AFTER_NS = 50_000_000`
  - `ChannelStats` (frozen) with fields `channel`, `native_rate`, `native_channels`, `seconds`, `rms_dbfs`, `peak_dbfs`, `dropped_chunks`, `corrections`, `inserted_ms`, `dropped_ms`, `padded_ms`, `drift_ms`, `gaps: tuple[Gap, ...]`
  - `CapturePipeline(sources: Mapping[Channel, AudioSource], on_frames: Callable[[Frames], None], *, start_ns: int, now_ns: Callable[[], int] = time.monotonic_ns)` with methods:
    - `.step() -> None`
    - `.flush() -> None`
    - `.swap_source(channel: Channel, reopen: Callable[[], None], cause: str = "device_change") -> None`
    - `.stats(channel: Channel) -> ChannelStats`

- [ ] **Step 1: Write failing tests** `tests/unit/audio/test_pipeline.py`

```python
from collections.abc import Iterator
from dataclasses import dataclass, field

import numpy as np
import pytest

from evra.audio.frames import MIC, SYSTEM, Frames
from evra.audio.pipeline import CapturePipeline
from evra.audio.ringbuffer import ChunkRing

MS = 1_000_000


@dataclass
class StubSource:
    native_rate: int = 48_000
    native_channels: int = 2
    pads_silence: bool = False
    name: str = "stub"
    latency_ns: int = 0
    ring: ChunkRing = field(default_factory=lambda: ChunkRing(200))

    def start(self) -> None: ...
    def stop(self) -> None: ...
    def reopen(self) -> None: ...


class FakeClock:
    def __init__(self) -> None:
        self.t = 0

    def __call__(self) -> int:
        return self.t


def _chunk(rate: int, channels: int, amp: float = 0.5, i: int = 0) -> np.ndarray:
    n = rate // 100
    t = (np.arange(n) + i * n) / rate
    mono = (amp * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1)


@pytest.fixture
def rig() -> Iterator[tuple[StubSource, StubSource, FakeClock, list[Frames], CapturePipeline]]:
    mic = StubSource(native_rate=44_100, native_channels=1)
    system = StubSource(pads_silence=True)
    clock = FakeClock()
    frames: list[Frames] = []
    pipe = CapturePipeline({MIC: mic, SYSTEM: system}, frames.append, start_ns=0, now_ns=clock)
    yield mic, system, clock, frames, pipe


def _tick(rig_parts, i: int, *, system: bool = True) -> None:  # type: ignore[no-untyped-def]
    mic, sysrc, clock, _, pipe = rig_parts
    clock.t = (i + 1) * 10 * MS
    mic.ring.put(_chunk(44_100, 1, i=i), clock.t)
    if system:
        sysrc.ring.put(_chunk(48_000, 2, i=i), clock.t)
    pipe.step()


def _per_channel(frames: list[Frames], ch: int) -> list[Frames]:
    return [f for f in frames if f.channel == ch]


def test_emits_contiguous_10ms_frames_per_channel(rig) -> None:  # type: ignore[no-untyped-def]
    for i in range(100):
        _tick(rig, i)
    frames = rig[3]
    for ch in (MIC, SYSTEM):
        chan = _per_channel(frames, ch)
        assert len(chan) >= 98
        assert all(len(f.pcm) == 160 and f.pcm.dtype == np.int16 for f in chan)
        assert [f.index for f in chan] == [k * 160 for k in range(len(chan))]
        assert all(f.t_capture_ns == f.index * 62_500 for f in chan)


def test_loopback_silence_is_padded_and_resume_keeps_alignment(rig) -> None:  # type: ignore[no-untyped-def]
    for i in range(300):
        _tick(rig, i, system=not (100 <= i < 200))
        if 150 <= i < 160:  # while silent, the system channel keeps moving
            assert _per_channel(rig[3], SYSTEM)[-1].index >= (i - 20) * 160
    pipe = rig[4]
    pipe.flush()
    mic_n = len(_per_channel(rig[3], MIC))
    sys_n = len(_per_channel(rig[3], SYSTEM))
    assert abs(mic_n - sys_n) <= 3  # within 30 ms
    stats = pipe.stats(SYSTEM)
    assert stats.padded_ms >= 800
    assert all(g.cause == "silence" for g in stats.gaps)
    assert stats.dropped_ms == 0


def test_ring_overflow_counts_drops_and_records_a_dropout_gap(rig) -> None:  # type: ignore[no-untyped-def]
    mic, system, clock, frames, pipe = rig
    for i in range(250):  # 2.5 s without a pipeline step: the 2 s ring overflows
        clock.t = (i + 1) * 10 * MS
        system.ring.put(_chunk(48_000, 2, i=i), clock.t)
    pipe.step()
    stats = pipe.stats(SYSTEM)
    assert stats.dropped_chunks == 50
    assert stats.gaps and stats.gaps[0].cause == "dropout"


def test_swap_source_records_device_change_gap_and_new_rate(rig) -> None:  # type: ignore[no-untyped-def]
    mic, system, clock, frames, pipe = rig
    for i in range(100):
        _tick(rig, i)

    def reopen() -> None:
        system.native_rate, system.native_channels = 44_100, 1

    pipe.swap_source(SYSTEM, reopen)
    for i in range(130, 230):  # new device starts 300 ms later at 44.1 kHz mono
        clock.t = (i + 1) * 10 * MS
        mic.ring.put(_chunk(44_100, 1, i=i), clock.t)
        system.ring.put(_chunk(44_100, 1, i=i), clock.t)
        pipe.step()
    causes = [g.cause for g in pipe.stats(SYSTEM).gaps]
    assert "device_change" in causes
    assert pipe.stats(SYSTEM).native_rate == 44_100


def test_flush_zero_pads_the_last_partial_frame(rig) -> None:  # type: ignore[no-untyped-def]
    for i in range(5):
        _tick(rig, i)
    rig[4].flush()
    for ch in (MIC, SYSTEM):
        assert all(len(f.pcm) == 160 for f in _per_channel(rig[3], ch))


def test_levels_are_measured_in_dbfs(rig) -> None:  # type: ignore[no-untyped-def]
    for i in range(200):
        _tick(rig, i)
    stats = rig[4].stats(MIC)
    assert -9.6 < stats.rms_dbfs < -8.5  # 0.5-amplitude sine ≈ −9.03 dBFS
    assert -6.5 < stats.peak_dbfs < -5.5
    assert stats.seconds == pytest.approx(len(_per_channel(rig[3], MIC)) / 100)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/audio/test_pipeline.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.audio.pipeline'`.

- [ ] **Step 3: Implement** `src/evra/capture/__init__.py` (empty) and `src/evra/capture/sources.py`:

```python
"""What a capture source must provide (BUILD.md §5.1), and the errors users can act on."""

from __future__ import annotations

from typing import Protocol

from evra.audio.ringbuffer import ChunkRing

MIC_PRIVACY_HINT = (
    "Check Windows Settings > Privacy & security > Microphone "
    "(ms-settings:privacy-microphone) and allow desktop apps to use the microphone."
)
NO_OUTPUT_HINT = "Connect speakers or headphones and make them the default output device."


class CaptureError(RuntimeError):
    def __init__(self, message: str, hint: str = "") -> None:
        super().__init__(message)
        self.hint = hint


class MicUnavailableError(CaptureError):
    pass


class LoopbackUnavailableError(CaptureError):
    pass


class AudioSource(Protocol):
    name: str
    ring: ChunkRing
    native_rate: int
    native_channels: int
    latency_ns: int
    pads_silence: bool

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def reopen(self) -> None: ...
```

`src/evra/audio/pipeline.py`:

```python
"""Per-channel drain → timestamp → convert → place → emit, every 10 ms (BUILD.md §5.2)."""

from __future__ import annotations

import math
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

import numpy as np

from evra.audio.clock import ChannelTimeline, Gap, SourceClock
from evra.audio.convert import ToMono16k
from evra.audio.frames import FRAME_SAMPLES, NS, SAMPLE_RATE, Channel, Frames, Int16Array
from evra.capture.sources import AudioSource

SILENCE_AFTER_NS = 50_000_000  # no loopback data for 50 ms → pad silence (§5.1)
_FULL_SCALE = 32767.0


def _dbfs(ratio: float) -> float:
    return round(20 * math.log10(ratio), 2) if ratio > 0 else -120.0


@dataclass(frozen=True)
class ChannelStats:
    channel: int
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
    gaps: tuple[Gap, ...]


class _ChannelState:
    def __init__(self, source: AudioSource, start_ns: int) -> None:
        self.source = source
        self.timeline = ChannelTimeline(start_ns)
        self.buffer: Int16Array = np.zeros(0, dtype=np.int16)
        self.frames_out = 0
        self.last_chunk_ns: int | None = None
        self.padding = False
        self.next_cause: str | None = None
        self.sum_squares = 0.0
        self.measured = 0
        self.peak = 0
        self.reset_format()

    def reset_format(self) -> None:
        self.converter = ToMono16k(self.source.native_rate, self.source.native_channels)
        self.clock = SourceClock(self.source.native_rate, latency_ns=self.source.latency_ns)


class CapturePipeline:
    def __init__(
        self,
        sources: Mapping[Channel, AudioSource],
        on_frames: Callable[[Frames], None],
        *,
        start_ns: int,
        now_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._start_ns = start_ns
        self._now = now_ns
        self._on_frames = on_frames
        self._states = {ch: _ChannelState(src, start_ns) for ch, src in sources.items()}
        self._lock = threading.Lock()

    def step(self) -> None:
        with self._lock:
            now = self._now()
            for channel, state in self._states.items():
                self._drain(state)
                self._maybe_pad(state, now)
                self._emit(channel, state)

    def flush(self) -> None:
        self.step()
        with self._lock:
            for channel, state in self._states.items():
                rest = len(state.buffer) % FRAME_SAMPLES
                if rest:
                    pad = np.zeros(FRAME_SAMPLES - rest, dtype=np.int16)
                    state.buffer = np.concatenate([state.buffer, pad])
                self._emit(channel, state)

    def swap_source(
        self, channel: Channel, reopen: Callable[[], None], cause: str = "device_change"
    ) -> None:
        """Re-open a source (e.g. new default output) without losing the timeline."""
        with self._lock:
            state = self._states[channel]
            self._drain(state)  # finish the old device's audio with the old converter
            reopen()
            state.reset_format()
            state.next_cause = cause
            state.padding = False

    def stats(self, channel: Channel) -> ChannelStats:
        with self._lock:
            s = self._states[channel]
            t = s.timeline.stats
            rms = math.sqrt(s.sum_squares / s.measured) / _FULL_SCALE if s.measured else 0.0
            return ChannelStats(
                channel=channel,
                native_rate=s.source.native_rate,
                native_channels=s.source.native_channels,
                seconds=s.frames_out * FRAME_SAMPLES / SAMPLE_RATE,
                rms_dbfs=_dbfs(rms),
                peak_dbfs=_dbfs(s.peak / _FULL_SCALE),
                dropped_chunks=s.source.ring.dropped_chunks,
                corrections=t.corrections,
                inserted_ms=t.inserted * 1000 / SAMPLE_RATE,
                dropped_ms=t.dropped * 1000 / SAMPLE_RATE,
                padded_ms=t.padded * 1000 / SAMPLE_RATE,
                drift_ms=t.drift * 1000 / SAMPLE_RATE,
                gaps=tuple(t.gaps),
            )

    def _drain(self, s: _ChannelState) -> None:
        for chunk in s.source.ring.drain():
            if s.padding:  # resuming after silence: re-anchor on this chunk
                s.clock = SourceClock(s.source.native_rate, latency_ns=s.source.latency_ns)
                s.next_cause = s.next_cause or "silence"
                s.padding = False
            t_first = s.clock.first_sample_ns(chunk.t_callback_ns, len(chunk.data))
            pcm = s.converter.process(chunk.data)
            self._measure(s, pcm)
            placed = s.timeline.place(pcm, t_first, cause=s.next_cause or "dropout")
            s.next_cause = None
            s.buffer = np.concatenate([s.buffer, placed])
            s.last_chunk_ns = chunk.t_callback_ns

    def _maybe_pad(self, s: _ChannelState, now: int) -> None:
        if not s.source.pads_silence:
            return
        last = s.last_chunk_ns if s.last_chunk_ns is not None else self._start_ns
        if now - last < SILENCE_AFTER_NS:
            return
        fill = s.timeline.pad_until(now)
        if len(fill):
            s.padding = True
            s.buffer = np.concatenate([s.buffer, fill])

    def _emit(self, channel: Channel, s: _ChannelState) -> None:
        count = len(s.buffer) // FRAME_SAMPLES
        for k in range(count):
            index = s.frames_out * FRAME_SAMPLES
            pcm = s.buffer[k * FRAME_SAMPLES : (k + 1) * FRAME_SAMPLES].copy()
            t_ns = self._start_ns + round(index * NS / SAMPLE_RATE)
            self._on_frames(Frames(channel, pcm, t_ns, index))
            s.frames_out += 1
        s.buffer = s.buffer[count * FRAME_SAMPLES :]

    @staticmethod
    def _measure(s: _ChannelState, pcm: Int16Array) -> None:
        if len(pcm):
            as_float = pcm.astype(np.float64)
            s.sum_squares += float(np.dot(as_float, as_float))
            s.measured += len(pcm)
            s.peak = max(s.peak, int(np.max(np.abs(pcm.astype(np.int32)))))
```

- [ ] **Step 4: Run tests and tools**, then commit and push

Run: `uv run python tools/check.py`
Expected: all PASS. Append to `PROGRESS.md`: `- Task 5: CapturePipeline — per-channel drain/clock/convert/place/emit; loopback padding, overflow gaps, device swap, levels.`

```powershell
git add src/evra/capture src/evra/audio/pipeline.py tests/unit/audio/test_pipeline.py PROGRESS.md
git commit -m "feat: capture pipeline aligning both channels on one timeline" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 6: Encrypted spill and meeting keys

**Files:**
- Create: `src/evra/audio/spill.py`, `src/evra/audio/keys.py`, `tests/unit/audio/test_spill.py`, `tests/unit/audio/test_keys.py`
- Modify: `src/evra/paths.py` (+ `spill_dir`), `tests/unit/test_paths.py`

**Interfaces:**
- Produces:
  - `SpillSegment(channel, index, start_ms, end_ms, path)`
  - `SpillError`
  - `SpillWriter(directory: Path, meeting_id: str, key: bytes, *, segment_samples: int = 480_000)` with `.write(frames: Frames) -> None`, `.close() -> list[SpillSegment]` and `.segments`
  - `read_segment(path: Path, key: bytes) -> tuple[dict[str, Any], Int16Array]`
  - `read_channel(directory: Path, key: bytes, channel: int) -> Int16Array`
  - `KeyStore` Protocol (`get`, `set`, `delete`), `MemoryKeyStore`, `KeyringKeyStore(service: str = APP_NAME)`
  - `new_meeting_key() -> bytes`
  - `AppPaths.spill_dir -> Path` (= `data_dir / "spill"`)

- [ ] **Step 1: Add dependencies**

```powershell
uv add cryptography keyring
```

- [ ] **Step 2: Write failing tests**

`tests/unit/audio/test_spill.py`:

```python
from pathlib import Path

import numpy as np
import pytest

from evra.audio.frames import MIC, SYSTEM, Frames
from evra.audio.keys import new_meeting_key
from evra.audio.spill import SpillError, SpillWriter, read_channel, read_segment


def _frames(channel: int, count: int, start: int = 0) -> list[Frames]:
    out = []
    for k in range(count):
        pcm = np.full(160, (k % 100) + 1, dtype=np.int16)
        index = (start + k) * 160
        out.append(Frames(channel, pcm, index * 62_500, index))  # type: ignore[arg-type]
    return out


def test_round_trip_both_channels_across_segments(tmp_path: Path) -> None:
    key = new_meeting_key()
    writer = SpillWriter(tmp_path, "m1", key, segment_samples=16_000)  # 1 s segments
    frames = _frames(MIC, 250) + _frames(SYSTEM, 130)
    for f in frames:
        writer.write(f)
    segments = writer.close()
    assert [s.channel for s in segments].count(MIC) == 3  # 1 s + 1 s + 0.5 s
    assert segments[0].start_ms == 0 and segments[0].end_ms == 1000
    mic = read_channel(tmp_path, key, MIC)
    expected = np.concatenate([f.pcm for f in frames if f.channel == MIC])
    np.testing.assert_array_equal(mic, expected)
    assert len(read_channel(tmp_path, key, SYSTEM)) == 130 * 160


def test_no_plaintext_on_disk(tmp_path: Path) -> None:
    writer = SpillWriter(tmp_path, "m1", new_meeting_key(), segment_samples=1_600)
    marker = np.frombuffer(b"EVRAPLAINTEXT!!!" * 20, dtype=np.int16)
    writer.write(Frames(MIC, marker, 0, 0))
    [seg] = writer.close()
    assert b"EVRAPLAINTEXT" not in seg.path.read_bytes()


def test_tampered_segment_fails(tmp_path: Path) -> None:
    key = new_meeting_key()
    writer = SpillWriter(tmp_path, "m1", key)
    for f in _frames(MIC, 10):
        writer.write(f)
    [seg] = writer.close()
    raw = bytearray(seg.path.read_bytes())
    raw[-5] ^= 0xFF
    seg.path.write_bytes(bytes(raw))
    with pytest.raises(SpillError, match="authentication"):
        read_segment(seg.path, key)


def test_wrong_key_fails(tmp_path: Path) -> None:
    writer = SpillWriter(tmp_path, "m1", new_meeting_key())
    writer.write(_frames(MIC, 1)[0])
    [seg] = writer.close()
    with pytest.raises(SpillError):
        read_segment(seg.path, new_meeting_key())


def test_not_a_spill_file(tmp_path: Path) -> None:
    bad = tmp_path / "0_00000.spill"
    bad.write_bytes(b"hello")
    with pytest.raises(SpillError, match="not a spill file"):
        read_segment(bad, new_meeting_key())


def test_header_is_authenticated_metadata(tmp_path: Path) -> None:
    key = new_meeting_key()
    writer = SpillWriter(tmp_path, "m-42", key)
    for f in _frames(SYSTEM, 3, start=10):
        writer.write(f)
    [seg] = writer.close()
    header, pcm = read_segment(seg.path, key)
    assert header["meeting_id"] == "m-42" and header["channel"] == SYSTEM
    assert header["start_ms"] == 100 and len(pcm) == 480
    assert not list(tmp_path.glob("*.tmp"))
```

`tests/unit/audio/test_keys.py`:

```python
from collections.abc import Iterator

import keyring
import keyring.backend
import keyring.errors
import pytest

from evra.audio.keys import KeyringKeyStore, MemoryKeyStore, new_meeting_key


class _DictKeyring(keyring.backend.KeyringBackend):
    priority = 1  # type: ignore[assignment]

    def __init__(self) -> None:
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self.store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self.store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        if (service, username) not in self.store:
            raise keyring.errors.PasswordDeleteError("missing")
        del self.store[(service, username)]


@pytest.fixture
def fake_keyring() -> Iterator[_DictKeyring]:
    previous = keyring.get_keyring()
    fake = _DictKeyring()
    keyring.set_keyring(fake)
    yield fake
    keyring.set_keyring(previous)


def test_new_key_is_256_bit_and_random() -> None:
    a, b = new_meeting_key(), new_meeting_key()
    assert len(a) == 32 and a != b


def test_keyring_store_round_trip_under_evra_meeting_id(fake_keyring: _DictKeyring) -> None:
    store = KeyringKeyStore()
    key = new_meeting_key()
    store.set("m1", key)
    assert ("Evra", "meeting/m1") in fake_keyring.store
    assert store.get("m1") == key
    store.delete("m1")
    assert store.get("m1") is None
    store.delete("m1")  # deleting twice is fine


def test_memory_store() -> None:
    store = MemoryKeyStore()
    store.set("m", b"k" * 32)
    assert store.get("m") == b"k" * 32
    store.delete("m")
    assert store.get("m") is None
```

Add to `tests/unit/test_paths.py`:

```python
def test_spill_dir_is_under_data(tmp_path: Path) -> None:
    assert AppPaths.under(tmp_path).spill_dir == tmp_path / "data" / "spill"
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/unit/audio/test_spill.py tests/unit/audio/test_keys.py tests/unit/test_paths.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.audio.spill'` (and `evra.audio.keys`), plus an `AttributeError` for `spill_dir`.

- [ ] **Step 4: Implement**

In `src/evra/paths.py`, add after `db_path`:

```python
    @property
    def spill_dir(self) -> Path:
        return self.data_dir / "spill"
```

`src/evra/audio/keys.py`:

```python
"""Per-meeting spill keys in the OS credential store (BUILD.md §5.5, D23 of v3: keyring)."""

from __future__ import annotations

import base64
from typing import Protocol

import keyring
import keyring.errors
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from evra.constants import APP_NAME


def new_meeting_key() -> bytes:
    return AESGCM.generate_key(bit_length=256)


class KeyStore(Protocol):
    def get(self, meeting_id: str) -> bytes | None: ...

    def set(self, meeting_id: str, key: bytes) -> None: ...

    def delete(self, meeting_id: str) -> None: ...


class KeyringKeyStore:
    """Windows Credential Manager via keyring: service "Evra", username "meeting/<id>"."""

    def __init__(self, service: str = APP_NAME) -> None:
        self._service = service

    @staticmethod
    def _user(meeting_id: str) -> str:
        return f"meeting/{meeting_id}"

    def get(self, meeting_id: str) -> bytes | None:
        value = keyring.get_password(self._service, self._user(meeting_id))
        return base64.b64decode(value) if value else None

    def set(self, meeting_id: str, key: bytes) -> None:
        encoded = base64.b64encode(key).decode("ascii")
        keyring.set_password(self._service, self._user(meeting_id), encoded)

    def delete(self, meeting_id: str) -> None:
        try:
            keyring.delete_password(self._service, self._user(meeting_id))
        except keyring.errors.PasswordDeleteError:
            pass


class MemoryKeyStore:
    def __init__(self) -> None:
        self._keys: dict[str, bytes] = {}

    def get(self, meeting_id: str) -> bytes | None:
        return self._keys.get(meeting_id)

    def set(self, meeting_id: str, key: bytes) -> None:
        self._keys[meeting_id] = key

    def delete(self, meeting_id: str) -> None:
        self._keys.pop(meeting_id, None)
```

`src/evra/audio/spill.py`:

```python
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
```

- [ ] **Step 5: Run tests and tools; licence register; commit and push**

Run: `uv run python tools/license_gate.py --write-register`, then `uv run python tools/check.py`
Expected: all PASS, licence gate 0 problems. Append to `PROGRESS.md`: `- Task 6: AES-GCM spill segments (authenticated header, atomic writes) + per-meeting keys in Credential Manager.`

```powershell
git add pyproject.toml uv.lock src/evra/paths.py src/evra/audio/spill.py src/evra/audio/keys.py tests/unit/audio/test_spill.py tests/unit/audio/test_keys.py tests/unit/test_paths.py THIRD_PARTY_LICENSES.md PROGRESS.md
git commit -m "feat: encrypted audio spill with per-meeting keys" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 7: Sources — fake, microphone, loopback, default-output watcher

**Files:**
- Create: `src/evra/capture/fake.py`, `src/evra/capture/mic.py`, `src/evra/capture/windows.py`, `tests/unit/capture/__init__.py`, `tests/unit/capture/test_fake.py`, `tests/unit/capture/test_mic.py`, `tests/unit/capture/test_windows.py`, `tests/hardware/__init__.py`, `tests/hardware/test_devices.py`
- Modify: `pyproject.toml` (deps; pytest `hardware` marker), `DECISIONS.md`, `BUILD.md` §5.1

**Interfaces:**
- Consumes:
  - From Task 2: `ChunkRing`.
  - From Task 5: `AudioSource`, `CaptureError` and its subclasses, the hints.
- Produces:
  - `FakeEvent(kind: Literal["silence", "dropout"], start_s: float, duration_s: float)`
  - `FakeSource(audio, rate, *, name="fake", events=(), pads_silence=False, now_ns=..., sleep=..., latency_ns=0)` with `.from_wav(path, **kw)`, `.finished: threading.Event`, and `start`/`stop`/`reopen`
  - `MicSource(device: int | str | None = None, *, backend: Any = None, now_ns=...)` with `.overflows`
  - `list_input_devices(backend: Any = None) -> list[dict[str, object]]`
  - `LoopbackSource(*, backend: Any = None, now_ns=...)`
  - `default_output_id() -> str | None`
  - `DefaultOutputWatcher(on_change: Callable[[str | None], None], *, get_id=default_output_id, interval_s=2.0)` with `start`/`stop`

- [ ] **Step 1: Add dependencies and the pytest marker**

```powershell
uv add sounddevice "pyaudiowpatch; sys_platform == 'win32'" "pycaw; sys_platform == 'win32'" "comtypes; sys_platform == 'win32'"
```

In `[tool.pytest.ini_options]`, set `addopts = "-ra -m 'not hardware'"` and add:

```toml
markers = ["hardware: needs real audio devices or the Windows credential store (run: uv run pytest -m hardware)"]
```

- [ ] **Step 2: Write failing tests**

`tests/unit/capture/test_fake.py` (plus empty `tests/unit/capture/__init__.py`):

```python
import wave
from pathlib import Path

import numpy as np

from evra.capture.fake import FakeEvent, FakeSource


class VirtualTime:
    def __init__(self) -> None:
        self.t = 0

    def now(self) -> int:
        return self.t

    def sleep(self, seconds: float) -> None:
        self.t += int(seconds * 1e9)


def _run(src: FakeSource) -> list[np.ndarray]:
    src.start()
    assert src.finished.wait(5)
    src.stop()
    return [c.data for c in src.ring.drain()]


def test_replays_all_audio_in_10ms_chunks() -> None:
    vt = VirtualTime()
    audio = np.linspace(-0.5, 0.5, 16_000, dtype=np.float32)  # 1 s at 16 kHz
    chunks = _run(FakeSource(audio, 16_000, now_ns=vt.now, sleep=vt.sleep))
    assert len(chunks) == 100 and all(c.shape == (160, 1) for c in chunks)
    np.testing.assert_array_equal(np.concatenate(chunks)[:, 0], audio)


def test_dropout_delivers_nothing_and_silence_delivers_zeros() -> None:
    vt = VirtualTime()
    audio = np.full(16_000, 0.25, dtype=np.float32)
    events = [FakeEvent("dropout", 0.2, 0.1), FakeEvent("silence", 0.5, 0.1)]
    chunks = _run(FakeSource(audio, 16_000, events=events, now_ns=vt.now, sleep=vt.sleep))
    assert len(chunks) == 90
    zeros = [c for c in chunks if not c.any()]
    assert len(zeros) == 10


def test_from_wav(tmp_path: Path) -> None:
    path = tmp_path / "a.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(48_000)
        w.writeframes(np.full((480, 2), 16384, dtype=np.int16).tobytes())
    src = FakeSource.from_wav(path)
    assert (src.native_rate, src.native_channels) == (48_000, 2)
    assert np.allclose(src.audio, 0.5)
```

`tests/unit/capture/test_mic.py`:

```python
from typing import Any

import numpy as np
import pytest

from evra.capture.mic import MicSource
from evra.capture.sources import MIC_PRIVACY_HINT, MicUnavailableError


class FakePortAudioError(Exception):
    pass


class FakeFlags:
    def __init__(self, overflow: bool = False) -> None:
        self.input_overflow = overflow


class FakeStream:
    def __init__(self, fail: bool, **kwargs: Any) -> None:
        if fail:
            raise FakePortAudioError("Error opening InputStream: Unanticipated host error")
        self.kwargs = kwargs
        self.latency = 0.02
        self.started = self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def close(self) -> None:
        self.closed = True


class FakeSd:
    PortAudioError = FakePortAudioError

    def __init__(self, *, fail_open: bool = False, missing: bool = False) -> None:
        self.fail_open = fail_open
        self.missing = missing
        self.stream: FakeStream | None = None

    def query_devices(self, device: Any = None, kind: str | None = None) -> Any:
        if self.missing:
            raise ValueError("No input device matching 'nope'")
        return {"name": "Test Mic", "default_samplerate": 44100.0, "max_input_channels": 1}

    def InputStream(self, **kwargs: Any) -> FakeStream:  # noqa: N802 - mirrors sounddevice
        self.stream = FakeStream(self.fail_open, **kwargs)
        return self.stream


def test_opens_at_native_rate_with_10ms_blocks() -> None:
    sd = FakeSd()
    mic = MicSource(backend=sd, now_ns=lambda: 123)
    mic.start()
    assert sd.stream is not None and sd.stream.started
    kw = sd.stream.kwargs
    assert (kw["samplerate"], kw["channels"], kw["dtype"], kw["blocksize"]) == (44100, 1, "float32", 441)
    assert mic.latency_ns == 20_000_000 and mic.name == "Test Mic"
    mic.stop()
    assert sd.stream.closed


def test_callback_copies_data_and_counts_overflows() -> None:
    sd = FakeSd()
    mic = MicSource(backend=sd, now_ns=lambda: 7)
    mic.start()
    buf = np.ones((441, 1), dtype=np.float32)
    sd.stream.kwargs["callback"](buf, 441, None, FakeFlags(overflow=True))  # type: ignore[union-attr]
    buf[:] = 0  # sounddevice reuses its buffer
    [chunk] = mic.ring.drain()
    assert chunk.data.all() and chunk.t_callback_ns == 7
    assert mic.overflows == 1


def test_start_failure_maps_to_mic_unavailable_with_privacy_hint() -> None:
    mic = MicSource(backend=FakeSd(fail_open=True))
    with pytest.raises(MicUnavailableError) as exc:
        mic.start()
    assert exc.value.hint == MIC_PRIVACY_HINT


def test_unknown_device_is_a_clear_error() -> None:
    with pytest.raises(MicUnavailableError, match="not found"):
        MicSource("nope", backend=FakeSd(missing=True))
```

`tests/unit/capture/test_windows.py`:

```python
import threading
from typing import Any

import numpy as np
import pytest

from evra.capture.sources import NO_OUTPUT_HINT, LoopbackUnavailableError
from evra.capture.windows import DefaultOutputWatcher, LoopbackSource


class FakeStream:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.closed = False

    def get_input_latency(self) -> float:
        return 0.01

    def stop_stream(self) -> None: ...

    def close(self) -> None:
        self.closed = True


class FakePyAudio:
    def __init__(self, module: "FakePaModule") -> None:
        self._m = module
        module.instances += 1

    def get_default_wasapi_loopback(self) -> dict[str, Any]:
        if self._m.no_device:
            raise LookupError("no loopback device")
        return {"index": 7, "name": f"Speakers {self._m.instances} [Loopback]",
                "defaultSampleRate": 48000.0, "maxInputChannels": 2}

    def open(self, **kwargs: Any) -> FakeStream:
        self._m.stream = FakeStream(**kwargs)
        return self._m.stream

    def terminate(self) -> None:
        self._m.terminated += 1


class FakePaModule:
    paFloat32 = 1
    paContinue = 0

    def __init__(self, no_device: bool = False) -> None:
        self.no_device = no_device
        self.instances = 0
        self.terminated = 0
        self.stream: FakeStream | None = None

    def PyAudio(self) -> FakePyAudio:  # noqa: N802 - mirrors pyaudiowpatch
        return FakePyAudio(self)


def test_opens_default_loopback_at_native_format() -> None:
    pa = FakePaModule()
    src = LoopbackSource(backend=pa, now_ns=lambda: 5)
    src.start()
    kw = pa.stream.kwargs  # type: ignore[union-attr]
    assert (kw["rate"], kw["channels"], kw["frames_per_buffer"], kw["input_device_index"]) == (48000, 2, 480, 7)
    assert (src.native_rate, src.native_channels, src.latency_ns) == (48000, 2, 10_000_000)
    assert src.pads_silence is True


def test_callback_deinterleaves_float32() -> None:
    pa = FakePaModule()
    src = LoopbackSource(backend=pa, now_ns=lambda: 9)
    src.start()
    frames = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
    result = pa.stream.kwargs["stream_callback"](frames.tobytes(), 2, {}, 0)  # type: ignore[union-attr]
    assert result == (None, 0)
    [chunk] = src.ring.drain()
    np.testing.assert_array_equal(chunk.data, frames)


def test_reopen_reinitialises_portaudio_to_see_the_new_default() -> None:
    pa = FakePaModule()
    src = LoopbackSource(backend=pa)
    src.start()
    src.reopen()
    assert pa.terminated == 1 and pa.instances == 2
    assert src.name == "Speakers 2 [Loopback]"


def test_no_output_device_is_a_clear_error() -> None:
    with pytest.raises(LoopbackUnavailableError) as exc:
        LoopbackSource(backend=FakePaModule(no_device=True)).start()
    assert exc.value.hint == NO_OUTPUT_HINT


def test_watcher_reports_changes_only() -> None:
    ids = iter(["A", "A", "B", "B", "C"])
    seen: list[str | None] = []
    got_two = threading.Event()

    def on_change(new: str | None) -> None:
        seen.append(new)
        if len(seen) == 2:
            got_two.set()

    watcher = DefaultOutputWatcher(on_change, get_id=lambda: next(ids, "C"), interval_s=0.001)
    watcher.start()
    assert got_two.wait(2)
    watcher.stop()
    assert seen[:2] == ["B", "C"]
```

`tests/hardware/test_devices.py` (plus empty `tests/hardware/__init__.py`):

```python
import time

import pytest

from evra.audio.keys import KeyringKeyStore, new_meeting_key

pytestmark = pytest.mark.hardware


def test_real_microphone_delivers_chunks() -> None:
    from evra.capture.mic import MicSource

    mic = MicSource()
    mic.start()
    time.sleep(1.0)
    mic.stop()
    assert len(mic.ring.drain()) > 20


def test_real_loopback_opens() -> None:
    from evra.capture.windows import LoopbackSource

    src = LoopbackSource()
    src.start()
    time.sleep(1.0)
    src.stop()
    assert src.native_rate > 0 and src.native_channels > 0


def test_default_output_id_is_available() -> None:
    from evra.capture.windows import default_output_id

    assert default_output_id()


def test_credential_manager_round_trip() -> None:
    store = KeyringKeyStore(service="Evra-test")
    key = new_meeting_key()
    store.set("hw", key)
    try:
        assert store.get("hw") == key
    finally:
        store.delete("hw")
    assert store.get("hw") is None
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/unit/capture -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.capture.fake'` (and `evra.capture.mic`, `evra.capture.windows`).

- [ ] **Step 4: Implement**

`src/evra/capture/fake.py`:

```python
"""Replays audio like a real device: 10 ms chunks, real-time pacing, injected faults (§5.1)."""

from __future__ import annotations

import threading
import time
import wave
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np

from evra.audio.frames import NS, Float32Array
from evra.audio.ringbuffer import ChunkRing


@dataclass(frozen=True)
class FakeEvent:
    kind: Literal["silence", "dropout"]  # silence: zeros delivered; dropout: nothing delivered
    start_s: float
    duration_s: float

    def covers(self, t_s: float) -> bool:
        return self.start_s <= t_s < self.start_s + self.duration_s


class FakeSource:
    def __init__(
        self,
        audio: Float32Array,
        rate: int,
        *,
        name: str = "fake",
        events: Sequence[FakeEvent] = (),
        pads_silence: bool = False,
        now_ns: Callable[[], int] = time.monotonic_ns,
        sleep: Callable[[float], None] = time.sleep,
        latency_ns: int = 0,
    ) -> None:
        self.audio = audio if audio.ndim == 2 else audio[:, None]
        self.name = name
        self.native_rate = rate
        self.native_channels = int(self.audio.shape[1])
        self.latency_ns = latency_ns
        self.pads_silence = pads_silence
        self.ring = ChunkRing.for_duration(2.0, 0.01)
        self.finished = threading.Event()
        self._events = tuple(events)
        self._now = now_ns
        self._sleep = sleep
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @classmethod
    def from_wav(cls, path: Path, **kwargs: Any) -> FakeSource:
        with wave.open(str(path), "rb") as w:
            if w.getsampwidth() != 2:
                raise ValueError(f"{path.name}: only 16-bit PCM WAV is supported")
            channels, rate = w.getnchannels(), w.getframerate()
            raw = w.readframes(w.getnframes())
        pcm = np.frombuffer(raw, dtype="<i2").reshape(-1, channels)
        return cls((pcm / 32768.0).astype(np.float32), rate, name=path.name, **kwargs)

    def chunks(self) -> Iterator[tuple[float, Float32Array | None]]:
        step = self.native_rate // 100
        for start in range(0, len(self.audio), step):
            t_s = start / self.native_rate
            chunk: Float32Array | None = self.audio[start : start + step]
            for event in self._events:
                if event.covers(t_s):
                    chunk = None if event.kind == "dropout" else np.zeros_like(chunk)
            yield t_s, chunk

    def start(self) -> None:
        self._stop.clear()
        self.finished.clear()
        self._thread = threading.Thread(target=self._run, name=f"fake-{self.name}", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None and self._thread is not threading.current_thread():
            self._thread.join(timeout=5)
        self._thread = None

    def reopen(self) -> None:
        self.stop()
        self.start()

    def _run(self) -> None:
        t0 = self._now()
        for t_s, chunk in self.chunks():
            if self._stop.is_set():
                break
            if chunk is None:
                continue
            due = t0 + int((t_s + len(chunk) / self.native_rate) * NS)
            wait = due - self._now()
            if wait > 0:
                self._sleep(wait / NS)
            self.ring.put(chunk.copy(), self._now())
        self.finished.set()
```

`src/evra/capture/mic.py`:

```python
"""Microphone capture with sounddevice (BUILD.md §5.1)."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Any

from evra.audio.ringbuffer import ChunkRing
from evra.capture.sources import MIC_PRIVACY_HINT, MicUnavailableError


def _sounddevice() -> Any:
    import sounddevice

    return sounddevice


def list_input_devices(backend: Any = None) -> list[dict[str, object]]:
    sd = backend or _sounddevice()
    return [
        {"index": i, "name": d["name"], "rate": d["default_samplerate"]}
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]


class MicSource:
    pads_silence = False

    def __init__(
        self,
        device: int | str | None = None,
        *,
        backend: Any = None,
        now_ns: Callable[[], int] = time.monotonic_ns,
    ) -> None:
        self._sd = backend or _sounddevice()
        try:
            info = self._sd.query_devices(device, kind="input")
        except (ValueError, self._sd.PortAudioError) as exc:
            raise MicUnavailableError(f"microphone {device!r} not found", MIC_PRIVACY_HINT) from exc
        self._device = device
        self._now = now_ns
        self.name = str(info["name"])
        self.native_rate = int(info["default_samplerate"])
        self.native_channels = 1
        self.latency_ns = 0
        self.ring = ChunkRing.for_duration(2.0, 0.01)
        self.overflows = 0
        self._stream: Any = None

    def _callback(self, indata: Any, frames: int, time_info: Any, status: Any) -> None:
        if status.input_overflow:
            self.overflows += 1
        self.ring.put(indata.copy(), self._now())

    def start(self) -> None:
        try:
            stream = self._sd.InputStream(
                device=self._device,
                samplerate=self.native_rate,
                channels=1,
                dtype="float32",
                blocksize=self.native_rate // 100,
                callback=self._callback,
            )
            stream.start()
        except self._sd.PortAudioError as exc:
            raise MicUnavailableError(
                f"could not open microphone {self.name!r}", MIC_PRIVACY_HINT
            ) from exc
        self._stream = stream
        self.latency_ns = int(float(stream.latency) * 1e9)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None

    def reopen(self) -> None:
        self.stop()
        self.start()
```

`src/evra/capture/windows.py`:

```python
"""System-output capture on Windows: WASAPI loopback (PyAudioWPatch) and default-device watch.

PortAudio's device list is fixed once initialised, so a new default output is only visible
after re-initialising PyAudio (reopen). The Windows default endpoint id comes from the
Core Audio API via pycaw (D25).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Any

import numpy as np

from evra.audio.ringbuffer import ChunkRing
from evra.capture.sources import NO_OUTPUT_HINT, LoopbackUnavailableError


def _pyaudio() -> Any:
    import pyaudiowpatch

    return pyaudiowpatch


class LoopbackSource:
    pads_silence = True  # WASAPI loopback may deliver nothing while nothing plays

    def __init__(
        self, *, backend: Any = None, now_ns: Callable[[], int] = time.monotonic_ns
    ) -> None:
        self._pam = backend or _pyaudio()
        self._now = now_ns
        self.ring = ChunkRing.for_duration(2.0, 0.01)
        self.name = ""
        self.native_rate = 0
        self.native_channels = 0
        self.latency_ns = 0
        self._pa: Any = None
        self._stream: Any = None
        self._cb_channels = 1

    def start(self) -> None:
        pa = self._pam.PyAudio()
        try:
            loop = pa.get_default_wasapi_loopback()
        except (LookupError, OSError, ValueError) as exc:
            pa.terminate()
            raise LoopbackUnavailableError("no output device to capture from", NO_OUTPUT_HINT) from exc
        rate = int(loop["defaultSampleRate"])
        channels = int(loop["maxInputChannels"])
        self._cb_channels = channels
        stream = pa.open(
            format=self._pam.paFloat32,
            channels=channels,
            rate=rate,
            input=True,
            input_device_index=int(loop["index"]),
            frames_per_buffer=rate // 100,
            stream_callback=self._callback,
        )
        self._pa, self._stream = pa, stream
        self.name = str(loop["name"])
        self.native_rate, self.native_channels = rate, channels
        self.latency_ns = int(float(stream.get_input_latency()) * 1e9)

    def _callback(self, in_data: bytes, frame_count: int, time_info: Any, status: int) -> tuple[None, int]:
        data = np.frombuffer(in_data, dtype=np.float32).reshape(-1, self._cb_channels).copy()
        self.ring.put(data, self._now())
        return (None, self._pam.paContinue)

    def stop(self) -> None:
        if self._stream is not None:
            self._stream.stop_stream()
            self._stream.close()
            self._stream = None
        if self._pa is not None:
            self._pa.terminate()
            self._pa = None

    def reopen(self) -> None:
        self.stop()
        self.start()


def default_output_id() -> str | None:
    """Id of the current Windows default output endpoint, or None if there is none."""
    import comtypes
    from pycaw.pycaw import AudioUtilities

    comtypes.CoInitialize()
    try:
        return str(AudioUtilities.GetSpeakers().id)
    except Exception:  # no output endpoint, or a COM failure: treat as "none"
        return None
    finally:
        comtypes.CoUninitialize()


class DefaultOutputWatcher:
    """Polls the default output device every `interval_s` and reports changes (§5.1)."""

    def __init__(
        self,
        on_change: Callable[[str | None], None],
        *,
        get_id: Callable[[], str | None] = default_output_id,
        interval_s: float = 2.0,
    ) -> None:
        self._on_change = on_change
        self._get_id = get_id
        self._interval = interval_s
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last: str | None = None

    def start(self) -> None:
        self._last = self._get_id()
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="output-watcher", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None

    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            current = self._get_id()
            if current != self._last:
                self._last = current
                self._on_change(current)
```

- [ ] **Step 5: Run unit tests, then the hardware tests on the dev machine**

Run: `uv run pytest -q`
Expected: all pass (hardware tests deselected).

Run: `uv run pytest -m hardware -v`
Expected: 4 passed on the dev machine: the mic delivers chunks, the loopback opens, a default output id exists, and the Credential Manager round-trip works. If a test fails because of a real device issue (e.g. mic privacy blocked), record it in `PROGRESS.md` and continue. The CLI surfaces it in Task 9.

- [ ] **Step 6: Decisions, licence register, commit, push**

Append to `DECISIONS.md`:

```markdown

## D25 — Default-output detection via pycaw (Core Audio) (2026-09-24)
- **Context:** BUILD.md §5.1 requires reopening loopback when the default output changes (polled every 2 s).
- **Evidence:** PortAudio (inside PyAudioWPatch) fixes its device list at initialisation, so it cannot see a new default device while running. pycaw (MIT; comtypes MIT) returns the current endpoint id from the Windows Core Audio API; verified on the dev machine.
- **Decision:** `DefaultOutputWatcher` polls `pycaw.AudioUtilities.GetSpeakers().id`; on change `LoopbackSource.reopen()` re-initialises PyAudio and the pipeline records a `device_change` gap.
- **Consequences:** two small Windows-only dependencies; macOS/Linux get their own watchers in their milestone.
```

In `BUILD.md` §5.1 "Device changes", append ` The default endpoint id is read via pycaw (D25).` Add D25 to the §2 table: `| D25 | Output-device watch | pycaw Core Audio endpoint id, polled every 2 s | 2026-09-24 |`.

Run `uv run python tools/license_gate.py --write-register`, then `uv run python tools/check.py`. It must be all PASS. Append to `PROGRESS.md`: `- Task 7: FakeSource, MicSource (sounddevice), LoopbackSource (PyAudioWPatch), DefaultOutputWatcher (pycaw, D25); hardware tests <N>/4 on the dev machine.`

```powershell
git add pyproject.toml uv.lock src/evra/capture tests/unit/capture tests/hardware THIRD_PARTY_LICENSES.md DECISIONS.md BUILD.md PROGRESS.md
git commit -m "feat: microphone, loopback and fake capture sources with output-device watch" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 8: CaptureSession and the health report

**Files:**
- Create: `src/evra/capture/session.py`, `tests/unit/capture/test_session.py`

**Interfaces:**
- Consumes:
  - From Task 5: `CapturePipeline`, `ChannelStats`, `AudioSource`, `CaptureError`.
  - From Task 7: `DefaultOutputWatcher`.
- Produces:
  - `ChannelHealth` (frozen) = every `ChannelStats` field, plus `device: str` and `gaps: list[dict]` in ms (`start_ms`, `duration_ms`, `cause`)
  - `CaptureHealth` (frozen) with fields `channels: dict[str, ChannelHealth]` (keys `"mic"`, `"system"`), `inter_channel_drift_ms: float`, `device_changes: int`, `hints: list[str]`, `ok: bool`
  - `WatcherFactory = Callable[[Callable[[str | None], None]], Any]` (returns an object with `start`/`stop`)
  - `CaptureSession(mic: AudioSource, system: AudioSource, *, watcher_factory: WatcherFactory | None = None, now_ns=..., tick_s=0.01)` with methods `.start(on_frames)`, `.stop() -> CaptureHealth`, `.health() -> CaptureHealth`, and attribute `.device_changes`
  - `DRIFT_LIMIT_MS = 30.0`

- [ ] **Step 1: Write failing tests** `tests/unit/capture/test_session.py`

```python
import time
from collections.abc import Callable

import numpy as np
import pytest

from evra.audio.frames import MIC, SYSTEM, Frames
from evra.capture.fake import FakeEvent, FakeSource
from evra.capture.session import CaptureSession
from evra.capture.sources import CaptureError


def _sine(rate: int, seconds: float, channels: int) -> np.ndarray:
    t = np.arange(int(rate * seconds)) / rate
    mono = (0.3 * np.sin(2 * np.pi * 300 * t)).astype(np.float32)
    return np.repeat(mono[:, None], channels, axis=1)


def _sources(seconds: float = 1.0, events: tuple[FakeEvent, ...] = ()) -> tuple[FakeSource, FakeSource]:
    mic = FakeSource(_sine(44_100, seconds, 1), 44_100, name="fake mic")
    system = FakeSource(_sine(48_000, seconds, 2), 48_000, name="fake out", pads_silence=True, events=events)
    return mic, system


def _run(session: CaptureSession, mic: FakeSource, system: FakeSource) -> tuple[list[Frames], object]:
    frames: list[Frames] = []
    session.start(frames.append)
    assert mic.finished.wait(5) and system.finished.wait(5)
    time.sleep(0.05)
    return frames, session.stop()


def test_real_time_run_produces_aligned_channels_and_a_healthy_report() -> None:
    mic, system = _sources(1.0)
    frames, health = _run(CaptureSession(mic, system), mic, system)
    mic_n = sum(f.channel == MIC for f in frames)
    sys_n = sum(f.channel == SYSTEM for f in frames)
    assert mic_n >= 95 and abs(mic_n - sys_n) <= 3
    assert health.ok  # type: ignore[attr-defined]
    assert health.channels["mic"].device == "fake mic"  # type: ignore[attr-defined]
    assert health.inter_channel_drift_ms < 30  # type: ignore[attr-defined]
    assert -14.5 < health.channels["system"].rms_dbfs < -12.5  # 0.3 sine ≈ −13.5 dBFS  # type: ignore[attr-defined]


def test_dropout_makes_the_report_not_ok() -> None:
    mic, system = _sources(1.0, (FakeEvent("dropout", 0.3, 0.3),))
    system.pads_silence = False  # a mic-like source: a hole is a dropout, not silence
    _, health = _run(CaptureSession(mic, system), mic, system)
    gaps = health.channels["system"].gaps  # type: ignore[attr-defined]
    assert any(g["cause"] == "dropout" for g in gaps)
    assert not health.ok  # type: ignore[attr-defined]


def test_output_change_reopens_loopback_and_is_counted() -> None:
    mic, system = _sources(1.0)
    callbacks: list[Callable[[str | None], None]] = []

    class ManualWatcher:
        def __init__(self, on_change: Callable[[str | None], None]) -> None:
            callbacks.append(on_change)

        def start(self) -> None: ...

        def stop(self) -> None: ...

    session = CaptureSession(mic, system, watcher_factory=ManualWatcher)
    frames: list[Frames] = []
    session.start(frames.append)
    time.sleep(0.2)
    callbacks[0]("new-device")
    assert mic.finished.wait(5) and system.finished.wait(5)
    health = session.stop()
    assert health.device_changes == 1


def test_silent_mic_produces_a_hint() -> None:
    mic = FakeSource(np.zeros((44_100, 1), dtype=np.float32), 44_100, name="muted")
    _, system = _sources(1.0)
    _, health = _run(CaptureSession(mic, system), mic, system)
    assert any("icrophone" in h for h in health.hints)  # type: ignore[attr-defined]


def test_start_failure_of_system_stops_the_mic() -> None:
    mic, _ = _sources(0.5)

    class Broken(FakeSource):
        def start(self) -> None:
            raise CaptureError("no output", "plug something in")

    broken = Broken(np.zeros((480, 2), dtype=np.float32), 48_000)
    session = CaptureSession(mic, broken)
    with pytest.raises(CaptureError):
        session.start(lambda f: None)
    assert mic._thread is None  # noqa: SLF001 - mic was stopped again
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/capture/test_session.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.capture.session'`.

- [ ] **Step 3: Implement** `src/evra/capture/session.py`

```python
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
        self.device_changes = 0

    def start(self, on_frames: Callable[[Frames], None]) -> None:
        mic, system = self._sources[MIC], self._sources[SYSTEM]
        mic.start()
        try:
            system.start()
        except CaptureError:
            mic.stop()
            raise
        self._pipeline = CapturePipeline(self._sources, on_frames, start_ns=self._now(), now_ns=self._now)
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
        if self._pipeline is not None:
            self._pipeline.flush()
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
            hints.append("Microphone looks silent: wrong device, muted, or blocked in privacy settings?")
        if system.seconds > 0 and system.padded_ms >= system.seconds * 1000 * 0.95:
            hints.append("No system audio arrived: nothing playing, or a different output device?")
        problems = (
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
            self._pipeline.step()

    def _on_output_changed(self, device_id: str | None) -> None:
        self.device_changes += 1
        log.info("output_device_changed", has_device=device_id is not None)
        if self._pipeline is None:
            return
        try:
            self._pipeline.swap_source(SYSTEM, self._sources[SYSTEM].reopen)
        except CaptureError as exc:
            log.warning("loopback_reopen_failed", hint=exc.hint)
```

- [ ] **Step 4: Run tests and tools**, then commit and push

Run: `uv run python tools/check.py`
Expected: all PASS. Append to `PROGRESS.md`: `- Task 8: CaptureSession — sources + pipeline thread + output watcher; CaptureHealth with drift, drops, gaps, hints.`

```powershell
git add src/evra/capture/session.py tests/unit/capture/test_session.py PROGRESS.md
git commit -m "feat: capture session with health report" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 9: `evra capture-test` CLI

**Files:**
- Create: `src/evra/capture/capture_test.py`, `tests/integration/__init__.py`, `tests/integration/test_capture_test.py`
- Modify: `src/evra/__main__.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Consumes:
  - From Task 2 (M0): `AppPaths`, `resolve_paths`, `configure_logging`.
  - From Task 6: `SpillWriter`, `read_channel`, `KeyStore`, `KeyringKeyStore`, `new_meeting_key`.
  - From Task 8: `CaptureSession`, `CaptureHealth`.
- Produces:
  - `write_wav(path: Path, pcm: Int16Array, rate: int = 16_000) -> None`
  - `run_capture_test(session, *, seconds: float, paths: AppPaths, keys: KeyStore, out_dir: Path, meeting_id: str, sleep: Callable[[float], None] = time.sleep) -> CaptureHealth`
  - `format_summary(health: CaptureHealth, seconds: float, out_dir: Path) -> str`
  - `capture_test_command(args: argparse.Namespace, paths: AppPaths, keys: KeyStore | None = None) -> int`
  - CLI: `evra capture-test SECONDS [--mic DEVICE] [--out DIR] [--fake-mic WAV --fake-system WAV] [--list-devices] [--data-dir PATH]`, with exit codes 0 = PASS, 1 = FAIL, 2 = capture error

- [ ] **Step 1: Write failing tests**

`tests/integration/test_capture_test.py` (plus empty `tests/integration/__init__.py`):

```python
import json
import wave
from pathlib import Path

import numpy as np
import pytest

from evra.__main__ import main
from evra.audio.keys import MemoryKeyStore
from evra.capture.capture_test import run_capture_test, write_wav
from evra.capture.fake import FakeSource
from evra.capture.session import CaptureSession
from evra.paths import AppPaths


def _wav(path: Path, rate: int, channels: int, seconds: float) -> Path:
    t = np.arange(int(rate * seconds)) / rate
    mono = (0.3 * 32767 * np.sin(2 * np.pi * 300 * t)).astype(np.int16)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.repeat(mono[:, None], channels, axis=1).tobytes())
    return path


def test_run_capture_test_writes_wavs_and_health_and_cleans_up(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path / "home")
    paths.ensure()
    keys = MemoryKeyStore()
    mic = FakeSource.from_wav(_wav(tmp_path / "m.wav", 44_100, 1, 1.2))
    system = FakeSource.from_wav(_wav(tmp_path / "s.wav", 48_000, 2, 1.2), pads_silence=True)
    out = tmp_path / "out"
    health = run_capture_test(
        CaptureSession(mic, system), seconds=1.0, paths=paths, keys=keys, out_dir=out, meeting_id="t1"
    )
    assert health.ok
    for name in ("mic.wav", "system.wav"):
        with wave.open(str(out / name), "rb") as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16_000, 1, 2)
            assert w.getnframes() >= 15_000
    report = json.loads((out / "health.json").read_text(encoding="utf-8"))
    assert report["ok"] is True and "mic" in report["channels"]
    assert not (paths.spill_dir / "t1").exists()  # temporary audio deleted
    assert keys.get("t1") is None  # key deleted


def test_cli_with_fake_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("evra.capture.capture_test.KeyringKeyStore", MemoryKeyStore)
    mic = _wav(tmp_path / "m.wav", 16_000, 1, 1.5)
    system = _wav(tmp_path / "s.wav", 48_000, 2, 1.5)
    out = tmp_path / "out"
    code = main([
        "capture-test", "1.0", "--fake-mic", str(mic), "--fake-system", str(system),
        "--data-dir", str(tmp_path / "home"), "--out", str(out),
    ])
    text = capsys.readouterr().out
    assert code == 0 and "PASS" in text
    assert (out / "health.json").exists()


def test_cli_reports_capture_error_with_hint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    from evra.capture import capture_test
    from evra.capture.sources import MIC_PRIVACY_HINT, MicUnavailableError

    def broken_mic(*args: object, **kwargs: object) -> None:
        raise MicUnavailableError("could not open microphone 'X'", MIC_PRIVACY_HINT)

    monkeypatch.setattr(capture_test, "MicSource", broken_mic)
    code = main(["capture-test", "1", "--data-dir", str(tmp_path / "home")])
    err = capsys.readouterr().err
    assert code == 2
    assert "could not open microphone" in err and "ms-settings:privacy-microphone" in err


def test_write_wav_round_trip(tmp_path: Path) -> None:
    pcm = np.arange(-100, 100, dtype=np.int16)
    write_wav(tmp_path / "x.wav", pcm)
    with wave.open(str(tmp_path / "x.wav"), "rb") as w:
        assert np.array_equal(np.frombuffer(w.readframes(200), dtype="<i2"), pcm)
```

Add to `tests/unit/test_cli.py`:

```python
def test_capture_test_subcommand_is_registered() -> None:
    from evra.__main__ import build_parser

    args = build_parser().parse_args(["capture-test", "60", "--mic", "2"])
    assert args.command == "capture-test" and args.seconds == 60.0 and args.mic == "2"


def test_capture_test_rejects_non_positive_seconds() -> None:
    from evra.__main__ import build_parser

    with pytest.raises(SystemExit):
        build_parser().parse_args(["capture-test", "0"])
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration tests/unit/test_cli.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.capture.capture_test'`; the CLI tests fail with `invalid choice: 'capture-test'`.

- [ ] **Step 3: Implement** `src/evra/capture/capture_test.py`

```python
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
    lines = [f"Evra capture test: {seconds:.1f} s"]
    for label, ch in health.channels.items():
        lines.append(
            f"  {label:<7} {ch.device[:40]:<40} {ch.native_rate} Hz x{ch.native_channels}"
            f"  rms {ch.rms_dbfs:.1f} dBFS  peak {ch.peak_dbfs:.1f}"
            f"  drops {ch.dropped_chunks}  corrections {ch.corrections}  drift {ch.drift_ms:+.1f} ms"
            f"  gaps {len(ch.gaps)}"
        )
    lines.append(
        f"  inter-channel drift: {health.inter_channel_drift_ms:.1f} ms (limit {DRIFT_LIMIT_MS:.0f})"
        f"  device changes: {health.device_changes}"
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
    return CaptureSession(
        MicSource(device), LoopbackSource(), watcher_factory=DefaultOutputWatcher
    )


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
```

In `src/evra/__main__.py`, add a positive-float helper and the subcommand inside `build_parser()` (after the `run` parser):

```python
def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("seconds must be > 0")
    return seconds
```

```python
    test = commands.add_parser("capture-test", help="record both channels, write WAVs + health")
    test.add_argument("seconds", type=_positive_seconds, help="how long to record")
    test.add_argument("--mic", default=None, help="microphone index or name (default: system default)")
    test.add_argument("--out", default=None, help="output folder (default: <data>/capture-test/<time>)")
    test.add_argument("--fake-mic", default=None, help="replay this WAV as the microphone")
    test.add_argument("--fake-system", default=None, help="replay this WAV as system audio")
    test.add_argument("--list-devices", action="store_true", help="list microphones and exit")
    test.add_argument("--data-dir", type=Path, default=None, help="keep all app data here")
```

And in `main()`, before `parser.print_help()`:

```python
    if args.command == "capture-test":
        from evra.capture.capture_test import capture_test_command
        from evra.paths import resolve_paths

        return capture_test_command(args, resolve_paths(args.data_dir))
```

`--list-devices` still requires the `seconds` positional; document `evra capture-test 1 --list-devices` in `README.md` and `CLAUDE.md`.

- [ ] **Step 4: Run tests and tools**

Run: `uv run python tools/check.py`
Expected: all PASS.

- [ ] **Step 5: Real run on the dev machine**

Run: `uv run evra capture-test 10`
Expected:
- A summary with both devices.
- `result: PASS` (0 drops, inter-channel drift < 30 ms).
- Two WAVs plus `health.json` under `.data\data\capture-test\<time>\`.
- The spill folder and the Credential Manager entry are deleted.

- [ ] **Step 6: Commit and push**

Append to `PROGRESS.md`: `- Task 9: \`evra capture-test SECONDS\` — two WAVs + health.json; spill + key cleaned up; dev-machine 10 s run: <PASS|FAIL + numbers>.` Update the `CLAUDE.md` Commands section with `- Capture check: \`uv run evra capture-test 60\` (list mics: \`uv run evra capture-test 1 --list-devices\`)`.

```powershell
git add src/evra/capture/capture_test.py src/evra/__main__.py tests/integration tests/unit/test_cli.py PROGRESS.md CLAUDE.md README.md
git commit -m "feat: evra capture-test writes both channels and a health report" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 10: 60-minute soak, HC1, and wrap-up

**Files:**
- Modify: `PROGRESS.md`, `BUILD.md` §0 build status

- [ ] **Step 1: Start the 60-minute soak in the background**

Run (background, ~61 min): `uv run evra capture-test 3600 --out .data/data/capture-test/soak-60`
Expected at the end: `result: PASS`, inter-channel drift < 30 ms, `drops 0` on both channels. Record the numbers (corrections, drift, gaps, CPU if observed) in `PROGRESS.md`.

- [ ] **Step 2: While it runs, request HUMAN CHECKPOINT HC1**

```
======== HUMAN CHECKPOINT HC1: two-channel capture on your machine ========
Why: only real hardware proves the mic and system audio line up and sound right.
Steps:
  1. Wait until the 60-minute soak test finishes (it uses the audio devices).
  2. Headphones: play a YouTube video, run `uv run evra capture-test 60`, and talk over the video.
  3. Laptop speakers: switch output to the laptop speakers and repeat step 2.
  4. For each run, open the folder it prints and listen to mic.wav and system.wav.
Expected result: both runs print "result: PASS"; mic.wav has your voice, system.wav has the video.
  (On speakers the mic will also hear the video: that is expected until echo cancellation in M2.)
Paste back: both printed summaries + "WAVs sound right" (or what sounds wrong).
==========================================================================
```

- [ ] **Step 3: Record results and finish**

When the soak and HC1 results are in:
- Add them to `PROGRESS.md`.
- Add `Build status: Phase 1 M1 done (tag p1-m1-done).` to `BUILD.md` §0.
- Commit and push.
- After the final whole-branch review and its fixes, tag `p1-m1-done` and push the tag.

If HC1 shows a real problem (e.g. Bluetooth hands-free mode, wrong device, drift), fix it with a failing test first, rerun, and record it in `DECISIONS.md` when it changes a decision.
