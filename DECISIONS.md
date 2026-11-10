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

## Note prompt A1 v2 (2026-11-07)
- **Context:** the owner's first real 1:1 (HC3, 8 Oct) got a summary that repeated the discussion point for point, topic-only bullets ("Employment document status."), a "maybe" filed as a decision and an empty "For next time"; on a 60-minute call, bullets led with "Topic:" labels whose capitalised words failed the name check, and promises cited only the reply ("Yeah, I can do that").
- **Evidence:** `tools/bakeoff_notes.py`, gemma4:12b, 2 runs: short fixture v1 14 kept / 1 dropped → v2 15 / 0, 10/10 facts both; 60-minute fixture v1 keeps 58–62% of points → v2 73–81%, facts unchanged (38–46%). On the HC3 call v2 gives a one-line summary and specific points. A stricter wording of the template's decisions and next-time lines only moved the misfiling elsewhere, so it was not kept.
- **Decision:** A1 rules 10–13 (Appendix A): the summary is one to three bullets that don't repeat the sections; every bullet states one specific point and starts with it (no "Topic:" label; action items start with their owner); decisions only when explicitly agreed; a topic for later goes to "next time"; a question and its short answer are both cited. The 1:1 template's discussion line asks for one point per bullet instead of "grouped by topic".
- **Consequences:** generations record `a1-v2`. Sorting points into decisions / action items / next time stays unreliable on a 12B model; BUILD.md's focused extraction calls (A4–A6) are the planned fix.

## Prompt size: measured estimate, budget just under the model's room (2026-11-07)
- **Context:** §7.4's single pass needs the prompt to fit `num_ctx − max_output_tokens`; the estimate (3.5 characters a token) was meant to be conservative.
- **Evidence:** gemma4:12b's real counts (Ollama `prompt_eval_count`, prompt a1-v2): short fixture 6,989 characters = 2,062 tokens (3.4 a token); 60-minute fixture 75,199 characters = 27,878 tokens (2.7: transcript lines are dense in digits). The old estimate said 21,486 for the hour, 23% low; with the default budget of 24,000 an accurate estimate would refuse an hour-long 1:1.
- **Decision:** the estimate uses 2.7 characters a token; `llm.context_budget` defaults to 28,000 (§7.4 said 24k); a prompt is refused before any call when its estimate exceeds the smaller of the budget and `num_ctx − max_output_tokens`. Ollama's real count is still checked after the call.
- **Consequences:** short prompts are over-estimated by about a quarter, harmless that far below the limit; a dense 60-minute 1:1 just fits and anything longer is refused until the per-window path exists. `tests/unit/notes/test_note_budget.py` pins the estimate to the measured counts.

## D19 replaced — the "Steno pad" look (2026-11-10)
- **Context:** D19 "Quiet paper" (serif note text, Inter UI, one teal accent) was a starting point; §8.5 said to refine it once real screens existed. After M3c the owner asked for a window that looks neat and creative and that developers and everyone else want to use, and wanted to see options before anything was built.
- **Evidence:** a direction round in Operate mode (Impeccable `concept-seed`): seven candidates from the world of 1:1s, a dice-assigned direction, catalog challengers weighed on audience identification and product clarity, then four first-viewport sketches built from the synthetic 1:1 fixture: Steno pad, Mission transcript, Catalog sleeve and the category standard. The owner chose Steno pad.
- **Decision:** D19 becomes "Steno pad".
  - A pale green pad (`#E7EFDB`), a tan chipboard rail (`#D3C8B3`), a deep green rule (`#2E6B4B`) and navy ink; a night version follows the Windows dark setting.
  - Sofia Sans Extra Condensed for titles, section heads, speakers and time tabs; Libre Franklin for all text at one reading size. Both are OFL-1.1, Latin only, bundled and never fetched.
  - The note is a sheet: each point, a timed centre rule, and the transcript lines it came from on the same row.
  - Colour fills whole areas: the record block turns red while recording, and a hovered point or cited line fills band green.
  - One motion grammar, "land and settle" (a live line lands heavier and relaxes; a cited line lands deep green and fades to band), switched off under reduced motion.
  - The top bar is gone: record, search (`Ctrl K` now focuses it), meetings by day and the microphone live in the rail.
  - The direction contract is `.impeccable/surfaces/frontend-src-app-tsx.md`; the design system is `DESIGN.md` with `.impeccable/design.json`.
- **Consequences:** Inter and Newsreader are removed. GSAP, React Bits components and transitions.dev snippets are not used: CSS carries the motion inside the recording CPU budget, and their licences (GSAP's standard no-charge licence, MIT + Commons Clause, custom) would each need a licence-policy decision first; the React Bits registry stays configured in `components.json` for later. The `Ctrl+K` palette and `Ctrl+Alt+R` stay M6. Per-meeting talk-rhythm marks and the note's written-at time need new bridge fields (BACKLOG).

## Theme: light by default; Dark or Match Windows in Settings (2026-11-10)
- **Context:** D19 "Steno pad" followed the Windows light/dark setting. The owner asked for a light window by default with Dark as a choice, then for Microsoft's "Use system setting" as a third, non-default option.
- **Evidence:** research notes in `private/research/` (2026-11-10):
  - Microsoft's app-settings guidance lets an app set its own theme, though its documented default follows Windows.
  - Lab readability studies mostly favour dark text on light backgrounds (Piepenbrock 2013, Dobres 2017), and NN/g (2020) advises against a dark default for a general audience.
  - Comparable local-first apps usually offer Light / Dark / System with System as the default.
- **Decision:**
  - The window opens light unless Dark or Match Windows is chosen in Settings. The choice is saved in `settings.toml` as `theme = "dark"` or `theme = "system"`.
  - Match Windows is Microsoft's "Use system setting", given a label that fits the theme tile. It follows Windows' app mode live, which WebView2 reports as `prefers-color-scheme`.
  - An unknown value reads as light without resetting the other settings.
  - Python opens the window as `index.html#theme=dark` (or `#theme=system`) with the matching pad as WebView2's background, so the page never flashes the wrong theme. For Match Windows, the pad is chosen from Windows' `AppsUseLightTheme` setting. It is a fragment, not a query: pywebview hands the URL to .NET's `System.Uri`, which escapes a file URL's `?` into the file name, and WebView2 then shows an error page. The real-window check caught this, and `tests/unit/test_window.py` now checks it with .NET's own `Uri`.
- **Consequences:**
  - Evra follows Windows only when Match Windows is chosen.
  - After a switch while Evra runs, WebView2's background behind a resizing window keeps the startup colour until the next start.

## Settings, first set (2026-11-10)
- **Context:**
  - BUILD.md §8 planned Settings for M6 (devices, default mode and situation, LLM model, templates, retention, hotkeys, People).
  - The owner asked for Settings now: only the settings that are needed, with the window kept clean.
- **Evidence:** a research round over five angles; notes and report in `private/research/`.
  - Microsoft's guidance: at most four or five settings, changes apply at once with no Save button, Settings at the foot of the navigation, About at the bottom of the page, and an unavailable setting disabled with the reason shown.
  - The most-requested settings in this category (note language, speaker names, editable templates, choice of recordings folder, auto-detecting meetings) belong to features Evra doesn't have yet.
  - The defaults users complain about (bots auto-joining, notes auto-shared) don't exist in Evra.
- **Decision:**
  - Settings opens on the pad from the foot of the rail or with `Ctrl ,`. Esc, the close button, a meeting or Record leave it.
  - It holds four rows on the timed rule:
    - Theme (Light / Dark).
    - Note model: the models installed in Ollama, with the default marked "recommended", asked with a 3-second timeout.
    - Meetings folder: where meetings are kept, with Open folder.
    - About: the version; no accounts, no analytics.
  - Changes apply at once.
  - The microphone stays in the rail and is not duplicated.
  - A setting arrives with its feature: retention and templates (M5), hotkeys and start with Windows (M6), People (M4), turning the live transcript off.
- **Consequences:**
  - `default_mode`, `default_situation`, `live_transcript` and `audio_retention` stay file-only until their features exist.
  - New bridge calls: `get_settings`, `set_theme`, `set_note_model`, `list_note_models`, `open_data_folder`. Model names are checked against a strict pattern. Opening the folder starts Explorer and nothing is served.
