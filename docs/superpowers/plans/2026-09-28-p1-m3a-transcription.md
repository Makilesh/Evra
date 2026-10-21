# Phase 1 · M3a Transcription Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record a 1:1 call and watch it become a stored, timestamped transcript. Voice detection cuts speech segments from both channels, and a separate ASR worker process transcribes each one with Parakeet. The results land in SQLite as utterances labelled "You" (mic) and "Them" (system). This is proven with `evra transcribe WAV` and `evra record SECONDS`.

**Architecture:**
- `models.yaml` catalogues the models; `modelstore.py` downloads them on first use (resumable, SHA-256 verified) into `<data>/models/<id>/`.
- `SpeechSegmenter` wraps sherpa-onnx Silero VAD per channel and adds a 300 ms pre-roll.
- A generic `Worker` (spawned `multiprocessing` child, typed request/response over a pipe, futures, lazy start, idle stop, restart after a crash) hosts the Parakeet engine (D6). `AsrClient` is the app-side handle.
- `LiveTranscriber` queues segments from the capture thread, transcribes them in order on its own thread, and writes utterances through `MeetingStore` on its own DB connection.

**Tech Stack:** sherpa-onnx 1.13.8 (VAD + Parakeet TDT 0.6B v3 int8 on CPU), multiprocessing (spawn), sqlite3, PyYAML, urllib (downloads).

**Spec:** `BUILD.md` §4 (workers), §4.5 (models), §5.4 (VAD), §6.1–6.2 (ASR, live pass), §8.1 (1:1 mode), §8.2 (schema), §10 row M3.

## Global Constraints

- Everything in the M0/M1 plans' Global Constraints still applies:
  - Python 3.12 managed by uv, `mypy --strict`, and files under about 500 lines.
  - No network listener.
  - D23: data lives in `.data/`.
  - D22: `tools/check.py` must pass, then commit and `git push` on branch **`one-on-one-notes`**.
- **Model files** live under `AppPaths.models_dir` (`.data/data/models` from a source checkout). They are never committed, and each has a `models.yaml` entry with its SHA-256, licence and attribution.
- **Model downloads:**
  - They are the only new outbound traffic, and happen only to the URLs in `models.yaml`.
  - A partial download resumes, and a checksum mismatch is fatal.
  - Only the listed files are extracted from an archive.
- **Workers:**
  - Worker processes use the `spawn` start method, and the factory is named as `"module:function"`.
  - Workers do not log.
  - Errors cross the pipe as the **exception type name only**, never a message, because messages can carry content.
- **Content never reaches logs above DEBUG.** Transcript text prints only to the user's own console, from `evra transcribe` / `evra record`.
- **1:1 labels (D18):** channel 0 (mic) = "You", channel 1 (system) = "Them". There is no diarization in M3a.
- **Parakeet settings:** CPU (`provider="cpu"`), `num_threads=4`, `model_type="nemo_transducer"`, loaded with `sherpa_onnx.OfflineRecognizer.from_transducer`. These were verified by a spike on 2026-09-28.
- **VAD** (BUILD.md §5.4): threshold 0.5, min speech 0.25 s, min silence 0.4 s, max speech 20 s, pre-roll 300 ms, and a 512-sample window at 16 kHz.
- **Tests:**
  - Tests that need downloaded models use `@requires_models` and skip when the models are missing; CI never downloads models.
  - Tests that need real audio devices keep the `hardware` marker.

## Review Focus

1. **The ASR worker crashes or hangs mid-meeting** (out of memory, a bad model file). Capture must continue, the segment is retried once and then counted as failed, and the worker restarts on the next request. → Task 4 `test_crash_fails_pending_and_next_call_restarts`, Task 7 `test_failed_segment_is_counted_and_later_segments_still_work`.
2. **A model download is interrupted, corrupted or partial.** It must resume, a checksum mismatch must be rejected, and a half-extracted model must never be used. → Task 1 `test_checksum_mismatch_is_fatal_and_removes_the_file`, `test_http_fetch_resumes_a_partial_download`.
3. **Continuous speech longer than 20 s** (VAD cuts it). Every piece must be transcribed and stored in order. → Task 7 `test_segments_are_stored_in_order_with_absolute_times`.
4. **Ctrl+C during `evra record`.** The meeting is finished, queued segments are transcribed, devices are closed, and there's no traceback. → Task 9 `test_interrupt_still_finishes_the_meeting`.
5. **A recording with no speech at all.** Zero utterances, the meeting still ends `ready`, and the summary says so. → Task 9 `test_silence_only_recording_says_no_speech`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `models.yaml` | + `silero-vad`, `parakeet-tdt-0.6b-v3-int8` |
| `src/evra/modelstore.py` | `ModelSpec`, `load_catalog`, `ensure_model`, `http_fetch`, `is_ready` |
| `src/evra/asr/engine.py` | `Word`, `Segment`, `AsrEngine`, `segment_from_dict` |
| `src/evra/asr/parakeet.py` | `ParakeetEngine`, `words_from_tokens`, `PARAKEET_ID` |
| `src/evra/audio/vad.py` | `SpeechSegment`, `VadBackend`, `silero_vad`, `SpeechSegmenter` |
| `src/evra/workers/protocol.py` | `Request`, `Response`, `serve`, `worker_main`, errors |
| `src/evra/workers/supervisor.py` | `Worker` (spawn, futures, crash restart, idle stop) |
| `src/evra/workers/asr.py` | `make_asr_handler` (in the worker), `AsrClient` (in the app) |
| `src/evra/store/meetings.py` | `MeetingStore`, `Utterance` |
| `src/evra/transcribe/live.py` | `LiveTranscriber` |
| `src/evra/transcribe/cli.py` | `transcribe_file`, `transcribe_command`, `models_command` |
| `src/evra/transcribe/record.py` | `run_recording`, `record_command` |
| `src/evra/__main__.py` | + `models`, `transcribe`, `record` subcommands |
| `tests/conftest.py` | + `requires_models` marker helper |
| `tests/unit/...`, `tests/integration/...` | tests per task |

---

### Task 1: Model catalogue and downloader

**Files:**
- Create: `src/evra/modelstore.py`, `tests/unit/test_modelstore.py`
- Modify: `models.yaml`, `pyproject.toml` (pyyaml runtime dependency; a `sherpa_onnx` mypy override), `tests/conftest.py`

**Interfaces:**
- Produces:
  - `ModelFile(name: str, sha256: str)` and `ModelSpec(id, url, archive: str | None, licence, files: tuple[ModelFile, ...], size_mb, attribution)`, with `.directory(models_dir) -> Path`
  - `ModelError`
  - `CATALOG: Path`
  - `load_catalog(path: Path = CATALOG) -> dict[str, ModelSpec]`
  - `sha256_of(path: Path) -> str`
  - `is_ready(spec, models_dir) -> bool`
  - `Fetcher = Callable[[str, Path], None]` and `http_fetch(url: str, dest: Path) -> None`
  - `ensure_model(spec, models_dir, fetch: Fetcher = http_fetch) -> Path`
  - Test helper `requires_models(*ids)` (a pytest skip marker)

- [ ] **Step 1: Dependencies and config**

```powershell
uv add pyyaml
```

In `pyproject.toml`, add `"sherpa_onnx", "sherpa_onnx.*"` to the second mypy override's `module` list. `sherpa-onnx` itself is added in Task 2.

- [ ] **Step 2: Catalogue entries** (append to `models.yaml` under `models:`, replacing `models: []`)

```yaml
models:
  - id: silero-vad
    source: {type: url, url: https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/silero_vad.onnx}
    licence: MIT
    files:
      - {name: silero_vad.onnx, sha256: 9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6}
    size_mb: 1
    loaded: during_meeting
    attribution: "Voice activity detection uses Silero VAD (MIT)."
  - id: parakeet-tdt-0.6b-v3-int8
    source:
      type: url
      url: https://github.com/k2-fsa/sherpa-onnx/releases/download/asr-models/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8.tar.bz2
      archive: tar.bz2
    licence: CC-BY-4.0
    files:
      - {name: encoder.int8.onnx, sha256: acfc2b4456377e15d04f0243af540b7fe7c992f8d898d751cf134c3a55fd2247}
      - {name: decoder.int8.onnx, sha256: 179e50c43d1a9de79c8a24149a2f9bac6eb5981823f2a2ed88d655b24248db4e}
      - {name: joiner.int8.onnx, sha256: 3164c13fc2821009440d20fcb5fdc78bff28b4db2f8d0f0b329101719c0948b3}
      - {name: tokens.txt, sha256: d58544679ea4bc6ac563d1f545eb7d474bd6cfa467f0a6e2c1dc1c7d37e3c35d}
    size_mb: 670
    loaded: during_meeting
    attribution: "Speech recognition uses NVIDIA Parakeet TDT 0.6B v3 (CC BY 4.0), converted to ONNX int8 by the sherpa-onnx project."
```

(The hashes were computed from the official release files on 2026-09-28.)

- [ ] **Step 3: Write failing tests** `tests/unit/test_modelstore.py`

```python
import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from evra import modelstore
from evra.modelstore import (
    CATALOG,
    ModelError,
    ModelFile,
    ModelSpec,
    ensure_model,
    http_fetch,
    is_ready,
    load_catalog,
)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _archive(files: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:bz2") as tar:
        for name, data in {**files, "model-dir/test_wavs/x.wav": b"skip me"}.items():
            info = tarfile.TarInfo(name if "/" in name else f"model-dir/{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _spec(files: dict[str, bytes], archive: str | None) -> ModelSpec:
    return ModelSpec(
        id="m", url="https://example/m", archive=archive, licence="MIT",
        files=tuple(ModelFile(n, _sha(d)) for n, d in files.items()), size_mb=1, attribution="",
    )


def test_real_catalogue_parses() -> None:
    catalogue = load_catalog(CATALOG)
    assert {"silero-vad", "parakeet-tdt-0.6b-v3-int8"} <= catalogue.keys()
    assert catalogue["parakeet-tdt-0.6b-v3-int8"].archive == "tar.bz2"


def test_archive_is_downloaded_extracted_verified_and_marked(tmp_path: Path) -> None:
    files = {"a.onnx": b"AAA", "tokens.txt": b"t"}
    calls: list[str] = []

    def fetch(url: str, dest: Path) -> None:
        calls.append(url)
        dest.write_bytes(_archive(files))

    spec = _spec(files, "tar.bz2")
    target = ensure_model(spec, tmp_path, fetch)
    assert (target / "a.onnx").read_bytes() == b"AAA"
    assert not (target / "x.wav").exists()  # only listed files are extracted
    assert is_ready(spec, tmp_path)
    assert not list(tmp_path.glob("*.download"))
    ensure_model(spec, tmp_path, fetch)
    assert len(calls) == 1  # second call: nothing to do


def test_single_file_model(tmp_path: Path) -> None:
    spec = _spec({"vad.onnx": b"VAD"}, None)
    target = ensure_model(spec, tmp_path, lambda url, dest: dest.write_bytes(b"VAD"))
    assert (target / "vad.onnx").read_bytes() == b"VAD"


def test_existing_correct_files_are_adopted_without_download(tmp_path: Path) -> None:
    spec = _spec({"vad.onnx": b"VAD"}, None)
    (tmp_path / "m").mkdir()
    (tmp_path / "m" / "vad.onnx").write_bytes(b"VAD")

    def no_fetch(url: str, dest: Path) -> None:
        raise AssertionError("should not download")

    ensure_model(spec, tmp_path, no_fetch)
    assert is_ready(spec, tmp_path)


def test_checksum_mismatch_is_fatal_and_removes_the_file(tmp_path: Path) -> None:
    spec = _spec({"vad.onnx": b"VAD"}, None)
    with pytest.raises(ModelError, match="checksum"):
        ensure_model(spec, tmp_path, lambda url, dest: dest.write_bytes(b"EVIL"))
    assert not (tmp_path / "m" / "vad.onnx").exists()
    assert not is_ready(spec, tmp_path)


def test_http_fetch_resumes_a_partial_download(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dest = tmp_path / "file.bin"
    (tmp_path / "file.bin.part").write_bytes(b"hello ")
    seen: dict[str, str] = {}

    class FakeResponse(io.BytesIO):
        status = 206

        def __enter__(self) -> "FakeResponse":
            return self

        def __exit__(self, *args: object) -> None: ...

    def fake_urlopen(request: object, timeout: float) -> FakeResponse:
        seen["range"] = request.get_header("Range")  # type: ignore[attr-defined]
        return FakeResponse(b"world")

    monkeypatch.setattr(modelstore.urllib.request, "urlopen", fake_urlopen)
    http_fetch("https://example/file", dest)
    assert seen["range"] == "bytes=6-"
    assert dest.read_bytes() == b"hello world"
```

Add to `tests/conftest.py`:

```python
from evra.modelstore import is_ready, load_catalog
from evra.paths import resolve_paths


def requires_models(*ids: str) -> pytest.MarkDecorator:
    """Skip unless these catalogue models are downloaded (run `uv run evra models --download`)."""
    catalogue = load_catalog()
    models_dir = resolve_paths().models_dir
    missing = [i for i in ids if not is_ready(catalogue[i], models_dir)]
    return pytest.mark.skipif(bool(missing), reason=f"models not downloaded: {missing}")
```

- [ ] **Step 4: Run to verify failure**

Run: `uv run pytest tests/unit/test_modelstore.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'evra.modelstore'`.

- [ ] **Step 5: Implement** `src/evra/modelstore.py`

```python
"""Model catalogue (models.yaml) and first-use downloads (BUILD.md §4.5).

Downloads resume, every file is checked against its SHA-256, and only the listed files are
taken out of an archive. A `.verified` marker records a model that passed its checks.
"""

from __future__ import annotations

import hashlib
import shutil
import tarfile
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import yaml

from evra.paths import REPO_ROOT

CATALOG = REPO_ROOT / "models.yaml"
MARKER = ".verified"
Fetcher = Callable[[str, Path], None]


class ModelError(RuntimeError):
    pass


@dataclass(frozen=True)
class ModelFile:
    name: str
    sha256: str


@dataclass(frozen=True)
class ModelSpec:
    id: str
    url: str
    archive: str | None
    licence: str
    files: tuple[ModelFile, ...]
    size_mb: int
    attribution: str

    def directory(self, models_dir: Path) -> Path:
        return models_dir / self.id


def load_catalog(path: Path = CATALOG) -> dict[str, ModelSpec]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    specs: dict[str, ModelSpec] = {}
    for m in raw.get("models") or []:
        source = m["source"]
        specs[m["id"]] = ModelSpec(
            id=m["id"],
            url=source["url"],
            archive=source.get("archive"),
            licence=m["licence"],
            files=tuple(ModelFile(f["name"], f["sha256"]) for f in m["files"]),
            size_mb=int(m.get("size_mb", 0)),
            attribution=m.get("attribution", ""),
        )
    return specs


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def is_ready(spec: ModelSpec, models_dir: Path) -> bool:
    target = spec.directory(models_dir)
    return (target / MARKER).is_file() and all((target / f.name).is_file() for f in spec.files)


def http_fetch(url: str, dest: Path) -> None:
    """Download `url` to `dest`, continuing a partial `.part` file with an HTTP Range request."""
    part = dest.with_name(dest.name + ".part")
    have = part.stat().st_size if part.exists() else 0
    headers = {"Range": f"bytes={have}-"} if have else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        mode = "ab" if have and response.status == 206 else "wb"
        with part.open(mode) as out:
            shutil.copyfileobj(response, out, 1 << 20)
    part.replace(dest)


def _verify(spec: ModelSpec, target: Path) -> bool:
    return all(
        (target / f.name).is_file() and sha256_of(target / f.name) == f.sha256 for f in spec.files
    )


def _extract(archive: Path, spec: ModelSpec, target: Path) -> None:
    wanted = {f.name for f in spec.files}
    with tarfile.open(archive, mode="r:bz2") as tar:
        for member in tar.getmembers():
            name = Path(member.name).name
            if member.isfile() and name in wanted:
                source = tar.extractfile(member)
                if source is None:
                    continue
                with source, (target / name).open("wb") as out:
                    shutil.copyfileobj(source, out, 1 << 20)


def ensure_model(spec: ModelSpec, models_dir: Path, fetch: Fetcher = http_fetch) -> Path:
    """Make sure the model is on disk and verified; download it if needed."""
    target = spec.directory(models_dir)
    if is_ready(spec, models_dir):
        return target
    target.mkdir(parents=True, exist_ok=True)
    if not _verify(spec, target):
        if spec.archive == "tar.bz2":
            archive = models_dir / f"{spec.id}.download"
            fetch(spec.url, archive)
            try:
                _extract(archive, spec, target)
            finally:
                archive.unlink(missing_ok=True)
        elif spec.archive is None:
            fetch(spec.url, target / spec.files[0].name)
        else:
            raise ModelError(f"{spec.id}: unsupported archive type {spec.archive!r}")
        for f in spec.files:
            path = target / f.name
            if not path.is_file() or sha256_of(path) != f.sha256:
                path.unlink(missing_ok=True)
                raise ModelError(f"{spec.id}: {f.name} failed its checksum")
    (target / MARKER).write_text("ok\n", encoding="utf-8")
    return target
```

- [ ] **Step 6: Run the tests and tools, and adopt the already-downloaded spike models**

Run: `uv run pytest -q`, then `bash private/scratch/check.sh` (or `uv run python tools/check.py`).
Expected: all pass.

Move the spike's downloads into the catalogue layout so nothing is downloaded twice:

```bash
M=.data/data/models
mkdir -p $M/silero-vad $M/parakeet-tdt-0.6b-v3-int8
mv $M/silero_vad.onnx $M/silero-vad/
mv $M/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/*.onnx $M/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/tokens.txt $M/parakeet-tdt-0.6b-v3-int8/
mkdir -p spikes/test_wavs && mv $M/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8/test_wavs/en.wav spikes/test_wavs/
rm -rf $M/sherpa-onnx-nemo-parakeet-tdt-0.6b-v3-int8
uv run python -c "from evra.modelstore import *; from evra.paths import resolve_paths; c=load_catalog(); [print(ensure_model(s, resolve_paths().models_dir, fetch=None)) for s in c.values()]"
```

Expected: both paths print. `fetch=None` is never called because the existing files verify.

- [ ] **Step 7: Licence register, commit, push**

Run `uv run python tools/license_gate.py --write-register`; the gate must report 0 problems (the models appear with their attributions). Append to `PROGRESS.md` under a new heading `## 2026-09-28 — M3a Transcription (branch \`one-on-one-notes\`)`, placed above M1: `- Task 1: models.yaml (Silero VAD, Parakeet v3 int8) + modelstore (resumable, SHA-256 verified, archive whitelist).`

```powershell
git add models.yaml pyproject.toml uv.lock src/evra/modelstore.py tests/unit/test_modelstore.py tests/conftest.py THIRD_PARTY_LICENSES.md PROGRESS.md
git commit -m "feat: model catalogue with verified, resumable downloads" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 2: Parakeet ASR engine

**Files:**
- Create: `src/evra/asr/__init__.py`, `src/evra/asr/engine.py`, `src/evra/asr/parakeet.py`, `tests/unit/asr/__init__.py`, `tests/unit/asr/test_parakeet.py`

**Interfaces:**
- Consumes: from Task 1 (M1), `Int16Array` and `SAMPLE_RATE`; from Task 1 (M3a), `requires_models`.
- Produces:
  - `Word(start_ms: int, end_ms: int, text: str)` and `Segment(start_ms: int, end_ms: int, text: str, words: tuple[Word, ...])`
  - `AsrEngine` Protocol with `name`, `languages` and `transcribe(pcm16k, language="en", keywords=None) -> list[Segment]`
  - `segment_to_dict(s) -> dict`, `segment_from_dict(d) -> Segment`
  - `PARAKEET_ID = "parakeet-tdt-0.6b-v3-int8"`
  - `words_from_tokens(tokens: Sequence[str], starts_s: Sequence[float], total_ms: int) -> list[Word]`
  - `ParakeetEngine(model_dir: Path, *, num_threads: int = 4, recognizer: Any = None)`

- [ ] **Step 1: Add the dependency**

```powershell
uv add sherpa-onnx
```

- [ ] **Step 2: Write failing tests** `tests/unit/asr/test_parakeet.py` (plus an empty `__init__.py`)

```python
import wave
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np

from evra.asr.engine import Segment, Word, segment_from_dict, segment_to_dict
from evra.asr.parakeet import PARAKEET_ID, ParakeetEngine, words_from_tokens
from evra.audio.convert import ToMono16k
from evra.paths import REPO_ROOT, resolve_paths
from tests.conftest import requires_models


def test_words_are_built_from_bpe_tokens() -> None:
    tokens = [" A", "sk", " not", " what", ",", " co", "un", "try", "."]
    starts = [0.0, 0.24, 0.4, 0.64, 0.7, 0.8, 0.96, 1.04, 1.3]
    words = words_from_tokens(tokens, starts, total_ms=1500)
    assert [w.text for w in words] == ["Ask", "not", "what,", "country."]
    assert [(w.start_ms, w.end_ms) for w in words] == [(0, 400), (400, 640), (640, 800), (800, 1500)]


def test_words_from_no_tokens() -> None:
    assert words_from_tokens([], [], 1000) == []


class FakeStream:
    def __init__(self, result: Any) -> None:
        self.result = result
        self.accepted: tuple[int, np.ndarray] | None = None

    def accept_waveform(self, rate: int, samples: np.ndarray) -> None:
        self.accepted = (rate, samples)


class FakeRecognizer:
    def __init__(self, text: str) -> None:
        self.result = SimpleNamespace(text=text, tokens=[" Hello", " there"], timestamps=[0.1, 0.5])
        self.stream: FakeStream | None = None

    def create_stream(self) -> FakeStream:
        self.stream = FakeStream(self.result)
        return self.stream

    def decode_stream(self, stream: FakeStream) -> None: ...


def test_engine_wraps_the_recognizer() -> None:
    rec = FakeRecognizer(" Hello there ")
    engine = ParakeetEngine(Path("unused"), recognizer=rec)
    pcm = np.full(16_000, 16384, dtype=np.int16)
    [seg] = engine.transcribe(pcm)
    assert seg.text == "Hello there" and (seg.start_ms, seg.end_ms) == (0, 1000)
    assert [w.text for w in seg.words] == ["Hello", "there"]
    rate, samples = rec.stream.accepted  # type: ignore[union-attr, misc]
    assert rate == 16_000 and samples.dtype == np.float32 and abs(samples[0] - 0.5) < 1e-6


def test_empty_audio_and_empty_text_give_no_segments() -> None:
    engine = ParakeetEngine(Path("unused"), recognizer=FakeRecognizer("  "))
    assert engine.transcribe(np.zeros(0, dtype=np.int16)) == []
    assert engine.transcribe(np.zeros(1600, dtype=np.int16)) == []


def test_segment_dict_round_trip() -> None:
    seg = Segment(10, 90, "hi", (Word(10, 50, "hi"),))
    assert segment_from_dict(segment_to_dict(seg)) == seg


@requires_models(PARAKEET_ID)
def test_real_parakeet_transcribes_english() -> None:
    with wave.open(str(REPO_ROOT / "spikes" / "test_wavs" / "en.wav")) as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    audio16k = ToMono16k(rate, 1).process((pcm / 32768.0).astype(np.float32))
    engine = ParakeetEngine(resolve_paths().models_dir / PARAKEET_ID)
    [seg] = engine.transcribe(audio16k)
    assert "country" in seg.text.lower()
    assert seg.words and seg.words[0].start_ms < 500
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/unit/asr -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'evra.asr'`.

- [ ] **Step 4: Implement**

`src/evra/asr/__init__.py`: empty. `src/evra/asr/engine.py`:

```python
"""Speech-to-text engine interface (BUILD.md §6.1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from evra.audio.frames import Int16Array


@dataclass(frozen=True)
class Word:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class Segment:
    start_ms: int  # relative to the audio passed in
    end_ms: int
    text: str
    words: tuple[Word, ...]


class AsrEngine(Protocol):
    name: str
    languages: frozenset[str]

    def transcribe(
        self, pcm16k: Int16Array, language: str = "en", keywords: list[str] | None = None
    ) -> list[Segment]: ...


def segment_to_dict(segment: Segment) -> dict[str, Any]:
    return asdict(segment)


def segment_from_dict(data: dict[str, Any]) -> Segment:
    words = tuple(Word(**w) for w in data["words"])
    return Segment(data["start_ms"], data["end_ms"], data["text"], words)
```

`src/evra/asr/parakeet.py`:

```python
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
```

- [ ] **Step 5: Run tests and tools; licence register; commit and push**

Run `uv run pytest -q`. The real-model test runs locally because the models are present. Then run `uv run python tools/license_gate.py --write-register` and `bash private/scratch/check.sh`; everything must pass.

Append to `PROGRESS.md`: `- Task 2: Parakeet engine (sherpa-onnx, CPU) with word timings from BPE tokens.`

```powershell
git add pyproject.toml uv.lock src/evra/asr tests/unit/asr THIRD_PARTY_LICENSES.md PROGRESS.md
git commit -m "feat: parakeet speech-to-text engine with word timings" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 3: Voice activity segmenter

**Files:**
- Create: `src/evra/audio/vad.py`, `tests/unit/audio/test_vad.py`

**Interfaces:**
- Consumes: `Frames`, `SAMPLE_RATE`, `Int16Array`, `Float32Array`, and `float_to_int16` (M1).
- Produces:
  - `SpeechSegment(channel: int, start_index: int, pcm: Int16Array)` with `.start_ms` and `.end_ms`
  - `VadBackend` Protocol (`accept_waveform`, `empty`, `flush`, `front`, `pop`)
  - `silero_vad(model_path: Path) -> VadBackend`
  - `SpeechSegmenter(channel: int, vad: VadBackend, *, pre_roll_ms: int = 300, history_s: float = 30.0)` with `.accept(frames) -> list[SpeechSegment]` and `.flush() -> list[SpeechSegment]`
  - `VAD_WINDOW = 512`, `PRE_ROLL_MS = 300`

- [ ] **Step 1: Write failing tests** `tests/unit/audio/test_vad.py`

```python
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from evra.audio.frames import Frames
from evra.audio.vad import VAD_WINDOW, SpeechSegmenter, silero_vad
from evra.paths import resolve_paths
from tests.conftest import requires_models


@dataclass
class _Seg:
    start: int
    samples: np.ndarray


@dataclass
class FakeVad:
    """Emits scripted (start, end) segments once enough audio has been accepted."""

    script: list[tuple[int, int]]
    audio: list[np.ndarray] = field(default_factory=list)
    sizes: list[int] = field(default_factory=list)
    ready: list[_Seg] = field(default_factory=list)
    flushed: bool = False

    def accept_waveform(self, samples: np.ndarray) -> None:
        self.sizes.append(len(samples))
        self.audio.append(samples.copy())
        self._release()

    def _release(self) -> None:
        have = sum(len(a) for a in self.audio)
        while self.script and (self.script[0][1] <= have or self.flushed):
            start, end = self.script.pop(0)
            everything = np.concatenate(self.audio)
            self.ready.append(_Seg(start, everything[start:end]))

    def flush(self) -> None:
        self.flushed = True
        self._release()

    def empty(self) -> bool:
        return not self.ready

    @property
    def front(self) -> _Seg:
        return self.ready[0]

    def pop(self) -> None:
        self.ready.pop(0)


def _frames(audio: np.ndarray, first_index: int = 0, channel: int = 0) -> list[Frames]:
    return [
        Frames(channel, audio[i : i + 160], (first_index + i) * 62_500, first_index + i)  # type: ignore[arg-type]
        for i in range(0, len(audio), 160)
    ]


def _run(seg: SpeechSegmenter, audio: np.ndarray, first_index: int = 0) -> list:  # type: ignore[type-arg]
    out = []
    for f in _frames(audio, first_index):
        out += seg.accept(f)
    return out + seg.flush()


def test_vad_is_fed_512_sample_windows() -> None:
    vad = FakeVad(script=[])
    _run(SpeechSegmenter(0, vad), np.zeros(16_000, dtype=np.int16))
    assert all(s == VAD_WINDOW for s in vad.sizes[:-1]) and sum(vad.sizes) == 16_000


def test_segment_maps_to_timeline_with_pre_roll() -> None:
    audio = np.arange(48_000, dtype=np.int16) % 1000  # distinct values to check alignment
    vad = FakeVad(script=[(16_000, 32_000)])  # speech from 1.0 s to 2.0 s of what it was fed
    [s] = _run(SpeechSegmenter(1, vad), audio, first_index=8_000)
    assert s.channel == 1
    assert s.start_index == 8_000 + 16_000 - 4_800  # 300 ms of pre-roll
    assert len(s.pcm) == 16_000 + 4_800
    np.testing.assert_array_equal(s.pcm, audio[16_000 - 4_800 : 32_000])
    assert (s.start_ms, s.end_ms) == ((8_000 + 11_200) // 16, (8_000 + 32_000) // 16)


def test_pre_roll_is_clipped_at_the_start_of_the_channel() -> None:
    audio = np.ones(32_000, dtype=np.int16)
    vad = FakeVad(script=[(1_600, 16_000)])
    [s] = _run(SpeechSegmenter(0, vad), audio)
    assert s.start_index == 0 and len(s.pcm) == 16_000


def test_flush_releases_speech_still_in_progress() -> None:
    vad = FakeVad(script=[(0, 20_000)])
    segs = _run(SpeechSegmenter(0, vad), np.ones(16_000, dtype=np.int16))
    assert len(segs) == 1 and vad.flushed


@requires_models("silero-vad")
def test_real_silero_finds_the_speech() -> None:
    import wave

    from evra.audio.convert import ToMono16k
    from evra.paths import REPO_ROOT

    with wave.open(str(REPO_ROOT / "spikes" / "test_wavs" / "en.wav")) as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    speech = ToMono16k(rate, 1).process((pcm / 32768.0).astype(np.float32))
    audio = np.concatenate([np.zeros(16_000, np.int16), speech, np.zeros(16_000, np.int16)])
    model = resolve_paths().models_dir / "silero-vad" / "silero_vad.onnx"
    segs = _run(SpeechSegmenter(0, silero_vad(Path(model))), audio)
    assert len(segs) >= 1
    assert 500 <= segs[0].start_ms <= 1_100
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/audio/test_vad.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'evra.audio.vad'`.

- [ ] **Step 3: Implement** `src/evra/audio/vad.py`

```python
"""Speech segments from one channel's timeline audio (BUILD.md §5.4, Silero VAD via sherpa-onnx)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import numpy as np

from evra.audio.convert import float_to_int16
from evra.audio.frames import SAMPLE_RATE, Float32Array, Frames, Int16Array

VAD_WINDOW = 512  # Silero's window at 16 kHz
PRE_ROLL_MS = 300


@dataclass(frozen=True)
class SpeechSegment:
    channel: int
    start_index: int  # timeline sample index of pcm[0]
    pcm: Int16Array

    @property
    def start_ms(self) -> int:
        return self.start_index * 1000 // SAMPLE_RATE

    @property
    def end_ms(self) -> int:
        return (self.start_index + len(self.pcm)) * 1000 // SAMPLE_RATE


class VadBackend(Protocol):
    def accept_waveform(self, samples: Float32Array) -> None: ...

    def flush(self) -> None: ...

    def empty(self) -> bool: ...

    @property
    def front(self) -> Any: ...  # has .start (sample index) and .samples (float32)

    def pop(self) -> None: ...


def silero_vad(model_path: Path) -> VadBackend:
    import sherpa_onnx

    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(model_path)
    config.silero_vad.threshold = 0.5
    config.silero_vad.min_speech_duration = 0.25
    config.silero_vad.min_silence_duration = 0.4
    config.silero_vad.max_speech_duration = 20.0
    config.silero_vad.window_size = VAD_WINDOW
    config.sample_rate = SAMPLE_RATE
    config.num_threads = 1
    vad: VadBackend = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=60)
    return vad


class SpeechSegmenter:
    """Feeds one channel to the VAD and returns closed speech segments, with pre-roll.

    Frames arrive contiguous from the pipeline, so the VAD's sample count maps straight onto
    the meeting timeline (offset by the channel's first frame index).
    """

    def __init__(
        self,
        channel: int,
        vad: VadBackend,
        *,
        pre_roll_ms: int = PRE_ROLL_MS,
        history_s: float = 30.0,
    ) -> None:
        self._channel = channel
        self._vad = vad
        self._pre_roll = pre_roll_ms * SAMPLE_RATE // 1000
        self._ring = np.zeros(int(history_s * SAMPLE_RATE), dtype=np.int16)
        self._written = 0  # samples appended to the history (== samples fed to the VAD)
        self._origin: int | None = None  # timeline index of the first sample
        self._pending: Float32Array = np.zeros(0, dtype=np.float32)

    def accept(self, frames: Frames) -> list[SpeechSegment]:
        if self._origin is None:
            self._origin = frames.index
        self._remember(frames.pcm)
        self._pending = np.concatenate([self._pending, frames.pcm.astype(np.float32) / 32768.0])
        while len(self._pending) >= VAD_WINDOW:
            self._vad.accept_waveform(self._pending[:VAD_WINDOW])
            self._pending = self._pending[VAD_WINDOW:]
        return self._collect()

    def flush(self) -> list[SpeechSegment]:
        if len(self._pending):
            self._vad.accept_waveform(self._pending)
            self._pending = np.zeros(0, dtype=np.float32)
        self._vad.flush()
        return self._collect()

    def _remember(self, pcm: Int16Array) -> None:
        size = len(self._ring)
        for start in range(0, len(pcm), size):
            part = pcm[start : start + size]
            at = self._written % size
            first = min(len(part), size - at)
            self._ring[at : at + first] = part[:first]
            self._ring[: len(part) - first] = part[first:]
            self._written += len(part)

    def _history(self, first: int, last: int) -> Int16Array:
        """Samples [first, last) counted from the channel start, if still remembered."""
        first = max(first, self._written - len(self._ring), 0)
        if last <= first:
            return np.zeros(0, dtype=np.int16)
        idx = np.arange(first, last) % len(self._ring)
        return self._ring[idx].copy()

    def _collect(self) -> list[SpeechSegment]:
        out: list[SpeechSegment] = []
        origin = self._origin or 0
        while not self._vad.empty():
            seg = self._vad.front
            start = int(seg.start)
            speech = float_to_int16(np.asarray(seg.samples, dtype=np.float32))
            self._vad.pop()
            pre = self._history(start - self._pre_roll, start)
            begin = start - len(pre)
            out.append(SpeechSegment(self._channel, origin + begin, np.concatenate([pre, speech])))
        return out
```

- [ ] **Step 4: Run tests and tools**, then commit and push

Run: `bash private/scratch/check.sh`. It must be all PASS; the real-VAD test runs locally. Append to `PROGRESS.md`: `- Task 3: SpeechSegmenter — Silero VAD per channel, 512-sample windows, 300 ms pre-roll, timeline-aligned.`

```powershell
git add src/evra/audio/vad.py tests/unit/audio/test_vad.py PROGRESS.md
git commit -m "feat: voice activity segmenter with pre-roll" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 4: Worker processes (protocol and supervisor)

**Files:**
- Create: `src/evra/workers/__init__.py`, `src/evra/workers/protocol.py`, `src/evra/workers/supervisor.py`, `tests/unit/workers/__init__.py`, `tests/unit/workers/fake_handlers.py`, `tests/unit/workers/test_supervisor.py`

**Interfaces:**
- Produces:
  - `Request(id: int, op: str, payload: Any)` and `Response(id: int, ok: bool, payload: Any = None, error: str = "")`
  - `SHUTDOWN`
  - `Handler = Callable[[str, Any], Any]`
  - `serve(conn, handler) -> None`
  - `worker_main(conn, factory: str, config: dict[str, Any]) -> None`
  - `WorkerCrashed`, and `WorkerError` (with `.error_type`)
  - `Worker(name: str, factory: str, config: Mapping[str, Any] | None = None, *, idle_timeout_s: float = 300.0, clock: Callable[[], float] = time.monotonic)` with:
    - `.submit(op, payload) -> Future[Any]`
    - `.call(op, payload, timeout: float | None = None) -> Any`
    - `.alive -> bool`
    - `.stop_if_idle() -> bool`
    - `.stop() -> None`

- [ ] **Step 1: Write failing tests**

`tests/unit/workers/fake_handlers.py` (plus an empty `tests/unit/workers/__init__.py`):

```python
"""Handler factories that run inside spawned test workers."""

import os
from typing import Any


def echo(**config: Any) -> Any:
    def handle(op: str, payload: Any) -> Any:
        if op == "echo":
            return payload
        if op == "config":
            return config
        if op == "boom":
            raise ValueError("secret content that must not cross the pipe")
        if op == "die":
            os._exit(3)
        if op == "pid":
            return os.getpid()
        raise KeyError(op)

    return handle
```

`tests/unit/workers/test_supervisor.py`:

```python
import pytest

from evra.workers.protocol import WorkerCrashed, WorkerError
from evra.workers.supervisor import Worker

FACTORY = "tests.unit.workers.fake_handlers:echo"


@pytest.fixture
def worker():  # type: ignore[no-untyped-def]
    w = Worker("test", FACTORY, {"threads": 2})
    yield w
    w.stop()


def test_starts_lazily_and_answers(worker) -> None:  # type: ignore[no-untyped-def]
    assert not worker.alive
    assert worker.call("echo", {"x": [1, 2]}, timeout=30) == {"x": [1, 2]}
    assert worker.alive
    assert worker.call("config", None, timeout=5) == {"threads": 2}


def test_errors_cross_as_type_names_only(worker) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(WorkerError) as exc:
        worker.call("boom", None, timeout=30)
    assert exc.value.error_type == "ValueError"
    assert "secret" not in str(exc.value)


def test_crash_fails_pending_and_next_call_restarts(worker) -> None:  # type: ignore[no-untyped-def]
    first_pid = worker.call("pid", None, timeout=30)
    with pytest.raises(WorkerCrashed):
        worker.call("die", None, timeout=30)
    assert worker.call("pid", None, timeout=30) != first_pid


def test_idle_worker_is_stopped_and_restarted_on_demand() -> None:
    now = [0.0]
    w = Worker("idle", FACTORY, idle_timeout_s=10, clock=lambda: now[0])
    try:
        w.call("echo", 1, timeout=30)
        assert not w.stop_if_idle()
        now[0] = 11
        assert w.stop_if_idle() and not w.alive
        assert w.call("echo", 2, timeout=30) == 2
    finally:
        w.stop()


def test_stop_is_clean_and_idempotent(worker) -> None:  # type: ignore[no-untyped-def]
    worker.call("echo", 1, timeout=30)
    worker.stop()
    worker.stop()
    assert not worker.alive
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/workers -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'evra.workers'`.

- [ ] **Step 3: Implement**

`src/evra/workers/__init__.py`: empty. `src/evra/workers/protocol.py`:

```python
"""Messages between the app and a model worker process (BUILD.md §4.2).

Errors cross the pipe as the exception *type* only: messages can quote meeting content.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable
from dataclasses import dataclass
from multiprocessing.connection import Connection
from typing import Any

SHUTDOWN = "__shutdown__"
Handler = Callable[[str, Any], Any]


@dataclass(frozen=True)
class Request:
    id: int
    op: str
    payload: Any


@dataclass(frozen=True)
class Response:
    id: int
    ok: bool
    payload: Any = None
    error: str = ""


class WorkerCrashed(RuntimeError):
    """The worker process died before answering."""


class WorkerError(RuntimeError):
    def __init__(self, error_type: str) -> None:
        super().__init__(f"worker raised {error_type}")
        self.error_type = error_type


def serve(conn: Connection, handler: Handler) -> None:
    while True:
        try:
            request = conn.recv()
        except (EOFError, OSError):
            return
        if request.op == SHUTDOWN:
            return
        try:
            conn.send(Response(request.id, True, handler(request.op, request.payload)))
        except Exception as exc:  # report the type only
            conn.send(Response(request.id, False, error=type(exc).__name__))


def worker_main(conn: Connection, factory: str, config: dict[str, Any]) -> None:
    """Entry point of a spawned worker: build the handler named "module:function", then serve."""
    module_name, _, attr = factory.partition(":")
    handler: Handler = getattr(importlib.import_module(module_name), attr)(**config)
    serve(conn, handler)
```

`src/evra/workers/supervisor.py`:

```python
"""A model worker process: started on first use, stopped when idle, restarted after a crash."""

from __future__ import annotations

import itertools
import multiprocessing
import threading
import time
from collections.abc import Callable, Mapping
from concurrent.futures import Future
from multiprocessing.connection import Connection
from multiprocessing.process import BaseProcess
from typing import Any

from evra.workers.protocol import SHUTDOWN, Request, WorkerCrashed, WorkerError, worker_main


class Worker:
    def __init__(
        self,
        name: str,
        factory: str,
        config: Mapping[str, Any] | None = None,
        *,
        idle_timeout_s: float = 300.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.name = name
        self._factory = factory
        self._config = dict(config or {})
        self._idle_timeout = idle_timeout_s
        self._clock = clock
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._pending: dict[int, Future[Any]] = {}
        self._proc: BaseProcess | None = None
        self._conn: Connection | None = None
        self._reader: threading.Thread | None = None
        self._last_used = clock()

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.is_alive()

    def submit(self, op: str, payload: Any) -> Future[Any]:
        future: Future[Any] = Future()
        with self._lock:
            self._ensure_started()
            assert self._conn is not None
            request_id = next(self._ids)
            self._pending[request_id] = future
            self._last_used = self._clock()
            try:
                self._conn.send(Request(request_id, op, payload))
            except (OSError, EOFError):
                self._pending.pop(request_id, None)
                future.set_exception(WorkerCrashed(self.name))
        return future

    def call(self, op: str, payload: Any, timeout: float | None = None) -> Any:
        return self.submit(op, payload).result(timeout)

    def stop_if_idle(self) -> bool:
        with self._lock:
            idle = not self._pending and self._clock() - self._last_used >= self._idle_timeout
        if idle and self.alive:
            self.stop()
            return True
        return False

    def stop(self) -> None:
        with self._lock:
            proc, conn, reader = self._proc, self._conn, self._reader
            self._proc = self._conn = self._reader = None
        if conn is not None:
            try:
                conn.send(Request(0, SHUTDOWN, None))
            except (OSError, EOFError):
                pass
        if proc is not None:
            proc.join(5)
            if proc.is_alive():
                proc.terminate()
                proc.join(5)
        if conn is not None:
            conn.close()
        if reader is not None:
            reader.join(5)

    def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.is_alive():
            return
        ctx = multiprocessing.get_context("spawn")
        parent, child = ctx.Pipe()
        proc = ctx.Process(
            target=worker_main,
            args=(child, self._factory, self._config),
            name=f"evra-{self.name}",
            daemon=True,
        )
        proc.start()
        child.close()
        self._proc, self._conn = proc, parent
        self._reader = threading.Thread(
            target=self._read, args=(parent,), name=f"{self.name}-reader", daemon=True
        )
        self._reader.start()

    def _read(self, conn: Connection) -> None:
        while True:
            try:
                response = conn.recv()
            except (EOFError, OSError):
                break
            with self._lock:
                future = self._pending.pop(response.id, None)
            if future is None:
                continue
            if response.ok:
                future.set_result(response.payload)
            else:
                future.set_exception(WorkerError(response.error))
        with self._lock:  # the process died or was stopped: nobody will answer these
            pending, self._pending = self._pending, {}
        for future in pending.values():
            future.set_exception(WorkerCrashed(self.name))
```

- [ ] **Step 4: Run tests and tools**, then commit and push

Run: `bash private/scratch/check.sh`. It must be all PASS; the worker tests take a few seconds while processes spawn. Append to `PROGRESS.md`: `- Task 4: Worker processes — spawn, typed request/response, futures, crash → restart, idle stop, errors as type names only.`

```powershell
git add src/evra/workers tests/unit/workers PROGRESS.md
git commit -m "feat: supervised model worker processes" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 5: ASR worker and client

**Files:**
- Create: `src/evra/workers/asr.py`, `tests/unit/workers/test_asr_client.py`
- Modify: `tests/unit/workers/fake_handlers.py`

**Interfaces:**
- Consumes: Task 2 (`ParakeetEngine`, `segment_to_dict`, `segment_from_dict`, `PARAKEET_ID`), and Task 4 (`Worker`, `Handler`).
- Produces:
  - `make_asr_handler(model_dir: str, num_threads: int = 4) -> Handler` (it runs in the worker)
  - `Transcriber` Protocol: `transcribe(pcm: Int16Array) -> list[Segment]`
  - `AsrClient(worker: Worker)` with `.for_models(models_dir, *, num_threads=4, idle_timeout_s=300.0)`, `.transcribe(pcm, *, timeout_s=60.0)`, `.warm_up(timeout_s=120.0)` and `.stop()`

- [ ] **Step 1: Write failing tests**

Append to `tests/unit/workers/fake_handlers.py`:

```python
def fake_asr(**config: Any) -> Any:
    def handle(op: str, payload: Any) -> Any:
        if op == "ping":
            return "pong"
        samples = len(payload["pcm"]) // 2
        end = samples * 1000 // 16_000
        return [{"start_ms": 0, "end_ms": end, "text": "hello there",
                 "words": [{"start_ms": 0, "end_ms": end // 2, "text": "hello"},
                           {"start_ms": end // 2, "end_ms": end, "text": "there"}]}]

    return handle
```

`tests/unit/workers/test_asr_client.py`:

```python
import wave

import numpy as np

from evra.asr.parakeet import PARAKEET_ID
from evra.audio.convert import ToMono16k
from evra.paths import REPO_ROOT, resolve_paths
from evra.workers.asr import AsrClient
from evra.workers.supervisor import Worker
from tests.conftest import requires_models


def test_client_sends_pcm_and_rebuilds_segments() -> None:
    client = AsrClient(Worker("asr-test", "tests.unit.workers.fake_handlers:fake_asr"))
    try:
        client.warm_up()
        [seg] = client.transcribe(np.zeros(16_000, dtype=np.int16))
        assert seg.text == "hello there" and seg.end_ms == 1000
        assert [w.text for w in seg.words] == ["hello", "there"]
    finally:
        client.stop()


@requires_models(PARAKEET_ID)
def test_real_parakeet_in_a_worker_process() -> None:
    with wave.open(str(REPO_ROOT / "spikes" / "test_wavs" / "en.wav")) as w:
        rate = w.getframerate()
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2")
    audio = ToMono16k(rate, 1).process((pcm / 32768.0).astype(np.float32))
    client = AsrClient.for_models(resolve_paths().models_dir)
    try:
        [seg] = client.transcribe(audio, timeout_s=120)
        assert "country" in seg.text.lower()
    finally:
        client.stop()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/workers/test_asr_client.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'evra.workers.asr'`.

- [ ] **Step 3: Implement** `src/evra/workers/asr.py`

```python
"""The speech-to-text worker (BUILD.md §4, D6, D8): Parakeet runs in its own process."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol

import numpy as np

from evra.asr.engine import Segment, segment_from_dict, segment_to_dict
from evra.asr.parakeet import PARAKEET_ID
from evra.audio.frames import Int16Array
from evra.workers.protocol import Handler
from evra.workers.supervisor import Worker


def make_asr_handler(model_dir: str, num_threads: int = 4) -> Handler:
    """Runs inside the worker process: load the model once, then answer requests."""
    from evra.asr.parakeet import ParakeetEngine

    engine = ParakeetEngine(Path(model_dir), num_threads=num_threads)

    def handle(op: str, payload: Any) -> Any:
        if op == "ping":
            return "pong"
        if op == "transcribe":
            pcm = np.frombuffer(payload["pcm"], dtype="<i2").astype(np.int16)
            return [segment_to_dict(s) for s in engine.transcribe(pcm, payload["language"])]
        raise ValueError(f"unknown op {op!r}")

    return handle


class Transcriber(Protocol):
    def transcribe(self, pcm: Int16Array) -> list[Segment]: ...


class AsrClient:
    """App-side handle to the ASR worker."""

    def __init__(self, worker: Worker) -> None:
        self._worker = worker

    @classmethod
    def for_models(
        cls, models_dir: Path, *, num_threads: int = 4, idle_timeout_s: float = 300.0
    ) -> AsrClient:
        config = {"model_dir": str(models_dir / PARAKEET_ID), "num_threads": num_threads}
        worker = Worker(
            "asr", "evra.workers.asr:make_asr_handler", config, idle_timeout_s=idle_timeout_s
        )
        return cls(worker)

    def warm_up(self, timeout_s: float = 120.0) -> None:
        """Start the worker and load the model before audio arrives."""
        self._worker.call("ping", None, timeout_s)

    def transcribe(self, pcm: Int16Array, *, timeout_s: float = 60.0) -> list[Segment]:
        payload = {"pcm": pcm.astype("<i2").tobytes(), "language": "en"}
        return [segment_from_dict(d) for d in self._worker.call("transcribe", payload, timeout_s)]

    def stop_if_idle(self) -> bool:
        return self._worker.stop_if_idle()

    def stop(self) -> None:
        self._worker.stop()
```

- [ ] **Step 4: Run tests and tools**, then commit and push

Run: `bash private/scratch/check.sh`. It must be all PASS, including the real Parakeet-in-a-worker test run locally. Append to `PROGRESS.md`: `- Task 5: ASR worker (Parakeet in its own process) + AsrClient.`

```powershell
git add src/evra/workers/asr.py tests/unit/workers PROGRESS.md
git commit -m "feat: speech-to-text worker process and client" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 6: Meeting and transcript store

**Files:**
- Create: `src/evra/store/meetings.py`, `tests/unit/test_meetings_store.py`

**Interfaces:**
- Consumes: M0 `connect` and `migrate`; Task 2 `Word`.
- Produces:
  - `new_id() -> str`
  - `now_ms() -> int`
  - `Utterance` (frozen) with fields `id, version_id, meeting_id, seq, channel, speaker_id, start_ms, end_ms, text, words: tuple[Word, ...], confidence`
  - `MeetingStore(conn)` with:
    - `.create_meeting(*, title, mode, situation, template, started_at_ms=None) -> str`
    - `.finish_meeting(meeting_id, *, state="ready") -> None`
    - `.get_meeting(meeting_id) -> dict[str, Any]`
    - `.create_transcript_version(meeting_id, *, kind, model) -> str` (it becomes the current version)
    - `.add_utterance(*, version_id, meeting_id, channel, start_ms, end_ms, text, words=(), confidence=None, speaker_id=None) -> Utterance`
    - `.utterances(version_id) -> list[Utterance]`

- [ ] **Step 1: Write failing tests** `tests/unit/test_meetings_store.py`

```python
from pathlib import Path

import pytest

from evra.asr.engine import Word
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate


@pytest.fixture
def store(tmp_path: Path) -> MeetingStore:
    conn = connect(tmp_path / "evra.db")
    migrate(conn)
    return MeetingStore(conn)


def _meeting(store: MeetingStore) -> str:
    return store.create_meeting(
        title="Sync", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )


def test_meeting_lifecycle(store: MeetingStore) -> None:
    mid = _meeting(store)
    assert store.get_meeting(mid)["state"] == "recording"
    store.finish_meeting(mid)
    row = store.get_meeting(mid)
    assert row["state"] == "ready" and row["ended_at"] is not None


def test_new_transcript_version_becomes_current(store: MeetingStore) -> None:
    mid = _meeting(store)
    v1 = store.create_transcript_version(mid, kind="live", model="parakeet")
    v2 = store.create_transcript_version(mid, kind="fast", model="parakeet")
    rows = store._conn.execute(  # noqa: SLF001 - checking the flag directly
        "SELECT id, is_current FROM transcript_version WHERE meeting_id = ?", (mid,)
    ).fetchall()
    assert {r["id"]: r["is_current"] for r in rows} == {v1: 0, v2: 1}


def test_utterances_get_sequence_numbers_and_come_back_in_time_order(store: MeetingStore) -> None:
    mid = _meeting(store)
    vid = store.create_transcript_version(mid, kind="live", model="parakeet")
    store.add_utterance(version_id=vid, meeting_id=mid, channel=1, start_ms=5000, end_ms=6000,
                        text="later", words=(Word(5000, 6000, "later"),))
    store.add_utterance(version_id=vid, meeting_id=mid, channel=0, start_ms=1000, end_ms=2000,
                        text="earlier")
    got = store.utterances(vid)
    assert [u.text for u in got] == ["earlier", "later"]
    assert sorted(u.seq for u in got) == [0, 1]
    assert got[1].words == (Word(5000, 6000, "later"),)
    assert got[0].words == ()
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_meetings_store.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'evra.store.meetings'`.

- [ ] **Step 3: Implement** `src/evra/store/meetings.py`

```python
"""Meetings, transcript versions and utterances (BUILD.md §8.2). One store per connection."""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from evra.asr.engine import Word


def new_id() -> str:
    return uuid.uuid4().hex


def now_ms() -> int:
    return time.time_ns() // 1_000_000


@dataclass(frozen=True)
class Utterance:
    id: str
    version_id: str
    meeting_id: str
    seq: int
    channel: int
    speaker_id: str | None
    start_ms: int
    end_ms: int
    text: str
    words: tuple[Word, ...]
    confidence: float | None


class MeetingStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create_meeting(
        self,
        *,
        title: str,
        mode: str,
        situation: str,
        template: str,
        started_at_ms: int | None = None,
    ) -> str:
        meeting_id, now = new_id(), now_ms()
        self._conn.execute(
            "INSERT INTO meeting (id, title, started_at, mode, situation, template, state,"
            " created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, 'recording', ?, ?)",
            (meeting_id, title, started_at_ms or now, mode, situation, template, now, now),
        )
        return meeting_id

    def finish_meeting(self, meeting_id: str, *, state: str = "ready") -> None:
        now = now_ms()
        self._conn.execute(
            "UPDATE meeting SET ended_at = COALESCE(ended_at, ?), state = ?, updated_at = ?"
            " WHERE id = ?",
            (now, state, now, meeting_id),
        )

    def get_meeting(self, meeting_id: str) -> dict[str, Any]:
        row = self._conn.execute("SELECT * FROM meeting WHERE id = ?", (meeting_id,)).fetchone()
        if row is None:
            raise KeyError(meeting_id)
        return dict(row)

    def create_transcript_version(self, meeting_id: str, *, kind: str, model: str) -> str:
        version_id = new_id()
        self._conn.execute("BEGIN")
        try:
            self._conn.execute(
                "UPDATE transcript_version SET is_current = 0 WHERE meeting_id = ?", (meeting_id,)
            )
            self._conn.execute(
                "INSERT INTO transcript_version (id, meeting_id, kind, model, created_at,"
                " is_current) VALUES (?, ?, ?, ?, ?, 1)",
                (version_id, meeting_id, kind, model, now_ms()),
            )
            self._conn.execute("COMMIT")
        except BaseException:
            self._conn.execute("ROLLBACK")
            raise
        return version_id

    def add_utterance(
        self,
        *,
        version_id: str,
        meeting_id: str,
        channel: int,
        start_ms: int,
        end_ms: int,
        text: str,
        words: Sequence[Word] = (),
        confidence: float | None = None,
        speaker_id: str | None = None,
    ) -> Utterance:
        utterance_id = new_id()
        seq = self._conn.execute(
            "SELECT COALESCE(MAX(seq), -1) + 1 FROM utterance WHERE version_id = ?", (version_id,)
        ).fetchone()[0]
        words_json = json.dumps([[w.start_ms, w.end_ms, w.text] for w in words]) if words else None
        self._conn.execute(
            "INSERT INTO utterance (id, version_id, meeting_id, seq, channel, speaker_id,"
            " start_ms, end_ms, text, words_json, confidence)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (utterance_id, version_id, meeting_id, seq, channel, speaker_id, start_ms, end_ms,
             text, words_json, confidence),
        )
        return Utterance(utterance_id, version_id, meeting_id, seq, channel, speaker_id,
                         start_ms, end_ms, text, tuple(words), confidence)

    def utterances(self, version_id: str) -> list[Utterance]:
        rows = self._conn.execute(
            "SELECT * FROM utterance WHERE version_id = ? ORDER BY start_ms, seq", (version_id,)
        ).fetchall()
        return [
            Utterance(
                r["id"], r["version_id"], r["meeting_id"], r["seq"], r["channel"],
                r["speaker_id"], r["start_ms"], r["end_ms"], r["text"],
                tuple(Word(*w) for w in json.loads(r["words_json"])) if r["words_json"] else (),
                r["confidence"],
            )
            for r in rows
        ]
```

- [ ] **Step 4: Run tests and tools**, then commit and push

Run: `bash private/scratch/check.sh`. It must be all PASS. Append to `PROGRESS.md`: `- Task 6: MeetingStore — meetings, current transcript version, utterances with word timings.`

```powershell
git add src/evra/store/meetings.py tests/unit/test_meetings_store.py PROGRESS.md
git commit -m "feat: meeting and transcript store" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 7: Live transcriber

**Files:**
- Create: `src/evra/transcribe/__init__.py`, `src/evra/transcribe/live.py`, `tests/unit/transcribe/__init__.py`, `tests/unit/transcribe/test_live.py`

**Interfaces:**
- Consumes: Task 3 `SpeechSegment`, Task 5 `Transcriber`, Task 6 `MeetingStore` / `Utterance`, M0 `connect`, and Task 4 `WorkerCrashed`.
- Produces:
  - `UtteranceListener = Callable[[Utterance], None]`
  - `TranscriberStats` (frozen) with fields `segments`, `utterances`, `failures`, `audio_ms` and `asr_ms`, and a `.rtf` property
  - `LiveTranscriber(asr: Transcriber, db_path: Path, *, meeting_id: str, version_id: str)` with:
    - `.add_listener(fn)`
    - `.start()`
    - `.submit(segment)` (thread-safe; callable from the capture thread)
    - `.stop(timeout_s=120.0) -> TranscriberStats` (drains the queue first)
    - `.stats() -> TranscriberStats`

- [ ] **Step 1: Write failing tests** `tests/unit/transcribe/test_live.py` (plus an empty `__init__.py`)

```python
from pathlib import Path

import numpy as np
import pytest

from evra.asr.engine import Segment, Word
from evra.audio.vad import SpeechSegment
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.migrate import migrate
from evra.transcribe.live import LiveTranscriber
from evra.workers.protocol import WorkerCrashed


class FakeAsr:
    def __init__(self, fail_first: int = 0, crash_once: bool = False) -> None:
        self.calls = 0
        self.fail_first = fail_first
        self.crash_once = crash_once

    def transcribe(self, pcm: np.ndarray) -> list[Segment]:
        self.calls += 1
        if self.crash_once:
            self.crash_once = False
            raise WorkerCrashed("asr")
        if self.fail_first:
            self.fail_first -= 1
            raise TimeoutError
        end = len(pcm) * 1000 // 16_000
        return [Segment(0, end, f"text {int(pcm[0])}", (Word(0, end, f"w{int(pcm[0])}"),))]


@pytest.fixture
def db(tmp_path: Path) -> tuple[Path, str, str]:
    path = tmp_path / "evra.db"
    conn = connect(path)
    migrate(conn)
    store = MeetingStore(conn)
    mid = store.create_meeting(title="t", mode="one_on_one", situation="call_headphones",
                               template="one_on_one")
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    conn.close()
    return path, mid, vid


def _seg(channel: int, start_s: float, marker: int) -> SpeechSegment:
    return SpeechSegment(channel, int(start_s * 16_000), np.full(16_000, marker, dtype=np.int16))


def _stored(path: Path, vid: str) -> list[Utterance]:
    conn = connect(path)
    try:
        return MeetingStore(conn).utterances(vid)
    finally:
        conn.close()


def test_segments_are_stored_in_order_with_absolute_times(db) -> None:  # type: ignore[no-untyped-def]
    path, mid, vid = db
    seen: list[Utterance] = []
    live = LiveTranscriber(FakeAsr(), path, meeting_id=mid, version_id=vid)
    live.add_listener(seen.append)
    live.start()
    for i, (ch, t) in enumerate([(0, 1.0), (1, 2.5), (0, 20.0), (0, 21.0)]):
        live.submit(_seg(ch, t, i + 1))
    stats = live.stop()
    rows = _stored(path, vid)
    assert [r.text for r in rows] == ["text 1", "text 2", "text 3", "text 4"]
    assert [(r.channel, r.start_ms, r.end_ms) for r in rows][:2] == [(0, 1000, 2000), (1, 2500, 3500)]
    assert rows[0].words[0].start_ms == 1000  # word times are absolute too
    assert [u.text for u in seen] == [r.text for r in rows]
    assert stats.segments == 4 and stats.utterances == 4 and stats.failures == 0


def test_failed_segment_is_counted_and_later_segments_still_work(db) -> None:  # type: ignore[no-untyped-def]
    path, mid, vid = db
    asr = FakeAsr(fail_first=1)
    live = LiveTranscriber(asr, path, meeting_id=mid, version_id=vid)
    live.start()
    live.submit(_seg(0, 1.0, 1))
    live.submit(_seg(0, 3.0, 2))
    stats = live.stop()
    assert stats.failures == 1
    assert [r.text for r in _stored(path, vid)] == ["text 2"]


def test_a_worker_crash_is_retried_once(db) -> None:  # type: ignore[no-untyped-def]
    path, mid, vid = db
    asr = FakeAsr(crash_once=True)
    live = LiveTranscriber(asr, path, meeting_id=mid, version_id=vid)
    live.start()
    live.submit(_seg(0, 1.0, 7))
    stats = live.stop()
    assert asr.calls == 2 and stats.failures == 0
    assert [r.text for r in _stored(path, vid)] == ["text 7"]


def test_a_listener_error_does_not_stop_transcription(db) -> None:  # type: ignore[no-untyped-def]
    path, mid, vid = db
    live = LiveTranscriber(FakeAsr(), path, meeting_id=mid, version_id=vid)

    def broken(u: Utterance) -> None:
        raise RuntimeError("ui gone")

    live.add_listener(broken)
    live.start()
    live.submit(_seg(0, 1.0, 1))
    live.submit(_seg(0, 2.0, 2))
    assert live.stop().utterances == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/transcribe -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'evra.transcribe'`.

- [ ] **Step 3: Implement** `src/evra/transcribe/__init__.py` (empty) and `src/evra/transcribe/live.py`:

```python
"""Live pass (BUILD.md §6.2): speech segments in, stored utterances out, in order."""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import structlog

from evra.asr.engine import Word
from evra.audio.vad import SpeechSegment
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.workers.asr import Transcriber
from evra.workers.protocol import WorkerCrashed

log = structlog.get_logger(__name__)
UtteranceListener = Callable[[Utterance], None]
_STOP = object()


@dataclass(frozen=True)
class TranscriberStats:
    segments: int
    utterances: int
    failures: int
    audio_ms: int
    asr_ms: int

    @property
    def rtf(self) -> float:
        return self.asr_ms / self.audio_ms if self.audio_ms else 0.0


class LiveTranscriber:
    def __init__(
        self, asr: Transcriber, db_path: Path, *, meeting_id: str, version_id: str
    ) -> None:
        self._asr = asr
        self._db_path = db_path
        self._meeting_id = meeting_id
        self._version_id = version_id
        self._queue: queue.Queue[object] = queue.Queue()
        self._listeners: list[UtteranceListener] = []
        self._thread: threading.Thread | None = None
        self._segments = self._utterances = self._failures = 0
        self._audio_ms = self._asr_ms = 0

    def add_listener(self, listener: UtteranceListener) -> None:
        self._listeners.append(listener)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="live-transcriber", daemon=True)
        self._thread.start()

    def submit(self, segment: SpeechSegment) -> None:
        self._queue.put(segment)

    def stop(self, timeout_s: float = 120.0) -> TranscriberStats:
        self._queue.put(_STOP)
        if self._thread is not None:
            self._thread.join(timeout_s)
            self._thread = None
        return self.stats()

    def stats(self) -> TranscriberStats:
        return TranscriberStats(
            self._segments, self._utterances, self._failures, self._audio_ms, self._asr_ms
        )

    def _run(self) -> None:
        conn = connect(self._db_path)
        store = MeetingStore(conn)
        try:
            while (item := self._queue.get()) is not _STOP:
                assert isinstance(item, SpeechSegment)
                self._handle(store, item)
        finally:
            conn.close()

    def _handle(self, store: MeetingStore, segment: SpeechSegment) -> None:
        self._segments += 1
        self._audio_ms += segment.end_ms - segment.start_ms
        started = time.perf_counter()
        try:
            try:
                results = self._asr.transcribe(segment.pcm)
            except WorkerCrashed:  # the worker restarts on the next call: try once more
                results = self._asr.transcribe(segment.pcm)
        except Exception as exc:
            self._failures += 1
            log.warning("transcription_failed", error=type(exc).__name__, channel=segment.channel)
            return
        finally:
            self._asr_ms += int((time.perf_counter() - started) * 1000)
        offset = segment.start_ms
        for result in results:
            if not result.text:
                continue
            utterance = store.add_utterance(
                version_id=self._version_id,
                meeting_id=self._meeting_id,
                channel=segment.channel,
                start_ms=offset + result.start_ms,
                end_ms=offset + result.end_ms,
                text=result.text,
                words=tuple(
                    Word(offset + w.start_ms, offset + w.end_ms, w.text) for w in result.words
                ),
            )
            self._utterances += 1
            for listener in self._listeners:
                try:
                    listener(utterance)
                except Exception as exc:  # a broken listener must not stop transcription
                    log.warning("utterance_listener_failed", error=type(exc).__name__)
```

- [ ] **Step 4: Run tests and tools**, then commit and push

Run: `bash private/scratch/check.sh`. It must be all PASS. Append to `PROGRESS.md`: `- Task 7: LiveTranscriber — ordered queue → ASR → utterances (absolute times) on its own DB connection; crash retried once; failures counted.`

```powershell
git add src/evra/transcribe tests/unit/transcribe PROGRESS.md
git commit -m "feat: live transcriber storing ordered utterances" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 8: `evra models` and `evra transcribe WAV`

**Files:**
- Create: `src/evra/transcribe/cli.py`, `tests/integration/test_transcribe_cli.py`
- Modify: `src/evra/__main__.py`, `tests/unit/test_cli.py`

**Interfaces:**
- Consumes: Tasks 1–5, M1 (`ToMono16k`, `Frames`), and M0 (`configure_logging`, `AppPaths`, `resolve_paths`).
- Produces:
  - `format_ms(ms: int) -> str` (returns `"mm:ss"`)
  - `ensure_speech_models(paths: AppPaths) -> dict[str, Path]`
  - `transcribe_file(path: Path, *, asr: Transcriber, vad: VadBackend) -> list[tuple[int, int, str]]`
  - `models_command(args, paths) -> int`
  - `transcribe_command(args, paths) -> int`
  - CLI: `evra models [--download] [--data-dir]` and `evra transcribe WAV [--data-dir]`

- [ ] **Step 1: Write failing tests**

`tests/integration/test_transcribe_cli.py`:

```python
import wave
from pathlib import Path

import numpy as np
import pytest

from evra.__main__ import main
from evra.asr.engine import Segment
from evra.asr.parakeet import PARAKEET_ID
from evra.paths import REPO_ROOT
from evra.transcribe.cli import format_ms, transcribe_file
from tests.conftest import requires_models
from tests.unit.audio.test_vad import FakeVad


class EchoAsr:
    def transcribe(self, pcm: np.ndarray) -> list[Segment]:
        return [Segment(0, len(pcm) * 1000 // 16_000, "speech", ())]


def _wav(path: Path, rate: int, seconds: float) -> Path:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(np.full(int(rate * seconds), 1000, dtype="<i2").tobytes())
    return path


def test_format_ms() -> None:
    assert format_ms(0) == "00:00" and format_ms(83_400) == "01:23" and format_ms(3_600_000) == "60:00"


def test_transcribe_file_resamples_segments_and_offsets(tmp_path: Path) -> None:
    wav = _wav(tmp_path / "a.wav", 48_000, 3.0)
    lines = transcribe_file(wav, asr=EchoAsr(), vad=FakeVad(script=[(16_000, 32_000)]))
    [(start, end, text)] = lines
    assert text == "speech" and 700 <= start <= 1000 and 1900 <= end <= 2100


def test_models_command_lists_catalogue(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["models", "--data-dir", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "silero-vad" in out and PARAKEET_ID in out and "missing" in out


@requires_models(PARAKEET_ID, "silero-vad")
def test_real_transcribe_command(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["transcribe", str(REPO_ROOT / "spikes" / "test_wavs" / "en.wav")]) == 0
    assert "country" in capsys.readouterr().out.lower()
```

Add to `tests/unit/test_cli.py`:

```python
def test_transcription_subcommands_are_registered() -> None:
    from evra.__main__ import build_parser

    parser = build_parser()
    assert parser.parse_args(["models", "--download"]).download is True
    assert parser.parse_args(["transcribe", "a.wav"]).wav == "a.wav"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_transcribe_cli.py tests/unit/test_cli.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'evra.transcribe.cli'`, and the CLI test fails.

- [ ] **Step 3: Implement** `src/evra/transcribe/cli.py`

```python
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


def transcribe_file(
    path: Path, *, asr: Transcriber, vad: VadBackend
) -> list[tuple[int, int, str]]:
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
                    (segment.start_ms + result.start_ms, segment.start_ms + result.end_ms, result.text)
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
```

In `src/evra/__main__.py`, add the subcommands to `build_parser()`:

```python
    models = commands.add_parser("models", help="list (and download) the speech models")
    models.add_argument("--download", action="store_true", help="download missing models")
    models.add_argument("--data-dir", type=Path, default=None, help="keep all app data here")
    transcribe = commands.add_parser("transcribe", help="transcribe a WAV file")
    transcribe.add_argument("wav", help="16-bit PCM WAV file")
    transcribe.add_argument("--data-dir", type=Path, default=None, help="keep all app data here")
```

And dispatch in `main()`:

```python
    if args.command in ("models", "transcribe"):
        from evra.paths import resolve_paths
        from evra.transcribe.cli import models_command, transcribe_command

        command = models_command if args.command == "models" else transcribe_command
        return command(args, resolve_paths(args.data_dir))
```

- [ ] **Step 4: Run tests and tools; real check; commit and push**

Run `bash private/scratch/check.sh`; it must be all PASS. Then run `uv run evra transcribe spikes/test_wavs/en.wav`. Expected: `[00:00] Ask not what your country can do for you, ask what you can do for your country.`

Append to `PROGRESS.md`: `- Task 8: \`evra models [--download]\`, \`evra transcribe WAV\` (VAD → Parakeet worker); en.wav transcribed correctly.`

```powershell
git add src/evra/transcribe/cli.py src/evra/__main__.py tests/integration/test_transcribe_cli.py tests/unit/test_cli.py PROGRESS.md
git commit -m "feat: evra models and evra transcribe" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 9: `evra record SECONDS` (1:1 live transcript)

**Files:**
- Create: `src/evra/transcribe/record.py`, `tests/integration/test_record.py`
- Modify: `src/evra/__main__.py`, `tests/unit/test_cli.py`, `CLAUDE.md`, `README.md`

**Interfaces:**
- Consumes: M1 (`CaptureSession`, `MicSource`, `LoopbackSource`, `DefaultOutputWatcher`, `CaptureError`, `CaptureHealth`), and Tasks 3–8.
- Produces:
  - `LABELS = {0: "You", 1: "Them"}`
  - `RecordingResult` (frozen) with fields `meeting_id`, `utterances`, `health`, `stats` and `interrupted`
  - `run_recording(session, segmenters: Mapping[int, SpeechSegmenter], transcriber: LiveTranscriber, store: MeetingStore, meeting_id: str, *, seconds: float, sleep: Callable[[float], None] = time.sleep) -> RecordingResult`
  - `record_command(args, paths) -> int`
  - CLI: `evra record SECONDS [--situation {call_headphones,call_speakers,in_person,hybrid}] [--mic DEVICE] [--data-dir]`

- [ ] **Step 1: Write failing tests** `tests/integration/test_record.py`

```python
from pathlib import Path

import numpy as np
import pytest

from evra.asr.engine import Segment
from evra.audio.vad import SpeechSegmenter
from evra.capture.fake import FakeSource
from evra.capture.session import CaptureSession
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.transcribe.live import LiveTranscriber
from evra.transcribe.record import LABELS, run_recording
from tests.unit.audio.test_vad import FakeVad


class NumberAsr:
    def transcribe(self, pcm: np.ndarray) -> list[Segment]:
        return [Segment(0, len(pcm) * 1000 // 16_000, "words", ())]


def _setup(tmp_path: Path) -> tuple[Path, MeetingStore, str, str]:
    db = tmp_path / "evra.db"
    conn = connect(db)
    migrate(conn)
    store = MeetingStore(conn)
    mid = store.create_meeting(title="t", mode="one_on_one", situation="call_headphones",
                               template="one_on_one")
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    return db, store, mid, vid


def _sources(seconds: float) -> tuple[FakeSource, FakeSource]:
    tone = (0.3 * np.sin(np.arange(int(16_000 * seconds)) / 5)).astype(np.float32)
    return (FakeSource(tone, 16_000, name="mic"),
            FakeSource(tone, 16_000, name="out", pads_silence=True))


def test_speech_on_both_channels_becomes_labelled_utterances(tmp_path: Path) -> None:
    db, store, mid, vid = _setup(tmp_path)
    mic, system = _sources(1.5)
    segmenters = {0: SpeechSegmenter(0, FakeVad(script=[(3_200, 9_600)])),
                  1: SpeechSegmenter(1, FakeVad(script=[(8_000, 14_400)]))}
    live = LiveTranscriber(NumberAsr(), db, meeting_id=mid, version_id=vid)
    result = run_recording(CaptureSession(mic, system), segmenters, live, store, mid, seconds=1.6)
    rows = store.utterances(vid)
    assert result.utterances == 2 and {r.channel for r in rows} == {0, 1}
    assert store.get_meeting(mid)["state"] == "ready"
    assert LABELS == {0: "You", 1: "Them"}


def test_silence_only_recording_says_no_speech(tmp_path: Path) -> None:
    db, store, mid, vid = _setup(tmp_path)
    mic, system = _sources(0.6)
    segmenters = {0: SpeechSegmenter(0, FakeVad(script=[])), 1: SpeechSegmenter(1, FakeVad(script=[]))}
    live = LiveTranscriber(NumberAsr(), db, meeting_id=mid, version_id=vid)
    result = run_recording(CaptureSession(mic, system), segmenters, live, store, mid, seconds=0.7)
    assert result.utterances == 0 and store.get_meeting(mid)["state"] == "ready"


def test_interrupt_still_finishes_the_meeting(tmp_path: Path) -> None:
    db, store, mid, vid = _setup(tmp_path)
    mic, system = _sources(3.0)
    segmenters = {0: SpeechSegmenter(0, FakeVad(script=[(1_600, 6_400)])),
                  1: SpeechSegmenter(1, FakeVad(script=[]))}
    live = LiveTranscriber(NumberAsr(), db, meeting_id=mid, version_id=vid)

    def interrupted_sleep(seconds: float) -> None:
        import time

        time.sleep(0.6)
        raise KeyboardInterrupt

    result = run_recording(CaptureSession(mic, system), segmenters, live, store, mid,
                           seconds=30, sleep=interrupted_sleep)
    assert result.interrupted and result.utterances == 1
    assert store.get_meeting(mid)["state"] == "ready"
    assert not mic.is_active() or mic._thread is None  # noqa: SLF001 - devices closed
```

Add to `tests/unit/test_cli.py`:

```python
def test_record_subcommand_is_registered() -> None:
    from evra.__main__ import build_parser

    args = build_parser().parse_args(["record", "60", "--situation", "call_speakers"])
    assert args.seconds == 60.0 and args.situation == "call_speakers"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/integration/test_record.py tests/unit/test_cli.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'evra.transcribe.record'`, and the CLI test fails.

- [ ] **Step 3: Implement** `src/evra/transcribe/record.py`

```python
"""`evra record SECONDS`: a 1:1 call → live, stored, labelled transcript (M3a, D18)."""

from __future__ import annotations

import argparse
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime

from evra.asr.parakeet import PARAKEET_ID
from evra.audio.frames import Frames
from evra.audio.vad import SpeechSegmenter, silero_vad
from evra.capture.session import CaptureHealth, CaptureSession
from evra.capture.sources import CaptureError
from evra.logging_setup import configure_logging
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.migrate import migrate
from evra.transcribe.cli import ensure_speech_models, format_ms
from evra.transcribe.live import LiveTranscriber, TranscriberStats
from evra.workers.asr import AsrClient

LABELS = {0: "You", 1: "Them"}  # 1:1 mode: mic = owner, system = the other person


@dataclass(frozen=True)
class RecordingResult:
    meeting_id: str
    utterances: int
    health: CaptureHealth | None
    stats: TranscriberStats
    interrupted: bool


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
    transcriber.start()
    try:
        session.start(on_frames)
        try:
            sleep(seconds)
        except KeyboardInterrupt:
            interrupted = True
        finally:
            health = session.stop()
            for segmenter in segmenters.values():
                for segment in segmenter.flush():
                    transcriber.submit(segment)
    finally:
        stats = transcriber.stop()
        store.finish_meeting(meeting_id, state="ready")
    return RecordingResult(meeting_id, stats.utterances, health, stats, interrupted)


def _print_utterance(utterance: Utterance) -> None:
    label = LABELS.get(utterance.channel, f"Channel {utterance.channel}")
    print(f"[{format_ms(utterance.start_ms)}] {label}: {utterance.text}", flush=True)


def record_command(args: argparse.Namespace, paths: AppPaths) -> int:
    from evra.capture.mic import MicSource
    from evra.capture.windows import DefaultOutputWatcher, LoopbackSource

    paths.ensure()
    configure_logging(paths.log_dir, debug=False)
    models = ensure_speech_models(paths)
    conn = connect(paths.db_path)
    migrate(conn)
    store = MeetingStore(conn)
    asr = AsrClient.for_models(paths.models_dir)
    try:
        print("Loading speech recognition...", flush=True)
        asr.warm_up()
        device: int | str | None = int(args.mic) if args.mic and args.mic.isdigit() else args.mic
        session = CaptureSession(
            MicSource(device), LoopbackSource(), watcher_factory=DefaultOutputWatcher
        )
        meeting_id = store.create_meeting(
            title=f"Recording {datetime.now():%Y-%m-%d %H:%M}",
            mode="one_on_one",
            situation=args.situation,
            template="one_on_one",
        )
        version_id = store.create_transcript_version(meeting_id, kind="live", model=PARAKEET_ID)
        vad_path = models["silero-vad"] / "silero_vad.onnx"
        segmenters = {ch: SpeechSegmenter(ch, silero_vad(vad_path)) for ch in (0, 1)}
        live = LiveTranscriber(asr, paths.db_path, meeting_id=meeting_id, version_id=version_id)
        live.add_listener(_print_utterance)
        print(f"Recording for {args.seconds:.0f} s (Ctrl+C to stop early)...", flush=True)
        result = run_recording(session, segmenters, live, store, meeting_id, seconds=args.seconds)
    except CaptureError as exc:
        print(f"{exc}", file=sys.stderr)
        if exc.hint:
            print(f"Fix: {exc.hint}", file=sys.stderr)
        return 2
    finally:
        asr.stop()
        conn.close()
    stats = result.stats
    if result.utterances == 0:
        print("-- no speech detected")
    print(
        f"-- {result.utterances} utterances, {stats.failures} failed segments,"
        f" ASR real-time factor {stats.rtf:.3f}; capture {'ok' if result.health and result.health.ok else 'had problems'}"
        f"; meeting {meeting_id}"
    )
    return 0
```

In `src/evra/__main__.py`, add to `build_parser()`:

```python
    record = commands.add_parser("record", help="record a 1:1 call and transcribe it live")
    record.add_argument("seconds", type=_positive_seconds, help="how long to record")
    record.add_argument(
        "--situation",
        default="call_headphones",
        choices=["call_headphones", "call_speakers", "in_person", "hybrid"],
    )
    record.add_argument("--mic", default=None, help="microphone index or name")
    record.add_argument("--data-dir", type=Path, default=None, help="keep all app data here")
```

Add `"record"` to the transcription dispatch in `main()`:

```python
    if args.command == "record":
        from evra.paths import resolve_paths
        from evra.transcribe.record import record_command

        return record_command(args, resolve_paths(args.data_dir))
```

Add to the `CLAUDE.md` Commands section:
- `- Models: \`uv run evra models [--download]\``
- `- Transcribe a file: \`uv run evra transcribe FILE.wav\``
- `- Record + live transcript (1:1): \`uv run evra record 60\``

Add a short "Transcription" subsection to `README.md` with the same three commands.

- [ ] **Step 4: Run tests and tools; real run; commit and push**

Run `bash private/scratch/check.sh`; it must be all PASS.

Real run on the dev machine (this plays `en.wav` through the speakers so the system channel has speech):

```powershell
Start-Job { Start-Sleep 5; Add-Type -AssemblyName presentationCore; $p = New-Object System.Windows.Media.MediaPlayer; $p.Open("D:\GEN AI\Evra\spikes\test_wavs\en.wav"); $p.Play(); Start-Sleep 6 } | Out-Null
uv run evra record 15 --mic 1
```

Expected: a `[00:0x] Them: Ask not what your country...` line appears within ~1 s of the clip ending, the summary shows ≥ 1 utterance, and the capture result is ok. Record the numbers (utterances, RTF) in `PROGRESS.md`: `- Task 9: \`evra record SECONDS\` — 1:1 live transcript (You/Them) into SQLite; dev-machine run: <result>.`

```powershell
git add src/evra/transcribe/record.py src/evra/__main__.py tests/integration/test_record.py tests/unit/test_cli.py CLAUDE.md README.md PROGRESS.md
git commit -m "feat: evra record — live 1:1 transcript into the database" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```

---

### Task 10: Decisions and wrap-up

**Files:**
- Modify: `DECISIONS.md`, `BUILD.md` (§2 D26, §10 note), `BACKLOG.md`, `PROGRESS.md`

- [ ] **Step 1: Record decisions.** Append to `DECISIONS.md`:

```markdown

## D26 — Voice detection moves into M3 (2026-09-28)
- **Context:** the owner parked M1's checkpoint and chose M3 (1:1 call end to end) next; live transcription needs VAD segments, which BUILD.md §10 scheduled in M2.
- **Decision:** Silero VAD (`SpeechSegmenter`) ships in M3a. M2 keeps echo cancellation and spill crash recovery.
- **Consequences:** 1:1 calls on headphones work end to end without M2; on laptop speakers the mic transcript will contain the other person's voice until M2's echo cancellation.
```

In `BUILD.md` §2, add `| D26 | VAD placement | Silero VAD ships in M3a (needed by the live transcript); M2 keeps AEC + spill recovery | 2026-09-28 |`. In §10, after the M2 row's "Delivers", add "(VAD moved to M3, D26)".

- [ ] **Step 2: Backlog.** Append to `BACKLOG.md` under a new heading `## M3a follow-ups`:
- worker logging (via a queue to the app process);
- hallucination guard for phantom phrases (§6.2);
- the post-meeting fast pass when the live transcript is off;
- spill during `evra record`, for later recovery and retention;
- the loopback endpoint role (multimedia vs communications) before real calls on speakers.

- [ ] **Step 3: Commit and push.** Update `PROGRESS.md` with a one-line M3a summary, then:

```powershell
git add DECISIONS.md BUILD.md BACKLOG.md PROGRESS.md
git commit -m "docs: record M3a decisions and follow-ups" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push
```
