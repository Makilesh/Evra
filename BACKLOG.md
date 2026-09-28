# BACKLOG.md — deliberately deferred work

Things we decided not to do yet. Move an item into `BUILD.md` when it is scheduled.

## Phases already planned (see BUILD.md §3)

- **Phase 2 — Knowledge:** hybrid search (SQLite FTS5 + vectors), document/PDF import.
- **Phase 3 — Evra Live:** starts with **Solo mode** (voice conversation with Evra as a thinking partner, saved as a note); then wake phrase, answers from meetings + documents + web + LLM, high-quality TTS, overlay.
- **Phase 4 — Google Meet bot:** joins only when the host admits it; speaks answers as an SME agent.

## Languages

- Hindi — Qwen3-ASR (0.6B/1.7B, Apache-2.0) is the leading candidate.
- Tamil — no plan model supports it; candidates: AI4Bharat IndicConformer 600M (MIT, gated), Whisper large-v3; cloud: Gemini 3.5 Transcribe, Sarvam.
- Hinglish (Hindi–English code-mixed) — Oriserve/Whisper-Hindi2Hinglish-Apex (Apache-2.0), Qwen3-ASR.
- Tanglish (Tamil–English code-mixed) — no open model found; cloud is the practical route.
- European languages — Parakeet v3 already covers 25.
- TTS in Indian languages — Indic Parler-TTS (Apache-2.0), Chatterbox Multilingual (Hindi), cloud (Sarvam, ElevenLabs, Gemini TTS).
- Language picker + "Auto" language detection.

## LLM

- Paid LLMs (Gemini 3.8 Flash, others) — compare quality, latency, cost; paid tier only for real meeting content.
- Bundled llama.cpp as an alternative to requiring an Ollama install.

## Platforms and distribution

- macOS (catap / Core Audio taps, macOS 14.2+) and Linux (PipeWire/PulseAudio monitor).
- Installer, auto-update (Velopack), code signing, opt-in crash reporting.

## Performance and quality

- GPU speech-to-text via sherpa-onnx (CUDA 12 wheel; Blackwell support unverified) or another engine.
- Accurate second transcription pass (Granite 4.0 1B Speech / Cohere Transcribe) chosen by benchmark.
- Automatic meeting-situation detection (headphones / speakers / in person / hybrid).
- Suggest a mode switch when more voices are detected than the mode expects (e.g. 1:1 → Meeting).

## Meeting bots beyond Meet

- Microsoft Teams (official route needs C#/.NET Graph media bot or ACS interop).
- Zoom (Meeting SDK + OBF token + signing service).

## M0 review follow-ups (deferred minors, 2026-09-24)

- `load_settings`: survive `OSError` (locked / permission-denied file) and keep timestamped `.bad` backups instead of overwriting.
- Refuse to open a database whose `user_version` is newer than this build's migrations ("created by a newer Evra").
- Licence gate: run pip-licenses with UTF-8 (`encoding="utf-8"`, `PYTHONIOENCODING=utf-8`); print SPDX ids in the register; count build-time CSS (Tailwind preflight) as shipped.
- CI: `uv sync --locked` to catch lock drift; pin all actions by SHA consistently.
- Frontend: take the product name from `app_info` / constants instead of hard-coding "Evra" in `index.html` and `App.tsx`.
- `.gitattributes`: `*.bat text eol=crlf`, `*.cmd text eol=crlf`.
- Bridge: isolate JS event handlers (one throwing handler must not block others); document that `EventBus.emit` blocks and must not run on the GUI thread.
- `vite.config.ts`: `import.meta.dirname` instead of `__dirname`.
- Test: assert the percent-encoded `file://` URL converts back to the same file.
- **Before M3 renders transcript/LLM text:** set pywebview `ALLOW_FILE_URLS = False` and add a CSP to the built `index.html`.
- **Packaging milestone:** lock DEBUG/devtools off in release builds; include the built UI in the bundle; full licence texts in the register; single-instance guard (M6).
- sounddevice 0.5.6 raises a NumPy 2.5 DeprecationWarning (setting array shape) inside its callback path; watch for a sounddevice release before NumPy removes it.

## M1 review follow-ups (deferred minors, 2026-09-24)

- Capture: open the new stream outside the pipeline lock during a device swap (a slow reopen can overflow the mic ring); guard `stop()` against a reopen still in progress.
- `capture-test`: "microphone not found" should suggest `--list-devices`; make `seconds` optional with `--list-devices`; list devices per host API (WASAPI only) and clean driver strings; print safely on non-UTF-8 consoles.
- Output watcher: query `GetDefaultAudioEndpoint(...).GetId()` directly, keep COM initialised per thread, ignore a single transient `None`.
- Run PortAudio init/terminate for the loopback on one fixed thread.
- Spill: `fsync` segment files before rename; count reopen time inside the `device_change` gap; map keyring errors in `run_capture_test`.
- Loopback endpoint role: decide multimedia vs communications default (call apps may use a separate communications device) — needs a DECISIONS entry and an HC1 check.
- Multichannel outputs (5.1/7.1): downmix with proper weights instead of a plain mean.
- M2 AEC: pair mic/system frames by timeline index (the system channel can lag ~100 ms while padding).

## M1 parked items (2026-09-28)

- **HC1** (owner): `uv run evra capture-test 60` on headphones, then on laptop speakers, talking over a video; listen to mic.wav / system.wav.
- Investigate the 70 ms system-channel "dropout" gap 2.7 s into the soak (cause unknown); add an INFO log per gap (channel, cause, length, clock decision — no audio content) to diagnose future ones.
- Mic "dropout" gaps under heavy system memory pressure (0.7–1.0 GB free) — confirm they are real loss; consider surfacing low system memory as a health hint.
- Tag `p1-m1-done` once the above close.
- `CaptureSession.start`: if the output watcher factory raises after the sources start, the devices stay open; stop the sources on that path.

## M3a follow-ups (2026-09-28)

- Worker logging (forward records from worker processes to the app's log via a queue).
- Hallucination guard for phantom phrases on low-confidence segments (BUILD.md §6.2).
- Post-meeting fast pass for when the live transcript is off.
- Spill audio during `evra record` (crash recovery, retention, click-to-play).
- Choose microphones by name, not index: Windows renumbers devices when Bluetooth reconnects (seen twice).
- Bluetooth hands-free switching causes short mic dropouts; surface "use a wired/USB mic or the laptop mic" as a hint.
- Loopback endpoint role (multimedia vs communications) before real calls on speakers.
- Worker heartbeats (BUILD.md §4.2): deferred; per-request deadlines that kill and replace a hung worker are the liveness check for now.
- Model store: write the spec's SHA-256s into the `.verified` marker and compare them, and drop the marker before any fetch or extract (a changed catalogue or an interrupted re-extract is otherwise reported ready).
- Model store: treat HTTP 416 on a full-length `.part` as complete and let the checksum decide (today it fails until the file is deleted).
- Model store: lock a model's directory while downloading so two processes cannot append to the same `.part`.
- Tests: a stronger device-closed assertion in `test_interrupt_still_finishes_the_meeting`; `requires_models` tests should skip, not fail, when `spikes/test_wavs/en.wav` is missing; add tests for a Range request answered with 200 and for 416.
- ASR payload is copied 3–4 times per segment (bytes, pickle, astype); fine at the 20 s cap, revisit with shared memory if segments grow.
- Scale the ASR timeout with segment length if long segments ever time out on slow CPUs (60 s today; a 20 s segment takes about 0.6 s).

## M3b follow-ups (2026-09-28)

- Embedding-based support check (cosine ≥ 0.55, §7.5) once Qwen3-Embedding runs (M5).
- Plain bullet-list fallback note after a failed repair (§9.1), built from extraction results (M5).
- Spoken years ("twenty twenty-six") in the number check.
- Map-reduce for meetings over the single-pass budget (A2/A3, M5).
- Flaky under heavy load: `tests/unit/capture/test_session.py::test_clean_start_needs_no_drift_corrections` failed once while a 14B model ran (timing-based); make its timing tolerant.
