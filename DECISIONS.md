# DECISIONS.md — why we chose what we chose

One entry per decision. Format: context · evidence · decision · consequences. Numbers match `BUILD.md` §2.

## D4 — Local LLM via Ollama (2026-09-24)
- **Context:** paid LLMs deferred; notes need JSON-schema-constrained output.
- **Evidence:** Ollama supports the RTX 5070 Ti, JSON-schema `format`, and `keep_alive=0` to free VRAM.
- **Decision:** Ollama behind an `LlmProvider` interface; model picked by testing 2–3 open models on the dev machine.
- **Consequences:** user must install Ollama; bundling llama.cpp is backlog.

## D5 — pywebview + React UI (2026-09-24)
- **Context:** portfolio polish; a later web version could reuse the same UI.
- **Evidence:** PySide6 widgets look dated without heavy styling and can't be reused on the web; Tauri adds Rust and a second process.
- **Decision:** pywebview (WebView2) hosting React + TypeScript + Tailwind + Vite.
- **Consequences:** the codebase has a TypeScript frontend; tray and hotkeys need small extra pieces.

## D6 — App process + model worker processes (2026-09-24)
- **Context:** heavy models, a UI and live capture in Python; CUDA 12 vs 13 conflicts on Blackwell.
- **Evidence:** CTranslate2/sherpa-onnx CUDA wheels use CUDA 12; torch cu130 and onnxruntime-gpu 1.30 use CUDA 13.
- **Decision:** light app process + onnx worker (CPU) + torch worker (CUDA 13) over multiprocessing pipes.
- **Consequences:** needs a message protocol and supervisor; gains crash isolation, clean memory release, and a path to server-side workers.

## D8 — Parakeet on CPU for Phase 1 (2026-09-24)
- **Context:** English first; avoid CUDA 12 in the process mix.
- **Evidence:** Parakeet TDT 0.6B v3 int8 via sherpa-onnx runs well under real time on a 24-core CPU (to be measured).
- **Decision:** onnx worker runs on CPU.
- **Consequences:** GPU speech-to-text is backlog; measure real-time factor in Phase 1.

## D10 — Echo cancellation: livekit AudioProcessingModule (2026-09-24)
- **Context:** hybrid is the everyday situation; the room mic hears the call through laptop speakers.
- **Evidence:** livekit 1.1.20 wraps libwebrtc's audio processing (Apache-2.0, Windows wheel, maintained); `pywebrtc-audio` is only three releases old and its vendored AEC3 licence is unclear; `webrtc-audio-processing`/`speexdsp` bindings are dead.
- **Decision:** livekit APM with the system channel as far-end reference; rapidfuzz dedupe as a safety net.
- **Consequences:** must pass the ≥ 90% remote-speech-removal test early; `pywebrtc-audio` is the fallback.

## D13 — Keep audio with user-set retention (2026-09-24)
- **Context:** the owner wants to replay moments from notes and transcripts; bounded retention limits storage and privacy exposure.
- **Evidence:** raw 16 kHz int16 on two channels is ~230 MB/hour; Opus brings it to ~20 MB/hour.
- **Decision:** after processing, re-encode to Opus, encrypt with the meeting key, keep for 7 / 30 (default) / 90 days / forever; per-meeting Keep forever / Delete now.
- **Consequences:** citations and transcript lines can play audio; a retention sweeper is required; raw spill still deleted after 72 h if processing never finishes.

## D21 — Code licence: FSL-1.1-ALv2 (2026-09-24)
- **Context:** the repository is public (portfolio) but the owner wants to keep commercial control.
- **Evidence:** FSL-1.1-ALv2 (Sentry) allows reading, running, modifying and non-competing use; bars competing commercial use; each release converts to Apache-2.0 after two years. Official text taken from getsentry/fsl.software.
- **Decision:** `LICENSE.md` = FSL-1.1-ALv2, Copyright 2026 Makilesh.
- **Consequences:** third-party components keep their own licences (tracked in the licence gate); contributors' terms to be decided if outside contributions are accepted.

## D22 — Commit and push after every completed feature (2026-09-24)
- **Context:** the owner wants the public repo to track progress continuously.
- **Decision:** after each coherent feature or update: `tools/check.py` and gitleaks pass → Conventional Commit → push to `origin` on the working branch.
- **Consequences:** small, frequent pushes; secret scanning and the §9.3 rules are the safety net; no force-push, history rewrite or push to `main` unless asked.

## D23 — Keep development data inside the project folder (2026-09-24)
- **Context:** the owner wants everything Evra and the builder create to live in `D:\GEN AI\Evra`, not scattered across `C:`.
- **Evidence:** models and recordings will be multi-GB; the project drive is where the owner looks for files.
- **Decision:** from a source checkout, `resolve_paths()` puts all app data in `<repo>/.data/`; installed builds use platformdirs; `evra run --data-dir` overrides. Spikes go in `spikes/`, scratch/research in `private/`; all git-ignored. uv's shared Python runtime stays in uv's own directory.
- **Consequences:** deleting `.data/` resets the dev app; tests always use temporary `AppPaths.under(tmp)`.
