# PROGRESS.md — what we did, what we built

Newest first. Each entry: date, what happened, and (once code exists) the commit hash.

## 2026-10-02 — M3c Main window (branch `main-window`)

- Task 1: microphones listed and chosen by name on the default input's host API (Windows lists each mic per audio API; bare names were ambiguous); `mic_name` setting.
- Task 2: one `LiveRecording` core for `evra record` and the window; capture opens before the meeting exists, so a missing mic leaves nothing behind; per-channel levels.
- Task 3: meeting list, rename, startup recovery of meetings left mid-way; JSON views for the window.
- Task 4: one note job (`write_and_save`) with fixed failure codes, shared by `evra note` and the window.
- Task 5: `MeetingService` — one recording at a time, events to the window, automatic note after Stop, Retry, closing the window saves the recording.
- Task 6: bridge calls (meetings, mics, record/stop, write note, rename, state); events to a closed window are dropped; the app shuts the service down when the window closes.
- Task 7: frontend types, strings, formats; Inter + Newsreader bundled (no web fonts).
- Task 8: `useEvra` keeps all window state from Python's events.
- Tasks 9–10: top bar (mic picker, Record/Stop, timer, level meters), meetings list, live transcript, cited note, meeting view with rename.
- Task 11: the window end to end (50 frontend tests).
- Real runs (2026-10-02): `evra record` with an unknown mic fails cleanly with no meeting; the service end to end with real capture, Parakeet and a public test clip played on the speakers: speech recognition ready in 2.6 s, both channels transcribed, levels moved, states in order; with Ollama stopped the note reported `ollama_down`, and Retry with Ollama up wrote the note in 10.4 s. The window opened on the latest meeting's cited note and closed cleanly.
- Final review (fresh reviewer): 0 Critical, 2 Important + 2 re-graded; fixed: mic list follows devices connected after start, an unexpected start error no longer sticks on "Loading…", choosing a mic keeps settings edited meanwhile, speech recognition unloads after 5 idle minutes. Minors in BACKLOG.
- **HC3 (owner, 2026-10-02), Bluetooth earbuds + Google Meet in Brave:**
  - 17:35 call: only "You" — Evra listened to the right output (Headphones, realme Buds Air7) but Windows played nothing on it for >95% of the recording; not reproduced since.
  - 21:31 test (owner on the phone as the other participant): "Them" lines from Meet, note with citations; the owner's voice also appears as "You" because the earbud mic hears them talking into the phone (test setup, not echo); 6 Bluetooth mic dropouts (360 ms); the owner's name is misheard.
  - Check from a fresh process (`evra capture-test 30` during the Meet): system channel −24.6 dBFS, PASS.
- Next: HC3 with a real second person; then merge M3c.

## 2026-09-28 — M3b Local LLM notes (branch `local-llm-notes`)

- Setup: Ollama upgraded 0.16.0 → 0.34.4 (winget); gemma4:12b, qwen3.5:9b, ministral-3:14b pulled into the owner's existing Ollama model folder (DECISIONS: Ollama is an external app).
- Task 1: `OllamaProvider` — structured JSON calls over Ollama's REST API with the standard library (loopback only, no proxies, redirects refused; the `ollama` package was dropped because httpx pulls in MPL-2.0 `certifi`); errors become one-line causes.
- Task 2: `NoteDraft` schema, prompt files A1/A9 (Appendix A), templates `one_on_one` and `general`.
- Task 3: A1 prompt input — utterances as `u:1…u:N` in time order, `You`/`Them` labels, data made inert inside its tags.
- Task 4: grounding (§7.5, lexical): bullets with unknown citations, too little word overlap, or numbers/names not in the cited lines are dropped and counted.
- Task 5: note writer — one pass, one JSON repair, too-long meetings refused, Ollama-side truncation detected.
- Task 6: generations + output blocks stored; the newest note is current.
- Task 7: `evra note [MEETING_ID]` — first real note from a dev recording with gemma4:12b in 12.0 s.
- Task 8: `tools/bakeoff_notes.py` + synthetic 1:1 fixture (27 utterances, 10 expected facts). Bake-off: **gemma4:12b** chosen (100% valid points, 10/10 expected facts, 20.3 s warm for a 4-minute call, fully on GPU); qwen3.5:9b fallback; ministral-3:14b doesn't fit 12 GB. The bake-off also found two fixes: grounding now cites the nearby line a name/number came from (it had dropped true points), and console output never crashes on cp1252.
- **M3b done** (pending HC3 on a real 1:1): `evra record` → `evra note` gives a cited note. Next: M3c (UI).

## 2026-09-28 — M3a Transcription (branch `one-on-one-notes`)

- Task 1: models.yaml (Silero VAD, Parakeet v3 int8) + modelstore (resumable, SHA-256 verified, archive whitelist); spike downloads adopted without re-download.
- Task 2: Parakeet engine (sherpa-onnx, CPU) with word timings from BPE tokens; sherpa-onnx-core pinned explicitly (its DLLs were missing, Windows loaded System32 onnxruntime 1.17).
- Task 3: SpeechSegmenter — Silero VAD per channel, 512-sample windows, 300 ms pre-roll, timeline-aligned.
- Task 4: Worker processes — spawn, typed request/response, futures, crash → restart, idle stop, errors as type names only.
- Task 5: ASR worker (Parakeet in its own process) + AsrClient — real transcription through the worker in 1.8 s incl. spawn + model load.
- Task 6: MeetingStore — meetings, current transcript version, utterances with word timings.
- Task 7: LiveTranscriber — ordered queue → ASR → utterances (absolute times) on its own DB connection; crash retried once; failures counted.
- Task 8: `evra models [--download]`, `evra transcribe WAV` (VAD → Parakeet worker); en.wav transcribed correctly in 1.8 s including model load.
- Task 9: `evra record SECONDS` — 1:1 live transcript (You/Them) into SQLite. Dev-machine runs: 2 utterances in 15 s, 0 failed segments, ASR real-time factor 0.031; health hints now printed, and dropouts always explained (Bluetooth hands-free switching caused short dropouts).
- Final review fix pass (fresh reviewer: 1 Critical, 3 Important, 12 Minor): a hung ASR worker is killed and replaced after its deadline instead of freezing recording and shutdown (04b1b99); Ctrl+C ends `evra record` cleanly at any point (2127dc8); continuous speech is cut every 20 s without duplicated words (40092df); the live transcriber survives database errors and the summary says what it could not finish (b19d7bf); sherpa-onnx pinned to its core's version (4d11a0b). Remaining minors in BACKLOG "M3a follow-ups".
- **M3a done:** a 1:1 call becomes a stored, labelled, timestamped transcript. Next: M3b (local LLM note writing).

## 2026-09-24 — M1 Windows capture (branch `windows-capture`)

**Status (2026-09-28): parked by the owner.** Code complete and reviewed; soak DoD met (drift 4.0 ms, 0 drops). Open items moved to BACKLOG.md "M1 parked items". No `p1-m1-done` tag until they close.

- Task 1: Frames + ToMono16k streaming converter (libsamplerate, D24).
- Task 2: ChunkRing — non-blocking callback hand-off, drops counted.
- Task 3: SourceClock — steady timestamps from jittery/bursty callbacks; follows drift; detects real jumps.
- Task 4: ChannelTimeline — ≥50 ms gaps filled, >20 ms drift corrected in 10 ms steps (60-min simulated drift < 30 ms throughout), silence padding.
- Task 5: CapturePipeline — per-channel drain/clock/convert/place/emit; loopback padding, overflow gaps, device swap, levels in dBFS.
- Task 6: AES-GCM spill segments (authenticated header, atomic writes) + per-meeting keys in Credential Manager (service Evra, user meeting/<id>).
- Task 7: FakeSource, MicSource (sounddevice), LoopbackSource (PyAudioWPatch), DefaultOutputWatcher (pycaw, D25); hardware tests 4/4 on the dev machine.
- Task 8: CaptureSession — sources + pipeline thread + output watcher; CaptureHealth with drift, drops, gaps, hints.
- Task 9: `evra capture-test SECONDS` — two WAVs + health.json; spill + key cleaned up. Dev-machine 10 s run: PASS (0 drops, inter-channel drift 0.0 ms, mic -26.4 dBFS, system -16.5 dBFS, earbuds 44.1k mic + 48k loopback).
- Final review (fresh reviewer): 1 Critical + 7 Important, all fixed test-first:
  - device swap could crash the pipeline thread (2-ch → 1-ch headset);
  - callback stalls created false gaps;
  - short loopback silences reordered audio;
  - starts dropped audio (start time + clock warm-up);
  - loopback errors unmapped and the watcher died;
  - health passed stalled / overflowing / blocked channels;
  - spill reader accepted swapped segments;
  - dead streams never restarted.
  Two more found on real hardware: start-up correction from a late first callback, and padding stretched by a slow device close. 13 minors deferred to BACKLOG.md.
- Real 10 s run on fixed code: PASS — 0 drops, 0 corrections on both channels, inter-channel drift 3.2 ms. Hardware tests 4/4.
- **60-minute soak on the fixed code (2026-09-25, built-in mic + speaker loopback):**
  - **DoD met:** inter-channel drift 4.0 ms (limit 30), 0 dropped chunks, 0 overflows, both channels 3600.3 s. 1 drift correction in the hour (mic).
  - **Memory:** Evra flat at 86–123 MB for the whole hour, so no leak. It spiked to 310 MB at the end while assembling an hour of WAV (capture-test only).
  - **Health said FAIL** because of 3 short gaps it labelled "dropout":
    - mic, 120 ms + 310 ms at 52:44, while the machine had only 0.7–1.0 GB RAM free (other apps) — most likely real audio lost while Windows was paging;
    - system, 70 ms at 2.7 s — cause not yet understood; to investigate.
  - 12 "silence" gaps on the system channel are expected (nothing playing).

## 2026-09-24 — M0 Bootstrap

- Task 1: Python skeleton, uv-managed 3.12, `evra --version`, CLAUDE.md, README.
- Task 2: AppPaths (platformdirs; `<repo>/.data` from source, D23) and TOML settings with safe reset on corrupt files.
- Task 3: structlog JSON rotating logs (10 × 5 MB) with content redaction above DEBUG.
- Task 4: SQLite store (WAL, FKs, busy timeout) with forward-only atomic migrations; 0001 Phase 1 schema (16 tables).
- Task 5: React 19 + TS 6 + Vite 8 + Tailwind v4 frontend with bridge client, theme, shadcn conventions; single-file build (227 kB) into src/evra/ui/web.
- Task 6: pywebview window loads the single-file UI via file:// — verified 0 listening TCP/UDP sockets; bridge works both ways (built and dev modes); `evra run [--dev] [--debug] [--data-dir]`.
- Task 7: licence gate (226 components: python + npm + models), policy file (MIT-0 allowed; clr-loader override verified MIT), models.yaml, generated THIRD_PARTY_LICENSES.md.
- Task 8: tools/check.py runs ruff (lint + format), mypy, pytest, oxlint, tsc, vitest and the licence gate in one command — all PASS.
- Task 9: GitHub Actions (Windows checks + gitleaks-action v3); local gitleaks 8.30.1 via tools/check.py — no leaks in history.
- Commits: bf0a634 (T1) · 3f940ee (T2) · e81e1c6 (T3) · 6a1b44b (T4) · 78cff1b (T5) · 443edc1 (T6) · 19b6baf (T7) · b1a559f (T8) · 5c1a360 + 3de7053 (T9).
- **M0 done:** CI green (run 35995915108); `tools/check.py` all PASS incl. gitleaks; window round-trips calls both ways; no network listener (0 TCP / 0 UDP, verified with Get-NetTCPConnection / Get-NetUDPEndpoint); 75 Python + 11 frontend tests.
- Final review (fresh reviewer): 0 Critical, 7 fixed with failing-test-first (log tracebacks + redaction on every path, bridge readiness race, BOM settings, WebView2 profile in `.data`, licence gate fail-closed, startup errors logged). 14 minors deferred to BACKLOG.md. 91 Python + 13 frontend tests.
- Next: M1 Windows capture (plan to be written).

## 2026-09-24 — Planning session 1

- Reviewed the agent-written `BUILD_PROMPT.md` v3; archived it at `docs/archive/BUILD_PROMPT.v3.md` (reference only).
- Research pass verified package/model names, licences, Blackwell/CUDA support, Gemini models, TTS options and meeting-bot rules (summary in `BUILD.md` Appendix V).
- Agreed: goals (personal use + portfolio + distributable), Windows first, notes first, English first, local LLM via Ollama, pywebview + React UI, app process + worker processes, all four meeting situations with hybrid first-class, phase roadmap.
- Agreed design section §4 (processes and components).
- Started `BUILD.md` (v4) draft, `BACKLOG.md`, `DECISIONS.md`.
- v4 draft renamed to `BUILD.md` (the living design + build spec).
- Agreed §5 audio pipeline: livekit echo cancellation, Silero VAD, encrypted spill; audio retention 7/30 (default)/90 days/forever re-encoded to Opus (D13).
- Agreed §6 transcription and speakers: Parakeet live + fast pass, pyannote per situation (both channels in hybrid), WeSpeaker voiceprints, voiceprints only for named people (D14), live panel on by default (D15).
- Agreed §7 notepad, alignment and note generation: time + BM25 + embedding alignment, single-pass or map-reduce by context budget, mechanical citation validation, six templates, provenance-safe regeneration; note appears once after stage progress (D16); Qwen3-Embedding in torch worker (D17). Note prompts A1–A9 and schemas carried from v3 into BUILD.md appendices.
- Agreed §8: modes (D18) — 1:1 is the main use case and default, Meeting is the full pipeline, Solo (voice thinking-partner) moves to the start of Phase 3; SQLite schema for Phase 1; job queue with one-GPU-job rule; screens; "Quiet paper" style (D19).
- Agreed §9: failure handling, test layers, one-command checks + licence gate, public-repo rules (D20), Windows CI, Phase 1 quality targets.
- Repo is public at github.com/Makilesh/Evra (branch `core`). Hardened `.gitignore` (`private/`, `.remember/`, audio, env files, node_modules).
- Code licence: FSL-1.1-ALv2 (D21), `LICENSE.md` added.
- Public docs contain only personal-use, portfolio and distribution goals.
- Agreed §10 Phase 1 milestones M0–M6 (1:1 call end-to-end at M3) and human checkpoints; §11 builder rules; git workflow D22 (commit + push after every completed feature).
- Next: owner reviews the full BUILD.md, then an implementation plan for M0 is written.
