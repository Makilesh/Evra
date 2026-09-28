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

## Config via pydantic + tomllib instead of pydantic-settings (2026-09-24)
- **Context:** BUILD.md §10 M0 lists pydantic-settings; settings live in a runtime-resolved TOML path and tests need to inject it.
- **Evidence:** pydantic-settings' TOML source is configured per class; injecting a path per call needs a workaround. Only `EVRA_DEBUG` comes from the environment.
- **Decision:** `Settings` is a plain pydantic model; `load_settings(path)`/`save_settings(path, s)` use `tomllib`/`tomli-w`; `debug_enabled()` reads `EVRA_DEBUG`.
- **Consequences:** one fewer dependency; corrupt files are moved to `settings.toml.bad` and defaults load.

## Secret scanning: CI always, locally via tools/check.py (2026-09-24)
- **Context:** BUILD.md §9.3 asks for gitleaks in CI and before commits.
- **Evidence:** Smart App Control blocked pnpm.exe on 2026-09-24 and was then switched off. Local gitleaks: runs (8.30.1, installed with winget); `gitleaks git` scanned 12 commits, no leaks.
- **Decision:** gitleaks runs in CI on every push (full history, gitleaks-action v3; no licence key needed for a personal account). `tools/check.py` runs it locally whenever `gitleaks` is on PATH.
- **Consequences:** every commit is scanned before push on the dev machine; CI is the backstop.

## D24 — libsamplerate (`samplerate`) instead of scipy `resample_poly` (2026-09-24)
- **Context:** BUILD.md §5.1 named `scipy.signal.resample_poly`; capture arrives in 10–26 ms chunks at 44.1/48 kHz.
- **Evidence:** `resample_poly` is stateless, so per-chunk calls create seams at every boundary. A spike on the dev machine showed the default mic at 44.1 kHz (a rational 160/441 ratio) and 26 ms callbacks. `samplerate` 0.2.4 (MIT binding; libsamplerate BSD-2-Clause) streams statefully: 88 200 → 31 954 samples, ≈3 ms held in the filter.
- **Decision:** `ToMono16k` uses `samplerate.Resampler("sinc_fastest")`; scipy is not a dependency.
- **Consequences:** one fewer large dependency; the tiny constant filter delay is absorbed by the timeline.

## D25 — Default-output detection via pycaw (Core Audio) (2026-09-24)
- **Context:** BUILD.md §5.1 requires reopening loopback when the default output changes (polled every 2 s).
- **Evidence:** PortAudio (inside PyAudioWPatch) fixes its device list at initialisation, so it cannot see a new default device while running. pycaw (MIT; comtypes MIT) returns the current endpoint id from the Windows Core Audio API; verified on the dev machine (hardware test).
- **Decision:** `DefaultOutputWatcher` polls `pycaw.AudioUtilities.GetSpeakers().id`; on change `LoopbackSource.reopen()` re-initialises PyAudio and the pipeline records a `device_change` gap.
- **Consequences:** two small Windows-only dependencies; macOS/Linux get their own watchers in their milestone.

## sherpa-onnx-core pinned explicitly (2026-09-28)
- **Context:** loading Parakeet crashed (access violation) with "Current ORT Version is: 1.17.1".
- **Evidence:** the sherpa-onnx 1.13.8 wheel requires `sherpa-onnx-core==1.13.8` (it carries `onnxruntime.dll` and the sherpa DLLs), but uv's lock recorded no dependencies for sherpa-onnx, so the core package was never installed and Windows loaded the old `onnxruntime.dll` from System32 (Windows ML).
- **Decision:** depend on `sherpa-onnx-core==1.13.8` directly, pinned to the same version as `sherpa-onnx`.
- **Consequences:** upgrade both together; packaging must bundle sherpa-onnx-core's DLLs and never rely on System32's onnxruntime.

## D26 — Voice detection moves into M3 (2026-09-28)
- **Context:** the owner parked M1's checkpoint and chose M3 (1:1 call end to end) next; live transcription needs VAD segments, which BUILD.md §10 scheduled in M2.
- **Decision:** Silero VAD (`SpeechSegmenter`) ships in M3a. M2 keeps echo cancellation and spill crash recovery.
- **Consequences:** 1:1 calls on headphones work end to end without M2; on laptop speakers the mic transcript will contain the other person's voice until M2's echo cancellation.

## Ollama is an external app with its own model store and listener (2026-09-28)
- **Context:** M3b writes notes with a local LLM through Ollama (D4). D23 keeps Evra's data inside the project folder, and Evra opens no network listener.
- **Evidence:** Ollama has one server-wide model folder (`OLLAMA_MODELS`); the dev machine already points it at an existing shared store with other models. Ollama's server listens on `127.0.0.1:11434` whether or not Evra runs.
- **Decision:** Evra does not manage Ollama's model folder: LLM weights live wherever the user's Ollama keeps them, outside D23. Evra only connects to Ollama as a client on localhost; that listener is Ollama's, not Evra's. Tested with Ollama 0.34.4.
- **Client:** Evra speaks Ollama's REST API with the Python standard library (no proxies, redirects refused). The official `ollama` package was tried and dropped: its HTTP stack (httpx) pulls in `certifi`, which is MPL-2.0, dev-only under §9.2.
- **Consequences:** note-writing models are not removed with `.data/`; setup docs tell users to install Ollama and pull the chosen model. Bundling llama.cpp (no external server) stays in the backlog.

## Note grounding in M3b: per bullet, lexical, short prompt ids (2026-09-28)
- **Context:** §7.5 checks every generated claim; Appendix B puts a regex on citations, so one malformed citation would fail the whole note; the embedding model (D17) arrives in M5.
- **Evidence:** 32-character utterance ids cost tokens and invite copy mistakes; grammar-constrained JSON already guarantees shape.
- **Decision:** prompts show utterances as `u:1…u:N` (time order) and citations are mapped back to real ids; citation syntax is checked per bullet (a bad citation drops only its bullet); support is lexical until M5 — ≥ 20% content-word overlap (5-letter prefixes), and numbers (incl. spoken numbers and "12k") and capitalised names must appear in the cited text — when one was said up to 3 lines from a cited line, that line is added as a citation (models merge context from neighbouring turns but cite one; bake-off 2026-09-28); A1 also shows the JSON schema in its system prompt. If the JSON is still invalid after one A9 repair, the note fails with a clear message: the plain bullet-list fallback of §9.1 is built from extraction results, which arrive in M5.
- **Consequences:** paraphrased numbers ("five hundred" said, "$0.5k" written) or years spoken as words are dropped; the bake-off reports drop rates per model.
- **Tightened after the final review (same day):**
  - **Names.** Only `.` `!` `?`, the start of a point and a leading "Label:" count as a sentence start. After `;` `(` `-` or a later `:`, a capital is a name.
  - **Names at a sentence start.** A capitalised word there is a name if the meeting only ever says it capitalised ("Priya"). An unknown word counts as a name only when it reads like one: alone after a label ("Owner: Marcus."), or followed by *will/and/is/has/was/said/agreed/asked/from/'s*.
  - **Numbers written as words** in a point are checked too.
  - **Numbers from a nearby line** are borrowed only if the line shares the word next to the number ("October 14" yes; "180 tickets" against "180 milliseconds" no). A lone "one"/"first"/"second" there doesn't count.
  - **Remaining risk:** a made-up name the meeting never said, at the start of a point, followed by another verb ("Marcus sends the deck"), or a name that is also a common word the meeting used ("Will", "Mark"). The fix is the embedding check and owner rule in M5.
  - **Bake-off after tightening:** gemma4 14/15 kept, and the drop was a number cited to the wrong line (the fact survives elsewhere in the note); qwen3.5 24/24; coverage 100% for both.

## M3 note model: gemma4:12b (2026-09-28)
- **Context:** D4 — pick the local note model by testing 2–3 open models on the dev machine.
- **Evidence:** `tools/bakeoff_notes.py` on the synthetic 1:1 fixture (27 utterances ≈ 4 min, 10 expected facts), 2 runs each (first run includes model load), Ollama 0.34.4, RTX 5070 Ti Laptop 12 GB, num_ctx 32768, temperature 0, thinking off:

  | model | seconds (cold / warm) | tokens in/out | kept | dropped | validity | coverage | on GPU |
  | --- | --- | --- | --- | --- | --- | --- | --- |
  | gemma4:12b | 28.8 / 20.3 | 1848/944 | 15 | 0 | 100% | 100% | 100% |
  | qwen3.5:9b | 25.7 / 18.3 | 1784/1303 | 24 | 0 | 100% | 100% | 100% |
  | ministral-3:14b | 94.4 / 78.6 | 1765/1373 | 19 | 0 | 100% | 90% | 67% |

  qwen3.5:9b with thinking on: 75 s, the 4,096-token output budget spent on thinking, empty note after the repair. No model followed the prompt-injection line (note in French). Licences: all three Apache-2.0 (`ollama show --license`). On the owner's latest dev recording (a short video clip, not a 1:1) both leaders answered in ≈ 10 s. Before the grounding fix of the same day, gemma4 lost 5 of 15 true points to "name/number not in the cited line" — see "Note grounding in M3b".
- **Decision:** `gemma4:12b` is the default `llm.model`: the tersest note (A1 rule 8), every action item with owner and date, fully on the GPU. `qwen3.5:9b` is the fallback (slightly faster, wordier: repeats the summary in Discussion, filed an action as a decision). Thinking stays off. ministral-3:14b is out (does not fit 12 GB VRAM, 4× slower).
- **Consequences:** a note for a 4-minute call takes ≈ 20 s warm; the owner's first real 1:1 (HC3) confirms or flips the choice (`evra note --model qwen3.5:9b`). Re-run the bake-off when a new model family ships and before the M5 extraction prompts.
