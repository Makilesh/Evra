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
