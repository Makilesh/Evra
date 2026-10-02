# Phase 1 · M3c Main Window Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record a 1:1 from the Evra window, watch the live transcript, press Stop, and see the cited note appear; a citation jumps to its transcript line.

**Architecture:**
- Python owns the session. `MeetingService` runs one recording at a time on top of a `LiveRecording` core that `evra record` shares, then writes the note in a background thread through the same `write_and_save` that `evra note` uses.
- The service pushes events (`recording.state`, `recording.levels`, `transcript.utterance`, `recording.finished`, `note.stage`, `note.ready`, `note.failed`) through the existing `EventBus`.
- `BridgeApi` gains read and control calls; every call opens its own database connection, because pywebview runs each call on its own thread (verified in `webview/util.py`: `Thread(target=_call)`).
- React keeps all window state in one `useEvra` hook and renders small components.

**Tech Stack:** Python 3.12 (uv), pywebview 6 bridge, sqlite3, sounddevice; React 19 + TypeScript 6 + Tailwind 4 + Vite 8 (single-file build), Vitest + Testing Library; `@fontsource/inter` and `@fontsource/newsreader` 5.3.0 (OFL-1.1).

**Spec:** `docs/superpowers/specs/2026-09-28-m3c-main-window-design.md` (approved 2026-10-02), narrowing `BUILD.md` §4, §7.3, §8.1, §8.4, §8.5, §9.1.

## Global Constraints

- Everything in the M0–M3b plans' Global Constraints still applies:
  - Python 3.12 via uv, `mypy --strict` over `src` and `tools`, files under about 500 lines.
  - Ruff rules `E F W I UP B SIM RUF` only — never add a `noqa` for another family (RUF100 fails). Run `uv run ruff format` on new files.
  - D22: `uv run python tools/check.py` must pass, then a Conventional Commit, then `git push` on branch **`main-window`**. Gate every commit on the check output containing no `FAIL` (piping through `tail` hides the exit code).
  - D23: data in `.data/`, scratch in `private/`, spikes in `spikes/`; never the system temp folder.
- **No content in logs above DEBUG.** Transcript, note and mic-free text go only to the user's own window through the bridge. Logs carry event names, counts, reason codes and exception *type names*.
- **Evra opens no listener.** pywebview loads `file://` or the dev server; fonts are bundled, nothing is fetched from the web.
- **Bridge arguments come from JavaScript:** a wrong type is refused (`{"ok": False}` / `None`), never trusted.
- **Threads:** one SQLite connection per thread; `MeetingService` holds one lock for its state and never emits or does slow work while holding it.
- **Microphones** (verified 2026-10-02 with `spikes/mic_names.py` and `sounddevice._get_device_id`):
  - Windows lists each mic once per host API (MME, DirectSound, WASAPI, WDM-KS), so a bare name like `"Headset (realme Buds Air7)"` makes sounddevice raise "Multiple input devices found".
  - MME cuts names at 31 characters (`"Microphone Array (Realtek(R) Au"`).
  - Evra lists and resolves mics only on the **default input's host API** (MME today — what `MicSource(None)` records from), shows the full name taken from another host API when the MME name is cut, and passes the device **index** to `MicSource`.
- **Settings:** new top-level `mic_name: str = ""` (`""` = Windows default; TOML has no null).
- **Frontend:**
  - TypeScript `strict`, `noUnusedLocals`, `noUnusedParameters`; oxlint with `react/rules-of-hooks`.
  - Every user-facing string lives in `frontend/src/strings.ts`; every control has an accessible name.
  - Text is rendered as text: never `dangerouslySetInnerHTML`.
  - Style tokens from `frontend/src/index.css` (`paper`, `ink`, `muted-ink`, `accent`, `rec`, `line`); serif for note/transcript text, sans for UI.
- **Licences:** run `uv run python tools/license_gate.py --write-register` after adding npm packages; the register `THIRD_PARTY_LICENSES.md` is committed.

## Review Focus

1. **The window closes while recording or while speech recognition is loading.** The meeting and its transcript are saved, nothing is left half-open, the ASR worker stops, and no empty meeting appears. → Task 5 `test_closing_the_window_while_recording_saves_the_meeting`, `test_closing_while_loading_starts_nothing`.
2. **The remembered mic is gone** (Bluetooth earbuds off). Record fails with a one-line reason and fix *before* any meeting exists; the picker still shows the remembered name as "(not connected)" next to the Windows default. → Task 1 `test_a_mic_that_is_gone_says_how_to_fix_it`, Task 5 `test_a_missing_mic_fails_before_any_meeting_exists`, Task 9 `test_keeps_a_remembered_mic_that_is_not_connected_visible`.
3. **Two clicks at once** (Record double-clicked, Retry twice) arrive on separate bridge threads. Exactly one recording or note job starts. → Task 5 `test_two_record_clicks_at_once_make_one_recording`.
4. **Events for a meeting that isn't open, duplicates, or a window reload mid-recording.** Lines appear only in their meeting, once; a reloaded window picks the recording back up. → Task 8 `appends live lines only for the open meeting, once each`, `picks up a recording in progress after the window reloads`.
5. **Transcript or note text containing HTML or `</script>`.** It shows as plain text in the window and cannot break the event script. → Task 6 `test_event_text_cannot_close_the_script`, Task 11 `shows transcript and note text as text, never as HTML`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `src/evra/capture/devices.py` | `MicList`, `list_mics`, `resolve_mic` (mics by name on the default input's host API) |
| `src/evra/config.py` | + `Settings.mic_name` |
| `src/evra/transcribe/recording.py` | `RecordingResult`, `frame_level`, `LiveRecording` (capture → VAD → live transcript), `RecordingKit` (models, ASR worker, VAD; builds recordings) |
| `src/evra/transcribe/record.py` | `evra record` on top of `RecordingKit` + `LiveRecording`; `run_recording(recording, seconds=…)` |
| `src/evra/store/meetings.py` | + `list_meetings`, `rename_meeting`, `recover_after_restart` |
| `src/evra/services/__init__.py` | package marker |
| `src/evra/services/views.py` | JSON views: `meeting_summary`, `utterance_view`, `note_view`, `meeting_detail`, `clean_title` |
| `src/evra/notes/job.py` | `NothingSupported`, `SavedNote`, `write_and_save`, `failure_reason` |
| `src/evra/notes/cli.py` | `evra note` uses `write_and_save` |
| `src/evra/services/meetings.py` | `MeetingService` (states, events, level ticker, note thread, retry, shutdown) |
| `src/evra/bridge/api.py` | + `list_meetings`, `get_meeting`, `list_mics`, `start_recording`, `stop_recording`, `write_note`, `rename_meeting`, `recording_state` |
| `src/evra/bridge/events.py` | + `EventBus.detach`; a failing window drops the event instead of raising |
| `src/evra/app.py` | builds the service, recovers stale meetings, shuts the service down when the window closes |
| `frontend/src/bridge.ts` | types + new API methods |
| `frontend/src/strings.ts` | every user-facing string, note-failure sentences |
| `frontend/src/format.ts` | `formatClock`, `formatDuration`, `formatDate` |
| `frontend/src/useEvra.ts` | all window state and actions, event subscriptions |
| `frontend/src/components/{Banner,LevelMeter,TopBar,MeetingList,TranscriptView,NoteView,MeetingView}.tsx` | UI |
| `frontend/src/App.tsx` | composition |
| `frontend/src/main.tsx` | + bundled fonts |
| `frontend/src/test/{setup.ts,fakeApi.ts}` | test setup, fake bridge |
| tests | `tests/unit/capture/test_devices.py`, `tests/integration/test_record.py` (rewritten), `tests/unit/transcribe/test_recording.py`, `tests/unit/test_meeting_lists.py`, `tests/unit/services/{__init__,test_views,test_meeting_service}.py`, `tests/unit/notes/test_job.py`, `tests/unit/test_bridge.py`, `tests/unit/test_app.py`, `frontend/src/**/*.test.ts(x)` |

---

### Task 1: Microphones by name

**Files:**
- Create: `src/evra/capture/devices.py`
- Modify: `src/evra/config.py` (one field)
- Test: `tests/unit/capture/test_devices.py`, `tests/unit/test_config.py` (one test)

**Interfaces:**
- Consumes: `MicUnavailableError(message, hint)` from `evra.capture.sources`.
- Produces:
  - `MicList(default: str, mics: tuple[str, ...])` (frozen dataclass);
  - `list_mics(backend: Any = None) -> MicList`;
  - `resolve_mic(name: str, backend: Any = None) -> int | None` — `None` means the Windows default; raises `MicUnavailableError` when the name matches nothing or several mics;
  - `PICK_AGAIN: str` (the hint);
  - `Settings.mic_name: str = ""`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/capture/test_devices.py`:

```python
from typing import Any

import pytest

from evra.capture.devices import MicList, list_mics, resolve_mic
from evra.capture.sources import MicUnavailableError

APIS = [{"name": "MME"}, {"name": "Windows DirectSound"}, {"name": "Windows WASAPI"}]
DEVICES: list[dict[str, Any]] = [
    {"name": "Microsoft Sound Mapper - Input", "hostapi": 0, "max_input_channels": 2},
    {"name": "Headset (realme Buds Air7)", "hostapi": 0, "max_input_channels": 1},
    {"name": "Microphone Array (Realtek(R) Au", "hostapi": 0, "max_input_channels": 2},
    {"name": "Speakers (Realtek(R) Audio)", "hostapi": 0, "max_input_channels": 0},
    {"name": "Primary Sound Capture Driver", "hostapi": 1, "max_input_channels": 2},
    {"name": "Headset (realme Buds Air7)", "hostapi": 1, "max_input_channels": 1},
    {"name": "Microphone Array (Realtek(R) Audio)", "hostapi": 1, "max_input_channels": 2},
    {"name": "Microphone Array (Realtek(R) Audio)", "hostapi": 2, "max_input_channels": 2},
]


class FakeSd:
    """sounddevice's query API, shaped like the dev machine (spikes/mic_names.py)."""

    def __init__(self, devices: list[dict[str, Any]] = DEVICES, default: int | None = 1) -> None:
        self.devices, self.default = devices, default

    def query_devices(self, device: int | None = None, kind: str | None = None) -> Any:
        if device is None and kind == "input":
            if self.default is None:
                raise ValueError("No input device matching")
            return self.devices[self.default]
        if device is None:
            return self.devices
        return self.devices[device]

    def query_hostapis(self) -> list[dict[str, str]]:
        return APIS


def test_mics_of_the_default_host_api_with_full_names() -> None:
    assert list_mics(FakeSd()) == MicList(
        default="Headset (realme Buds Air7)",
        mics=("Headset (realme Buds Air7)", "Microphone Array (Realtek(R) Audio)"),
    )


def test_no_input_device_at_all_lists_nothing() -> None:
    assert list_mics(FakeSd(default=None)) == MicList("", ())


def test_resolve_by_full_name_case_insensitively_or_a_unique_part() -> None:
    sd = FakeSd()
    assert resolve_mic("Microphone Array (Realtek(R) Audio)", sd) == 2
    assert resolve_mic("headset (realme buds air7)", sd) == 1
    assert resolve_mic("realtek", sd) == 2


def test_an_empty_name_means_the_windows_default() -> None:
    assert resolve_mic("", FakeSd()) is None
    assert resolve_mic("   ", FakeSd()) is None


def test_a_mic_that_is_gone_says_how_to_fix_it() -> None:
    with pytest.raises(MicUnavailableError) as caught:
        resolve_mic("Headset (Mivi Roam 2)", FakeSd())
    assert "not connected" in str(caught.value)
    assert caught.value.hint


def test_a_name_matching_several_mics_is_refused() -> None:
    devices = [
        {"name": "USB Mic A", "hostapi": 0, "max_input_channels": 1},
        {"name": "USB Mic B", "hostapi": 0, "max_input_channels": 1},
    ]
    with pytest.raises(MicUnavailableError, match="several"):
        resolve_mic("usb mic", FakeSd(devices, default=0))
```

Append to `tests/unit/test_config.py`:

```python


def test_the_microphone_defaults_to_windows_default_and_round_trips(tmp_path: Path) -> None:
    from evra.config import Settings, load_settings, save_settings

    assert Settings().mic_name == ""
    path = tmp_path / "settings.toml"
    save_settings(path, Settings(mic_name="Headset (realme Buds Air7)"))
    assert load_settings(path).mic_name == "Headset (realme Buds Air7)"
```

(If `tests/unit/test_config.py` does not already import `Path`, add `from pathlib import Path` at its top.)

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/capture/test_devices.py tests/unit/test_config.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'evra.capture.devices'`, and the config test fails on `mic_name`.

- [ ] **Step 3: Implement**

`src/evra/capture/devices.py`:

```python
"""Microphones by name (M3c, BUILD.md §5.1).

Windows lists each microphone once per host API (MME, DirectSound, WASAPI, WDM-KS), so a bare
name is ambiguous to sounddevice ("Multiple input devices found"), and MME cuts names at 31
characters. Evra lists the mics of the default input's host API — the one `MicSource(None)`
records from — shows each with its full name when another host API has it, and resolves a
stored name back to that host API's device index.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evra.capture.sources import MicUnavailableError

MME_NAME_LIMIT = 31
PSEUDO_DEVICES = frozenset({"Microsoft Sound Mapper - Input", "Primary Sound Capture Driver"})
PICK_AGAIN = "Pick the microphone again in Evra, or check that it is connected and turned on."


@dataclass(frozen=True)
class MicList:
    default: str
    mics: tuple[str, ...]


def _sounddevice() -> Any:
    import sounddevice

    return sounddevice


def _full_name(name: str, names: list[str]) -> str:
    if len(name) != MME_NAME_LIMIT:
        return name
    longer = [n for n in names if len(n) > len(name) and n.startswith(name)]
    return min(longer, key=len) if longer else name


def _entries(sd: Any) -> tuple[list[tuple[int, str]], str]:
    """(device index, display name) of each mic on the default input's host API, and the
    default mic's display name."""
    try:
        default = sd.query_devices(kind="input")
    except Exception:  # no input device at all (sounddevice raises ValueError/PortAudioError)
        return [], ""
    devices = list(sd.query_devices())
    names = [str(d["name"]) for d in devices if d["max_input_channels"] > 0]
    entries = [
        (index, _full_name(str(d["name"]), names))
        for index, d in enumerate(devices)
        if d["hostapi"] == default["hostapi"]
        and d["max_input_channels"] > 0
        and str(d["name"]) not in PSEUDO_DEVICES
    ]
    return entries, _full_name(str(default["name"]), names)


def list_mics(backend: Any = None) -> MicList:
    entries, default = _entries(backend or _sounddevice())
    return MicList(default, tuple(dict.fromkeys(name for _, name in entries)))


def resolve_mic(name: str, backend: Any = None) -> int | None:
    """Device index for a mic name from `list_mics` (or a unique part of one); None = default."""
    wanted = " ".join(name.split()).lower()
    if not wanted:
        return None
    entries, _ = _entries(backend or _sounddevice())
    exact = [index for index, full in entries if full.lower() == wanted]
    if exact:
        return exact[0]
    partial = [index for index, full in entries if wanted in full.lower()]
    if len(partial) == 1:
        return partial[0]
    if partial:
        raise MicUnavailableError(f"several microphones match {name!r}", PICK_AGAIN)
    raise MicUnavailableError(f"microphone {name!r} is not connected", PICK_AGAIN)
```

In `src/evra/config.py`, add to `class Settings` after `default_situation`:

```python
    mic_name: str = ""  # chosen in the window, by name ("" = Windows default; M3c)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/capture/test_devices.py tests/unit/test_config.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff format src/evra/capture/devices.py tests/unit/capture/test_devices.py tests/unit/test_config.py
uv run python tools/check.py   # must show no FAIL
git add src/evra/capture/devices.py src/evra/config.py tests/unit/capture/test_devices.py tests/unit/test_config.py
git commit -m "feat: list and choose microphones by name"
git push -u origin main-window
```

---
### Task 2: One live recording core for the CLI and the window

**Files:**
- Create: `src/evra/transcribe/recording.py`
- Modify: `src/evra/transcribe/record.py` (rewritten on top of the core)
- Test: `tests/integration/test_record.py` (rewritten), `tests/unit/transcribe/test_recording.py`

**Interfaces:**
- Consumes:
  - `resolve_mic` (Task 1);
  - `CaptureSession(mic, system, *, watcher_factory=None)` with `start(on_frames)` / `stop() -> CaptureHealth`;
  - `SpeechSegmenter(channel, vad)` with `accept(frames)` / `flush()`, `silero_vad(path)`;
  - `LiveTranscriber(asr, db_path, *, meeting_id, version_id)` with `add_listener`, `start`, `submit`, `stop() -> TranscriberStats`;
  - `MeetingStore.create_meeting(..., started_at_ms=)`, `create_transcript_version`, `finish_meeting(id, state=)`, `now_ms()`;
  - `ensure_speech_models(paths) -> dict[str, Path]` (from `evra.transcribe.cli`), `AsrClient.for_models(models_dir)` with `warm_up()` / `stop()`.
- Produces:
  - `RecordingResult(meeting_id, utterances, health, stats, interrupted)` — moved here from `record.py`, still importable from `evra.transcribe.record`;
  - `frame_level(pcm: Int16Array) -> float` (0..1: −60 dBFS → 0, 0 dBFS → 1);
  - `LiveRecording(*, session, segmenters, asr, db_path, title, situation, on_utterance=None, on_level=None)` with `meeting_id: str | None`, `started_at_ms: int | None`, `start() -> str`, `stop(*, state: str = "ready") -> RecordingResult`;
  - `RecordingKit(paths, *, asr=None)` with `prepare()`, `new_recording(mic: int | str | None, *, title, situation, on_utterance=None, on_level=None) -> LiveRecording`, `close()`;
  - `run_recording(recording: LiveRecording, *, seconds, sleep=time.sleep) -> RecordingResult` in `record.py`.
- **Behaviour change (spec §3.1):** capture opens *before* the meeting is created, so a missing or busy mic leaves no meeting behind. The old test `test_capture_start_failure_marks_the_meeting_failed` becomes `test_capture_start_failure_creates_no_meeting`.

- [ ] **Step 1: Write the failing tests**

Replace the whole of `tests/integration/test_record.py` with:

```python
from collections.abc import Sequence
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from evra.asr.engine import Segment
from evra.audio.vad import SpeechSegmenter
from evra.capture.fake import FakeSource
from evra.capture.session import CaptureSession
from evra.capture.sources import CaptureError
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.migrate import migrate
from evra.transcribe.labels import LABELS
from evra.transcribe.record import run_recording
from evra.transcribe.recording import LiveRecording
from tests.unit.audio.test_vad import FakeVad


class NumberAsr:
    def transcribe(self, pcm: np.ndarray) -> list[Segment]:
        return [Segment(0, len(pcm) * 1000 // 16_000, "words", ())]


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "evra.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    return db


def _sources(seconds: float) -> tuple[FakeSource, FakeSource]:
    tone = (0.3 * np.sin(np.arange(int(16_000 * seconds)) / 5)).astype(np.float32)
    return (
        FakeSource(tone, 16_000, name="mic"),
        FakeSource(tone, 16_000, name="out", pads_silence=True),
    )


def _recording(
    db: Path,
    mic: FakeSource,
    system: FakeSource,
    scripts: Sequence[Sequence[tuple[int, int]]] = ((), ()),
    **kwargs: Any,
) -> LiveRecording:
    segmenters = {
        channel: SpeechSegmenter(channel, FakeVad(script=list(script)))
        for channel, script in enumerate(scripts)
    }
    return LiveRecording(
        session=CaptureSession(mic, system),
        segmenters=segmenters,
        asr=NumberAsr(),
        db_path=db,
        title="t",
        situation="call_headphones",
        **kwargs,
    )


def _stored(db: Path, meeting_id: str) -> tuple[dict[str, Any], list[Utterance]]:
    conn = connect(db)
    try:
        store = MeetingStore(conn)
        version = store.current_transcript_version(meeting_id)
        return store.get_meeting(meeting_id), store.utterances(version) if version else []
    finally:
        conn.close()


def test_speech_on_both_channels_becomes_labelled_utterances(tmp_path: Path) -> None:
    db = _db(tmp_path)
    mic, system = _sources(1.5)
    heard: list[Utterance] = []
    recording = _recording(
        db, mic, system, ([(3_200, 9_600)], [(8_000, 14_400)]), on_utterance=heard.append
    )
    result = run_recording(recording, seconds=1.6)
    meeting, rows = _stored(db, result.meeting_id)
    assert result.utterances == 2 and {r.channel for r in rows} == {0, 1}
    assert meeting["state"] == "ready" and meeting["mode"] == "one_on_one"
    assert len(heard) == 2
    assert LABELS == {0: "You", 1: "Them"}


def test_silence_only_recording_says_no_speech(tmp_path: Path) -> None:
    db = _db(tmp_path)
    mic, system = _sources(0.6)
    result = run_recording(_recording(db, mic, system), seconds=0.7)
    meeting, _ = _stored(db, result.meeting_id)
    assert result.utterances == 0 and meeting["state"] == "ready"


def test_interrupt_still_finishes_the_meeting(tmp_path: Path) -> None:
    db = _db(tmp_path)
    mic, system = _sources(3.0)

    def interrupted_sleep(seconds: float) -> None:
        import time

        time.sleep(0.6)
        raise KeyboardInterrupt

    recording = _recording(db, mic, system, ([(1_600, 6_400)], []))
    result = run_recording(recording, seconds=30, sleep=interrupted_sleep)
    meeting, _ = _stored(db, result.meeting_id)
    assert result.interrupted and result.utterances == 1
    assert meeting["state"] == "ready"
    assert not mic.is_active() or mic._thread is None


def test_ctrl_c_is_held_off_while_wrapping_up() -> None:
    import signal

    from evra.transcribe.record import ignore_ctrl_c

    before = signal.getsignal(signal.SIGINT)
    with ignore_ctrl_c():
        assert signal.getsignal(signal.SIGINT) == signal.SIG_IGN
    assert signal.getsignal(signal.SIGINT) == before


def test_capture_start_failure_creates_no_meeting(tmp_path: Path) -> None:
    db = _db(tmp_path)
    _, system = _sources(0.5)

    class BrokenMic(FakeSource):
        def start(self) -> None:
            raise CaptureError("no microphone", "plug one in")

    mic = BrokenMic(np.zeros((1600, 1), dtype=np.float32), 16_000)
    with pytest.raises(CaptureError):
        run_recording(_recording(db, mic, system), seconds=1)
    conn = connect(db)
    try:
        assert MeetingStore(conn).latest_meeting_id() is None
    finally:
        conn.close()


def test_levels_are_reported_for_both_channels(tmp_path: Path) -> None:
    db = _db(tmp_path)
    mic, system = _sources(0.6)
    levels: dict[int, list[float]] = {0: [], 1: []}
    recording = _recording(db, mic, system, on_level=lambda ch, v: levels[ch].append(v))
    run_recording(recording, seconds=0.7)
    assert levels[0] and levels[1]
    assert max(levels[0]) > 0.5
    assert all(0.0 <= v <= 1.0 for v in levels[0] + levels[1])


def test_summary_only_claims_no_speech_when_none_was_detected() -> None:
    from evra.transcribe.live import TranscriberStats
    from evra.transcribe.record import RecordingResult, summary_lines

    silent = RecordingResult("m", 0, None, TranscriberStats(0, 0, 0, 0, 0), False)
    failed = RecordingResult("m", 0, None, TranscriberStats(3, 0, 3, 3000, 10), False)
    leftover = RecordingResult(
        "m", 2, None, TranscriberStats(5, 2, 0, 5000, 10, unprocessed=3, drained=False), False
    )
    assert "no speech detected" in "\n".join(summary_lines(silent))
    failed_text = "\n".join(summary_lines(failed))
    assert "no speech detected" not in failed_text and "3 failed" in failed_text
    assert "3 segments were still waiting" in "\n".join(summary_lines(leftover))
```

`tests/unit/transcribe/test_recording.py`:

```python
from pathlib import Path

import numpy as np
import pytest

from evra.paths import AppPaths
from evra.transcribe.recording import RecordingKit, frame_level


def test_frame_level_maps_minus_60_to_0_dbfs_onto_0_to_1() -> None:
    assert frame_level(np.zeros(160, dtype=np.int16)) == 0.0
    assert frame_level(np.full(160, 32767, dtype=np.int16)) == pytest.approx(1.0, abs=1e-3)
    assert frame_level(np.full(160, 3277, dtype=np.int16)) == pytest.approx(40 / 60, abs=1e-3)
    assert frame_level(np.zeros(0, dtype=np.int16)) == 0.0


class FakeAsr:
    def __init__(self) -> None:
        self.warmups = 0
        self.stopped = False

    def warm_up(self) -> None:
        self.warmups += 1

    def stop(self) -> None:
        self.stopped = True


def test_the_kit_loads_once_and_stops_the_worker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[AppPaths] = []

    def fake_models(paths: AppPaths) -> dict[str, Path]:
        calls.append(paths)
        return {"silero-vad": tmp_path}

    monkeypatch.setattr("evra.transcribe.recording.ensure_speech_models", fake_models)
    asr = FakeAsr()
    kit = RecordingKit(AppPaths.under(tmp_path), asr=asr)  # type: ignore[arg-type]
    kit.prepare()
    kit.prepare()
    assert len(calls) == 1 and asr.warmups == 1
    kit.close()
    assert asr.stopped
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/integration/test_record.py tests/unit/transcribe/test_recording.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'evra.transcribe.recording'`.

- [ ] **Step 3: Implement the core**

`src/evra/transcribe/recording.py`:

```python
"""One live 1:1 recording: capture -> voice detection -> live transcript (M3a), shared by
`evra record` and the window (M3c spec §3.1).

Capture opens first and the meeting is created only once it runs, so a missing or busy
microphone never leaves an empty meeting behind. Segments cut in the moment before the
transcriber exists are held and handed over in order.
"""

from __future__ import annotations

import math
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from evra.asr.parakeet import PARAKEET_ID
from evra.audio.frames import Frames, Int16Array
from evra.audio.vad import SpeechSegment, SpeechSegmenter, silero_vad
from evra.capture.devices import resolve_mic
from evra.capture.session import CaptureHealth, CaptureSession
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance, now_ms
from evra.transcribe.cli import ensure_speech_models
from evra.transcribe.live import LiveTranscriber, TranscriberStats
from evra.workers.asr import AsrClient, Transcriber

SILENCE_DB = -60.0
UtteranceListener = Callable[[Utterance], None]
LevelListener = Callable[[int, float], None]


@dataclass(frozen=True)
class RecordingResult:
    meeting_id: str
    utterances: int
    health: CaptureHealth | None
    stats: TranscriberStats
    interrupted: bool


def frame_level(pcm: Int16Array) -> float:
    """Loudness of one frame on 0..1 (-60 dBFS -> 0, 0 dBFS -> 1) for the level meters.
    Only this number leaves the capture thread, never the audio."""
    if len(pcm) == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(np.square(pcm.astype(np.float32) / 32768.0))))
    if rms <= 1e-6:
        return 0.0
    db = 20 * math.log10(rms)
    return min(1.0, max(0.0, (db - SILENCE_DB) / -SILENCE_DB))


class LiveRecording:
    def __init__(
        self,
        *,
        session: CaptureSession,
        segmenters: Mapping[int, SpeechSegmenter],
        asr: Transcriber,
        db_path: Path,
        title: str,
        situation: str,
        on_utterance: UtteranceListener | None = None,
        on_level: LevelListener | None = None,
    ) -> None:
        self._session = session
        self._segmenters = segmenters
        self._asr = asr
        self._db_path = db_path
        self._title = title
        self._situation = situation
        self._on_utterance = on_utterance
        self._on_level = on_level
        self._lock = threading.Lock()
        self._live: LiveTranscriber | None = None
        self._pending: list[SpeechSegment] = []
        self.meeting_id: str | None = None
        self.started_at_ms: int | None = None

    def _on_frames(self, frames: Frames) -> None:  # runs on the capture pipeline thread
        if self._on_level is not None:
            self._on_level(frames.channel, frame_level(frames.pcm))
        for segment in self._segmenters[frames.channel].accept(frames):
            with self._lock:
                if self._live is None:
                    self._pending.append(segment)
                    continue
                live = self._live
            live.submit(segment)

    def start(self) -> str:
        self._session.start(self._on_frames)  # a missing or busy mic fails here: no meeting yet
        try:
            started = now_ms()
            conn = connect(self._db_path)
            try:
                store = MeetingStore(conn)
                meeting_id = store.create_meeting(
                    title=self._title,
                    mode="one_on_one",
                    situation=self._situation,
                    template="one_on_one",
                    started_at_ms=started,
                )
                version_id = store.create_transcript_version(
                    meeting_id, kind="live", model=PARAKEET_ID
                )
            finally:
                conn.close()
            live = LiveTranscriber(
                self._asr, self._db_path, meeting_id=meeting_id, version_id=version_id
            )
            if self._on_utterance is not None:
                live.add_listener(self._on_utterance)
            live.start()
        except BaseException:
            self._session.stop()
            raise
        with self._lock:  # hand held segments over in order, before any newer one
            self._live = live
            for segment in self._pending:
                live.submit(segment)
            self._pending = []
        self.meeting_id, self.started_at_ms = meeting_id, started
        return meeting_id

    def stop(self, *, state: str = "ready") -> RecordingResult:
        live, meeting_id = self._live, self.meeting_id
        if live is None or meeting_id is None:
            raise RuntimeError("the recording has not started")
        health: CaptureHealth | None = None
        try:
            health = self._session.stop()
            for segmenter in self._segmenters.values():
                for segment in segmenter.flush():
                    live.submit(segment)
        finally:  # whatever capture did, keep the queued speech and finish the meeting
            stats = live.stop()
            conn = connect(self._db_path)
            try:
                MeetingStore(conn).finish_meeting(meeting_id, state=state)
            finally:
                conn.close()
        return RecordingResult(meeting_id, stats.utterances, health, stats, False)


class RecordingKit:
    """What a live recording needs, loaded once and kept: speech models, the ASR worker, VAD."""

    def __init__(self, paths: AppPaths, *, asr: AsrClient | None = None) -> None:
        self._paths = paths
        self._asr = asr or AsrClient.for_models(paths.models_dir)
        self._vad_path: Path | None = None
        self._lock = threading.Lock()

    def prepare(self) -> None:
        """Download (first run) and load what recording needs: slow once, then instant."""
        with self._lock:
            if self._vad_path is not None:
                return
            models = ensure_speech_models(self._paths)
            self._asr.warm_up()
            self._vad_path = models["silero-vad"] / "silero_vad.onnx"

    def new_recording(
        self,
        mic: int | str | None,
        *,
        title: str,
        situation: str,
        on_utterance: UtteranceListener | None = None,
        on_level: LevelListener | None = None,
    ) -> LiveRecording:
        from evra.capture.mic import MicSource
        from evra.capture.windows import DefaultOutputWatcher, LoopbackSource

        self.prepare()
        vad_path = self._vad_path
        assert vad_path is not None
        device = mic if isinstance(mic, int) else resolve_mic(mic or "")
        session = CaptureSession(
            MicSource(device), LoopbackSource(), watcher_factory=DefaultOutputWatcher
        )
        segmenters = {ch: SpeechSegmenter(ch, silero_vad(vad_path)) for ch in (0, 1)}
        return LiveRecording(
            session=session,
            segmenters=segmenters,
            asr=self._asr,
            db_path=self._paths.db_path,
            title=title,
            situation=situation,
            on_utterance=on_utterance,
            on_level=on_level,
        )

    def close(self) -> None:
        self._asr.stop()
```

- [ ] **Step 4: Rebuild `record.py` on the core**

Replace `src/evra/transcribe/record.py` from the top of the file down to (and including) the end of `record_command` with the following. Keep `summary_lines` exactly as it is.

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/integration/test_record.py tests/unit/transcribe -q`
Expected: PASS.

- [ ] **Step 6: Try the CLI for real**

1. Run `uv run evra record 15` while a video with speech plays.
   Expected: live lines, then the summary line, as before M3c.
2. Run `uv run evra record 5 --mic "no such mic"`.
   Expected: `microphone 'no such mic' is not connected`, a `Fix:` line, exit code 2, and no new meeting.

- [ ] **Step 7: Commit**

```bash
uv run ruff format src/evra/transcribe tests/integration/test_record.py tests/unit/transcribe
uv run python tools/check.py   # must show no FAIL
git add src/evra/transcribe/recording.py src/evra/transcribe/record.py tests/integration/test_record.py tests/unit/transcribe/test_recording.py
git commit -m "refactor: one live recording core for evra record and the window"
git push
```

---

### Task 3: Meeting queries and JSON views for the window

**Files:**
- Modify: `src/evra/store/meetings.py` (three methods)
- Create: `src/evra/services/__init__.py`, `src/evra/services/views.py`
- Test: `tests/unit/test_meeting_lists.py`, `tests/unit/services/__init__.py`, `tests/unit/services/test_views.py`

**Interfaces:**
- Consumes: `MeetingStore`, `Utterance`, `now_ms`; `NoteStore.current_note -> StoredNote | None`, `SUMMARY`; `load_template(id) -> Template` (raises `KeyError`); `speaker_label(channel)`.
- Produces:
  - `MeetingStore.list_meetings() -> list[dict[str, Any]]` — newest first, keys `id, title, started_at, ended_at, state, mode, has_note` (`has_note` is 0/1);
  - `MeetingStore.rename_meeting(meeting_id: str, title: str) -> bool`;
  - `MeetingStore.recover_after_restart() -> int` — `processing` → `ready`, `recording` → `failed`; returns how many changed;
  - `meeting_summary(row: Mapping[str, Any]) -> dict[str, Any]` — `{id, title, started_at, duration_ms, state, has_note}`;
  - `utterance_view(u: Utterance) -> dict[str, Any]` — `{id, channel, speaker, start_ms, end_ms, text}`;
  - `note_view(note: StoredNote, utterances: Sequence[Utterance]) -> dict[str, Any]` — `{model, sections: [{id, title, blocks: [{text, citations: [{utterance_id, start_ms}]}]}]}`;
  - `meeting_detail(conn, meeting_id) -> dict[str, Any] | None` — `{meeting, utterances, note}`;
  - `clean_title(title: str) -> str | None` — whitespace collapsed, 1–200 characters, else `None`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_meeting_lists.py`:

```python
import sqlite3
from pathlib import Path

import pytest

from evra.notes.validate import CheckedBullet, CheckedNote
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _meeting(store: MeetingStore, title: str, started: int) -> str:
    return store.create_meeting(
        title=title,
        mode="one_on_one",
        situation="call_headphones",
        template="one_on_one",
        started_at_ms=started,
    )


def test_meetings_are_listed_newest_first_with_a_note_flag(conn: sqlite3.Connection) -> None:
    store = MeetingStore(conn)
    old = _meeting(store, "Old", 1_000)
    new = _meeting(store, "New", 2_000)
    version = store.create_transcript_version(old, kind="live", model="fake")
    note = CheckedNote((CheckedBullet("Done.", ("u",)),), (), 1, 0, {})
    NoteStore(conn).save_generation(
        meeting_id=old,
        transcript_version_id=version,
        note=note,
        provider="fake",
        model="fake",
        prompt_version="a1-v1",
        template="one_on_one",
        tokens_in=1,
        tokens_out=1,
    )
    rows = store.list_meetings()
    assert [(r["id"], r["title"], bool(r["has_note"])) for r in rows] == [
        (new, "New", False),
        (old, "Old", True),
    ]


def test_rename_reports_whether_the_meeting_exists(conn: sqlite3.Connection) -> None:
    store = MeetingStore(conn)
    mid = _meeting(store, "Recording", 1_000)
    assert store.rename_meeting(mid, "Sync with Priya") is True
    assert store.get_meeting(mid)["title"] == "Sync with Priya"
    assert store.rename_meeting("nope", "x") is False


def test_meetings_left_mid_way_by_a_closed_app_are_recovered(conn: sqlite3.Connection) -> None:
    store = MeetingStore(conn)
    recording = _meeting(store, "a", 1_000)
    processing = _meeting(store, "b", 2_000)
    store.finish_meeting(processing, state="processing")
    done = _meeting(store, "c", 3_000)
    store.finish_meeting(done)
    assert store.recover_after_restart() == 2
    assert store.get_meeting(recording)["state"] == "failed"
    assert store.get_meeting(recording)["ended_at"] is not None
    assert store.get_meeting(processing)["state"] == "ready"
    assert store.get_meeting(done)["state"] == "ready"
```

`tests/unit/services/__init__.py`: empty.

`tests/unit/services/test_views.py`:

```python
import json
import sqlite3
from pathlib import Path

import pytest

from evra.notes.validate import CheckedBullet, CheckedNote, CheckedSection
from evra.services.views import clean_title, meeting_detail, meeting_summary
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def test_detail_has_labelled_lines_and_note_sections_with_citation_times(
    conn: sqlite3.Connection,
) -> None:
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="Weekly 1:1", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    them = store.add_utterance(
        version_id=vid,
        meeting_id=mid,
        channel=1,
        start_ms=65_000,
        end_ms=70_000,
        text="Marketing wants October 14.",
    )
    you = store.add_utterance(
        version_id=vid,
        meeting_id=mid,
        channel=0,
        start_ms=110_000,
        end_ms=114_000,
        text="I'll send the proposal by Thursday.",
    )
    note = CheckedNote(
        summary=(CheckedBullet("Launch moves to October 14.", (them.id,)),),
        sections=(
            CheckedSection(
                "action_items",
                "Action items",
                (CheckedBullet("You: send the proposal.", (you.id, "gone")),),
            ),
        ),
        kept=2,
        dropped=0,
        drop_reasons={},
    )
    NoteStore(conn).save_generation(
        meeting_id=mid,
        transcript_version_id=vid,
        note=note,
        provider="ollama",
        model="gemma4:12b",
        prompt_version="a1-v1",
        template="one_on_one",
        tokens_in=1,
        tokens_out=1,
    )
    detail = meeting_detail(conn, mid)
    assert detail is not None
    assert detail["meeting"]["has_note"] is True
    assert [(u["speaker"], u["text"]) for u in detail["utterances"]] == [
        ("Them", "Marketing wants October 14."),
        ("You", "I'll send the proposal by Thursday."),
    ]
    assert detail["note"] == {
        "model": "gemma4:12b",
        "sections": [
            {
                "id": "summary",
                "title": "Summary",
                "blocks": [
                    {
                        "text": "Launch moves to October 14.",
                        "citations": [{"utterance_id": them.id, "start_ms": 65_000}],
                    }
                ],
            },
            {
                "id": "action_items",
                "title": "Action items",
                "blocks": [
                    {
                        "text": "You: send the proposal.",
                        "citations": [{"utterance_id": you.id, "start_ms": 110_000}],
                    }
                ],
            },
        ],
    }
    json.dumps(detail)  # everything crosses the bridge as JSON


def test_a_meeting_without_note_or_transcript(conn: sqlite3.Connection) -> None:
    mid = MeetingStore(conn).create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    detail = meeting_detail(conn, mid)
    assert detail is not None
    assert (detail["utterances"], detail["note"], detail["meeting"]["has_note"]) == ([], None, False)


def test_an_unknown_meeting_has_no_detail(conn: sqlite3.Connection) -> None:
    assert meeting_detail(conn, "nope") is None


def test_summary_duration_only_once_finished() -> None:
    base = {"id": "m", "title": "t", "started_at": 1_000, "state": "recording", "has_note": 0}
    assert meeting_summary({**base, "ended_at": None})["duration_ms"] is None
    finished = meeting_summary({**base, "ended_at": 61_000, "state": "ready"})
    assert finished == {
        "id": "m",
        "title": "t",
        "started_at": 1_000,
        "duration_ms": 60_000,
        "state": "ready",
        "has_note": False,
    }


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("  Sync   with Priya ", "Sync with Priya"),
        ("", None),
        ("   ", None),
        ("x" * 200, "x" * 200),
        ("x" * 201, None),
    ],
)
def test_titles_are_tidied_and_bounded(given: str, expected: str | None) -> None:
    assert clean_title(given) == expected
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_meeting_lists.py tests/unit/services -q`
Expected: FAIL — `AttributeError: 'MeetingStore' object has no attribute 'list_meetings'` and `ModuleNotFoundError: No module named 'evra.services'`.

- [ ] **Step 3: Implement**

Add to `MeetingStore` in `src/evra/store/meetings.py`, after `current_transcript_version`:

```python
    def list_meetings(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT m.id, m.title, m.started_at, m.ended_at, m.state, m.mode,"
            " EXISTS(SELECT 1 FROM generation g WHERE g.meeting_id = m.id AND g.is_current = 1)"
            " AS has_note FROM meeting m ORDER BY m.started_at DESC, m.created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def rename_meeting(self, meeting_id: str, title: str) -> bool:
        cursor = self._conn.execute(
            "UPDATE meeting SET title = ?, updated_at = ? WHERE id = ?",
            (title, now_ms(), meeting_id),
        )
        return cursor.rowcount == 1

    def recover_after_restart(self) -> int:
        """Meetings a closed or crashed app left mid-way keep their transcript: one still
        `processing` its note becomes `ready` (the note can be retried), one still `recording`
        becomes `failed` (its audio may be recoverable from spill later, M2)."""
        now = now_ms()
        noted = self._conn.execute(
            "UPDATE meeting SET state = 'ready', updated_at = ? WHERE state = 'processing'",
            (now,),
        ).rowcount
        cut = self._conn.execute(
            "UPDATE meeting SET state = 'failed', ended_at = COALESCE(ended_at, ?),"
            " updated_at = ? WHERE state = 'recording'",
            (now, now),
        ).rowcount
        return noted + cut
```

`src/evra/services/__init__.py`:

```python
"""What the window drives: meetings, recording and notes (M3c)."""
```

`src/evra/services/views.py`:

```python
"""JSON-ready views of meetings for the window (M3c spec §3.3). Their text goes only to the
user's own window, never to logs."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from evra.notes.templates import load_template
from evra.store.meetings import MeetingStore, Utterance
from evra.store.notes import SUMMARY, NoteStore, StoredNote
from evra.transcribe.labels import speaker_label

MAX_TITLE = 200


def meeting_summary(row: Mapping[str, Any]) -> dict[str, Any]:
    ended = row.get("ended_at")
    return {
        "id": row["id"],
        "title": row["title"],
        "started_at": row["started_at"],
        "duration_ms": None if ended is None else int(ended) - int(row["started_at"]),
        "state": row["state"],
        "has_note": bool(row.get("has_note", False)),
    }


def utterance_view(utterance: Utterance) -> dict[str, Any]:
    return {
        "id": utterance.id,
        "channel": utterance.channel,
        "speaker": speaker_label(utterance.channel),
        "start_ms": utterance.start_ms,
        "end_ms": utterance.end_ms,
        "text": utterance.text,
    }


def note_view(note: StoredNote, utterances: Sequence[Utterance]) -> dict[str, Any]:
    try:
        titles = {s.id: s.title for s in load_template(note.template).sections}
    except KeyError:
        titles = {}
    titles[SUMMARY] = "Summary"
    starts = {u.id: u.start_ms for u in utterances}
    sections: list[dict[str, Any]] = []
    for block in note.blocks:
        if not sections or sections[-1]["id"] != block.section:
            title = titles.get(block.section) or block.section.replace("_", " ").capitalize()
            sections.append({"id": block.section, "title": title, "blocks": []})
        citations = [
            {"utterance_id": c, "start_ms": starts[c]} for c in block.citations if c in starts
        ]
        sections[-1]["blocks"].append({"text": block.text, "citations": citations})
    return {"model": note.model, "sections": sections}


def meeting_detail(conn: sqlite3.Connection, meeting_id: str) -> dict[str, Any] | None:
    store = MeetingStore(conn)
    try:
        meeting = store.get_meeting(meeting_id)
    except KeyError:
        return None
    version = store.current_transcript_version(meeting_id)
    utterances = store.utterances(version) if version else []
    note = NoteStore(conn).current_note(meeting_id)
    return {
        "meeting": meeting_summary({**meeting, "has_note": note is not None}),
        "utterances": [utterance_view(u) for u in utterances],
        "note": note_view(note, utterances) if note is not None else None,
    }


def clean_title(title: str) -> str | None:
    cleaned = " ".join(title.split())
    return cleaned if 1 <= len(cleaned) <= MAX_TITLE else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_meeting_lists.py tests/unit/services tests/unit/test_meetings_store.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run ruff format src/evra/store src/evra/services tests/unit/test_meeting_lists.py tests/unit/services
uv run python tools/check.py   # must show no FAIL
git add src/evra/store/meetings.py src/evra/services tests/unit/test_meeting_lists.py tests/unit/services
git commit -m "feat: meeting list, rename, restart recovery and JSON views for the window"
git push
```

---

### Task 4: One note job for `evra note` and the window

**Files:**
- Create: `src/evra/notes/job.py`
- Modify: `src/evra/notes/cli.py` (uses the job)
- Test: `tests/unit/notes/test_job.py` (the existing `tests/integration/test_note_cli.py` must stay green)

**Interfaces:**
- Consumes: `write_note(...) -> NoteResult` and `NoteError`, `NoteTooLong`, `NoteCutOff`, `NoteInvalid`, `NoTranscript` (M3b); `LlmUnavailable`, `LlmModelMissing`, `LlmTimeout`, `LlmProvider`; `NoteStore.save_generation`.
- Produces:
  - `NothingSupported(dropped: int)` (a `NoteError`, has `.dropped`);
  - `SavedNote(result: NoteResult, generation_id: str)`;
  - `write_and_save(conn, *, meeting: Mapping[str, Any], version_id: str, utterances, template, provider, model, settings) -> SavedNote` — raises `NothingSupported` instead of saving an empty note;
  - `failure_reason(exc: BaseException) -> str` — one of `ollama_down`, `model_missing`, `timeout`, `too_long`, `cut_off`, `invalid`, `nothing_supported`, `no_transcript`, `llm_error`.
- `no_transcript` is an addition to spec §3.2/§4.1: a recording with no speech has nothing to write a note from.

- [ ] **Step 1: Write the failing tests**

`tests/unit/notes/test_job.py`:

```python
import json
import sqlite3
from pathlib import Path

import pytest

from evra.config import LlmSettings
from evra.llm.provider import LlmConfigError, LlmError, LlmModelMissing, LlmTimeout, LlmUnavailable
from evra.notes.job import NothingSupported, failure_reason, write_and_save
from evra.notes.templates import load_template
from evra.notes.writer import NoteCutOff, NoteInvalid, NoteTooLong, NoTranscript
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore
from tests.unit.notes.fakes import FakeProvider

GOOD = json.dumps(
    {
        "summary": [
            {"text": "You finished the search migration on Tuesday.", "citations": ["u:1"]}
        ],
        "sections": [],
    }
)
UNSUPPORTED = json.dumps(
    {"summary": [{"text": "Everyone loved the cake.", "citations": ["u:1"]}], "sections": []}
)


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = connect(tmp_path / "evra.db")
    migrate(c)
    return c


def _save(conn: sqlite3.Connection, reply: str) -> str:
    store = MeetingStore(conn)
    mid = store.latest_meeting_id() or store.create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.current_transcript_version(mid)
    if vid is None:
        vid = store.create_transcript_version(mid, kind="live", model="fake")
        store.add_utterance(
            version_id=vid,
            meeting_id=mid,
            channel=0,
            start_ms=0,
            end_ms=4_000,
            text="I finished the search migration on Tuesday.",
        )
    write_and_save(
        conn,
        meeting=store.get_meeting(mid),
        version_id=vid,
        utterances=store.utterances(vid),
        template=load_template("one_on_one"),
        provider=FakeProvider([reply]),
        model="fake:1b",
        settings=LlmSettings(),
    )
    return mid


def test_a_supported_note_is_saved_as_current(conn: sqlite3.Connection) -> None:
    mid = _save(conn, GOOD)
    note = NoteStore(conn).current_note(mid)
    assert note is not None and note.model == "fake:1b"


def test_a_note_with_nothing_supported_is_refused_and_the_old_one_kept(
    conn: sqlite3.Connection,
) -> None:
    mid = _save(conn, GOOD)
    before = NoteStore(conn).current_note(mid)
    with pytest.raises(NothingSupported) as caught:
        _save(conn, UNSUPPORTED)
    assert caught.value.dropped == 1
    assert NoteStore(conn).current_note(mid) == before


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (LlmUnavailable("down"), "ollama_down"),
        (LlmModelMissing("gemma4:12b"), "model_missing"),
        (LlmTimeout("slow"), "timeout"),
        (NoteTooLong(30_000, 24_000), "too_long"),
        (NoteCutOff(4096), "cut_off"),
        (NoteInvalid("m"), "invalid"),
        (NothingSupported(3), "nothing_supported"),
        (NoTranscript("none"), "no_transcript"),
        (LlmConfigError("not local"), "llm_error"),
        (LlmError("HTTP 500"), "llm_error"),
        (RuntimeError("anything"), "llm_error"),
    ],
)
def test_every_failure_has_a_fixed_reason_code(error: BaseException, reason: str) -> None:
    assert failure_reason(error) == reason
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/notes/test_job.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'evra.notes.job'`.

- [ ] **Step 3: Implement**

`src/evra/notes/job.py`:

```python
"""Write a stored meeting's note and keep it (M3b rules), shared by `evra note` and the
window (M3c). An empty note is never saved, so it can never hide an earlier one."""

from __future__ import annotations

import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evra.config import LlmSettings
from evra.llm.provider import LlmModelMissing, LlmProvider, LlmTimeout, LlmUnavailable
from evra.notes.templates import Template
from evra.notes.writer import (
    NoteCutOff,
    NoteError,
    NoteInvalid,
    NoteResult,
    NoteTooLong,
    NoTranscript,
    write_note,
)
from evra.store.meetings import Utterance
from evra.store.notes import NoteStore


class NothingSupported(NoteError):
    def __init__(self, dropped: int) -> None:
        super().__init__(f"{dropped} points dropped as unsupported")
        self.dropped = dropped


@dataclass(frozen=True)
class SavedNote:
    result: NoteResult
    generation_id: str


_REASONS: tuple[tuple[type[BaseException], str], ...] = (
    (LlmUnavailable, "ollama_down"),
    (LlmModelMissing, "model_missing"),
    (LlmTimeout, "timeout"),
    (NoteTooLong, "too_long"),
    (NoteCutOff, "cut_off"),
    (NoteInvalid, "invalid"),
    (NothingSupported, "nothing_supported"),
    (NoTranscript, "no_transcript"),
)


def failure_reason(exc: BaseException) -> str:
    """A fixed code the window turns into a sentence (M3c spec §4.1); never the error's text."""
    for kind, reason in _REASONS:
        if isinstance(exc, kind):
            return reason
    return "llm_error"


def write_and_save(
    conn: sqlite3.Connection,
    *,
    meeting: Mapping[str, Any],
    version_id: str,
    utterances: Sequence[Utterance],
    template: Template,
    provider: LlmProvider,
    model: str,
    settings: LlmSettings,
) -> SavedNote:
    result = write_note(
        provider,
        model=model,
        meeting=meeting,
        utterances=utterances,
        template=template,
        settings=settings,
    )
    if result.note.kept == 0:  # never replace a usable note with an empty one
        raise NothingSupported(result.note.dropped)
    generation_id = NoteStore(conn).save_generation(
        meeting_id=str(meeting["id"]),
        transcript_version_id=version_id,
        note=result.note,
        provider=provider.name,
        model=result.model,
        prompt_version=result.prompt_version,
        template=template.id,
        tokens_in=result.tokens_in,
        tokens_out=result.tokens_out,
    )
    return SavedNote(result, generation_id)
```

In `src/evra/notes/cli.py`:

1. Change the import `from evra.notes.writer import NoteCutOff, NoteInvalid, NoteTooLong, write_note` to:

```python
from evra.notes.job import NothingSupported, write_and_save
from evra.notes.writer import NoteCutOff, NoteInvalid, NoteTooLong
```

2. Inside `_run`'s `try:` block, replace the `result = write_note(...)` call with:

```python
        saved = write_and_save(
            conn,
            meeting=meeting,
            version_id=version_id,
            utterances=utterances,
            template=template,
            provider=llm,
            model=model,
            settings=settings,
        )
```

3. Add this handler right before `except LlmError as exc:`:

```python
    except NothingSupported as exc:  # never replace a usable note with an empty one
        _err(
            f"Nothing in the note could be checked against the transcript"
            f" ({exc.dropped} points dropped); nothing saved, any earlier note is kept."
            " Try another model with --model."
        )
        return 1
```

4. Replace everything from the old `if result.note.kept == 0:` block down to the end of the `generation_id = notes.save_generation(...)` call with:

```python
    result, generation_id = saved.result, saved.generation_id
    notes = NoteStore(conn)
```

(`stored = notes.current_note(meeting_id)` and the printing below stay as they are.) Remove any import that is now unused (ruff F401 will name it).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/notes tests/integration/test_note_cli.py -q`
Expected: PASS — including `test_a_note_with_nothing_supported_is_not_saved_and_keeps_the_previous_one`.

- [ ] **Step 5: Commit**

```bash
uv run ruff format src/evra/notes tests/unit/notes
uv run python tools/check.py   # must show no FAIL
git add src/evra/notes/job.py src/evra/notes/cli.py tests/unit/notes/test_job.py
git commit -m "refactor: one note job with fixed failure codes for evra note and the window"
git push
```

---

### Task 5: `MeetingService` — one recording at a time, then the note

**Files:**
- Create: `src/evra/services/meetings.py`
- Test: `tests/unit/services/test_meeting_service.py`

**Interfaces:**
- Consumes:
  - `LiveRecording` / `RecordingKit` / `RecordingResult` (Task 2) — through the `Recording` and `Kit` protocols below;
  - `utterance_view` (Task 3); `write_and_save`, `failure_reason` (Task 4);
  - `MeetingStore.get_meeting`, `current_transcript_version`, `utterances`, `finish_meeting`; `load_template`; `save_settings`;
  - `CaptureError` (has `.hint`), `ModelError`, `WorkerError`, `WorkerCrashed`, `LlmError`, `LlmModelMissing` (has `.model`), `NoteError`, `NoTranscript`.
- Produces:
  - `MeetingService(*, paths, settings, emit, kit, provider_factory=OllamaProvider, level_interval_s=0.1)`;
  - `.mic_name -> str` (property), `.state() -> dict`, `.start(mic_name: str) -> dict`, `.stop() -> dict`, `.write_note(meeting_id: str) -> dict`, `.shutdown() -> None`.
  - Replies: `start` → `{"ok": True, "meeting_id"}` or `{"ok": False, "reason": "busy" | "closing"}` or `{"ok": False, "error", "hint"}`; `stop` / `write_note` → `{"ok": bool}`.
  - Events (spec §3.2): `recording.state {state, meeting_id?, started_at?}`, `recording.levels {you, them}`, `transcript.utterance {meeting_id, id, channel, speaker, start_ms, end_ms, text}`, `recording.finished {meeting_id, utterances, failed_segments, hints}`, `note.stage {meeting_id, stage: "writing"}`, `note.ready {meeting_id}`, `note.failed {meeting_id, reason, model?}`.
- **Rules:** states `idle → loading → recording → stopping → processing → idle`. A call that doesn't fit the state is refused and answered with the current `recording.state` event. Record is refused while a note is written (`processing`). Nothing slow and no `emit` runs while holding the lock. On shutdown a running recording is stopped and saved, no note is written, and the kit is closed.

- [ ] **Step 1: Write the failing tests**

`tests/unit/services/test_meeting_service.py`:

```python
import json
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from evra.asr.engine import Segment
from evra.audio.vad import SpeechSegmenter
from evra.capture.fake import FakeSource
from evra.capture.session import CaptureSession
from evra.capture.sources import MicUnavailableError
from evra.config import LlmSettings, Settings, load_settings
from evra.llm.provider import ChatMessage, ChatResult, LlmModelMissing, LlmProvider, LlmUnavailable
from evra.modelstore import ModelError
from evra.paths import AppPaths
from evra.services.meetings import MeetingService
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.migrate import migrate
from evra.store.notes import NoteStore
from evra.transcribe.recording import LiveRecording
from tests.unit.audio.test_vad import FakeVad
from tests.unit.notes.fakes import FakeProvider

GOOD = json.dumps(
    {"summary": [{"text": "Some words were said.", "citations": ["u:1"]}], "sections": []}
)


class NumberAsr:
    def transcribe(self, pcm: np.ndarray) -> list[Segment]:
        return [Segment(0, len(pcm) * 1000 // 16_000, "words", ())]


class FakeKit:
    def __init__(
        self,
        paths: AppPaths,
        *,
        speech: bool = True,
        mic_error: Exception | None = None,
        prepare_error: Exception | None = None,
        prepare_delay: float = 0.0,
    ) -> None:
        self.paths, self.speech = paths, speech
        self.mic_error, self.prepare_error, self.prepare_delay = (
            mic_error,
            prepare_error,
            prepare_delay,
        )
        self.mics: list[object] = []
        self.closed = False

    def prepare(self) -> None:
        time.sleep(self.prepare_delay)
        if self.prepare_error is not None:
            raise self.prepare_error

    def new_recording(
        self,
        mic: int | str | None,
        *,
        title: str,
        situation: str,
        on_utterance: Callable[[Utterance], None] | None = None,
        on_level: Callable[[int, float], None] | None = None,
    ) -> LiveRecording:
        self.mics.append(mic)
        if self.mic_error is not None:
            raise self.mic_error
        tone = (0.3 * np.sin(np.arange(16_000 * 3) / 5)).astype(np.float32)
        session = CaptureSession(
            FakeSource(tone, 16_000, name="mic"),
            FakeSource(tone, 16_000, name="out", pads_silence=True),
        )
        script = [(3_200, 9_600)] if self.speech else []
        segmenters = {
            0: SpeechSegmenter(0, FakeVad(script=script)),
            1: SpeechSegmenter(1, FakeVad(script=[])),
        }
        return LiveRecording(
            session=session,
            segmenters=segmenters,
            asr=NumberAsr(),
            db_path=self.paths.db_path,
            title=title,
            situation=situation,
            on_utterance=on_utterance,
            on_level=on_level,
        )

    def close(self) -> None:
        self.closed = True


class Events:
    def __init__(self) -> None:
        self.items: list[tuple[str, dict[str, Any]]] = []
        self._cond = threading.Condition()

    def __call__(self, name: str, payload: Mapping[str, Any]) -> bool:
        with self._cond:
            self.items.append((name, dict(payload)))
            self._cond.notify_all()
        return True

    def wait_for(self, name: str, timeout: float = 10.0, **match: Any) -> dict[str, Any]:
        deadline = time.monotonic() + timeout
        with self._cond:
            while True:
                for n, p in self.items:
                    if n == name and all(p.get(k) == v for k, v in match.items()):
                        return p
                left = deadline - time.monotonic()
                if left <= 0:
                    raise AssertionError(f"no {name} {match}; got {[n for n, _ in self.items]}")
                self._cond.wait(left)

    def names(self) -> list[str]:
        with self._cond:
            return [n for n, _ in self.items]

    def states(self) -> list[str]:
        with self._cond:
            return [p["state"] for n, p in self.items if n == "recording.state"]


class Down(FakeProvider):
    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        raise LlmUnavailable("down")


class NoModel(FakeProvider):
    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        raise LlmModelMissing(model)


def make(
    tmp_path: Path,
    provider: Callable[[LlmSettings], LlmProvider] | None = None,
    **kit: Any,
) -> tuple[MeetingService, Events, FakeKit, AppPaths]:
    paths = AppPaths.under(tmp_path)
    paths.ensure()
    conn = connect(paths.db_path)
    migrate(conn)
    conn.close()
    events, fake_kit = Events(), FakeKit(paths, **kit)
    service = MeetingService(
        paths=paths,
        settings=Settings(),
        emit=events,
        kit=fake_kit,
        provider_factory=provider or (lambda settings: FakeProvider([GOOD])),
        level_interval_s=0.02,
    )
    return service, events, fake_kit, paths


def _db(paths: AppPaths) -> tuple[MeetingStore, NoteStore, Callable[[], None]]:
    conn = connect(paths.db_path)
    return MeetingStore(conn), NoteStore(conn), conn.close


def test_a_full_run_streams_the_transcript_and_writes_the_note(tmp_path: Path) -> None:
    service, events, kit, paths = make(tmp_path)
    reply = service.start("")
    assert reply["ok"] is True
    mid = reply["meeting_id"]
    line = events.wait_for("transcript.utterance")
    assert (line["meeting_id"], line["speaker"], line["text"]) == (mid, "You", "words")
    assert service.stop() == {"ok": True}
    events.wait_for("note.ready", meeting_id=mid)
    events.wait_for("recording.state", state="idle")
    assert events.states() == ["loading", "recording", "stopping", "processing", "idle"]
    finished = events.wait_for("recording.finished")
    assert finished["meeting_id"] == mid and finished["utterances"] >= 1
    names = events.names()
    assert names.index("note.stage") < names.index("note.ready")
    meetings, notes, close = _db(paths)
    try:
        assert meetings.get_meeting(mid)["state"] == "ready"
        assert notes.current_note(mid) is not None
    finally:
        close()
    assert kit.mics == [None]


def test_levels_are_pushed_only_while_recording(tmp_path: Path) -> None:
    service, events, _, _ = make(tmp_path)
    service.start("")
    events.wait_for("recording.levels")
    time.sleep(0.2)
    levels = [p for n, p in events.items if n == "recording.levels"]
    assert any(p["you"] > 0 for p in levels)
    assert all(0.0 <= p["you"] <= 1.0 and 0.0 <= p["them"] <= 1.0 for p in levels)
    service.stop()
    events.wait_for("recording.state", state="idle")
    count = events.names().count("recording.levels")
    time.sleep(0.1)
    assert events.names().count("recording.levels") == count


def test_a_missing_mic_fails_before_any_meeting_exists(tmp_path: Path) -> None:
    error = MicUnavailableError("microphone 'Headset' is not connected", "Pick it again.")
    service, events, _, paths = make(tmp_path, mic_error=error)
    assert service.start("Headset") == {
        "ok": False,
        "error": "microphone 'Headset' is not connected",
        "hint": "Pick it again.",
    }
    assert events.states() == ["loading", "idle"]
    meetings, _, close = _db(paths)
    try:
        assert meetings.latest_meeting_id() is None
    finally:
        close()


def test_a_model_that_will_not_load_is_explained(tmp_path: Path) -> None:
    service, events, _, _ = make(tmp_path, prepare_error=ModelError("checksum mismatch"))
    reply = service.start("")
    assert reply["ok"] is False and "ModelError" in reply["error"]
    assert events.states() == ["loading", "idle"]


def test_record_twice_and_stop_while_idle_are_refused(tmp_path: Path) -> None:
    service, events, _, _ = make(tmp_path)
    assert service.stop() == {"ok": False}
    assert events.states() == ["idle"]
    assert service.start("")["ok"] is True
    assert service.start("") == {"ok": False, "reason": "busy"}
    assert events.states()[-1] == "recording"
    service.stop()
    events.wait_for("note.ready")


def test_two_record_clicks_at_once_make_one_recording(tmp_path: Path) -> None:
    service, events, kit, _ = make(tmp_path, prepare_delay=0.2)
    replies: list[dict[str, Any]] = []
    threads = [threading.Thread(target=lambda: replies.append(service.start(""))) for _ in "ab"]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(r["ok"] for r in replies) == [False, True]
    assert len(kit.mics) == 1
    service.stop()
    events.wait_for("note.ready")


def test_a_failed_note_keeps_the_transcript_and_says_why(tmp_path: Path) -> None:
    service, events, _, paths = make(tmp_path, provider=lambda s: Down([]))
    mid = service.start("")["meeting_id"]
    events.wait_for("transcript.utterance")
    service.stop()
    assert events.wait_for("note.failed") == {"meeting_id": mid, "reason": "ollama_down"}
    events.wait_for("recording.state", state="idle")
    meetings, notes, close = _db(paths)
    try:
        assert meetings.get_meeting(mid)["state"] == "ready"
        version = meetings.current_transcript_version(mid)
        assert version is not None and meetings.utterances(version)
        assert notes.current_note(mid) is None
    finally:
        close()


def test_a_missing_model_is_named(tmp_path: Path) -> None:
    service, events, _, _ = make(tmp_path, provider=lambda s: NoModel([]))
    service.start("")
    events.wait_for("transcript.utterance")
    service.stop()
    failed = events.wait_for("note.failed")
    assert (failed["reason"], failed["model"]) == ("model_missing", "gemma4:12b")


def test_retry_writes_the_note_for_a_finished_meeting(tmp_path: Path) -> None:
    providers: list[LlmProvider] = [Down([]), FakeProvider([GOOD])]
    service, events, _, _ = make(tmp_path, provider=lambda s: providers.pop(0))
    mid = service.start("")["meeting_id"]
    events.wait_for("transcript.utterance")
    service.stop()
    events.wait_for("note.failed")
    events.wait_for("recording.state", state="idle")
    assert service.write_note(mid) == {"ok": True}
    events.wait_for("note.ready", meeting_id=mid)


def test_no_speech_means_no_note(tmp_path: Path) -> None:
    service, events, _, _ = make(tmp_path, speech=False)
    mid = service.start("")["meeting_id"]
    time.sleep(0.3)
    service.stop()
    assert events.wait_for("note.failed") == {"meeting_id": mid, "reason": "no_transcript"}


def test_closing_the_window_while_recording_saves_the_meeting(tmp_path: Path) -> None:
    service, events, kit, paths = make(tmp_path)
    mid = service.start("")["meeting_id"]
    events.wait_for("transcript.utterance")
    service.shutdown()
    assert kit.closed
    assert "note.stage" not in events.names()
    assert service.start("") == {"ok": False, "reason": "closing"}
    meetings, _, close = _db(paths)
    try:
        assert meetings.get_meeting(mid)["state"] == "ready"
        version = meetings.current_transcript_version(mid)
        assert version is not None and meetings.utterances(version)
    finally:
        close()


def test_closing_while_loading_starts_nothing(tmp_path: Path) -> None:
    service, _, kit, paths = make(tmp_path, prepare_delay=0.3)
    replies: list[dict[str, Any]] = []
    thread = threading.Thread(target=lambda: replies.append(service.start("")))
    thread.start()
    time.sleep(0.1)
    service.shutdown()
    thread.join()
    assert replies == [{"ok": False, "reason": "closing"}]
    assert kit.mics == []
    meetings, _, close = _db(paths)
    try:
        assert meetings.latest_meeting_id() is None
    finally:
        close()


def test_the_chosen_mic_is_remembered(tmp_path: Path) -> None:
    service, events, kit, paths = make(tmp_path)
    service.start("Headset (realme Buds Air7)")
    assert kit.mics == ["Headset (realme Buds Air7)"]
    assert service.mic_name == "Headset (realme Buds Air7)"
    assert load_settings(paths.settings_file).mic_name == "Headset (realme Buds Air7)"
    service.stop()
    events.wait_for("note.ready")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/services/test_meeting_service.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'evra.services.meetings'`.

- [ ] **Step 3: Implement**

`src/evra/services/meetings.py`:

```python
"""The window's meeting flow (M3c spec §3.1): one recording at a time, then its note
(BUILD.md §7.3, D16).

Bridge calls arrive on their own threads (pywebview), so the state lives under one lock and
nothing slow, and no event, runs while holding it. Events carry transcript text only to the
user's own window; logs get codes and counts.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, Literal, Protocol

import structlog

from evra.capture.sources import CaptureError
from evra.config import LlmSettings, Settings, save_settings
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import LlmError, LlmModelMissing, LlmProvider
from evra.modelstore import ModelError
from evra.notes.job import failure_reason, write_and_save
from evra.notes.templates import load_template
from evra.notes.writer import NoteError, NoTranscript
from evra.paths import AppPaths
from evra.services.views import utterance_view
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.transcribe.recording import RecordingResult
from evra.workers.protocol import WorkerCrashed, WorkerError

log = structlog.get_logger(__name__)

State = Literal["idle", "loading", "recording", "stopping", "processing"]
Emit = Callable[[str, Mapping[str, Any]], object]


class Recording(Protocol):
    meeting_id: str | None
    started_at_ms: int | None

    def start(self) -> str: ...

    def stop(self, *, state: str = "ready") -> RecordingResult: ...


class Kit(Protocol):
    def prepare(self) -> None: ...

    def new_recording(
        self,
        mic: int | str | None,
        *,
        title: str,
        situation: str,
        on_utterance: Callable[[Utterance], None] | None = None,
        on_level: Callable[[int, float], None] | None = None,
    ) -> Recording: ...

    def close(self) -> None: ...


class MeetingService:
    def __init__(
        self,
        *,
        paths: AppPaths,
        settings: Settings,
        emit: Emit,
        kit: Kit,
        provider_factory: Callable[[LlmSettings], LlmProvider] = OllamaProvider,
        level_interval_s: float = 0.1,
    ) -> None:
        self._paths = paths
        self._settings = settings
        self._emit = emit
        self._kit = kit
        self._provider_factory = provider_factory
        self._level_interval = level_interval_s
        self._lock = threading.Lock()
        self._state: State = "idle"
        self._meeting_id: str | None = None
        self._started_at: int | None = None
        self._recording: Recording | None = None
        self._closing = False
        self._levels = [0.0, 0.0]
        self._ticker_stop = threading.Event()
        self._ticker: threading.Thread | None = None

    @property
    def mic_name(self) -> str:
        return self._settings.mic_name

    def state(self) -> dict[str, Any]:
        with self._lock:
            return self._payload()

    # --- recording -------------------------------------------------------------------------

    def start(self, mic_name: str) -> dict[str, Any]:
        with self._lock:
            refused = "closing" if self._closing else "" if self._state == "idle" else "busy"
            payload = self._payload() if refused else self._set("loading")
        self._announce(payload)
        if refused:
            return {"ok": False, "reason": refused}
        try:
            self._kit.prepare()
            if self._is_closing():  # the window closed while speech recognition loaded
                return self._back_to_idle({"ok": False, "reason": "closing"})
            recording = self._kit.new_recording(
                mic_name or None,
                title=f"Recording {datetime.now():%Y-%m-%d %H:%M}",
                situation=self._settings.default_situation,
                on_utterance=self._on_utterance,
                on_level=self._on_level,
            )
            meeting_id = recording.start()
        except CaptureError as exc:
            log.info("recording_not_started", error=type(exc).__name__)
            return self._back_to_idle({"ok": False, "error": str(exc), "hint": exc.hint})
        except (ModelError, WorkerError, WorkerCrashed, OSError) as exc:
            log.warning("recording_not_started", error=type(exc).__name__)
            message = f"Could not start recording ({type(exc).__name__}): {exc}"
            return self._back_to_idle({"ok": False, "error": message, "hint": ""})
        with self._lock:
            closing = self._closing
            if not closing:
                self._recording = recording
                payload = self._set("recording", meeting_id, recording.started_at_ms)
        if closing:  # the window closed while capture was opening: keep what exists
            recording.stop(state="ready")
            return self._back_to_idle({"ok": False, "reason": "closing"})
        self._remember_mic(mic_name)
        self._start_ticker()
        self._announce(payload)
        return {"ok": True, "meeting_id": meeting_id}

    def stop(self) -> dict[str, Any]:
        with self._lock:
            recording = self._recording if self._state == "recording" else None
            if recording is not None:
                payload = self._set("stopping", self._meeting_id, self._started_at)
            else:
                payload = self._payload()
        self._announce(payload)
        if recording is None:
            return {"ok": False}
        self._stop_ticker()
        try:
            result = recording.stop(state="processing")
        except Exception as exc:  # capture failed while closing: the meeting is still kept
            log.warning("recording_stop_failed", error=type(exc).__name__)
            if recording.meeting_id is not None:
                self._finish(recording.meeting_id)
            with self._lock:
                self._recording = None
            return self._back_to_idle({"ok": False})
        with self._lock:
            self._recording = None
        hints = list(result.health.hints) if result.health is not None else []
        self._emit(
            "recording.finished",
            {
                "meeting_id": result.meeting_id,
                "utterances": result.utterances,
                "failed_segments": result.stats.failures,
                "hints": hints,
            },
        )
        with self._lock:
            closing = self._closing
            if not closing:
                payload = self._set("processing", result.meeting_id)
        if closing:  # never write a note while the app shuts down
            self._finish(result.meeting_id)
            return self._back_to_idle({"ok": True})
        self._announce(payload)
        self._start_note_job(result.meeting_id)
        return {"ok": True}

    # --- notes -----------------------------------------------------------------------------

    def write_note(self, meeting_id: str) -> dict[str, Any]:
        with self._lock:
            allowed = self._state == "idle" and not self._closing
            payload = self._set("processing", meeting_id) if allowed else self._payload()
        self._announce(payload)
        if not allowed:
            return {"ok": False}
        self._start_note_job(meeting_id)
        return {"ok": True}

    def _start_note_job(self, meeting_id: str) -> None:
        self._emit("note.stage", {"meeting_id": meeting_id, "stage": "writing"})
        threading.Thread(
            target=self._note_job, args=(meeting_id,), name="note-writer", daemon=True
        ).start()

    def _note_job(self, meeting_id: str) -> None:
        try:
            conn = connect(self._paths.db_path)
            try:
                event = self._write(conn, meeting_id)
                MeetingStore(conn).finish_meeting(meeting_id, state="ready")
            finally:
                conn.close()
        except Exception as exc:  # e.g. the database is busy: say so and stay usable
            log.warning("note_job_failed", error=type(exc).__name__)
            event = ("note.failed", {"meeting_id": meeting_id, "reason": "llm_error"})
        with self._lock:
            payload = self._set("idle")
        self._emit(*event)
        self._announce(payload)

    def _write(
        self, conn: sqlite3.Connection, meeting_id: str
    ) -> tuple[str, dict[str, Any]]:
        store = MeetingStore(conn)
        meeting = store.get_meeting(meeting_id)
        version_id = store.current_transcript_version(meeting_id)
        utterances = store.utterances(version_id) if version_id else []
        llm = self._settings.llm
        try:
            if version_id is None or not utterances:
                raise NoTranscript("no transcript")
            write_and_save(
                conn,
                meeting=meeting,
                version_id=version_id,
                utterances=utterances,
                template=load_template(str(meeting["template"])),
                provider=self._provider_factory(llm),
                model=llm.model,
                settings=llm,
            )
        except (LlmError, NoteError) as exc:
            reason = failure_reason(exc)
            log.info("note_not_written", reason=reason)
            failed: dict[str, Any] = {"meeting_id": meeting_id, "reason": reason}
            if isinstance(exc, LlmModelMissing):
                failed["model"] = exc.model
            return "note.failed", failed
        return "note.ready", {"meeting_id": meeting_id}

    # --- shutdown --------------------------------------------------------------------------

    def shutdown(self) -> None:
        """The window closed: save a running recording (no note), then stop the ASR worker."""
        with self._lock:
            self._closing = True
            recording = self._recording if self._state == "recording" else None
            self._recording = None
        self._stop_ticker()
        if recording is not None:
            try:
                recording.stop(state="ready")
            except Exception as exc:
                log.warning("recording_stop_failed", error=type(exc).__name__)
            with self._lock:
                self._set("idle")
        self._kit.close()

    # --- helpers ---------------------------------------------------------------------------

    def _payload(self) -> dict[str, Any]:  # the caller holds the lock
        payload: dict[str, Any] = {"state": self._state}
        if self._meeting_id is not None:
            payload["meeting_id"] = self._meeting_id
            payload["started_at"] = self._started_at
        return payload

    def _set(
        self, state: State, meeting_id: str | None = None, started_at: int | None = None
    ) -> dict[str, Any]:  # the caller holds the lock
        self._state, self._meeting_id, self._started_at = state, meeting_id, started_at
        return self._payload()

    def _announce(self, payload: dict[str, Any]) -> None:
        self._emit("recording.state", payload)

    def _back_to_idle(self, reply: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            payload = self._set("idle")
        self._announce(payload)
        return reply

    def _is_closing(self) -> bool:
        with self._lock:
            return self._closing

    def _finish(self, meeting_id: str) -> None:
        try:
            conn = connect(self._paths.db_path)
            try:
                MeetingStore(conn).finish_meeting(meeting_id, state="ready")
            finally:
                conn.close()
        except Exception as exc:
            log.warning("meeting_not_finished", error=type(exc).__name__)

    def _remember_mic(self, mic_name: str) -> None:
        if mic_name == self._settings.mic_name:
            return
        self._settings = self._settings.model_copy(update={"mic_name": mic_name})
        try:
            save_settings(self._paths.settings_file, self._settings)
        except OSError as exc:
            log.warning("settings_not_saved", error=type(exc).__name__)

    def _on_utterance(self, utterance: Utterance) -> None:  # the transcriber's thread
        self._emit(
            "transcript.utterance", {"meeting_id": utterance.meeting_id, **utterance_view(utterance)}
        )

    def _on_level(self, channel: int, level: float) -> None:  # the capture thread
        if channel in (0, 1):
            self._levels[channel] = level

    def _start_ticker(self) -> None:
        self._levels = [0.0, 0.0]
        self._ticker_stop.clear()
        self._ticker = threading.Thread(target=self._tick, name="level-meter", daemon=True)
        self._ticker.start()

    def _tick(self) -> None:
        while not self._ticker_stop.wait(self._level_interval):
            you, them = self._levels
            self._emit("recording.levels", {"you": round(you, 3), "them": round(them, 3)})

    def _stop_ticker(self) -> None:
        self._ticker_stop.set()
        ticker, self._ticker = self._ticker, None
        if ticker is not None:
            ticker.join(timeout=1)
```

Notes for the implementer:
- mypy may report `payload` as possibly undefined after the `if not closing:` blocks; if so, initialise `payload: dict[str, Any] = {}` just before each `with self._lock:` block that assigns it conditionally.
- `OllamaProvider(settings)` matches `Callable[[LlmSettings], LlmProvider]` (its other parameters are keyword-only with defaults).

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/services -q`
Expected: PASS. Run it three times in a row to make sure the thread-based tests are stable.

- [ ] **Step 5: Commit**

```bash
uv run ruff format src/evra/services tests/unit/services
uv run python tools/check.py   # must show no FAIL
git add src/evra/services/meetings.py tests/unit/services/test_meeting_service.py
git commit -m "feat: meeting service runs one recording at a time, then writes its note"
git push
```

---

### Task 6: Bridge calls, safe events and app wiring

**Files:**
- Modify: `src/evra/bridge/api.py`, `src/evra/bridge/events.py`, `src/evra/app.py`
- Test: `tests/unit/test_bridge.py` (updated), `tests/unit/test_app.py` (two tests added)

**Interfaces:**
- Consumes: `MeetingService` (Task 5) through the `Control` protocol below; `meeting_summary`, `meeting_detail`, `clean_title` (Task 3); `MeetingStore.list_meetings`, `rename_meeting`, `recover_after_restart`; `list_mics`, `MicList` (Task 1); `RecordingKit` (Task 2).
- Produces:
  - `BridgeApi(*, app_name, version, bus, control: Control, db_path: Path, mic_lister=list_mics)` with public methods exactly: `app_info`, `get_meeting`, `list_meetings`, `list_mics`, `ping`, `recording_state`, `rename_meeting`, `request_hello`, `start_recording`, `stop_recording`, `write_note`.
  - `list_mics()` → `{default, mics: [str], chosen}` (`chosen` = the remembered mic; an addition to the spec table so the picker can preselect it).
  - `EventBus.detach()`; `EventBus.emit` returns `False` instead of raising when the window is gone.
  - `App` gains `service: MeetingService`; `build_app` recovers stale meetings; `run_app` detaches the bus and calls `service.shutdown()` after the window closes (or fails).

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_bridge.py`:

1. Add these imports and helpers below the existing imports:

```python
import sqlite3
from pathlib import Path

from evra.capture.devices import MicList
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate


class StubControl:
    mic_name = "Headset (realme Buds Air7)"

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def start(self, mic_name: str) -> dict[str, Any]:
        self.calls.append(("start", mic_name))
        return {"ok": True, "meeting_id": "m"}

    def stop(self) -> dict[str, Any]:
        self.calls.append(("stop", None))
        return {"ok": True}

    def write_note(self, meeting_id: str) -> dict[str, Any]:
        self.calls.append(("write_note", meeting_id))
        return {"ok": True}

    def state(self) -> dict[str, Any]:
        return {"state": "idle"}


def _api(tmp_path: Path, bus: EventBus | None = None, **kwargs: Any) -> tuple[BridgeApi, Path]:
    db = tmp_path / "evra.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    api = BridgeApi(
        app_name="Evra",
        version="0.1.0",
        bus=bus or EventBus(),
        control=kwargs.pop("control", StubControl()),
        db_path=db,
        **kwargs,
    )
    return api, db


def _meeting(db: Path, title: str = "Weekly 1:1") -> str:
    conn: sqlite3.Connection = connect(db)
    try:
        return MeetingStore(conn).create_meeting(
            title=title, mode="one_on_one", situation="call_headphones", template="one_on_one"
        )
    finally:
        conn.close()
```

2. Change every existing `BridgeApi(app_name="Evra", version="0.1.0", bus=...)` construction to `_api(tmp_path, bus=...)[0]` (add a `tmp_path: Path` parameter to those tests), and replace the expected list in `test_api_surface_is_only_the_intended_methods` with:

```python
    assert public == [
        "app_info",
        "get_meeting",
        "list_meetings",
        "list_mics",
        "ping",
        "recording_state",
        "rename_meeting",
        "request_hello",
        "start_recording",
        "stop_recording",
        "write_note",
    ]
```

3. Append these tests:

```python
def test_meetings_are_listed_and_opened_as_json(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid = _meeting(db)
    [summary] = api.list_meetings()
    assert (summary["id"], summary["title"], summary["has_note"]) == (mid, "Weekly 1:1", False)
    detail = api.get_meeting(mid)
    assert detail is not None and detail["meeting"]["id"] == mid
    json.dumps(detail)
    assert api.get_meeting("nope") is None
    assert api.get_meeting(42) is None  # type: ignore[arg-type]


def test_mics_include_the_remembered_choice(tmp_path: Path) -> None:
    api, _ = _api(tmp_path, mic_lister=lambda: MicList("Headset", ("Headset", "Array")))
    assert api.list_mics() == {
        "default": "Headset",
        "mics": ["Headset", "Array"],
        "chosen": "Headset (realme Buds Air7)",
    }


def test_mics_that_cannot_be_listed_fall_back_to_the_default(tmp_path: Path) -> None:
    def broken() -> MicList:
        raise OSError("PortAudio not initialised")

    api, _ = _api(tmp_path, mic_lister=broken)
    assert api.list_mics() == {"default": "", "mics": [], "chosen": "Headset (realme Buds Air7)"}


def test_rename_tidies_the_title_and_refuses_bad_input(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid = _meeting(db)
    assert api.rename_meeting(mid, "  Sync   with Priya ") == {"ok": True}
    assert api.list_meetings()[0]["title"] == "Sync with Priya"
    assert api.rename_meeting(mid, "   ") == {"ok": False}
    assert api.rename_meeting(mid, 5) == {"ok": False}  # type: ignore[arg-type]
    assert api.rename_meeting("nope", "x") == {"ok": False}


def test_recording_calls_go_to_the_service_and_bad_input_is_refused(tmp_path: Path) -> None:
    control = StubControl()
    api, _ = _api(tmp_path, control=control)
    assert api.start_recording("Headset") == {"ok": True, "meeting_id": "m"}
    assert api.start_recording(None) == {"ok": False, "reason": "invalid"}  # type: ignore[arg-type]
    assert api.stop_recording() == {"ok": True}
    assert api.write_note("m") == {"ok": True}
    assert api.write_note(["m"]) == {"ok": False}  # type: ignore[arg-type]
    assert api.recording_state() == {"state": "idle"}
    assert control.calls == [("start", "Headset"), ("stop", None), ("write_note", "m")]


def test_events_after_the_window_is_gone_are_dropped(tmp_path: Path) -> None:
    class ClosedWindow:
        def run_js(self, script: str) -> Any:
            raise RuntimeError("window destroyed")

    bus = EventBus()
    bus.attach(ClosedWindow())
    assert bus.emit("recording.state", {"state": "idle"}) is False
    window = FakeWindow()
    bus.attach(window)
    bus.detach()
    assert bus.emit("recording.state", {"state": "idle"}) is False
    assert window.scripts == []


def test_event_text_cannot_close_the_script() -> None:
    script = build_emit_script("transcript.utterance", {"text": "</script><b>x</b>"})
    assert "</script>" not in script
```

In `tests/unit/test_app.py`, append:

```python
def test_build_app_recovers_meetings_left_mid_way(tmp_path: Path) -> None:
    from evra.store.meetings import MeetingStore
    from evra.store.migrate import migrate

    paths = AppPaths.under(tmp_path)
    paths.ensure()
    conn = connect(paths.db_path)
    migrate(conn)
    mid = MeetingStore(conn).create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    conn.close()
    build_app(paths, debug=False)
    conn = connect(paths.db_path)
    try:
        assert MeetingStore(conn).get_meeting(mid)["state"] == "failed"
    finally:
        conn.close()


def test_closing_the_window_shuts_the_meeting_service_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evra.services.meetings import MeetingService

    closed: list[bool] = []
    monkeypatch.setattr(MeetingService, "shutdown", lambda self: closed.append(True))

    def fake_opener(
        *, url: str, api: BridgeApi, bus: EventBus, debug: bool, storage_dir: Path
    ) -> None:
        return None

    paths = AppPaths.under(tmp_path / "home")
    assert run_app(dev=False, debug=False, paths=paths, web_dir=_built_ui(tmp_path), opener=fake_opener) == 0
    assert closed == [True]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/test_bridge.py tests/unit/test_app.py -q`
Expected: FAIL — `BridgeApi.__init__() got an unexpected keyword argument 'control'`, `EventBus` has no `detach`, and the app tests fail on the missing service.

- [ ] **Step 3: Implement**

Replace `src/evra/bridge/api.py` with:

```python
"""Methods React can call as window.pywebview.api.<name>(...) (M0, M3c spec §3.3).

pywebview exposes every public attribute, so keep state in underscore attributes. Each call
runs on its own thread, so each opens its own database connection. Arguments come from
JavaScript: anything of the wrong type is refused, never trusted.
"""

from __future__ import annotations

import contextlib
import sqlite3
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any, Protocol, TypedDict

import structlog

from evra.bridge.events import EventBus
from evra.capture.devices import MicList, list_mics
from evra.services.views import clean_title, meeting_detail, meeting_summary
from evra.store.db import connect
from evra.store.meetings import MeetingStore

log = structlog.get_logger(__name__)


class PingReply(TypedDict):
    reply: str


class AppInfoDict(TypedDict):
    name: str
    version: str


class Control(Protocol):
    @property
    def mic_name(self) -> str: ...

    def start(self, mic_name: str) -> dict[str, Any]: ...

    def stop(self) -> dict[str, Any]: ...

    def write_note(self, meeting_id: str) -> dict[str, Any]: ...

    def state(self) -> dict[str, Any]: ...


class BridgeApi:
    def __init__(
        self,
        *,
        app_name: str,
        version: str,
        bus: EventBus,
        control: Control,
        db_path: Path,
        mic_lister: Callable[[], MicList] = list_mics,
    ) -> None:
        self._app_name = app_name
        self._version = version
        self._bus = bus
        self._control = control
        self._db_path = db_path
        self._mic_lister = mic_lister

    def ping(self, message: str) -> PingReply:
        return {"reply": f"pong: {message}"}

    def app_info(self) -> AppInfoDict:
        return {"name": self._app_name, "version": self._version}

    def request_hello(self) -> None:
        """Proves the Python -> React push path."""
        self._bus.emit("app.hello", {"message": "Python is connected"})

    def list_meetings(self) -> list[dict[str, Any]]:
        with self._db() as conn:
            return [meeting_summary(row) for row in MeetingStore(conn).list_meetings()]

    def get_meeting(self, meeting_id: str) -> dict[str, Any] | None:
        if not isinstance(meeting_id, str):
            return None
        with self._db() as conn:
            return meeting_detail(conn, meeting_id)

    def list_mics(self) -> dict[str, Any]:
        try:
            mics = self._mic_lister()
        except Exception as exc:  # no audio stack: the Windows default mic still works
            log.warning("mics_not_listed", error=type(exc).__name__)
            mics = MicList("", ())
        return {"default": mics.default, "mics": list(mics.mics), "chosen": self._control.mic_name}

    def start_recording(self, mic_name: str) -> dict[str, Any]:
        if not isinstance(mic_name, str):
            return {"ok": False, "reason": "invalid"}
        return self._control.start(mic_name)

    def stop_recording(self) -> dict[str, Any]:
        return self._control.stop()

    def write_note(self, meeting_id: str) -> dict[str, Any]:
        if not isinstance(meeting_id, str):
            return {"ok": False}
        return self._control.write_note(meeting_id)

    def rename_meeting(self, meeting_id: str, title: str) -> dict[str, Any]:
        cleaned = clean_title(title) if isinstance(title, str) else None
        if not isinstance(meeting_id, str) or cleaned is None:
            return {"ok": False}
        with self._db() as conn:
            return {"ok": MeetingStore(conn).rename_meeting(meeting_id, cleaned)}

    def recording_state(self) -> dict[str, Any]:
        return self._control.state()

    @contextlib.contextmanager
    def _db(self) -> Iterator[sqlite3.Connection]:
        conn = connect(self._db_path)
        try:
            yield conn
        finally:
            conn.close()
```

In `src/evra/bridge/events.py`:
- add `import structlog` and `log = structlog.get_logger(__name__)` below the imports;
- replace the `EventBus` class with:

```python
class EventBus:
    def __init__(self) -> None:
        self._runner: JsRunner | None = None

    def attach(self, runner: JsRunner) -> None:
        self._runner = runner

    def detach(self) -> None:
        """The window is gone: later events are dropped."""
        self._runner = None

    def emit(self, name: str, payload: Mapping[str, Any]) -> bool:
        """Push an event to the UI. False if no window is attached or it is closing."""
        script = build_emit_script(name, payload)
        runner = self._runner
        if runner is None:
            return False
        try:
            runner.run_js(script)
        except Exception as exc:  # a window that is closing; the event only mattered to it
            log.debug("event_dropped", event=name, error=type(exc).__name__)
            return False
        return True
```

In `src/evra/app.py`:

1. Add imports:

```python
from evra.services.meetings import MeetingService
from evra.store.meetings import MeetingStore
from evra.transcribe.recording import RecordingKit
```

2. Add `service: MeetingService` as the last field of the `App` dataclass.

3. In `build_app`, replace the block from `conn = connect(paths.db_path)` to the `return App(...)` with:

```python
    conn = connect(paths.db_path)
    try:
        schema = migrate(conn)
        recovered = MeetingStore(conn).recover_after_restart()
    finally:
        conn.close()
    bus = EventBus()
    service = MeetingService(
        paths=paths, settings=settings, emit=bus.emit, kit=RecordingKit(paths)
    )
    api = BridgeApi(
        app_name=APP_NAME, version=__version__, bus=bus, control=service, db_path=paths.db_path
    )
    log.info("app_started", version=__version__, schema_version=schema, recovered=recovered)
    return App(paths=paths, settings=settings, bus=bus, api=api, debug=debug, service=service)
```

4. In `run_app`, wrap the `opener(...)` call so the service always shuts down when the window closes:

```python
        app = build_app(paths, debug=debug or debug_enabled())
        try:
            opener(
                url=url,
                api=app.api,
                bus=app.bus,
                debug=app.debug,
                storage_dir=app.paths.data_dir / "webview",
            )
        finally:  # the window is closed: save a running recording, stop the workers
            app.bus.detach()
            app.service.shutdown()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_bridge.py tests/unit/test_app.py -q`
Expected: PASS. Then `uv run pytest -q` — the whole suite passes.

- [ ] **Step 5: Commit**

```bash
uv run ruff format src/evra tests/unit/test_bridge.py tests/unit/test_app.py
uv run python tools/check.py   # must show no FAIL
git add src/evra/bridge src/evra/app.py tests/unit/test_bridge.py tests/unit/test_app.py
git commit -m "feat: bridge calls for meetings and recording; the window's close saves the recording"
git push
```

---

### Task 7: Frontend foundation — bridge types, strings, formats, fonts

**Files:**
- Modify: `frontend/src/bridge.ts`, `frontend/src/bridge.test.ts`, `frontend/src/App.test.tsx` (fake bridge only), `frontend/src/main.tsx`, `frontend/src/test/setup.ts`, `frontend/package.json` + `package-lock.json`, `THIRD_PARTY_LICENSES.md`
- Create: `frontend/src/strings.ts`, `frontend/src/format.ts`, `frontend/src/format.test.ts`, `frontend/src/test/fakeApi.ts`

**Interfaces:**
- Consumes: the bridge calls and events of Tasks 5–6.
- Produces (TypeScript, all exported from `@/bridge` unless noted):
  - `RecordingPhase = "idle" | "loading" | "recording" | "stopping" | "processing"`; `RecordingState { state; meeting_id?; started_at? }`; `Levels { you; them }`;
  - `MeetingSummary { id; title; started_at; duration_ms: number | null; state; has_note }`; `Utterance { id; channel; speaker; start_ms; end_ms; text }`;
  - `Citation { utterance_id; start_ms }`, `NoteBlock { text; citations }`, `NoteSection { id; title; blocks }`, `Note { model; sections }`, `MeetingDetail { meeting; utterances; note: Note | null }`;
  - `MicList { default; mics; chosen }`, `StartReply { ok; meeting_id?; reason?; error?; hint? }`, `OkReply { ok }`;
  - `NoteFailureReason` (the nine codes), `RecordingFinished`, `NoteFailed`;
  - `EvraApi` with the old three methods plus `list_meetings`, `get_meeting`, `list_mics`, `start_recording`, `stop_recording`, `write_note`, `rename_meeting`, `recording_state`;
  - `@/strings`: `strings`, `noteFailureText(reason, model?)`, `canRetry(reason)`;
  - `@/format`: `formatClock(ms)`, `formatDuration(ms | null)`, `formatDate(epochMs)`;
  - `@/test/fakeApi`: `MEETING`, `DETAIL`, `makeFakeApi(overrides?)`.

- [ ] **Step 1: Add the fonts and pass the licence gate**

```bash
npm --prefix frontend install @fontsource/inter@5.3.0 @fontsource/newsreader@5.3.0
ls frontend/node_modules/@fontsource/inter/latin-400.css frontend/node_modules/@fontsource/inter/latin-600.css frontend/node_modules/@fontsource/newsreader/latin-400.css
uv run python tools/license_gate.py --write-register
uv run python tools/license_gate.py
```

Expected: the three CSS files exist; the gate passes (both packages are `OFL-1.1`, which `tools/license_policy.yaml` allows). If a `latin-*.css` file is missing, list the package folder and use the matching per-weight file (for example `400.css`) in Step 4.

- [ ] **Step 2: Write the failing tests**

`frontend/src/format.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { formatClock, formatDate, formatDuration } from "@/format";

describe("formatClock", () => {
  it("shows minutes and seconds, and hours only when needed", () => {
    expect(formatClock(0)).toBe("00:00");
    expect(formatClock(65_000)).toBe("01:05");
    expect(formatClock(3_725_000)).toBe("1:02:05");
    expect(formatClock(-5)).toBe("00:00");
  });
});

describe("formatDuration", () => {
  it("rounds to minutes", () => {
    expect(formatDuration(720_000)).toBe("12 min");
    expect(formatDuration(20_000)).toBe("<1 min");
    expect(formatDuration(null)).toBe("");
  });
});

describe("formatDate", () => {
  it("shows the day, month and time", () => {
    const text = formatDate(new Date(2026, 8, 28, 13, 51).getTime());
    expect(text).toMatch(/28/);
    expect(text).toMatch(/Sep/);
    expect(text).toMatch(/13:51/);
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `npm --prefix frontend run test -- src/format.test.ts`
Expected: FAIL — cannot resolve `@/format`.

- [ ] **Step 4: Implement**

Replace the types and `EvraApi` interface at the top of `frontend/src/bridge.ts` (everything above `type Handler = ...`) with:

```ts
// Python <-> React bridge (BUILD.md §4, D5; M3c spec §3.2-3.3).
// JS -> Python: window.pywebview.api.<method>(...) returns a Promise.
// Python -> JS: Python runs window.__evraEmit(name, payload).

export interface AppInfo {
  name: string;
  version: string;
}

export interface PingReply {
  reply: string;
}

export type RecordingPhase = "idle" | "loading" | "recording" | "stopping" | "processing";

export interface RecordingState {
  state: RecordingPhase;
  meeting_id?: string;
  started_at?: number | null;
}

export interface Levels {
  you: number;
  them: number;
}

export interface MeetingSummary {
  id: string;
  title: string;
  started_at: number;
  duration_ms: number | null;
  state: string;
  has_note: boolean;
}

export interface Utterance {
  id: string;
  channel: number;
  speaker: string;
  start_ms: number;
  end_ms: number;
  text: string;
}

export interface Citation {
  utterance_id: string;
  start_ms: number;
}

export interface NoteBlock {
  text: string;
  citations: Citation[];
}

export interface NoteSection {
  id: string;
  title: string;
  blocks: NoteBlock[];
}

export interface Note {
  model: string;
  sections: NoteSection[];
}

export interface MeetingDetail {
  meeting: MeetingSummary;
  utterances: Utterance[];
  note: Note | null;
}

export interface MicList {
  default: string;
  mics: string[];
  chosen: string;
}

export interface StartReply {
  ok: boolean;
  meeting_id?: string;
  reason?: string;
  error?: string;
  hint?: string;
}

export interface OkReply {
  ok: boolean;
}

export type NoteFailureReason =
  | "ollama_down"
  | "model_missing"
  | "too_long"
  | "cut_off"
  | "invalid"
  | "nothing_supported"
  | "timeout"
  | "no_transcript"
  | "llm_error";

export interface RecordingFinished {
  meeting_id: string;
  utterances: number;
  failed_segments: number;
  hints: string[];
}

export interface NoteFailed {
  meeting_id: string;
  reason: NoteFailureReason;
  model?: string;
}

export interface EvraApi {
  ping(message: string): Promise<PingReply>;
  app_info(): Promise<AppInfo>;
  request_hello(): Promise<null>;
  list_meetings(): Promise<MeetingSummary[]>;
  get_meeting(meetingId: string): Promise<MeetingDetail | null>;
  list_mics(): Promise<MicList>;
  start_recording(micName: string): Promise<StartReply>;
  stop_recording(): Promise<OkReply>;
  write_note(meetingId: string): Promise<OkReply>;
  rename_meeting(meetingId: string, title: string): Promise<OkReply>;
  recording_state(): Promise<RecordingState>;
}
```

(Leave the rest of `bridge.ts` — handlers, `setApiForTests`, `readyApi`, `getApi`, `onEvent`, `emit`, `window.__evraEmit = emit` — unchanged.)

`frontend/src/format.ts`:

```ts
// Times and dates as the window shows them.

export function formatClock(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(total / 3600);
  const minutes = String(Math.floor((total % 3600) / 60)).padStart(2, "0");
  const seconds = String(total % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${minutes}:${seconds}` : `${minutes}:${seconds}`;
}

export function formatDuration(ms: number | null): string {
  if (ms === null) return "";
  const minutes = Math.round(ms / 60_000);
  return minutes < 1 ? "<1 min" : `${minutes} min`;
}

export function formatDate(epochMs: number): string {
  return new Date(epochMs).toLocaleString("en-GB", {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}
```

`frontend/src/strings.ts`:

```ts
// Every user-facing string in one place (BUILD.md §8.4: one i18n layer later).
import type { NoteFailureReason } from "@/bridge";

export const strings = {
  record: "Record",
  stop: "Stop",
  loading: "Loading…",
  stopping: "Stopping…",
  writingNote: "Writing note…",
  microphone: "Microphone",
  windowsDefault: (name: string) => (name ? `Windows default (${name})` : "Windows default"),
  notConnected: (name: string) => `${name} (not connected)`,
  recordingTime: "Recording time",
  you: "You",
  them: "Them",
  meetings: "Meetings",
  searchMeetings: "Search meetings",
  noMeetings: "No meetings yet. Press Record to start one.",
  noMatches: "No meetings match.",
  liveNow: "Recording",
  selectMeeting: "Select a meeting, or press Record to start one.",
  meetingTabs: "Meeting",
  noteTab: "Note",
  transcriptTab: "Transcript",
  oneOnOne: "1:1",
  renameMeeting: "Rename meeting",
  meetingTitle: "Meeting title",
  captureNotes: "Capture notes",
  noTranscript: "Nothing has been transcribed yet.",
  noNote: "No note yet.",
  writeNote: "Write note",
  retry: "Retry",
  dismiss: "Dismiss",
  jumpTo: (clock: string) => `Jump to ${clock} in the transcript`,
  stages: { writing: "Writing note…" } as Record<string, string>,
  bridgeDown: "Evra couldn't reach its Python side. Close the window and start Evra again.",
};

export function noteFailureText(reason: NoteFailureReason, model?: string): string {
  switch (reason) {
    case "ollama_down":
      return "Ollama isn't running. Start it from the system tray (or install it from ollama.com).";
    case "model_missing":
      return `The note model isn't installed. Run: ollama pull ${model ?? ""}`.trim();
    case "too_long":
      return "This meeting is too long for one note pass yet.";
    case "cut_off":
      return "The model ran out of room while writing.";
    case "invalid":
      return "The model didn't return a valid note.";
    case "nothing_supported":
      return "Nothing in the note could be checked against the transcript.";
    case "timeout":
      return "The model took too long.";
    case "no_transcript":
      return "Nothing was transcribed, so there's no note to write.";
    default:
      return "The note couldn't be written.";
  }
}

export function canRetry(reason: NoteFailureReason): boolean {
  return reason !== "too_long" && reason !== "no_transcript";
}
```

`frontend/src/test/fakeApi.ts`:

```ts
import { vi } from "vitest";
import type { EvraApi, MeetingDetail, MeetingSummary } from "@/bridge";

export const MEETING: MeetingSummary = {
  id: "m1",
  title: "Weekly 1:1",
  started_at: new Date(2026, 8, 28, 13, 51).getTime(),
  duration_ms: 720_000,
  state: "ready",
  has_note: true,
};

export const DETAIL: MeetingDetail = {
  meeting: MEETING,
  utterances: [
    { id: "u1", channel: 1, speaker: "Them", start_ms: 65_000, end_ms: 70_000, text: "Marketing wants October 14." },
    { id: "u2", channel: 0, speaker: "You", start_ms: 110_000, end_ms: 114_000, text: "I'll send the proposal by Thursday." },
  ],
  note: {
    model: "gemma4:12b",
    sections: [
      {
        id: "summary",
        title: "Summary",
        blocks: [{ text: "Launch moves to October 14.", citations: [{ utterance_id: "u1", start_ms: 65_000 }] }],
      },
      {
        id: "action_items",
        title: "Action items",
        blocks: [
          { text: "You: send the proposal by Thursday.", citations: [{ utterance_id: "u2", start_ms: 110_000 }] },
        ],
      },
    ],
  },
};

export function makeFakeApi(overrides: Partial<EvraApi> = {}): EvraApi {
  return {
    ping: vi.fn(async (message: string) => ({ reply: `pong: ${message}` })),
    app_info: vi.fn(async () => ({ name: "Evra", version: "0.1.0" })),
    request_hello: vi.fn(async () => null),
    list_meetings: vi.fn(async () => [MEETING]),
    get_meeting: vi.fn(async (id: string) => (id === MEETING.id ? DETAIL : null)),
    list_mics: vi.fn(async () => ({
      default: "Headset (realme Buds Air7)",
      mics: ["Headset (realme Buds Air7)", "Microphone Array (Realtek(R) Audio)"],
      chosen: "",
    })),
    start_recording: vi.fn(async () => ({ ok: true, meeting_id: "m2" })),
    stop_recording: vi.fn(async () => ({ ok: true })),
    write_note: vi.fn(async () => ({ ok: true })),
    rename_meeting: vi.fn(async () => ({ ok: true })),
    recording_state: vi.fn(async () => ({ state: "idle" as const })),
    ...overrides,
  };
}
```

In `frontend/src/bridge.test.ts` and `frontend/src/App.test.tsx`, replace the local `const fakeApi: EvraApi = { ... };` with:

```ts
import { makeFakeApi } from "@/test/fakeApi";

const fakeApi = makeFakeApi();
```

and drop `type EvraApi` from their `@/bridge` imports if it is no longer used. In `App.test.tsx`, the test "shows an error when the bridge is unavailable" spreads `...fakeApi` — keep it as is. (`App.test.tsx` is replaced in Task 11.)

Append to `frontend/src/test/setup.ts`:

```ts
// jsdom has no layout: give elements a no-op scrollIntoView so components can call it.
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
```

In `frontend/src/main.tsx`, add the fonts above `import "./index.css";`:

```ts
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-600.css";
import "@fontsource/newsreader/latin-400.css";
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `npm --prefix frontend run test` then `npm --prefix frontend run typecheck` then `npm --prefix frontend run lint`
Expected: all pass (the M0 `App` still renders; its tests use the new fake).

- [ ] **Step 6: Check the build bundles the fonts locally**

Run: `npm --prefix frontend run build`
Expected: success; `src/evra/ui/web/index.html` contains `@font-face` with `data:font/woff2` and no `fonts.googleapis.com` or `http` font URLs:

```bash
grep -c "data:font/woff2" src/evra/ui/web/index.html
grep -c "fonts.googleapis" src/evra/ui/web/index.html   # expect 0
```

- [ ] **Step 7: Commit**

```bash
uv run python tools/check.py   # must show no FAIL
git add frontend/package.json frontend/package-lock.json frontend/src THIRD_PARTY_LICENSES.md
git commit -m "feat: frontend bridge types, strings, formats and bundled fonts"
git push
```

---

### Task 8: `useEvra` — the window's state and actions

**Files:**
- Create: `frontend/src/useEvra.ts`, `frontend/src/useEvra.test.tsx`

**Interfaces:**
- Consumes: `getApi`, `onEvent` and the types of Task 7.
- Produces:
  - `NoteStatus { stage?: string; failed?: { reason: NoteFailureReason; model?: string } }`;
  - `StartError { error: string; hint: string }`;
  - `EvraState { appName, ready, bridgeError, recording, levels, meetings, mics, selectedId, detail, noteStatus: Record<string, NoteStatus>, hints: Record<string, string[]>, startError }`;
  - `useEvra()` → `{ state, select(id), startRecording(mic), stopRecording(), writeNote(id), rename(id, title) => Promise<boolean>, dismissStartError() }`.
- **Rules:**
  - On load: `app_info`, `recording_state`, `list_meetings`, `list_mics`; open the recording meeting if one is running, else the newest meeting.
  - `recording.state` → set it; when it says `recording` with a new meeting, open that meeting; always refresh the list.
  - `transcript.utterance` → append to the open meeting only, once per id.
  - `recording.finished` → keep its hints; reload the open meeting.
  - `note.stage` / `note.failed` → per-meeting status; `note.ready` → clear status, refresh list, reload the open meeting.
  - A `start_recording` reply with `error` becomes `startError`; one with only `reason` (`busy`, `closing`) is not an error.

- [ ] **Step 1: Write the failing tests**

`frontend/src/useEvra.test.tsx`:

```tsx
import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { emit, setApiForTests, type MeetingSummary } from "@/bridge";
import { DETAIL, MEETING, makeFakeApi } from "@/test/fakeApi";
import { useEvra } from "@/useEvra";

afterEach(() => setApiForTests(null));

const LIVE: MeetingSummary = {
  ...MEETING,
  id: "m2",
  title: "Recording 2026-09-28 13:51",
  state: "recording",
  has_note: false,
  duration_ms: null,
};

it("loads the meetings and opens the newest one", async () => {
  setApiForTests(makeFakeApi());
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).toEqual(DETAIL));
  expect(result.current.state.appName).toBe("Evra");
  expect(result.current.state.meetings).toEqual([MEETING]);
  expect(result.current.state.selectedId).toBe("m1");
});

it("appends live lines only for the open meeting, once each", async () => {
  setApiForTests(makeFakeApi());
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail).not.toBeNull());
  const line = { meeting_id: "m1", id: "x1", channel: 0, speaker: "You", start_ms: 200_000, end_ms: 201_000, text: "New line." };
  act(() => {
    emit("transcript.utterance", line);
    emit("transcript.utterance", line);
    emit("transcript.utterance", { ...line, meeting_id: "other", id: "x2" });
  });
  expect(result.current.state.detail?.utterances.map((u) => u.id)).toEqual(["u1", "u2", "x1"]);
});

it("picks up a recording in progress after the window reloads", async () => {
  setApiForTests(
    makeFakeApi({
      recording_state: async () => ({ state: "recording", meeting_id: "m2", started_at: 5 }),
      list_meetings: async () => [LIVE, MEETING],
      get_meeting: async (id) => (id === "m2" ? { meeting: LIVE, utterances: [], note: null } : DETAIL),
    }),
  );
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.detail?.meeting.id).toBe("m2"));
  expect(result.current.state.recording.state).toBe("recording");
});

it("opens a meeting when its recording starts", async () => {
  let meetings = [MEETING];
  setApiForTests(
    makeFakeApi({
      list_meetings: async () => meetings,
      get_meeting: async (id) => (id === "m2" ? { meeting: LIVE, utterances: [], note: null } : DETAIL),
    }),
  );
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.selectedId).toBe("m1"));
  meetings = [LIVE, MEETING];
  act(() => emit("recording.state", { state: "recording", meeting_id: "m2", started_at: 5 }));
  await waitFor(() => expect(result.current.state.detail?.meeting.id).toBe("m2"));
  await waitFor(() => expect(result.current.state.meetings).toHaveLength(2));
});

it("tracks note progress and failure per meeting, and clears them when the note is ready", async () => {
  setApiForTests(makeFakeApi());
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.ready).toBe(true));
  act(() => emit("note.stage", { meeting_id: "m1", stage: "writing" }));
  expect(result.current.state.noteStatus.m1).toEqual({ stage: "writing" });
  act(() => emit("note.failed", { meeting_id: "m1", reason: "model_missing", model: "gemma4:12b" }));
  expect(result.current.state.noteStatus.m1).toEqual({ failed: { reason: "model_missing", model: "gemma4:12b" } });
  act(() => emit("note.ready", { meeting_id: "m1" }));
  expect(result.current.state.noteStatus.m1).toBeUndefined();
});

it("keeps capture hints from the finished recording", async () => {
  setApiForTests(makeFakeApi());
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.ready).toBe(true));
  act(() =>
    emit("recording.finished", { meeting_id: "m1", utterances: 2, failed_segments: 0, hints: ["No system audio arrived."] }),
  );
  expect(result.current.state.hints.m1).toEqual(["No system audio arrived."]);
});

it("reports why recording could not start, but not a busy reply", async () => {
  const replies = [
    { ok: false, error: "microphone 'Headset' is not connected", hint: "Pick it again." },
    { ok: false, reason: "busy" },
  ];
  setApiForTests(makeFakeApi({ start_recording: async () => replies.shift()! }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.ready).toBe(true));
  await act(() => result.current.startRecording("Headset"));
  expect(result.current.state.startError).toEqual({ error: "microphone 'Headset' is not connected", hint: "Pick it again." });
  await act(() => result.current.startRecording("Headset"));
  expect(result.current.state.startError).toBeNull();
});

it("says so when the bridge is unavailable", async () => {
  setApiForTests(makeFakeApi({ app_info: async () => { throw new Error("boom"); } }));
  const { result } = renderHook(() => useEvra());
  await waitFor(() => expect(result.current.state.bridgeError).toBe("boom"));
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend run test -- src/useEvra.test.tsx`
Expected: FAIL — cannot resolve `@/useEvra`.

- [ ] **Step 3: Implement**

`frontend/src/useEvra.ts`:

```ts
// All window state (M3c spec §4): Python pushes events, this hook keeps them and offers actions.
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getApi,
  onEvent,
  type Levels,
  type MeetingDetail,
  type MeetingSummary,
  type MicList,
  type NoteFailed,
  type NoteFailureReason,
  type RecordingFinished,
  type RecordingState,
  type Utterance,
} from "@/bridge";

export interface NoteStatus {
  stage?: string;
  failed?: { reason: NoteFailureReason; model?: string };
}

export interface StartError {
  error: string;
  hint: string;
}

export interface EvraState {
  appName: string;
  ready: boolean;
  bridgeError: string;
  recording: RecordingState;
  levels: Levels;
  meetings: MeetingSummary[];
  mics: MicList | null;
  selectedId: string | null;
  detail: MeetingDetail | null;
  noteStatus: Record<string, NoteStatus>;
  hints: Record<string, string[]>;
  startError: StartError | null;
}

const QUIET: Levels = { you: 0, them: 0 };

const INITIAL: EvraState = {
  appName: "",
  ready: false,
  bridgeError: "",
  recording: { state: "idle" },
  levels: QUIET,
  meetings: [],
  mics: null,
  selectedId: null,
  detail: null,
  noteStatus: {},
  hints: {},
  startError: null,
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function without<T>(map: Record<string, T>, key: string): Record<string, T> {
  const rest = { ...map };
  delete rest[key];
  return rest;
}

export function useEvra() {
  const [state, setState] = useState<EvraState>(INITIAL);
  const selected = useRef<string | null>(null);

  const refreshMeetings = useCallback(async () => {
    try {
      const meetings = await (await getApi()).list_meetings();
      setState((s) => ({ ...s, meetings }));
    } catch {
      // the list stays as it was; the next event refreshes it
    }
  }, []);

  const loadDetail = useCallback(async (id: string) => {
    try {
      const detail = await (await getApi()).get_meeting(id);
      if (selected.current === id) setState((s) => ({ ...s, detail }));
    } catch {
      // keep what is shown
    }
  }, []);

  const select = useCallback(
    (id: string) => {
      selected.current = id;
      setState((s) => ({ ...s, selectedId: id, detail: s.detail?.meeting.id === id ? s.detail : null }));
      void loadDetail(id);
    },
    [loadDetail],
  );

  useEffect(() => {
    let alive = true;
    const offs = [
      onEvent("recording.state", (payload) => {
        const recording = payload as RecordingState;
        setState((s) => ({ ...s, recording, levels: recording.state === "recording" ? s.levels : QUIET }));
        if (recording.state === "recording" && recording.meeting_id && selected.current !== recording.meeting_id) {
          select(recording.meeting_id);
        }
        void refreshMeetings();
      }),
      onEvent("recording.levels", (payload) => setState((s) => ({ ...s, levels: payload as Levels }))),
      onEvent("transcript.utterance", (payload) => {
        const { meeting_id, ...utterance } = payload as Utterance & { meeting_id: string };
        setState((s) => {
          const detail = s.detail;
          if (!detail || detail.meeting.id !== meeting_id) return s;
          if (detail.utterances.some((u) => u.id === utterance.id)) return s;
          return { ...s, detail: { ...detail, utterances: [...detail.utterances, utterance] } };
        });
      }),
      onEvent("recording.finished", (payload) => {
        const finished = payload as RecordingFinished;
        setState((s) => ({ ...s, hints: { ...s.hints, [finished.meeting_id]: finished.hints } }));
        if (selected.current === finished.meeting_id) void loadDetail(finished.meeting_id);
      }),
      onEvent("note.stage", (payload) => {
        const { meeting_id, stage } = payload as { meeting_id: string; stage: string };
        setState((s) => ({ ...s, noteStatus: { ...s.noteStatus, [meeting_id]: { stage } } }));
      }),
      onEvent("note.ready", (payload) => {
        const { meeting_id } = payload as { meeting_id: string };
        setState((s) => ({ ...s, noteStatus: without(s.noteStatus, meeting_id) }));
        void refreshMeetings();
        if (selected.current === meeting_id) void loadDetail(meeting_id);
      }),
      onEvent("note.failed", (payload) => {
        const failed = payload as NoteFailed;
        setState((s) => ({
          ...s,
          noteStatus: { ...s.noteStatus, [failed.meeting_id]: { failed: { reason: failed.reason, model: failed.model } } },
        }));
      }),
    ];
    getApi()
      .then(async (api) => {
        const [info, recording, meetings, mics] = await Promise.all([
          api.app_info(),
          api.recording_state(),
          api.list_meetings(),
          api.list_mics(),
        ]);
        if (!alive) return;
        setState((s) => ({ ...s, appName: info.name, ready: true, recording, meetings, mics }));
        const first = recording.meeting_id ?? meetings[0]?.id;
        if (first) select(first);
      })
      .catch((error: unknown) => {
        if (alive) setState((s) => ({ ...s, bridgeError: message(error) }));
      });
    return () => {
      alive = false;
      offs.forEach((off) => off());
    };
  }, [select, refreshMeetings, loadDetail]);

  const startRecording = useCallback(async (mic: string) => {
    setState((s) => ({ ...s, startError: null }));
    try {
      const reply = await (await getApi()).start_recording(mic);
      if (!reply.ok && reply.error) {
        const startError = { error: reply.error, hint: reply.hint ?? "" };
        setState((s) => ({ ...s, startError }));
      }
    } catch (error) {
      setState((s) => ({ ...s, startError: { error: message(error), hint: "" } }));
    }
  }, []);

  const stopRecording = useCallback(async () => {
    await (await getApi()).stop_recording();
  }, []);

  const writeNote = useCallback(async (id: string) => {
    setState((s) => ({ ...s, noteStatus: without(s.noteStatus, id) }));
    await (await getApi()).write_note(id);
  }, []);

  const rename = useCallback(
    async (id: string, title: string) => {
      const reply = await (await getApi()).rename_meeting(id, title);
      if (reply.ok) {
        void refreshMeetings();
        if (selected.current === id) void loadDetail(id);
      }
      return reply.ok;
    },
    [refreshMeetings, loadDetail],
  );

  const dismissStartError = useCallback(() => setState((s) => ({ ...s, startError: null })), []);

  return { state, select, startRecording, stopRecording, writeNote, rename, dismissStartError };
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend run test -- src/useEvra.test.tsx` then `npm --prefix frontend run typecheck` and `npm --prefix frontend run lint`
Expected: PASS, no type or lint errors.

- [ ] **Step 5: Commit**

```bash
uv run python tools/check.py   # must show no FAIL
git add frontend/src/useEvra.ts frontend/src/useEvra.test.tsx
git commit -m "feat: one hook keeps the window's meetings, recording and note state"
git push
```

---

### Task 9: Top bar — microphone, Record/Stop, timer, levels

**Files:**
- Create: `frontend/src/components/Banner.tsx`, `frontend/src/components/LevelMeter.tsx`, `frontend/src/components/TopBar.tsx`, `frontend/src/components/TopBar.test.tsx`

**Interfaces:**
- Consumes: `Levels`, `MicList`, `RecordingState` (Task 7); `StartError` (Task 8); `strings`, `formatClock`, `cn`.
- Produces:
  - `Banner({ message, hint?, action?: { label, onClick }, onDismiss? })` — `role="alert"`;
  - `LevelMeter({ label, value })` — an element with `aria-label={label}` and `aria-valuenow` (0..1);
  - `TopBar({ appName, recording, levels, mics, startError, onStart(mic), onStop(), onDismissError(), now? })`.
- **Rules:** the picker lists the Windows default (`""`) first, then each mic; a remembered mic that is not in the list stays selected as "(not connected)". The picker is disabled unless idle. Idle → **Record**; loading/stopping/processing → a disabled button labelled "Loading…" / "Stopping…" / "Writing note…"; recording → red **Stop**, the timer and two level meters.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/TopBar.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import type { MicList, RecordingState } from "@/bridge";
import { TopBar } from "@/components/TopBar";

const MICS: MicList = {
  default: "Headset (realme Buds Air7)",
  mics: ["Headset (realme Buds Air7)", "Microphone Array (Realtek(R) Audio)"],
  chosen: "",
};

function bar(recording: RecordingState, extra: Partial<Parameters<typeof TopBar>[0]> = {}) {
  const props = {
    appName: "Evra",
    recording,
    levels: { you: 0.5, them: 0.25 },
    mics: MICS,
    startError: null,
    onStart: vi.fn(),
    onStop: vi.fn(),
    onDismissError: vi.fn(),
    ...extra,
  };
  render(<TopBar {...props} />);
  return props;
}

it("records with the chosen microphone", async () => {
  const props = bar({ state: "idle" });
  expect(screen.getByRole("option", { name: "Windows default (Headset (realme Buds Air7))" })).toBeInTheDocument();
  await userEvent.selectOptions(
    screen.getByRole("combobox", { name: "Microphone" }),
    "Microphone Array (Realtek(R) Audio)",
  );
  await userEvent.click(screen.getByRole("button", { name: "Record" }));
  expect(props.onStart).toHaveBeenCalledWith("Microphone Array (Realtek(R) Audio)");
});

it("keeps a remembered mic that is not connected visible", () => {
  bar({ state: "idle" }, { mics: { ...MICS, chosen: "Headset (Mivi Roam 2)" } });
  expect(screen.getByRole("combobox", { name: "Microphone" })).toHaveValue("Headset (Mivi Roam 2)");
  expect(screen.getByRole("option", { name: "Headset (Mivi Roam 2) (not connected)" })).toBeInTheDocument();
});

it("shows Stop, the time and both levels while recording", async () => {
  const props = bar({ state: "recording", meeting_id: "m", started_at: 1_000_000 }, { now: () => 1_065_000 });
  expect(screen.getByLabelText("Recording time")).toHaveTextContent("01:05");
  expect(screen.getByLabelText("You")).toHaveAttribute("aria-valuenow", "0.5");
  expect(screen.getByLabelText("Them")).toHaveAttribute("aria-valuenow", "0.25");
  expect(screen.getByRole("combobox", { name: "Microphone" })).toBeDisabled();
  await userEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(props.onStop).toHaveBeenCalled();
});

it.each([
  ["loading", "Loading…"],
  ["stopping", "Stopping…"],
  ["processing", "Writing note…"],
] as const)("is busy while %s", (state, label) => {
  bar({ state });
  expect(screen.getByRole("button", { name: label })).toBeDisabled();
});

it("shows why recording could not start, with its fix, until dismissed", async () => {
  const props = bar(
    { state: "idle" },
    { startError: { error: "microphone 'Headset' is not connected", hint: "Pick the microphone again." } },
  );
  const alert = screen.getByRole("alert");
  expect(alert).toHaveTextContent("microphone 'Headset' is not connected");
  expect(alert).toHaveTextContent("Pick the microphone again.");
  await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
  expect(props.onDismissError).toHaveBeenCalled();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend run test -- src/components/TopBar.test.tsx`
Expected: FAIL — cannot resolve `@/components/TopBar`.

- [ ] **Step 3: Implement**

`frontend/src/components/Banner.tsx`:

```tsx
import { strings } from "@/strings";

interface BannerProps {
  message: string;
  hint?: string;
  action?: { label: string; onClick: () => void };
  onDismiss?: () => void;
}

// A calm notice: what happened, how to fix it, and at most one action.
export function Banner({ message, hint, action, onDismiss }: BannerProps) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-md border border-line bg-paper px-4 py-3 text-sm">
      <div className="flex-1">
        <p>{message}</p>
        {hint && <p className="mt-1 text-muted-ink">{hint}</p>}
      </div>
      {action && (
        <button type="button" onClick={action.onClick} className="rounded-md bg-accent px-3 py-1 text-paper">
          {action.label}
        </button>
      )}
      {onDismiss && (
        <button type="button" onClick={onDismiss} aria-label={strings.dismiss} className="px-1 text-muted-ink hover:text-ink">
          ×
        </button>
      )}
    </div>
  );
}
```

`frontend/src/components/LevelMeter.tsx`:

```tsx
interface LevelMeterProps {
  label: string;
  value: number;
}

// One channel's loudness (0..1) while recording, so the owner sees both sides are live.
export function LevelMeter({ label, value }: LevelMeterProps) {
  const level = Math.min(1, Math.max(0, value));
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-ink">
      <span aria-hidden="true">{label}</span>
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={1}
        aria-valuenow={level}
        className="h-1.5 w-12 overflow-hidden rounded-full bg-line"
      >
        <div className="h-full bg-accent transition-[width] duration-100" style={{ width: `${Math.round(level * 100)}%` }} />
      </div>
    </div>
  );
}
```

`frontend/src/components/TopBar.tsx`:

```tsx
import { useEffect, useState } from "react";
import type { Levels, MicList, RecordingPhase, RecordingState } from "@/bridge";
import { Banner } from "@/components/Banner";
import { LevelMeter } from "@/components/LevelMeter";
import { formatClock } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";
import type { StartError } from "@/useEvra";

interface TopBarProps {
  appName: string;
  recording: RecordingState;
  levels: Levels;
  mics: MicList | null;
  startError: StartError | null;
  onStart: (mic: string) => void;
  onStop: () => void;
  onDismissError: () => void;
  now?: () => number;
}

function useElapsed(startedAt: number | null, now: () => number): number {
  const [, tick] = useState(0);
  useEffect(() => {
    if (startedAt === null) return;
    const timer = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [startedAt]);
  return startedAt === null ? 0 : now() - startedAt;
}

const BUSY: Record<Exclude<RecordingPhase, "idle" | "recording">, string> = {
  loading: strings.loading,
  stopping: strings.stopping,
  processing: strings.writingNote,
};

export function TopBar({ appName, recording, levels, mics, startError, onStart, onStop, onDismissError, now = Date.now }: TopBarProps) {
  const [picked, setPicked] = useState<string | null>(null);
  const phase = recording.state;
  const chosen = picked ?? mics?.chosen ?? "";
  const known = mics?.mics ?? [];
  const elapsed = useElapsed(phase === "recording" ? (recording.started_at ?? null) : null, now);
  return (
    <header className="border-b border-line">
      <div className="flex items-center gap-3 px-4 py-2">
        <span className="font-serif text-lg">{appName}</span>
        <div className="ml-auto flex items-center gap-3">
          {phase === "recording" && (
            <>
              <LevelMeter label={strings.you} value={levels.you} />
              <LevelMeter label={strings.them} value={levels.them} />
              <span aria-label={strings.recordingTime} className="tabular-nums text-sm text-rec">
                {formatClock(elapsed)}
              </span>
            </>
          )}
          <select
            aria-label={strings.microphone}
            value={chosen}
            disabled={phase !== "idle"}
            onChange={(event) => setPicked(event.target.value)}
            className="max-w-64 rounded-md border border-line bg-paper px-2 py-1 text-sm disabled:opacity-60"
          >
            <option value="">{strings.windowsDefault(mics?.default ?? "")}</option>
            {chosen !== "" && !known.includes(chosen) && <option value={chosen}>{strings.notConnected(chosen)}</option>}
            {known.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
          {phase === "recording" ? (
            <button type="button" onClick={onStop} className="rounded-md bg-rec px-4 py-1.5 text-sm text-paper">
              {strings.stop}
            </button>
          ) : phase === "idle" ? (
            <button type="button" onClick={() => onStart(chosen)} className="rounded-md bg-accent px-4 py-1.5 text-sm text-paper">
              <span aria-hidden="true">● </span>
              {strings.record}
            </button>
          ) : (
            <button type="button" disabled className={cn("rounded-md bg-accent px-4 py-1.5 text-sm text-paper opacity-60")}>
              {BUSY[phase]}
            </button>
          )}
        </div>
      </div>
      {startError && (
        <div className="px-4 pb-2">
          <Banner message={startError.error} hint={startError.hint} onDismiss={onDismissError} />
        </div>
      )}
    </header>
  );
}
```

(If oxlint's `react/only-export-components` warns about `BUSY`, keep it — warnings don't fail the check; or move `BUSY` inside the component.)

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend run test -- src/components/TopBar.test.tsx` then `npm --prefix frontend run typecheck` and `npm --prefix frontend run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run python tools/check.py   # must show no FAIL
git add frontend/src/components/Banner.tsx frontend/src/components/LevelMeter.tsx frontend/src/components/TopBar.tsx frontend/src/components/TopBar.test.tsx
git commit -m "feat: top bar with microphone picker, Record/Stop, timer and level meters"
git push
```

---

### Task 10: Meeting list, transcript, note and meeting view

**Files:**
- Create: `frontend/src/components/MeetingList.tsx`, `TranscriptView.tsx`, `NoteView.tsx`, `MeetingView.tsx` and their tests `MeetingList.test.tsx`, `TranscriptView.test.tsx`, `NoteView.test.tsx`, `MeetingView.test.tsx` (all in `frontend/src/components/`)

**Interfaces:**
- Consumes: types of Task 7, `NoteStatus` (Task 8), `Banner` (Task 9), `strings`, `noteFailureText`, `canRetry`, `formatClock`, `formatDate`, `formatDuration`, `cn`.
- Produces:
  - `MeetingList({ meetings, selectedId, liveId, onSelect })`;
  - `TranscriptView({ utterances, follow, highlightId })` — each line is an `<li data-utterance-id>`; the highlighted one has `data-highlighted="true"` and is scrolled into view; with `follow`, new lines scroll the list to the bottom unless the user scrolled up;
  - `NoteView({ note, status, canWrite, onWrite, onCite })`;
  - `MeetingView({ detail, isLive, noteStatus, hints, canWrite, onWrite, onRename })` — key it by meeting id; opens on Transcript while live, else on Note; switches to Note when a note stage starts; a citation switches to Transcript and highlights the line.

- [ ] **Step 1: Write the failing tests**

`frontend/src/components/MeetingList.test.tsx`:

```tsx
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { MeetingList } from "@/components/MeetingList";
import { MEETING } from "@/test/fakeApi";

const LIST = [MEETING, { ...MEETING, id: "m3", title: "Design review", has_note: false }];

it("filters by title and says when nothing matches", async () => {
  render(<MeetingList meetings={LIST} selectedId={null} liveId={null} onSelect={vi.fn()} />);
  await userEvent.type(screen.getByRole("searchbox", { name: "Search meetings" }), "design");
  expect(screen.getByRole("button", { name: /Design review/ })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Weekly 1:1/ })).toBeNull();
  await userEvent.type(screen.getByRole("searchbox", { name: "Search meetings" }), "zzz");
  expect(screen.getByText("No meetings match.")).toBeInTheDocument();
});

it("marks the open meeting and the one being recorded, and opens a meeting on click", async () => {
  const onSelect = vi.fn();
  render(<MeetingList meetings={LIST} selectedId="m1" liveId="m3" onSelect={onSelect} />);
  expect(screen.getByRole("button", { name: /Weekly 1:1/ })).toHaveAttribute("aria-current", "true");
  expect(within(screen.getByRole("button", { name: /Design review/ })).getByText(/Recording/)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /Design review/ }));
  expect(onSelect).toHaveBeenCalledWith("m3");
});

it("says how to start when there are no meetings", () => {
  render(<MeetingList meetings={[]} selectedId={null} liveId={null} onSelect={vi.fn()} />);
  expect(screen.getByText("No meetings yet. Press Record to start one.")).toBeInTheDocument();
});
```

`frontend/src/components/TranscriptView.test.tsx`:

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import type { Utterance } from "@/bridge";
import { TranscriptView } from "@/components/TranscriptView";
import { DETAIL } from "@/test/fakeApi";

const MORE: Utterance = { id: "u3", channel: 1, speaker: "Them", start_ms: 120_000, end_ms: 121_000, text: "Sounds good." };

function scrollBox(height: number) {
  const box = screen.getByTestId("transcript-scroll");
  let top = 0;
  Object.defineProperty(box, "scrollHeight", { configurable: true, get: () => height });
  Object.defineProperty(box, "clientHeight", { configurable: true, get: () => 100 });
  Object.defineProperty(box, "scrollTop", { configurable: true, get: () => top, set: (v: number) => { top = v; } });
  return { box, top: () => top, setTop: (v: number) => { top = v; } };
}

it("shows time, speaker and text for each line", () => {
  render(<TranscriptView utterances={DETAIL.utterances} follow={false} highlightId={null} />);
  const line = screen.getByText("Marketing wants October 14.").closest("li")!;
  expect(line).toHaveTextContent("01:05");
  expect(line).toHaveTextContent("Them");
});

it("follows new lines while live, unless the owner scrolled up", () => {
  const { rerender } = render(<TranscriptView utterances={DETAIL.utterances} follow highlightId={null} />);
  const scroll = scrollBox(500);
  rerender(<TranscriptView utterances={[...DETAIL.utterances, MORE]} follow highlightId={null} />);
  expect(scroll.top()).toBe(500);
  scroll.setTop(0);
  fireEvent.scroll(scroll.box);
  rerender(
    <TranscriptView utterances={[...DETAIL.utterances, MORE, { ...MORE, id: "u4" }]} follow highlightId={null} />,
  );
  expect(scroll.top()).toBe(0);
});

it("highlights and scrolls to a cited line", () => {
  const spy = vi.spyOn(Element.prototype, "scrollIntoView");
  render(<TranscriptView utterances={DETAIL.utterances} follow={false} highlightId="u2" />);
  const line = screen.getByText("I'll send the proposal by Thursday.").closest("li")!;
  expect(line).toHaveAttribute("data-highlighted", "true");
  expect(spy).toHaveBeenCalled();
  spy.mockRestore();
});

it("says when nothing has been transcribed", () => {
  render(<TranscriptView utterances={[]} follow highlightId={null} />);
  expect(screen.getByText("Nothing has been transcribed yet.")).toBeInTheDocument();
});
```

`frontend/src/components/NoteView.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { NoteView } from "@/components/NoteView";
import { DETAIL } from "@/test/fakeApi";

it("shows sections with citation chips that jump to the transcript", async () => {
  const onCite = vi.fn();
  render(<NoteView note={DETAIL.note} status={undefined} canWrite onWrite={vi.fn()} onCite={onCite} />);
  expect(screen.getByRole("heading", { name: "Action items" })).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Jump to 01:50 in the transcript" }));
  expect(onCite).toHaveBeenCalledWith("u2");
});

it("shows progress instead of an old note while a new one is written", () => {
  render(<NoteView note={DETAIL.note} status={{ stage: "writing" }} canWrite={false} onWrite={vi.fn()} onCite={vi.fn()} />);
  expect(screen.getByRole("status")).toHaveTextContent("Writing note…");
  expect(screen.queryByText("Launch moves to October 14.")).toBeNull();
});

it("explains a failure and offers Retry only when it can help", async () => {
  const onWrite = vi.fn();
  const { rerender } = render(
    <NoteView note={null} status={{ failed: { reason: "invalid" } }} canWrite onWrite={onWrite} onCite={vi.fn()} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("The model didn't return a valid note.");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(onWrite).toHaveBeenCalled();
  rerender(<NoteView note={null} status={{ failed: { reason: "too_long" } }} canWrite onWrite={onWrite} onCite={vi.fn()} />);
  expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
});

it("offers to write a note for a meeting that has none", async () => {
  const onWrite = vi.fn();
  render(<NoteView note={null} status={undefined} canWrite onWrite={onWrite} onCite={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Write note" }));
  expect(onWrite).toHaveBeenCalled();
});
```

`frontend/src/components/MeetingView.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { MeetingView } from "@/components/MeetingView";
import { DETAIL } from "@/test/fakeApi";

function view(extra: Partial<Parameters<typeof MeetingView>[0]> = {}) {
  const props = {
    detail: DETAIL,
    isLive: false,
    noteStatus: undefined,
    hints: undefined,
    canWrite: true,
    onWrite: vi.fn(),
    onRename: vi.fn(async () => true),
    ...extra,
  };
  return { props, ...render(<MeetingView {...props} />) };
}

it("opens a finished meeting on its note and a live one on its transcript", () => {
  view();
  expect(screen.getByRole("tab", { name: "Note" })).toHaveAttribute("aria-selected", "true");
  screen.getByText("Launch moves to October 14.");
});

it("opens a live meeting on the transcript, then the note once it is being written", () => {
  const { rerender, props } = view({ isLive: true });
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
  rerender(<MeetingView {...props} isLive={false} noteStatus={{ stage: "writing" }} />);
  expect(screen.getByRole("tab", { name: "Note" })).toHaveAttribute("aria-selected", "true");
});

it("jumps from a citation to its highlighted transcript line", async () => {
  view();
  await userEvent.click(screen.getByRole("button", { name: "Jump to 01:05 in the transcript" }));
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Marketing wants October 14.").closest("li")).toHaveAttribute("data-highlighted", "true");
});

it("renames the meeting in place", async () => {
  const { props } = view();
  await userEvent.click(screen.getByRole("button", { name: "Rename meeting" }));
  const input = screen.getByRole("textbox", { name: "Meeting title" });
  await userEvent.clear(input);
  await userEvent.type(input, "Sync with Priya{Enter}");
  expect(props.onRename).toHaveBeenCalledWith("Sync with Priya");
  expect(screen.queryByRole("textbox", { name: "Meeting title" })).toBeNull();
});

it("shows the capture notes from the recording", () => {
  view({ hints: ["No system audio arrived."] });
  expect(screen.getByRole("list", { name: "Capture notes" })).toHaveTextContent("No system audio arrived.");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend run test -- src/components`
Expected: FAIL — cannot resolve `@/components/MeetingList` (and the other three). `TopBar.test.tsx` still passes.

- [ ] **Step 3: Implement**

`frontend/src/components/MeetingList.tsx`:

```tsx
import { useState } from "react";
import type { MeetingSummary } from "@/bridge";
import { formatDate, formatDuration } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";

interface MeetingListProps {
  meetings: MeetingSummary[];
  selectedId: string | null;
  liveId: string | null;
  onSelect: (id: string) => void;
}

export function MeetingList({ meetings, selectedId, liveId, onSelect }: MeetingListProps) {
  const [query, setQuery] = useState("");
  const wanted = query.trim().toLowerCase();
  const shown = meetings.filter((m) => m.title.toLowerCase().includes(wanted));
  return (
    <nav aria-label={strings.meetings} className="flex h-full flex-col">
      <input
        type="search"
        aria-label={strings.searchMeetings}
        placeholder={strings.searchMeetings}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        className="m-3 rounded-md border border-line bg-paper px-3 py-1.5 text-sm"
      />
      {meetings.length === 0 ? (
        <p className="px-4 text-sm text-muted-ink">{strings.noMeetings}</p>
      ) : shown.length === 0 ? (
        <p className="px-4 text-sm text-muted-ink">{strings.noMatches}</p>
      ) : (
        <ul className="flex-1 overflow-y-auto">
          {shown.map((meeting) => (
            <li key={meeting.id}>
              <button
                type="button"
                onClick={() => onSelect(meeting.id)}
                aria-current={meeting.id === selectedId ? "true" : undefined}
                className={cn("w-full px-4 py-2 text-left hover:bg-line/60", meeting.id === selectedId && "bg-line")}
              >
                <span className="block truncate">
                  {meeting.id === liveId && <span className="mr-1 text-rec">● {strings.liveNow}</span>}
                  {meeting.title}
                </span>
                <span className="block text-xs text-muted-ink">
                  {[formatDate(meeting.started_at), formatDuration(meeting.duration_ms)].filter(Boolean).join(" · ")}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </nav>
  );
}
```

`frontend/src/components/TranscriptView.tsx`:

```tsx
import { useEffect, useRef } from "react";
import type { Utterance } from "@/bridge";
import { formatClock } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";

interface TranscriptViewProps {
  utterances: Utterance[];
  follow: boolean;
  highlightId: string | null;
}

const SPEAKER_COLOUR: Record<number, string> = {
  0: "text-accent",
  1: "text-amber-700 dark:text-amber-400",
};
const NEAR_BOTTOM_PX = 40;

export function TranscriptView({ utterances, follow, highlightId }: TranscriptViewProps) {
  const box = useRef<HTMLDivElement>(null);
  const atBottom = useRef(true);

  useEffect(() => {
    const el = box.current;
    if (follow && el && atBottom.current) el.scrollTop = el.scrollHeight;
  }, [utterances.length, follow]);

  useEffect(() => {
    if (!highlightId || !box.current) return;
    const lines = Array.from(box.current.querySelectorAll<HTMLElement>("[data-utterance-id]"));
    lines.find((line) => line.dataset.utteranceId === highlightId)?.scrollIntoView?.({ block: "center" });
  }, [highlightId]);

  function onScroll() {
    const el = box.current;
    if (el) atBottom.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  }

  if (utterances.length === 0) return <p className="p-6 text-muted-ink">{strings.noTranscript}</p>;
  return (
    <div ref={box} onScroll={onScroll} data-testid="transcript-scroll" className="h-full overflow-y-auto px-6 py-4">
      <ol aria-label={strings.transcriptTab} className="space-y-1">
        {utterances.map((u) => (
          <li
            key={u.id}
            data-utterance-id={u.id}
            data-highlighted={u.id === highlightId ? "true" : undefined}
            className={cn("flex gap-3 rounded-md px-2 py-1", u.id === highlightId && "bg-accent/15")}
          >
            <span className="shrink-0 pt-1 text-xs tabular-nums text-muted-ink">{formatClock(u.start_ms)}</span>
            <span className={cn("shrink-0 pt-0.5 text-sm font-semibold", SPEAKER_COLOUR[u.channel] ?? "text-muted-ink")}>
              {u.speaker}
            </span>
            <span className="font-serif leading-relaxed">{u.text}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
```

`frontend/src/components/NoteView.tsx`:

```tsx
import type { Note } from "@/bridge";
import { Banner } from "@/components/Banner";
import { formatClock } from "@/format";
import { canRetry, noteFailureText, strings } from "@/strings";
import type { NoteStatus } from "@/useEvra";

interface NoteViewProps {
  note: Note | null;
  status: NoteStatus | undefined;
  canWrite: boolean;
  onWrite: () => void;
  onCite: (utteranceId: string) => void;
}

// The note appears once, complete (D16): while one is written, only its progress shows.
export function NoteView({ note, status, canWrite, onWrite, onCite }: NoteViewProps) {
  if (status?.stage) {
    return (
      <p role="status" className="animate-pulse p-6 text-muted-ink">
        {strings.stages[status.stage] ?? strings.writingNote}
      </p>
    );
  }
  const failed = status?.failed;
  return (
    <div className="h-full overflow-y-auto px-6 py-4">
      {failed && (
        <div className="mb-4">
          <Banner
            message={noteFailureText(failed.reason, failed.model)}
            action={canWrite && canRetry(failed.reason) ? { label: strings.retry, onClick: onWrite } : undefined}
          />
        </div>
      )}
      {note ? (
        <article className="space-y-5">
          {note.sections.map((section) => (
            <section key={section.id} aria-labelledby={`note-${section.id}`}>
              <h3 id={`note-${section.id}`} className="text-xs font-semibold uppercase tracking-wide text-muted-ink">
                {section.title}
              </h3>
              <ul className="mt-2 space-y-1.5 font-serif">
                {section.blocks.map((block, index) => (
                  <li key={index} className="leading-relaxed">
                    {block.text}
                    {block.citations.map((citation) => (
                      <button
                        key={citation.utterance_id}
                        type="button"
                        onClick={() => onCite(citation.utterance_id)}
                        aria-label={strings.jumpTo(formatClock(citation.start_ms))}
                        className="ml-1.5 rounded bg-line px-1.5 font-sans text-xs tabular-nums text-muted-ink hover:text-accent"
                      >
                        {formatClock(citation.start_ms)}
                      </button>
                    ))}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </article>
      ) : (
        !failed && (
          <div className="text-muted-ink">
            <p>{strings.noNote}</p>
            {canWrite && (
              <button type="button" onClick={onWrite} className="mt-3 rounded-md bg-accent px-3 py-1.5 text-paper">
                {strings.writeNote}
              </button>
            )}
          </div>
        )
      )}
    </div>
  );
}
```

`frontend/src/components/MeetingView.tsx`:

```tsx
import { useEffect, useState } from "react";
import type { MeetingDetail } from "@/bridge";
import { NoteView } from "@/components/NoteView";
import { TranscriptView } from "@/components/TranscriptView";
import { formatDate, formatDuration } from "@/format";
import { cn } from "@/lib/utils";
import { strings } from "@/strings";
import type { NoteStatus } from "@/useEvra";

interface MeetingViewProps {
  detail: MeetingDetail;
  isLive: boolean;
  noteStatus: NoteStatus | undefined;
  hints: string[] | undefined;
  canWrite: boolean;
  onWrite: () => void;
  onRename: (title: string) => Promise<boolean>;
}

type Tab = "note" | "transcript";

export function MeetingView({ detail, isLive, noteStatus, hints, canWrite, onWrite, onRename }: MeetingViewProps) {
  const [tab, setTab] = useState<Tab>(isLive ? "transcript" : "note");
  const [highlight, setHighlight] = useState<string | null>(null);
  const stage = noteStatus?.stage;
  useEffect(() => {
    if (stage) setTab("note");
  }, [stage]);
  const { meeting } = detail;

  function cite(utteranceId: string) {
    setHighlight(utteranceId);
    setTab("transcript");
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b border-line px-6 pt-4">
        <Title title={meeting.title} onRename={onRename} />
        <p className="mt-1 text-xs text-muted-ink">
          {[formatDate(meeting.started_at), formatDuration(meeting.duration_ms), strings.oneOnOne].filter(Boolean).join(" · ")}
        </p>
        {hints && hints.length > 0 && (
          <ul aria-label={strings.captureNotes} className="mt-2 space-y-0.5 text-xs text-muted-ink">
            {hints.map((hint) => (
              <li key={hint}>{hint}</li>
            ))}
          </ul>
        )}
        <div role="tablist" aria-label={strings.meetingTabs} className="mt-3 flex gap-5">
          {(["note", "transcript"] as const).map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={tab === name}
              onClick={() => setTab(name)}
              className={cn("border-b-2 pb-2 text-sm", tab === name ? "border-accent text-ink" : "border-transparent text-muted-ink")}
            >
              {name === "note" ? strings.noteTab : strings.transcriptTab}
            </button>
          ))}
        </div>
      </div>
      <div role="tabpanel" className="min-h-0 flex-1">
        {tab === "note" ? (
          <NoteView note={detail.note} status={noteStatus} canWrite={canWrite} onWrite={onWrite} onCite={cite} />
        ) : (
          <TranscriptView utterances={detail.utterances} follow={isLive} highlightId={highlight} />
        )}
      </div>
    </div>
  );
}

function Title({ title, onRename }: { title: string; onRename: (title: string) => Promise<boolean> }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);

  async function save() {
    if (await onRename(draft)) setEditing(false);
  }

  if (!editing) {
    return (
      <h2 className="flex items-center gap-2 font-serif text-2xl">
        {title}
        <button
          type="button"
          aria-label={strings.renameMeeting}
          onClick={() => {
            setDraft(title);
            setEditing(true);
          }}
          className="text-base text-muted-ink hover:text-accent"
        >
          ✎
        </button>
      </h2>
    );
  }
  return (
    <input
      aria-label={strings.meetingTitle}
      autoFocus
      value={draft}
      maxLength={200}
      onChange={(event) => setDraft(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === "Enter") void save();
        if (event.key === "Escape") setEditing(false);
      }}
      onBlur={() => setEditing(false)}
      className="w-full rounded-md border border-line bg-paper px-2 py-1 font-serif text-2xl"
    />
  );
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `npm --prefix frontend run test -- src/components` then `npm --prefix frontend run typecheck` and `npm --prefix frontend run lint`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
uv run python tools/check.py   # must show no FAIL
git add frontend/src/components
git commit -m "feat: meeting list, live transcript, cited note and meeting view"
git push
```

---

### Task 11: The window, end to end — then the real run and the records

**Files:**
- Modify: `frontend/src/App.tsx`, `frontend/src/App.test.tsx` (replaced), `PROGRESS.md`, `DECISIONS.md`, `BACKLOG.md`

**Interfaces:**
- Consumes: `useEvra` (Task 8), `TopBar`, `Banner` (Task 9), `MeetingList`, `MeetingView` (Task 10).
- Produces: the M3c window: top bar over a meetings list and the open meeting.
- **Rules:** `isLive` = the open meeting is the one being recorded. `canWrite` = the open meeting is not live, the service is idle, and it has a transcript.

- [ ] **Step 1: Write the failing tests**

Replace `frontend/src/App.test.tsx` with:

```tsx
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";
import App from "@/App";
import { emit, setApiForTests, type MeetingSummary } from "@/bridge";
import { DETAIL, MEETING, makeFakeApi } from "@/test/fakeApi";

afterEach(() => setApiForTests(null));

const LIVE: MeetingSummary = {
  ...MEETING,
  id: "m2",
  title: "Recording 2026-09-28 13:51",
  state: "recording",
  has_note: false,
  duration_ms: null,
};

it("opens on the newest meeting's note and jumps from a citation to its transcript line", async () => {
  setApiForTests(makeFakeApi());
  render(<App />);
  expect(await screen.findByText("Launch moves to October 14.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Jump to 01:05 in the transcript" }));
  expect(screen.getByRole("tab", { name: "Transcript" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByText("Marketing wants October 14.").closest("li")).toHaveAttribute("data-highlighted", "true");
});

it("records, shows the live transcript, then the note once it is written", async () => {
  let meetings = [MEETING];
  let noted = false;
  const api = makeFakeApi({
    list_meetings: async () => meetings,
    get_meeting: async (id) =>
      id === "m2" ? { meeting: LIVE, utterances: [], note: noted ? DETAIL.note : null } : DETAIL,
  });
  setApiForTests(api);
  render(<App />);
  await screen.findByText("Launch moves to October 14.");

  await userEvent.click(screen.getByRole("button", { name: "Record" }));
  expect(api.start_recording).toHaveBeenCalledWith("");
  meetings = [LIVE, MEETING];
  act(() => emit("recording.state", { state: "recording", meeting_id: "m2", started_at: Date.now() }));
  expect(await screen.findByRole("tab", { name: "Transcript", selected: true })).toBeInTheDocument();
  act(() =>
    emit("transcript.utterance", { meeting_id: "m2", id: "x1", channel: 0, speaker: "You", start_ms: 1_000, end_ms: 2_000, text: "Hello there." }),
  );
  expect(screen.getByText("Hello there.")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Stop" }));
  expect(api.stop_recording).toHaveBeenCalled();
  act(() => {
    emit("recording.state", { state: "processing", meeting_id: "m2" });
    emit("note.stage", { meeting_id: "m2", stage: "writing" });
  });
  expect(await screen.findByRole("status")).toHaveTextContent("Writing note…");
  expect(screen.getByRole("button", { name: "Writing note…" })).toBeDisabled();

  noted = true;
  act(() => {
    emit("note.ready", { meeting_id: "m2" });
    emit("recording.state", { state: "idle" });
  });
  expect(await screen.findByText("Launch moves to October 14.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Record" })).toBeEnabled();
});

it("explains a failed note and retries it", async () => {
  const api = makeFakeApi({ get_meeting: async () => ({ ...DETAIL, note: null }) });
  setApiForTests(api);
  render(<App />);
  await screen.findByRole("button", { name: "Write note" });
  act(() => emit("note.failed", { meeting_id: "m1", reason: "ollama_down" }));
  expect(screen.getByRole("alert")).toHaveTextContent("Ollama isn't running");
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(api.write_note).toHaveBeenCalledWith("m1");
});

it("shows why recording could not start", async () => {
  setApiForTests(
    makeFakeApi({
      start_recording: async () => ({
        ok: false,
        error: "microphone 'Headset' is not connected",
        hint: "Pick the microphone again in Evra, or check that it is connected and turned on.",
      }),
    }),
  );
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Record" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("is not connected");
  expect(alert).toHaveTextContent("Pick the microphone again");
});

it("renames a meeting", async () => {
  const api = makeFakeApi();
  setApiForTests(api);
  render(<App />);
  await userEvent.click(await screen.findByRole("button", { name: "Rename meeting" }));
  const input = screen.getByRole("textbox", { name: "Meeting title" });
  await userEvent.clear(input);
  await userEvent.type(input, "Sync with Priya{Enter}");
  expect(api.rename_meeting).toHaveBeenCalledWith("m1", "Sync with Priya");
});

it("shows transcript and note text as text, never as HTML", async () => {
  const evil = "<img src=x onerror=alert(1)> </script><b>bold</b>";
  setApiForTests(
    makeFakeApi({
      get_meeting: async () => ({
        ...DETAIL,
        note: { model: "m", sections: [{ id: "summary", title: "Summary", blocks: [{ text: evil, citations: [] }] }] },
      }),
    }),
  );
  render(<App />);
  expect(await screen.findByText(evil)).toBeInTheDocument();
  expect(document.querySelector("img")).toBeNull();
  expect(document.querySelector("b")).toBeNull();
});

it("says so when Python can't be reached", async () => {
  setApiForTests(makeFakeApi({ app_info: async () => { throw new Error("boom"); } }));
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent("couldn't reach its Python side");
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `npm --prefix frontend run test -- src/App.test.tsx`
Expected: FAIL — the M0 screen has no Record button, tabs or note.

- [ ] **Step 3: Implement**

Replace `frontend/src/App.tsx` with:

```tsx
import { Banner } from "@/components/Banner";
import { MeetingList } from "@/components/MeetingList";
import { MeetingView } from "@/components/MeetingView";
import { TopBar } from "@/components/TopBar";
import { strings } from "@/strings";
import { useEvra } from "@/useEvra";

// The main window (M3c spec §4): top bar, meetings list, the open meeting.
export default function App() {
  const { state, select, startRecording, stopRecording, writeNote, rename, dismissStartError } = useEvra();
  if (state.bridgeError) {
    return (
      <main className="mx-auto max-w-xl p-10">
        <Banner message={strings.bridgeDown} hint={state.bridgeError} />
      </main>
    );
  }
  const { recording, detail } = state;
  const liveId = recording.state === "recording" ? (recording.meeting_id ?? null) : null;
  const isLive = detail !== null && detail.meeting.id === liveId;
  const canWrite = detail !== null && !isLive && recording.state === "idle" && detail.utterances.length > 0;
  return (
    <div className="flex h-screen flex-col">
      <TopBar
        appName={state.appName}
        recording={recording}
        levels={state.levels}
        mics={state.mics}
        startError={state.startError}
        onStart={(mic) => void startRecording(mic)}
        onStop={() => void stopRecording()}
        onDismissError={dismissStartError}
      />
      <div className="flex min-h-0 flex-1">
        <aside className="w-72 shrink-0 border-r border-line">
          <MeetingList meetings={state.meetings} selectedId={state.selectedId} liveId={liveId} onSelect={select} />
        </aside>
        <main className="min-w-0 flex-1">
          {detail ? (
            <MeetingView
              key={detail.meeting.id}
              detail={detail}
              isLive={isLive}
              noteStatus={state.noteStatus[detail.meeting.id]}
              hints={state.hints[detail.meeting.id]}
              canWrite={canWrite}
              onWrite={() => void writeNote(detail.meeting.id)}
              onRename={(title) => rename(detail.meeting.id, title)}
            />
          ) : (
            <p className="p-10 text-muted-ink">{strings.selectMeeting}</p>
          )}
        </main>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run every check**

Run: `npm --prefix frontend run test`, `npm --prefix frontend run typecheck`, `npm --prefix frontend run lint`, then `uv run python tools/check.py`.
Expected: all pass, no `FAIL`.

- [ ] **Step 5: Commit the window**

```bash
git add frontend/src/App.tsx frontend/src/App.test.tsx
git commit -m "feat: the main window records a 1:1 and shows its live transcript and cited note"
git push
```

- [ ] **Step 6: Run it for real**

```bash
npm --prefix frontend run build
uv run evra run
```

With Ollama running and a video with speech playing (or a real call on headphones):
1. The window opens on the newest meeting; the mic picker shows "Windows default (…)" plus the connected mics.
2. Press **Record**: "Loading…" (first time), then **Stop**, the timer and both level bars move; live lines appear on the Transcript tab.
3. Press **Stop**: "Writing note…", then the note appears once; a time chip jumps to its highlighted transcript line.
4. Stop Ollama (tray → Quit) and press **Retry** on any meeting's note: the "Ollama isn't running" banner appears; start Ollama and Retry writes it.
5. Pick a Bluetooth mic, turn the earbuds off, press **Record**: the "not connected" banner appears and no new meeting is added.
6. Start a recording and close the window: run `uv run evra note` — the meeting closed mid-recording is there with its transcript.

Take a screenshot of the Evra window only (never the full screen), check it, then delete it. Record what happened, without meeting content, in Step 7.

- [ ] **Step 7: Record decisions, progress and follow-ups**

Append to `DECISIONS.md`:

```markdown

## M3c scope: the main window first (2026-10-02)
- **Context:** BUILD.md §10 lists the meeting window under M3; it must stay on top without stealing focus, which is the M2 spike that was skipped.
- **Decision (owner):** M3c ships the main window only: Record/Stop with timer, levels and live transcript, the meetings list, Note and Transcript tabs, the automatic note with Retry. The floating meeting window follows the M2 focus spike.
- **Consequences:** during a call the main window is the meeting window; HC3 is done from it.

## Microphones are chosen by name on the default input's host API (2026-10-02)
- **Context:** Windows lists every mic once per host API (MME, DirectSound, WASAPI, WDM-KS) and Bluetooth reconnects renumber them; sounddevice refuses a bare name that matches several ("Multiple input devices found"); MME cuts names at 31 characters (`spikes/mic_names.py`).
- **Decision:** `evra.capture.devices` lists the mics of the default input's host API (MME, the API `MicSource(None)` already records from), shows the full name from another host API when MME cut it, stores the chosen name in settings (`mic_name`, `""` = Windows default) and resolves it to that API's device index at Record. A name that is gone fails before any meeting exists, and the picker keeps showing it as "(not connected)".
- **Consequences:** WASAPI-only devices are not offered; revisit if one is ever missing from the list.

## Meetings are created only once capture runs (2026-10-02)
- **Context:** M3a created the meeting before opening the devices, so a missing mic left a `failed` empty meeting.
- **Decision:** `LiveRecording` opens capture first and creates the meeting right after; `evra record` and the window share it. Segments cut before the transcriber exists are held and handed over in order.
- **Consequences:** a failed start leaves nothing behind; `test_capture_start_failure_creates_no_meeting` replaces the M3a test that expected a `failed` meeting.

## The window's recording and note flow (2026-10-02)
- **Decision:**
  - One recording or note job at a time (`idle → loading → recording → stopping → processing → idle`); Record is refused while a note is written; refused calls get the current state back.
  - The note is written automatically after Stop (D16); failures carry a fixed reason code, never error text. `no_transcript` was added to the spec's codes for a recording with no speech.
  - Closing the window saves a running recording and writes no note; on the next start, meetings left `processing` become `ready` (Retry writes the note) and meetings left `recording` become `failed`.
- **Consequences:** an `evra record` running in another process while the app starts would see its meeting marked `failed`; run one recorder at a time.
```

Add an M3c section at the top of `PROGRESS.md` (below the header lines): one line per task 1–11, the result of Step 6 (what worked, timings such as "note appeared N s after Stop", any problem), and "Next: HC3 — a real 1:1 recorded and noted from the window".

Append to `BACKLOG.md`:

```markdown

## M3c follow-ups (2026-10-02)

- Floating meeting window (always on top, never steals focus) after the M2 focus spike.
- Record while a note is still being written (today Record waits until the note is done).
- Offer WASAPI-only microphones if one is ever missing from the picker.
- Delete a meeting from the window (with its audio and keys, BUILD.md §8.2).
```

Then:

```bash
uv run python tools/check.py   # must show no FAIL
git add DECISIONS.md PROGRESS.md BACKLOG.md
git commit -m "docs: record M3c decisions, progress and follow-ups"
git push
```

---

## Self-Review

- **Spec coverage:**
  - §1 goal → Tasks 5, 8–11; success = HC3 from the window (Task 11 Step 6, then the owner).
  - §2 decisions: scope → Task 11 DECISIONS; automatic note → Task 5; mic by name → Tasks 1, 5, 9; approach A → Tasks 5, 6, 8.
  - §3.1 service → Task 5 (states, loading, mic error before a meeting, note thread, Retry, refused calls, close while recording); shared recording loop → Task 2.
  - §3.2 events → Task 5 (all seven) and Task 8 (handled); levels as RMS 0..1 → Task 2 `frame_level`.
  - §3.3 bridge calls → Task 6 (all eight, plus `chosen` in `list_mics`); `mic_name` setting → Task 1.
  - §3.4 rules → Global Constraints; per-thread connections in Tasks 5–6; no content in logs (reason codes and type names only).
  - §4 window → Tasks 9–11 (top bar, list, tabs, note chips, transcript follow/highlight, failure banners, style tokens, fonts bundled, `strings.ts`, accessible names).
  - §4.1 failure sentences → Task 7 `noteFailureText` (+ `no_transcript`).
  - §5 testing → each task; HC3 → Task 11 Step 6.
  - §6 out of scope → BACKLOG in Task 11.
- **Placeholder scan:** the only fill-ins are Task 11 Step 6 observations and the PROGRESS lines that record them — measurements that can't be known in advance.
- **Type consistency:**
  - `LiveRecording.start() -> str`, `.stop(*, state)`, `.meeting_id`, `.started_at_ms` match the `Recording` protocol (Task 5);
  - `RecordingKit.new_recording(mic, *, title, situation, on_utterance, on_level)` matches `Kit` and `FakeKit`;
  - `MeetingService` methods match `Control` (Task 6) and `StubControl`;
  - payload keys (`meeting_id`, `started_at`, `speaker`, `start_ms`, `citations[].utterance_id/start_ms`, `reason`, `model`, `hints`) match between Tasks 3, 5, 6, 7 and 8;
  - `NoteStatus` and `StartError` (Task 8) are the types Tasks 9–10 import.
- **Review Focus:** each of the five lines names its owning test, and each test is in its task's Step 1.
