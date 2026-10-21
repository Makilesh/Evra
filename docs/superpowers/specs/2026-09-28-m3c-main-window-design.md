# M3c — Main window for the 1:1 flow (design)

Status: approved in conversation on 2026-09-28; the owner reviews this written spec before the implementation plan.
Branch: `main-window` (from `windows-capture`). Source of truth: `BUILD.md` (§4, §7.3, §8.1, §8.4, §8.5, §9.1). This spec narrows BUILD.md's M3 UI scope to what M3c delivers.

## 1. Goal and success

The owner starts a 1:1 from the Evra window, watches the live transcript, presses Stop, and a cited note appears in the window; clicking a citation jumps to that transcript line. Everything the CLI (`evra record`, `evra note`) does is reachable from the window, and the CLI keeps working.

**Success:** HC3 from the window — a real 1:1 on headphones, recorded and noted without touching the terminal.

## 2. Decisions taken in the brainstorm

| Topic | Decision |
| --- | --- |
| Scope | Main window only. The floating meeting window waits for the M2 "focus" spike. |
| Note after Stop | Written automatically (BUILD.md §7.3, D16): stage progress, then the finished note appears once. On failure the transcript stays and a banner explains, with Retry. |
| Microphone | A picker next to Record, defaulting to the Windows default mic; the choice is remembered **by name** in settings (Bluetooth renumbers indices). |
| Architecture | Approach A: Python owns the session and pushes events; React only renders. |

## 3. Python side

### 3.1 `MeetingService` (new, app process)

One recording at a time. States: `idle → loading → recording → stopping → processing → idle`.

- `start(mic_name: str | None) -> str` (meeting id)
  - Loads what recording needs on first use (speech models, ASR worker warm-up, VAD), pushing `loading`.
  - Opens capture with the named mic; a missing or busy mic raises the same `CaptureError` + hint as `evra record`, **before** a meeting is created.
  - Creates the meeting (mode `one_on_one`, situation from settings, template `one_on_one`) and a live transcript version, starts `LiveTranscriber`, pushes `recording`.
- `stop() -> None`: stops capture, flushes the segmenters, drains the transcriber, finishes the meeting (`processing` while the note is written), pushes capture health hints and stats, then starts the note thread.
- Note thread: `write_note` → `NoteStore.save_generation` → meeting `ready` → `note.ready`; on failure the meeting is still `ready` (transcript kept) and `note.failed` carries a reason code. A zero-point note is not saved (M3b rule).
- `write_note(meeting_id)`: Retry / re-run for a finished meeting, same thread and events.
- Calls that do not fit the current state (Record twice, Stop while idle) are ignored and answered with the current `recording.state`; they never raise into the UI.
- Window closed while recording: the service stops the recording cleanly (same wrap-up as Ctrl+C in `evra record`) so the meeting and transcript are saved; the note is not written on shutdown.

**Reuse, no rewrite:** capture (M1); `SpeechSegmenter`, `AsrClient`, `LiveTranscriber`, `MeetingStore` (M3a); `write_note`, `NoteStore`, `OllamaProvider` (M3b). The recording loop in `transcribe/record.py` is split so the CLI and the service share one implementation of start → run → wrap-up.

### 3.2 Events pushed to the window (`EventBus.emit`)

| Event | Payload |
| --- | --- |
| `recording.state` | `{state, meeting_id?, started_at?}` |
| `recording.levels` | `{you: 0..1, them: 0..1}`, about 10 per second while recording |
| `transcript.utterance` | `{meeting_id, id, channel, speaker, start_ms, end_ms, text}` |
| `recording.finished` | `{meeting_id, utterances, failed_segments, hints: [str]}` |
| `note.stage` | `{meeting_id, stage}` — e.g. `writing` |
| `note.ready` | `{meeting_id}` (the window then calls `get_meeting`) |
| `note.failed` | `{meeting_id, reason}` with `reason` ∈ `ollama_down`, `model_missing`, `too_long`, `cut_off`, `invalid`, `nothing_supported`, `timeout`, `llm_error`; `model` included for `model_missing` |

Level values are RMS of the latest frames, scaled to 0..1 — never audio content.

### 3.3 Bridge calls (`BridgeApi`)

| Call | Returns |
| --- | --- |
| `list_meetings()` | newest first: `{id, title, started_at, duration_ms, state, has_note}` |
| `get_meeting(id)` | `{meeting, utterances: [...], note: {sections: [{id, title, blocks: [{text, citations}]}]} \| null}` |
| `list_mics()` | `{default: name, mics: [name]}` |
| `start_recording(mic_name)` | `{ok, meeting_id?, error?, hint?}` |
| `stop_recording()` | `{ok}` |
| `write_note(id)` | `{ok}` (progress arrives as events) |
| `rename_meeting(id, title)` | `{ok}` (title trimmed, 1–200 characters) |
| `recording_state()` | current state (for a window that reloads) |

The chosen mic is saved in settings as `mic_name` (new top-level field, default `""` = the Windows default mic; TOML cannot store null).

### 3.4 Rules that stay

- One SQLite connection per thread; the service opens its own.
- Logs carry counts and codes only — never transcript or note text (CLAUDE.md).
- Transcript and note text go only to the user's own window through the bridge.
- Evra opens no listener; pywebview loads `file://` (or the dev server in `--dev`).

## 4. The window (React)

```
┌──────────────────────────────────────────────────────────────────────┐
│ Evra                                      [Mic: Headset ▾] [● Record]│
├───────────────────┬──────────────────────────────────────────────────┤
│ Search meetings   │  Weekly 1:1  ✎            28 Sep · 12 min · 1:1  │
│───────────────────│  [ Note ]  [ Transcript ]                        │
│ ● Recording 12:04 │  Summary                                         │
│ Weekly 1:1        │  • Launch moves to October 14.  [01:05]          │
│ Recording 13:51   │  Action items                                    │
│ …                 │  • You: send the proposal by Thursday. [01:50]   │
└───────────────────┴──────────────────────────────────────────────────┘
```

- **TopBar:** mic picker; Record button (teal) → while recording red **Stop** + timer + two level bars (You / Them); "Loading…" while speech recognition loads; capture errors as a banner under the bar.
- **MeetingList:** newest first, title + date + length, live row while recording, title filter.
- **MeetingView:** title renamed in place; tabs **Note** and **Transcript**; the live meeting opens on Transcript.
- **NoteView:** serif text, section headings, a `[mm:ss]` chip per point; clicking a chip switches to Transcript, scrolls to and highlights that line. While the note is written: stage progress, then the note appears once. Failure: a calm banner with the reason's sentence and fix, plus **Retry**.
- **TranscriptView:** time, speaker colour (You / Them), text; follows new lines while recording unless the user scrolled up.
- **Style ("Quiet paper", D19):** existing tokens in `index.css`; light/dark follows Windows; Newsreader (content) and Inter (UI) bundled locally via `@fontsource` packages (SIL OFL fonts, MIT packaging — licence gate); no network fetches. Every control has an accessible name; all user-facing strings in one `strings.ts` (i18n later).
- **Components:** plain React + Tailwind, our own small components; a headless primitive only where needed (the mic dropdown can be a native `<select>`). No router.

### 4.1 Failure sentences (UI)

| Reason | Sentence | Action |
| --- | --- | --- |
| `ollama_down` | Ollama isn't running. Start it from the system tray (or install it from ollama.com). | Retry |
| `model_missing` | The note model isn't installed. Run: `ollama pull <model>` | Retry |
| `too_long` | This meeting is too long for one note pass yet. | — |
| `cut_off` | The model ran out of room while writing. | Retry |
| `invalid` | The model didn't return a valid note. | Retry |
| `nothing_supported` | Nothing in the note could be checked against the transcript. | Retry |
| `timeout` | The model took too long. | Retry |
| `llm_error` | The note couldn't be written. | Retry |

## 5. Testing

- **Python:** `MeetingService` with `FakeSource` capture, a fake ASR and `FakeProvider`: event order for a full run, what is stored, each failure reason, close-while-recording, Record twice / Stop while idle, mic-missing before a meeting exists. `BridgeApi` methods over a temporary database. `record.py` keeps its existing tests after the split.
- **React:** Vitest + Testing Library with a fake bridge: list, live transcript append + follow, note stages then note once, citation click → transcript line highlighted, failure banner + Retry, mic choice, rename.
- **By hand (HC3):** a real 1:1 recorded and noted from the window.

## 6. Out of scope for M3c

Floating meeting window (after the M2 spike); tray, hotkeys, settings screen, onboarding, Ctrl+K (M6); note editing, regenerate, version history, "My notes" (M5); deleting meetings (with audio/keys, M5–M6); audio playback (needs retained audio, M5); speaker naming (M4).
