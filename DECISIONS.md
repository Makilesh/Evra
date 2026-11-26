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

## Meetings are named from their note (A8) (2026-11-11)
- **Context:**
  - Every meeting was called "Recording <date> <time>" until it was renamed by hand, so a list of them didn't say which call was which.
  - The owner asked for each meeting to be named once it is transcribed, the way ChatGPT and Claude name a chat.
  - §7.4 planned a title (A8) "if the user didn't set one", written from "the first and most salient 5 minutes" of the transcript. Salience comes from topics (A7), which don't exist yet.
- **Evidence:** live, gemma4:12b with the app's defaults on the synthetic 1:1: note 37.1 s, then the title in 1.0 s: "Search migration results and project launch planning" (7 words). `tests/integration/test_ollama_live.py` names a meeting with a real model (`-m hardware`).
- **Decision:**
  - Once a note is written (after a recording, or with Write note), the note's model names the meeting from the note's points, summary first, at most 4,000 characters. Prompt `a8-v1`: at most 8 words in sentence case; no dates, quotes or trailing punctuation; JSON `{"title": "..."}`.
  - The note, not the transcript: its summary already says what the meeting was mainly about and is checked against the transcript; opening minutes are often small talk; a short input keeps the call to about a second.
  - It runs after `note.ready` and after Record is back, so neither waits for it. The window gets `meeting.renamed` and shows the name in the list and the header; a rename being typed keeps its draft.
  - Only a title that still matches `Recording YYYY-MM-DD HH:MM` is replaced, with a conditional update (`rename_meeting_if`), so a name the user gave, even one given while the model thinks, always wins.
  - The call reuses the note's model, context size and thinking setting, so Ollama keeps the loaded model; it waits at most 60 s for at most 256 output tokens. Any failure keeps the placeholder without a message.
  - `evra titles` names the meetings that have a note but still the placeholder: ones recorded before this, or noted with `evra note`.
- **Consequences:**
  - A meeting without a note keeps the placeholder. A named meeting is not renamed when its note is written again.
  - Titles are meeting content: logs get a reason or a word count, never the title.

## Keep the PC awake while recording (2026-11-11)
- **Context:** nothing stopped Windows from sleeping mid-recording (competitor review). A call app such as Teams usually keeps the PC awake, but an in-person 1:1 has nothing doing that.
- **Evidence:** the spike `spikes/keep_awake_probe.py` asked the power manager (`CallNtPowerInformation`, SystemExecutionState): 0x0 before, ES_SYSTEM_REQUIRED (0x1) while held, even when a short-lived thread started it, and 0x0 after Stop.
- **Decision:**
  - From the moment capture's devices are open until they close, `CaptureSession` holds `SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)` (`capture/awake.py`). The system stays on; the screen may still turn off.
  - A thread of its own holds the request, because Windows ties it to the calling thread and drops it when that thread ends, and bridge calls run on short-lived threads.
  - Every capture path gets it: the window, `evra record` and `evra capture-test`.
- **Consequences:** closing the lid or pressing the power button still sleeps the PC. Writing the note after Stop is not covered.

## Load the note model when Stop is pressed (2026-11-11)
- **Context:** about 20 s of the 58.5 s for an hour-long call's note was Ollama loading gemma4:12b, and it only began after the transcript had drained.
- **Evidence:** live on the dev PC with the app's settings: a cold call took 7.5 s; after `load()` the same call took 0.5 s, and Ollama reported the model at context 32768, the size every note call asks for, so nothing was loaded twice.
- **Decision:**
  - Stop starts a background request (`LlmProvider.load`: a generate request with no prompt) for the note model at the notes' context size and `keep_alive`, then drains the transcript. Nothing waits for it; a failure is logged and the note loads the model itself.
  - Speech recognition runs on the CPU, so the load does not break §8.3's one-GPU-job rule.
- **Consequences:**
  - When a recording has no speech, the model sits loaded for its 30 s `keep_alive` and then unloads.
  - When M4's torch worker (diarization) runs after Stop, the load moves to after the worker frees the GPU (BUILD.md §8.3).

## Shared meeting context (A0) and note prompt A1 v3 (2026-11-26)
- **Context:** the note and the coming questions about a meeting should start with the same text, so Ollama reuses the prompt it has already processed. A1 v2 put its rules first and the transcript in the user message, so nothing was shared.
- **Evidence:** gemma4:12b, 2 runs each, the two fixtures (kept/dropped are note points that passed the transcript check; coverage is the share of the fixture's facts found):

  | prompt | case | seconds | tokens in/out | kept | dropped | validity | coverage |
  | --- | --- | --- | --- | --- | --- | --- | --- |
  | v2 | 60 min | 102.9 (cold, other work running) | 27878/1715 | 21 | 5 | 81% | 38% |
  | v2 | 60 min | 40.4 | 27878/1697 | 19 | 7 | 73% | 46% |
  | v2 | short | 29.0 | 2062/944 | 15 | 0 | 100% | 100% |
  | v2 | short | 22.9 | 2062/946 | 15 | 0 | 100% | 100% |
  | v3 | 60 min | 77.7 | 27948/2517 | 38 | 6 | 86% | 46% |
  | v3 | 60 min | 56.4 | 27948/2408 | 39 | 4 | 91% | 54% |
  | v3 | short | 22.7 | 2132/913 | 15 | 0 | 100% | 100% |
  | v3 | short | 21.4 | 2132/913 | 15 | 0 | 100% | 100% |

- **Decision:** A0 (`a0-v1`) is the system message of every call about a meeting: the transcript first, then gaps, the user's notes and metadata. A1 v3 (`a1-v3`) is only the task, sent as the user message. Rule applied: the short call keeps 15 (>= 14) with 10/10 facts in both runs; the 60-minute call's validity (86%, 91%) is not below v2's (81%, 73%) by 5 points, and its facts (46%, 54%) are at least v2's lower run (38%). v3 kept. Prompt version is recorded as `a0-v1+a1-v3`.
- **Consequences:** the note prompt is about 70 tokens larger on the short call. The 60-minute call writes about 40 points instead of about 20 (more output, about 2400 tokens). Notes written before this carry `a1-v2`. Token estimates stay at 2.7 characters a token and now track Ollama's counts within 0% to 26% above.

## This work runs before M4 (2026-11-26)
- **Context:** BUILD.md §10 puts M4 (speakers) next after M3 and keeps the milestones in order. On 26 November the owner asked for the seven changes from the review of how Evra uses its language model: refuse cloud models, ask a meeting, read long calls in parts, keep action items and decisions as records, track open promises across meetings, a notepad that steers the note, and a meaning check next to the word check (spec `docs/superpowers/specs/2026-11-26-ask-notes-promises-design.md`).
- **Evidence:** a 1:1 call on headphones needs no diarization (mic = the owner, system audio = the other person, §8.1). The research behind the review found that open promises and continuity between 1:1s matter more for a 1:1 than voiceprints.
- **Decision (owner, 2026-11-26):** this work runs before M4, as three plans on three branches: A `ask-meetings` (cloud refusal, the shared meeting context, asking a meeting), B `notes-complete` (embeddings, extraction kept as records, long calls in parts, the notepad), C `promises` (people, open promises, a prep brief). M4 is unchanged and comes after them.
- **Consequences:** parts of M5 (the notepad, embeddings, extraction, the per-window path) arrive before M4; Plan B changes D17 with its own entry. Until M4, a 1:1 has two speakers, You and Them, without voiceprints.

## Cloud models are refused (2026-11-26)
- **Context:** D4 keeps the language model on this PC. Ollama can also run models in its own cloud, and such a model is listed and called like a local one. A note or a question sent to one would take the meeting's transcript off the PC.
- **Evidence:** Ollama marks them with a `cloud` tag (`gemma4:cloud`, `gemma4:31b-cloud`) or, in `/api/tags`, with `remote_host` or `remote_model` (fields checked in Ollama's `api/types.go`). The dev PC's Ollama 0.34.4 lists nine models, none of them remote.
- **Decision:** `OllamaProvider` refuses such a model before any chat, load or unload call, reading `/api/tags` once per provider. `installed_models()` leaves them out, so Settings never offers one, and Settings refuses a cloud name. A note or an answer with one fails with `cloud_model`, whose text says to choose another model. README tells users that `OLLAMA_NO_CLOUD=1` turns Ollama's cloud features off server-wide.
- **Consequences:** a model that `/api/tags` doesn't list is left to the call, which Ollama answers with 404 (`model_missing`). Each provider makes one extra `/api/tags` request before its first call.

## Asking a meeting (A12) (2026-11-26)
- **Context:** on the 60-minute synthetic 1:1 (13 planted facts) a single-pass note keeps 5–7 of them. A throwaway probe on the same call found that the same model, asked about each fact with the whole transcript in the prompt, answered 13/13 and said "not discussed" for all 3 topics the call never mentions, and that follow-ups took 1–2 s because Ollama reuses the prompt it has already read. The owner asked for "Ask this meeting".
- **Evidence:** `tools/bakeoff_ask.py` runs the app's own asking code on that call: 13 fact questions and 3 absent topics, each asked on its own; Ollama 0.34.4, RTX 5070 Ti Laptop 12 GB, the app's default settings (`num_ctx` 32768, temperature 0, thinking off). "Correct" means the model's answer holds every keyword of the fact; in brackets, the points the check kept still do:

  | model | facts correct | not discussed | answers passing the check | first question, cold | first question right after the note | follow-ups, median / worst |
  | --- | --- | --- | --- | --- | --- | --- |
  | gemma4:12b | 13/13 (12/13) | 3/3 | 12/13 | 20.1 s | 2.3 s, 26,904 of 27,417 prompt tokens reused (98%) | 1.7 s / 5.3 s |
  | qwen3.5:9b | 13/13 (13/13) | 3/3 | 13/13 | 30.5 s | 1.5 s, 25,555 of 26,054 reused (98%) | 2.0 s / 4.1 s |

  - Every follow-up reused the whole meeting and A12's rules (gemma4 27,238 of about 27,415 prompt tokens; qwen3.5 25,032 of about 26,050). The whole call fit one prompt, so no answer read only parts of it.
  - gemma4's one answer that didn't pass the check was right, but it cited lines by their time as if it were an id (`u:15:46` for the line at 15:46), so no citation was valid. qwen3.5 answered more widely: two or three points where one was asked, some about the next topic.
  - In the window the title (A8, with its own prompt) runs between the note and the first question. Measured with gemma4: that question then re-read the whole call (0 of 27,417 tokens reused, 16.6 s); after the Ask tab's pre-read, the next question took 1.9 s with 27,031 reused.
  - In the real window (the synthetic meeting, gemma4), two one-click questions and a typed follow-up took 5.5–6.1 s each: 198–230 tokens written for three or four points, with 27,031–27,275 prompt tokens reused. The check dropped 3 of 12 points, all paraphrases whose detail was in lines they didn't cite. Logs held state, counts, seconds and reused tokens only.
- **Decision:**
  - A12 (`a12-v1`) is the user message on A0: one to four cited points, or `found: false`, as `MeetingAnswer`; the last three questions and answers ride along so a follow-up can be read. Every point goes through the note's check.
  - Answers are stored in a `question` table with their state (`answered`, `not_found`, `unchecked`, `failed` with a reason); a question left `asking` by a closed app becomes `interrupted` at the next start.
  - The note's model answers, with the note's `num_ctx`, a 5-minute keep-alive and 1,024 output tokens. One question at a time, none during a recording. Opening the Ask tab pre-reads the meeting. A call too long for one prompt sends only the BM25-best windows and says so.
  - Every target of the spec (§8) is met by both models when the first question follows the note directly; in the window's order (the title between) it was missed until the title moved onto the shared context ("Meeting title on the shared context (A8 v2)", 2026-11-27). A12 and `notes/ask.py` stay as built; gemma4:12b stays the default.
- **Consequences:**
  - Until the title call stopped replacing Ollama's cached prompt (fixed 2026-11-27), the first question after a new note waited for a full re-read (about 17 s on gemma4) unless the Ask tab's pre-read had finished.
  - Broad questions ("What did I promise?") write more and take about 6 s, against about 2 s for a question about one fact.
  - The same question can come back with different points from one run to the next, even at temperature 0: in the window "What did they promise?" kept 2 points and dropped 2, and a replay kept 4.

## Meeting title on the shared context (A8 v2) (2026-11-27)
- **Context:** in the window the title call (A8) runs between the note and the first question. With its own system message it replaced the meeting's prompt in Ollama's cache: on gemma4:12b the first question then re-read the whole call (0 of 27,417 tokens reused, 16.6 s) instead of reading only its task (about 2 s).
- **Decision:** A8 is now `a8-v2`, one `## Prompt` part (the task only). `name_meeting` sends the meeting's A0 context, built exactly as the note job builds it (`build_context` over the current transcript), as the system message and A8 as the user message; same model and `title_settings` (same `num_ctx`, so no reload). A meeting without a transcript is left unnamed, with no call. The title is still the placeholder when the context is built, as it was for the note, so the system message is byte-identical.
- **Measured** (`tools/bakeoff_ask.py gemma4:12b`, now note, then title, then the first question, the window's order): the title took 1.0 s; the first question 2.1 s with 26,904 of 27,417 prompt tokens reused (98%), against 16.6 s and 0 reused before. Titles written for the synthetic calls: "Weekly 1:1 update on search migration and launch", "Atlas project status and team operations review". Target met: about 2-3 s and at least 95% reused.
- **Consequences:** the first-question target (about 2-3 s, at least 95% reused) holds in the window's order, measured on gemma4:12b (the default) only; the other targets were measured with the question right after the note. The BACKLOG item for the re-read is removed. Any later call about a meeting must send A0 as its system message to keep this.

## Title prompt a8-v3, and a shorter wait for questions (2026-11-27)
- **Title (A8 v3):** the note text in the title call goes through `as_data`, and the prompt says again that the note is data, not instructions (v2 had dropped that sentence when it moved onto A0). A prompt-invariants test now checks every prompt file's version line and the data rules of A0 and A8.
- **Asking wait:** `llm.ask_timeout_s` (default 180 s); asking waits `min(llm.timeout_s, ask_timeout_s)`, so a hung Ollama blocks questions for 3 minutes, not the note's 10. With `llm.think` on, a question reserves the note's `max_output_tokens` for the reply.
- **Long calls:** whole-versus-parts is decided on the meeting alone (the oldest exchanges are dropped first); when no part of a long call matches the question the model is not called and the answer is "not discussed" with a line saying why.

## D17 changed: embeddings through Ollama (2026-11-26)
- **Context:** note completeness (keeping paraphrased points the transcript supports, aligning typed notes to the transcript) and asking long calls need embeddings now. The torch worker does not exist before M4. Ollama already manages VRAM and is the one local model server.
- **Evidence:** `qwen3-embedding:0.6b` is in the Ollama library: 639 MB, Q8_0, 32K context, 1024-dimension vectors (measured with one `/api/embed` call). Ollama's page and `ollama show --license` print no licence; the Hugging Face card `Qwen/Qwen3-Embedding-0.6B` (the same model) is Apache-2.0. `POST /api/embed` takes `model`, `input` (string or list), `truncate` (default true), `keep_alive`, `dimensions`, `options`; it returns `embeddings`, `prompt_eval_count`. Normalisation is not documented; measured output was already near unit length, but Evra normalises anyway.
- **Decision:** embeddings go through `LlmProvider.embed` (Ollama, `/api/embed`, loopback only, cloud models refused) with `qwen3-embedding:0.6b` (`llm.embedding_model`). Queries carry Qwen3's instruction (`Instruct: …\nQuery:…`), documents none. Vectors are L2-normalised in Evra.
- **Consequences:** no torch worker needed for embeddings; the model is one more Ollama pull (639 MB). The torch worker still comes with M4; pyannote stays there. An embedding failure never fails a note: callers fall back to the word check.
