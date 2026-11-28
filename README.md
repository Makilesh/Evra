# Evra

Local-first meeting notes for Windows. Evra records your microphone and your computer's audio
on your own machine, without joining the call. It transcribes on the device and writes a meeting
note with a local LLM. Every point in the note cites the transcript lines it came from.

Nothing leaves your computer. Speech recognition runs on the CPU, the note model runs in
[Ollama](https://ollama.com), and Evra opens no network listener of its own.

> **Status:** early development (Phase 1, Windows only). The 1:1 flow works end to end:
> record a call, watch the live transcript, type your own notes, get a cited note. Speaker
> separation, echo cancellation for laptop speakers and installers are still to come.
> See [`PROGRESS.md`](PROGRESS.md) for what is done and [`BUILD.md`](BUILD.md) for the full design.

## What works today

- **Two-channel capture.** Your mic ("You") and the computer's output ("Them") are recorded
  as separate channels through WASAPI loopback, so it works with any call app (Meet, Teams, Zoom…).
- **Live transcript.** [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)
  through sherpa-onnx, with Silero voice activity detection.
- **Cited notes.** After you press Stop, a local model writes a summary, the discussion and
  topics for next time, and lists the action items, decisions and open questions in focused
  calls. Points that can't be checked against the transcript are dropped, not shown. A call
  longer than an hour is read in parts and combined.
- **Action items you can tick.** Each action item has a Done box; the tick survives writing the
  note again.
- **My notes.** Type notes during the call, one line each. Every line is stamped with the time
  you typed it and linked to what was being said, and the note expands the topics you noted. A
  point taken from your notes quotes your line.
- **Ask a meeting.** The Ask tab answers a typed question, or a one-click one such as "What did I
  promise?", from that meeting's transcript. The answer comes as cited points, each checked like
  the note's, or as "Not discussed in this meeting." when the call didn't cover it.
- **Who a 1:1 was with.** Say who the other person was on the meeting's date line, and the
  transcript, the note and their tasks use their name instead of "Them".
- **Promises.** One page lists every open promise across your meetings, both ways: what you
  promised and what they promised. Tick one Done, Undo it, or set it aside as Not a promise.
- **People.** Everyone you have named is on the People page. Each has a page of their own, with
  your open promises both ways and a prep brief for your next 1:1 from your recent notes with
  them, each point citing the meeting it came from.
- **Main window.** Record and stop, pick a mic (remembered by name), browse past meetings,
  rename them, and click a citation to jump to that transcript line.
- **Command line.** Recording, notes, naming meetings from their note and asking also work as
  `evra` commands. Promises, people and the brief are in the window only for now, as are saying
  who a 1:1 was with, ticking action items, typing your own notes, and browsing or renaming
  meetings.

Best results today: a 1:1 call on headphones or earbuds. On laptop speakers your mic also hears
the other person, until echo cancellation lands.

## Requirements

- Windows 11
- [uv](https://docs.astral.sh/uv/) (installs Python 3.12 for you)
- Node.js 24 and npm (to build the UI)
- [Ollama](https://ollama.com) for notes, with the default note model and the embedding model
  (it checks points by meaning and links your typed notes to the transcript):

      ollama pull gemma4:12b
      ollama pull qwen3-embedding:0.6b

  Without the embedding model, notes are still written, and checked by their words alone.

  Evra refuses models that run in Ollama's cloud. To make Ollama itself refuse them too, set
  `OLLAMA_NO_CLOUD=1` before it starts (or `"disable_ollama_cloud": true` in `~/.ollama/server.json`).

Developed on 32 GB RAM with an RTX laptop GPU, but every model has a CPU path.

## Quick start

    git clone https://github.com/Makilesh/Evra.git
    cd Evra
    uv sync
    npm ci --prefix frontend
    npm --prefix frontend run build
    uv run evra models --download    # speech models, ~670 MB, first time only
    uv run evra run                  # opens the Evra window

Press **Record**, have your call, press **Stop**. The note appears once it is written.

While running from the source folder, all app data (database, settings, models, logs) stays
in `.data/` inside the repo. `evra run --data-dir PATH` puts it elsewhere.

## Command line

| Command | What it does |
| --- | --- |
| `uv run evra run` | Open the window (`--dev` uses the Vite dev server, `--debug` adds verbose logs) |
| `uv run evra capture-test 60` | Record mic + system audio for 60 s; writes two WAVs and a health report |
| `uv run evra capture-test 1 --list-devices` | List microphones |
| `uv run evra models [--download]` | Show or download the speech models |
| `uv run evra transcribe FILE.wav` | Transcribe a WAV file |
| `uv run evra record 60` | Record a 1:1 for 60 s with a live transcript in the terminal |
| `uv run evra note [--model NAME]` | Write the note for the latest recording |
| `uv run evra titles` | Name meetings that have a note but still a "Recording …" title; needs Ollama running |
| `uv run python -m evra ask "QUESTION" [--meeting-id ID]` | Ask the latest meeting (or `--meeting-id`) a question; needs Ollama running |

## How it works

```
Evra (app process)                                   separate processes
├── pywebview window ⇄ React UI (js_api + events)
├── capture: mic + WASAPI loopback → align → VAD ──▶ speech worker (sherpa-onnx, Parakeet)
├── SQLite store: meetings, transcripts, notes
└── notes: prompt → validate citations ────────────▶ Ollama (local HTTP, loopback only)
```

- Heavy models run in worker processes, so a model crash never stops a recording and memory is
  freed when a worker stops.
- Notes are checked mechanically: each point must cite transcript lines that share its words
  (or, failing that, say the same thing by meaning), and its numbers and names must be in them.
  Unsupported points are dropped; a note with nothing left is never saved.
- Logs carry counts and codes only, never transcript, note or audio content.

## Development

    uv run python tools/check.py          # all checks: ruff, mypy, pytest, frontend lint/types/tests
    npm --prefix frontend run dev         # UI with hot reload, then: uv run evra run --dev --debug
    uv run python tools/license_gate.py   # licence check for every dependency

Layout:

| Path | Contents |
| --- | --- |
| `src/evra/` | App package: capture, transcription, store, notes, LLM client, bridge, services |
| `frontend/` | React + TypeScript + Tailwind app (builds into `src/evra/ui/web/`) |
| `tools/` | Check runner, licence gate, note-model bake-off |
| `tests/` | pytest suites (`-m hardware` for tests that need a real mic and speakers) |
| `docs/superpowers/` | Specs and implementation plans per milestone |

Project records: [`BUILD.md`](BUILD.md) (design, source of truth) · [`PROGRESS.md`](PROGRESS.md) ·
[`DECISIONS.md`](DECISIONS.md) · [`BACKLOG.md`](BACKLOG.md).

## Roadmap

1. **Core notes (in progress):** echo cancellation for laptop speakers, crash recovery of
   recordings, speaker separation and voice recognition, edit and regenerate, onboarding, tray
   and hotkeys.
2. **Knowledge:** search across meetings; import documents and PDFs.
3. **Evra Live:** ask "Hey Evra, …" during a meeting and get answers from past meetings,
   documents and the web, on screen and aloud.
4. **Meet bot:** an assistant the host can admit to a call to speak answers.

## Licence

Evra's code is under [FSL-1.1-ALv2](LICENSE.md): source-available, no competing commercial use,
and each release becomes Apache-2.0 two years after it ships. Third-party components, models and
fonts are listed in [`THIRD_PARTY_LICENSES.md`](THIRD_PARTY_LICENSES.md).
