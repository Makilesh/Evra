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

## Meaning check threshold (2026-11-26)
- **Context:** the word check (§7.5) drops a point that says what its cited lines say in other words, because fewer than 20% of its content words are in them. The meaning check scores such a point against the text it cites with `qwen3-embedding:0.6b` (the point as the query, with Qwen3's instruction) and keeps it at or above a threshold; its numbers and names must still be cited. §7.5 names 0.55. The plan's rule: the smallest of 0.55, 0.60, 0.65, 0.70 and 0.75 at which at most 2% of mismatched pairs pass.
- **Evidence:** `tools/calibrate_semantic.py gemma4:12b` (Ollama 0.34.4, RTX 5070 Ti Laptop). Both synthetic fixtures; the note is written with the meaning check off, then three groups of pairs are embedded in one batch: each kept point against the text it cites (supported), against 3 random lines that are neither cited nor within 3 lines of a cited one (mismatched, `random.Random(7)`), and each point dropped as unsupported against the text it cites. Two runs, because temperature 0 does not repeat exactly (run 1: 53 kept points, 1 unsupported; run 2: 54 and 3):

  | group (run 1 / run 2) | pairs | p5 | p50 | p95 | max |
  | --- | --- | --- | --- | --- | --- |
  | supported | 53 / 54 | 0.519 / 0.515 | 0.774 / 0.780 | 0.886 / 0.912 | - / 0.931 |
  | mismatched | 159 / 162 | 0.208 / 0.213 | 0.318 / 0.318 | 0.446 / 0.456 | - / 0.525 |
  | unsupported | 1 / 3 | 0.528 / 0.508 | 0.528 / 0.513 | 0.528 / 0.528 | 0.528 / 0.530 |

  | threshold | mismatched at or above | supported at or above | dropped points it would keep |
  | --- | --- | --- | --- |
  | 0.55 | 0/159, 0/162 (0%) | 92.5%, 88.9% | 0, 0 |
  | 0.60 | 0%, 0% | 90.6%, 83.3% | 0, 0 |
  | 0.65 | 0%, 0% | 84.9%, 81.5% | 0, 0 |
  | 0.70 | 0%, 0% | 77.4%, 75.9% | 0, 0 |
  | 0.75 | 0%, 0% | 56.6%, 59.3% | 0, 0 |

  - A third run, which also counts below the candidates, wrote the same note as run 1. At 0.50, 2 of 159 mismatched pairs pass (1.3%) and run 1's dropped point is kept; at 0.45, 6 of 159 pass (3.8%).
  - The runs dropped 4 points as unsupported, 3 different ones (the first came back in run 2), with cosines 0.508–0.530. Judged against the fixture, all three are true of the call, but part of each is said in lines they don't cite. "Reviewed the recent weekend outage and planned improvements for monitoring and alerting" cites the outage lines; the alerting plans come at 30:19–34:38. "The automated testing suite for the new module lacks a defined baseline": the suite is named the line before and the baseline two lines on. "You will prepare a plan for Dana's onboarding starting on the 14th": Dana and the 14th are in the line before, which the nearby-line rule would cite.
  - Supplementary, `tools/calibrate_semantic.py qwen3.5:9b`: 1 of 123 mismatched pairs at or above 0.55 (0.8%, max 0.620), so the rule again gives 0.55. Both of its points dropped as unsupported (0.655, 0.609) pass at 0.55 and keep their numbers and names. Both are true of the call: team morale strained by the integration-layer bottleneck, and friction with the infrastructure team over subjective code-review comments. Again, part of their detail is in nearby lines they don't cite.
- **Decision:** `SUPPORT_COSINE` stays 0.55, the rule's answer on every run. The meaning check runs once per note and once per answer, in one embedding batch after the model's reply, over the points the word check calls unsupported. A point it lets through still needs its numbers and names (with the nearby-line rule). An embedding failure logs `semantic_check_skipped` with the error type and keeps the word check's verdicts.
- **Consequences:** on gemma4:12b's notes of the two synthetic calls the check rescues nothing: the points the word check drops there score 0.51–0.53, just under 0.55. The other drops (names or numbers not cited: 5 in run 1, 1 in run 2) are never overridden by meaning. At 0.50 the three true points the words dropped would be kept (in the run that counted it, 2 of 159 mismatched pairs passed, 1.3%), but 0.50 is below the rule's lowest candidate. Real meetings, with more paraphrase than the synthetic calls, should re-measure it (BACKLOG). The note's log line now carries `rescued`, and so does the answer's.

## Long-call asking reads by meaning (2026-11-26)
- **Context:** a call too long for one prompt is asked through the transcript windows that best match the question. Words alone (BM25) choose nothing for a question that shares no word with its answer: Plan A's final review found that "What did I promise?" read nothing on such a call and answered "Not discussed in this meeting.".
- **Evidence:** `tools/bakeoff_ask.py gemma4:12b --hours 2 --one-click` (with `--no-embed` for words only). The 60-minute synthetic call is joined to itself an hour later (1,680 lines, about 55,000 tokens), so every question reads parts of it. Asked: its 13 fact questions, the 3 topics it never mentions and the Ask tab's four one-click questions, each on its own. "In all" is the whole question (choosing parts, the answer, the check); the other times are the model's alone. Meaning was measured twice: first with a new embedder for every question, then as the app now runs (one embedder per meeting, embedding context 1536):

  | | words only | meaning, new embedder each question | meaning, one embedder per meeting |
  | --- | --- | --- | --- |
  | facts correct (still correct after the check) | 13/13 (13/13) | 13/13 (13/13) | 13/13 (13/13) |
  | not discussed, of 3 | 3/3 | 3/3 | 3/3 |
  | answers passing the check | 13/13 | 13/13 | 13/13 |
  | one-click questions that read any lines | 2/4 | 4/4 | 4/4 |
  | one-click points shown | 3 | 12 | 13 |
  | first question, cold: model / in all | 12.8 s / 12.8 s | 10.9 s / 18.0 s | 10.2 s / 15.8 s |
  | first question after the Ask tab's pre-read: model / in all | - | - | 5.8 s / 5.9 s |
  | follow-ups, model: median / worst | 5.9 s / 9.0 s | 7.6 s / 12.2 s | 7.4 s / 13.5 s |
  | follow-ups in all: median / worst | 5.9 s / 9.0 s | 11.5 s / 16.1 s | 7.5 s / 13.5 s |
  | prompt per question | 0–8,700 tokens | 8,200–9,050 tokens | 8,200–9,050 tokens |

  - Words only: neither "promise" question read anything (no line holds the word). "What did we decide?" read 1,500 tokens and found nothing. "What's still open?" answered with 3 points.
  - With meaning, all four read 8,600–9,050 tokens. In the first run "What did I promise?" kept 3 points and dropped 1. The meaning check kept one of them: "You promised to notify the team about the new hire's arrival", which cites "I'll also make sure the team knows she's coming so they can... you know, be prepared to welcome her.". It is true. In the second run it kept 3 and dropped 1 with no point kept by meaning (the answers differ between runs, even at temperature 0).
  - A re-run of the four questions after the first run, judged against the fixture: every point shown was true and given to the right person. The two dropped points were true too: a Lisbon summary whose name was in a line it didn't cite, and "Right. I'll get on that.", whose meaning is in the line before.
  - The pre-read, run with both models unloaded, loaded gemma4:12b and embedded the call's 560 windows in 10.3 s. The question after it embedded only its query.
  - Ollama kept both models on the GPU (`ollama ps`: gemma4:12b 8.1 GB with its 32k context, qwen3-embedding:0.6b 1.8 GB at context 1536, "Embedding model context: 1536 tokens"), so neither was evicted between the ranking, the answer and the check.
- **Decision:**
  - Asking a long call ranks each window by `0.5 · BM25 / best BM25 + 0.5 · max(0, cosine)`. The cosine is between the question (with the question before it, for a follow-up) as a query with `ASK_TASK`, and the window's text, embedded by the same Ollama (`llm.embedding_model`). This holds in the window and on the console. When embedding fails, words alone choose (`semantic_check_skipped`).
  - Answers also get the meaning check, one batch after the reply. In excerpt mode the oldest exchanges are dropped until the parts fit, as on the whole-meeting path, before `too_long`.
  - The window keeps one embedder per meeting for the session (the two meetings asked most recently; the console keeps one per run). The Ask tab's pre-read of a long call loads the model, then embeds the call's windows into it. A question that arrives meanwhile waits for that embedding instead of doing it again. So a long call's windows are embedded once, and each question embeds only its query and its check.
- **Consequences:**
  - A long call's question always reads a full excerpt (about 8,000 tokens), so the model takes longer on questions that words matched narrowly: a median of 7.4 s against 5.9 s by words alone. A follow-up adds about 0.1 s for its query and check (median 7.5 s in all).
  - The first question pays for the windows unless the pre-read ran: 15.8 s cold (both models loaded and every window embedded first) against 5.9 s after the pre-read.
  - A meeting's vectors stay in memory while it is one of the two asked most recently, about 18 MB for a 2-hour call.
  - The model is called without lines only when embeddings fail and no word matches. The "no part matches" sentence (`askExcerptNothing`; the console prints the same, and a test compares the two) now says Evra looked only at the parts that match the question, without "the words of".
  - A call that fits one prompt is asked as before; its answer embeds only the points the word check drops, after the reply.

## Embedding model context: 1536 tokens (2026-11-26)
- **Context:** with both models loaded, Ollama held gemma4:12b at 7.54 GiB (its 32k context) and qwen3-embedding:0.6b at 2.21 GiB (Ollama's default 4096 context), 11.1 of the GPU's 12.2 GB. Evra's embedding inputs are short. The plan's rule: send a smaller `options.num_ctx` with `/api/embed` only if Ollama honours it, it saves at least 0.5 GB, the vectors stay the same (cosine ≥ 0.9999 against the default for 20 fixture windows), and it is at least 4× the longest input Evra sends.
- **Evidence:** Ollama 0.34.4's API doc lists `options` ("additional model parameters listed in the documentation for the Modelfile") for `/api/embed` but does not name `num_ctx`, so a spike measured it, reading `/api/ps` after each load:

  | num_ctx | size in VRAM | context Ollama reports | min cosine against the default (20 windows) |
  | --- | --- | --- | --- |
  | default | 2.21 GiB | 4096 | 1.000000 in 5 of 8 reloads, 0.999826 in 3 |
  | 2048 | 1.98 GiB | 2048 | 1.000000 (1 trial) |
  | 1536 | 1.63 GiB | 1536 | 1.000000 in 4 of 5 trials against a default of the same session, 0.999826 in 1 |
  | 1024 | 1.28 GiB | 1024 | 1.000000 or 0.999826 |

  - Honoured: Ollama reloads the model at the size asked for and reports it; a second call with the same size does not reload it.
  - The 0.999826 is one of the 20 windows, whose vector flips between two values from one load to the next. It happens at every size, the default against itself included, so `num_ctx` does not change the vectors beyond what a reload already does.
  - Longest inputs by `prompt_eval_count`:
    - a 6-line window: 158 tokens (median 86, over the 289 windows of both fixtures);
    - every question of the bake-offs as a query: at most 129;
    - the longest point the schema allows (600 characters) as a query: 321.
  - Past the context, `truncate: true` cuts the end of each input to fit (the doc's wording; measured: a 4,095-token text at `num_ctx` 1024 was read as 1,023 tokens), and `truncate: false` answers HTTP 400.
  - A model unloads with `/api/generate` and `keep_alive: 0` (done_reason `unload`), embedding models too.
  - `ollama ps` with both models loaded as Evra loads them after this change: gemma4:12b 8.1 GB at context 32768 and qwen3-embedding:0.6b 1.8 GB at context 1536, both 100% GPU (at the default context the embedding model took 2.4 GB).
- **Decision:** every `/api/embed` request sends `options.num_ctx = 1536` (`EMBED_NUM_CTX` in `evra.llm.ollama`, one value, so Ollama loads the model once at that size). That saves 0.58 GiB against the default, is 4.8× the longest point query the schema allows and 9.7× the longest window, and leaves the vectors as they are.
- **Consequences:**
  - Both models together now take about 9.2 GiB instead of 9.75.
  - An input past 1,536 tokens (a point citing very many lines) is embedded from its first 1,536 tokens.
  - The first embedding after this change reloads the model once at the new size.
  - 1024 would save more (0.93 GiB) but is under 4× the longest point query.

## Long calls: single pass up to 60 minutes, then parts (A2/A3) (2026-11-27)
- **Context:** a call whose note prompt (A1) did not fit the context budget failed `too_long`, and a single-pass note keeps fewer of a call's facts as the call grows (spec §1). Plan B reads long calls in parts of about 10 minutes (A2), combines the parts (A3), and sets the length where one pass stops from a measurement (spec §3.5, §4.6).
- **How a long call is written** (`notes/windows.py`, `notes/mapreduce.py`):
  - A part runs from its first line to the last line that starts within 10 minutes of it, then to the end of that speaker's turn, but no further than the last line starting within 13 minutes. The next part starts at the first line from a minute before this one ends, moved back to the start of that line's turn, but no earlier than 2 minutes before the end. A tail under 3 minutes joins the last part, and a call of 13 minutes or less is one part. So a call with no change of speaker splits by time too, into parts of at most 16 minutes overlapping by at most 2. Every part adds a line: after a silence longer than a part's reach, the next part starts at the first line after it, with no overlap across the silence (RB51; the literal rule made a part for each line of the minute before such a silence: 22 parts instead of 7 for an hour of 4-second lines with a 15-minute break).
  - Each part (A2, `a2-v1`) is read on the meeting's A0 context with only its own lines printed, their ids still the whole call's (u:1…u:N), after "This is part i of n of the meeting (mm:ss–mm:ss); … marks lines left out." Its rules carry what A4–A6 taught (RB26). The code numbers the parts; the model's `window_index` is ignored. Every part sees all of the user's notes.
  - A3 (`a3-v2`) is A1 v4 with its first line replaced, a rule for the note's length ("at most 25 points in all, the summary included", merging repeats across parts), two rules for `repeats` and `answered`, and the parts' digests as inert JSON, every point numbered p1, p2, … across the parts. It writes the note on a context that shows none of the call's lines, and its points are checked like A1's. Its reply has twice the usual room (8,192 tokens by default, its repair too), so its prompt limit leaves that room; the context size (`num_ctx`) stays, so the model is not reloaded.
  - The digests' commitments, decisions and questions become the action items, decisions and open questions through A4–A6's own steps (`check_items`, then `settle_items`): owner, one check of them all (a commitment's due phrase is part of its claim), A3's pruning, repeats kept once (the earliest, which now cites its repeats' lines too, on one pass as well), and a decision that restates a kept task left to the task. Digest points carry no confidence.
  - A3 only removes: an item it lists as a repeat of an earlier one of the same kind (its lines join the earlier one), and a question it lists as answered later, together with the kept questions that repeat it (the same question read in two overlapping parts, which the merge has not folded yet). Every other entry is ignored. Removals are counted (`repeats`, `answered`), not dropped. A reply that is not used removes nothing.
  - A part whose reply fails is left out (`note_part_failed`, with its number and reason); when every part fails, the first error is raised. When A3's JSON still fails after its repair, the note is its records alone (`a0-v1+a2-v1`). A cut-off A3 reply, or digests too long for one prompt, fail the note: the window and the console then say "This meeting is too long for a note. You can still ask about it."
  - Version `a0-v1+a2-v1+a3-v2`, with `+a9-v1` after `a2-v1` when a part was repaired and after `a3-v2` when A3 was. Tokens and seconds are every call's. Stages: "Reading part i of n…", then "Putting the note together…".
  - `write_note_and_items` chooses, on the estimate `draft_note` checks: a call longer than `llm.single_pass_minutes`, or one whose single-pass prompt passes the budget, is read in parts. `evra note`, the window and the bake-off share that choice, and a long transcript no longer fails `too_long`.
  - The title (A8) of a call whose whole transcript and title task would not fit is written on a context with none of its lines, from the note alone (RB46).
- **Departure from spec §3.6 (RB24):** the spec merges digest items at a text ratio ≥ 0.9 "or overlapping citations". Parts overlap by a minute, so a line holding two tasks ("I'll update the deck and send it to Priya") is read in two parts, and a shared line alone would fold the two tasks into one. The merge uses `extract.is_repeat` instead (ratio ≥ 0.9, or a shared line and ratio ≥ 0.6), the one rule for every repeat.
- **Evidence, first measurement** (A3 `a3-v1`, without the length rule or the room): `tools/bakeoff_notes.py gemma4:12b --runs 2 --minutes 15,30,45,60 --path single`, then the same with `--path windows` (Ollama 0.34.4, RTX 5070 Ti Laptop). A cut is the first N minutes of the 60-minute synthetic 1:1, scored on the facts planted before it. Coverage: facts in the note's own points, then with the records (what the owner sees, RB31). Seconds: from the first call to the checked note and its records.

  | cut (facts) | parts | one pass: own / with records | in parts: own / with records | one pass, s | in parts, s |
  | --- | --- | --- | --- | --- | --- |
  | 15 min (2) | 2 | 50/50%, 50/50% | 50/50%, 50/50% | 37.5, 29.8 | 77.4, 67.5 |
  | 30 min (6) | 3 | 83/100%, 33/50% | 67/83%, 33/50% | 55.9, 35.1 | 184.5, 166.5 |
  | 45 min (8) | 5 | 62/75%, 50/62% | A3 cut off, 50/75% | 80.1, 61.7 | failed, 222.9 |
  | 60 min (13) | 7 | 46/77%, 46/62% | 38/85%, 38/85% | 111.0, 80.0 | 307.4, 303.9 |

  - Records on the 60-minute call: one pass 19 action items, 7 decisions and 3 open questions in both runs, with 2 of the 3 planted commitments (the laptop question to finance missed both times); in parts 25/6/1, with all 3.
  - A3's lists: 1 repeat removed in 1 of the 7 runs that combined (15 minutes, run 1), no question removed as answered. No planted fact was in two records of one kind in any run.
  - The note in parts is long: 20 kept points at 15 minutes, 26–37 at 30, 47 at 45 and 61 at 60, against 10, 10–15, 14–17 and 16–17 in one pass.
  - The 60-minute call in parts, run 1: parts 23.1, 27.6, 43.1, 29.1, 26.1, 34.6 and 28.4 s, then A3 94.1 s.
  - At temperature 0 the runs still differ: 30 minutes in one pass found 6/6 facts in run 1 and 3/6 in run 2.
  - A3 ran out of room: on the 45-minute cut, run 1, all 5 parts were read and A3's reply hit the 4,096-token output limit, so there was no note (`cut_off`, RB28). Run again with room for 8,192 tokens (a diagnostic), A3 wrote 4,157 tokens at 45 minutes and 4,024 at 60, in 95–98 s.
- **Evidence, after the review round** (A3 `a3-v2` with its length rule and twice the room; parts cut at 13 minutes): `--runs 2 --minutes 45,60 --path windows`, and one note on the 2-hour call that `tools/bakeoff_ask.py --hours 2` builds (the 60-minute call said twice, an hour apart; `--hours 2`, auto path, which reads it in parts).

  | call (facts) | parts | own / with records | kept points | items a/d/q | A3: seconds, reply tokens | in all, s |
  | --- | --- | --- | --- | --- | --- | --- |
  | 45 min (8), run 1 | 5 | 75/100% | 51 | 15/6/0 | 84.6 s, 3,620 | 263.7 |
  | 45 min (8), run 2 | 5 | 50/75% | 45 | 11/8/0 | 75.1 s, 3,173 | 224.0 |
  | 60 min (13), runs 1 and 2 | 7 | 62/100%, 62/100% | 59, 59 | 25/6/1 | 92.5 and 91.9 s, 3,909 | 309.0, 308.5 |
  | 2 hours (13), auto | 13 | 54/85% | 68 | 36/16/1 | 133.7 s, 5,398 | 622.9 |

  - No A3 reply was cut off. On the 2-hour call A3 wrote 5,398 tokens, past the usual 4,096, so the doubled room is what let that note through.
  - gemma4:12b does not keep to the length rule: the notes kept 45–68 points where A3 is asked for at most 25. Its replies shrank a little (3,173–3,909 tokens at 45–60 minutes, against 4,024–4,157).
  - Removed by A3: 1 question as answered (45 minutes, run 1); on the 2-hour call 1 repeat and 5 answered questions. The 2-hour call keeps 2 planted facts in two records of one kind: every fact is said twice there, in different words.
  - Commitments: 1/1 at 45 minutes, 3/3 at 60 minutes and on the 2-hour call. The 2-hour call's 13 parts took 23.6–71.8 s each.
- **Decision:** `llm.single_pass_minutes = 60` (RB44). Up to 60 minutes a call is written in one pass whenever it fits the budget; longer calls, and calls that do not fit, are read in parts.
  - The plan's rule was the longest cut at which one pass's coverage with the records is at least the parts' in both runs. That rule gives 30: 30 minutes 100% ≥ 83% and 50% ≥ 50%; 45 minutes 75% against a failed note, but 62% < 75%; 60 minutes 77% < 85% and 62% < 85%.
  - It weighs recall alone, and was overridden. In parts takes 3–4 times as long:
    - 60 minutes: 304–309 s, against one pass's 80–111 s and §9.5's 90 s;
    - 30 minutes: 166–184 s, against 35–56 s.
  - In the first measurement, 1 run in 4 at 45–60 minutes failed (A3 cut off). The recall gain there (62–77% with the records, to 75–100%) comes with a note of 45–61 points.
  - The spec sets §9.5's time target as well as recall, and a note that fails is worse than a shorter one.
  - Revisit once parts are read while the call is recorded (BACKLOG "Digest windows while recording"); then only A3 runs after Stop.
- **A 60-minute note** against §9.5's 1.5 minutes: 80.0–111.0 s in one pass, the way it is now written; 303.9–309.0 s in parts, over three times the target.
- **Consequences:**
  - A call of up to an hour is written as before: one pass, then A4–A6. It gets one pass's recall (62–77% with the records on the 60-minute call, where parts found 85–100%). Cost if wrong: that recall gap on 45–60 minute calls.
  - A longer call is read in parts instead of failing `too_long`: the 2-hour call took about 10 minutes and found 11 of its 13 facts with the records.
  - Its note is long (45–68 points) because A3 does not keep to its length; the records still list every item (BACKLOG "A3's note runs long").
  - A part that fails leaves about 10 minutes out of the note, and only the log says so; a call whose digests together pass the budget (over about four hours) fails `too_long` (BACKLOG has both).

## Notepad alignment weights (2026-11-27)
- **Context:** the note job links each line the owner typed during a call to the transcript lines it was written about (BUILD.md §7.2, `notes/align.py`), so A1 can expand those topics and a long call's parts get the notes about them. §7.2 gives the starting weights (time 0.4, words 0.3, meaning 0.3), the candidates (utterances ending from 90 s before the line was typed to 30 s after, the time weight peaking 15 s after a line ends, spread 30 s), a starting cut-off of 0.35 and at most 5 lines a note. It asks to tune the threshold on labelled lines against: precision ≥ 0.80 at recall ≥ 0.60, and a 60-minute meeting with 50 note lines linked in under 5 s. Without meaning (no embedder, or the batch fails) the score is (0.4 · time + 0.3 · words) / 0.7.
- **The labelled set:** `tests/fixtures/notes/one_on_one_60min_notes.json`, 12 synthetic lines we wrote and labelled ourselves, not the owner's. They are terse lines typed during the 60-minute synthetic 1:1, one after each planted fact but the last. Each started 6–29 s after the last line it notes ended (6–45 s after the first), and is labelled with the 1–3 lines it is about (21 in all). Measured with `tools/eval_alignment.py` (with `--sweep`, with and without `--no-embed`; Ollama 0.34.4, RTX 5070 Ti Laptop, `qwen3-embedding:0.6b`). "Right" is a linked line that is labelled.
- **The rule (RB52):** a link must agree with the note in its words or its meaning, not only in its time. So each mode's cut-off sits just above the best score that time alone gives:
  - with meaning, 0.55: 0.4 at the peak, plus 0.3 × 0.5, the cosine qwen3 gives two lines of one conversation;
  - by time and words alone, 0.57: 0.4 / 0.7.
- **Evidence, at §7.2's starting cut-off of 0.35:** every note linked 5 lines, 60 in all, 20 of them right: 33% precision at 95% recall in both modes.
  - With meaning, each note's best line is one it is about (0.69–0.97), and its other labelled lines score 0.53–0.89.
  - Its neighbours score 0.42–0.62. Time alone gives a line heard 0–30 s before the note 0.31–0.40, and qwen3 adds 0.06–0.15 for any line of the same conversation.
  - Without meaning, the reweighting lifts time alone to 0.45–0.57 and shared words alone to 0.43.
- **Evidence, the sweep** (precision / recall; the score at least, at most 5 a note):

  | score at least | with meaning | time and words alone |
  | --- | --- | --- |
  | 0.35 | 33% / 95% | 33% / 95% |
  | 0.40 | 33% / 95% | 33% / 95% |
  | 0.45 | 36% / 95% | 33% / 95% |
  | 0.50 | 53% / 95% | 33% / 95% |
  | 0.55 | 79% / 90% | 45% / 95% |
  | **0.60** | **95% / 86%** (19 linked, 18 right) | 73% / 90% |
  | **0.65** | 100% / 76% | **85% / 81%** (20 linked, 17 right) |
  | 0.70 | 100% / 67% | 100% / 76% |

  - At most one line a note gives 100% / 57% in both modes (52% at 0.70); at most two gives 100% / 86% with meaning at 0.60, and 89% / 81% without at 0.65.
  - The one labelled line missed with meaning at 0.60 is "Right, we don't have an answer on that yet." (the legacy API, n12). Without meaning at 0.65, four are missed.
- **Evidence, time:** Ollama embeds 93–99 short lines a second whatever the request size (a spike: 64, 128 and 256 lines a request; 512 answered HTTP 400).
  - Embedding every candidate, the 12 notes' windows hold 331 transcript lines, and 50 lines spread over the hour hold 836, every line of the call.
  - RB53 leaves out, before the batch, a candidate that could not reach 0.60 even with a perfect meaning (0.4 · time + 0.3 · words + 0.3 < 0.60). That leaves 98 of the 331 and 409 of the 836.
  - It changes no link: without meaning such a candidate scores under 0.30 / 0.7 = 0.43, below 0.65, and a test checks the fixture's links in both modes.

  | | 12 lines, embedding model loaded first | 12 lines, warm | 50 lines over the hour |
  | --- | --- | --- | --- |
  | with meaning, every candidate embedded | 5.19 s | 3.31 s | 8.36–8.64 s |
  | with meaning, candidates that cannot reach 0.60 left out (3 runs) | 2.75–2.84 s | 1.06–1.11 s | 4.25–4.28 s |
  | time and words alone | under 0.01 s | under 0.01 s | 0.02 s |

  - Loading the embedding model takes about 1.7–1.9 s. gemma4:12b being loaded as well made no difference.
- **Decision (RB52, RB53):**
  - `MIN_SCORE = 0.60` with meaning, and `MIN_SCORE_NO_MEANING = 0.65` by time and words alone, which includes a failed batch.
  - The weights stay 0.4 / 0.3 / 0.3, the window 90 s before to 30 s after (peak 15 s, spread 30 s), and at most 5 lines a note, with `ALIGN_TASK` as the query's instruction.
  - A candidate that cannot reach `MIN_SCORE` even with a perfect meaning is not embedded, and a note left with no candidate sends no query.
  - Both cut-offs meet §7.2 on this set: 95% / 86% with meaning, 85% / 81% without. So does the time: 4.25–4.28 s for 50 lines, about 15% under the 5 s.
  - The set is 12 lines we labelled ourselves, so the cut-offs are to be re-tuned on the owner's own labelled lines (BACKLOG).
- **Consequences:**
  - A typed line's `|| aligned:` lists 1–3 lines, on the fixture 19 for 12 notes. A1 reads what the note is about, and a long call's parts get the notes about their stretch (RB36); the My notes tab shows those lines.
  - A note that agrees with no line in words or meaning links nothing. RB36 then routes it by its time, and A1 still sees its time.
  - On real notes a note may link fewer lines than it should (cost if wrong).
  - Linking is the note job's one embedding batch before its chats (RB35). It adds about 1.1 s with 12 notes (2.8 s when the embedding model has to load) and about 4.3 s with 50 over an hour.
  - The batch holds the transcript lines most likely to be cited, so a point citing one of them is checked without embedding it again.

## Typed notes in the note, and a note cited by its label (2026-11-27)
- **Context:** the owner's typed lines now reach every prompt about a meeting, in A0's `<user_notes>`: `[n:k] (mm:ss | before | after) text || aligned: u:…`, or `[n:k] (context) text`, numbered over the whole meeting. The note job, the title and asking build that context in one place (`user_notes.meeting_context`, RB1). A long call's part shows the notes about its stretch, and A3 shows them all (RB36). A0 asks for the notes to be cited as `user`, and the check accepted only `user` (or `[user]` in a point's text).
- **Evidence:** `tools/bakeoff_notes.py gemma4:12b --runs 1 --minutes 60 [--notes]` (the whole 60-minute synthetic 1:1, auto path), and the same call with its notes in one pass, its budget raised to 28,400 (a scratch run; Ollama counted 28,460 prompt tokens, under the 28,672 that `num_ctx` leaves after the reply's room). "Own" coverage counts the note's own points; "with items" adds the action items, decisions and open questions.

  | run | path, in all | kept / dropped | validity | coverage own / with items | items a/d/q | commitments | points citing the notes: written / kept, items |
  | --- | --- | --- | --- | --- | --- | --- | --- |
  | no notes | one pass, 111.2 s | 16 / 1 | 94% | 46% / 77% | 19/7/3 | 2/3 | - |
  | notes, before the label fix | 7 parts, 280.2 s | 18 / 10 | 64% | 8% / 46% | 22/10/0 | 3/3 | 9 / 0, 0 |
  | notes | 7 parts, 274.3 s | 27 / 1 | 96% | 54% / 77% | 22/10/0 | 3/3 | 9 / 9, 1 |
  | notes, one pass, before the label fix | one pass, 107.9 s | 18 / 1 | 95% | 92% / 92% | 9/6/3 | 3/3 | 12 (counted later) / 0, 0 |
  | notes, one pass | one pass, 107.6 s | 19 / 0 | 100% | 92% / 92% | 9/6/3 | 3/3 | 12 / 12, 3 |
  | notes, linked at the new cut-offs | 7 parts, 293.5 s | 61 / 2 | 97% | 46% / 69% | 18/5/0 | 2/3 | 5 / 5, 1 |
  | notes, linked at the new cut-offs, one pass | one pass, 115.7 s | 21 / 1 | 95% | 92% / 92% | 14/7/3 | 2/3 | 12 / 12, 3 |

  - The rows above the last two link 5 lines to every note (the starting cut-off of 0.35). The last two use the cut-offs of "Notepad alignment weights", 1–3 lines a note.
  - The 12 notes add about 440 tokens with 5 links each: the call's A1 estimate goes from 27,738 to 28,175, over the 28,000 budget. With 1–3 links it is 28,070, still over. So with its notes the call is read in parts: 274–294 s, against 108–116 s in one pass. Ollama counted 28,460 and 28,217 prompt tokens in the two one-pass runs.
  - At temperature 0 the runs still differ with the prompt. On parts, the new links gave a longer note (61 points, A3's reply 3,955 tokens against 2,926) with fewer points from the notes (5). The two runs at the new cut-offs each found 2 of the 3 planted commitments as action items: in one pass the postmortem was a point instead, and in parts the promotion packet was missed.
  - A3 wrote one point for each of 9 notes, each ending in a citation list such as "[u:140, u:138, u:139, u:140, u:141, u:142, user.2]": `user` and the note's number. The check read only `u:…` and `user` in brackets, so the bracket stayed in the claim, its numbers were not in the cited lines, and all 9 were dropped as `number_not_cited`. In one pass, A1 cited the notes by their label too, in its citation lists; those points were kept for their transcript lines, but not as citing the notes.
- **Decision:** the check reads a note's label, `n:3`, and gemma4's `user.3` (or `user:3`), in a citation list or in brackets in a point's text, as a citation of the user's notes, the same as `user` (`notes/validate.py`). Appendix B's citation pattern already names `n:<id>`. Such a point is still checked against all of the notes' text, as `user` is. The prompts are unchanged (A0 stays `a0-v1`).
- **Consequences:**
  - In one pass, the notes took the 60-minute call's own coverage from 46% to 92% in both runs: 12 of 13 facts, the 13th (38 customers) being in the note as "38 sign-ups", which the score's keywords don't match. Every point written from a note was kept (12 of 12).
  - A call close to the budget is read in parts once its notes are added, and the budget stays at 28,000 (RB54): Ollama cuts a prompt that doesn't fit and loses part of the call, which is worse than a slower note. That is 2.5 times slower here (274–294 s; §9.5 asks for 90 s, and one pass took 108–116 s), and its coverage gain is smaller (46–54% own, 69–77% with items) (BACKLOG "Typed notes can send a call to parts").
  - A point that cites a note by its label is checked against every note, so a name from another note can support it. One point ("The Atlas beta currently has 38 sign-ups…") was kept that way, and it is true.

## A point from your notes quotes your line (2026-11-27)
- **Context:** a point the owner's notes support cites `[user]`, never one typed line (a label such as `n:3` is read as `user` too, and its number is not kept). The note sheet and `evra note` should still show which line it came from.
- **Decision:** the view (`services/views.note_view`) picks the line for each point citing `[user]`, in this order:
  1. a typed line linked to one of the point's cited transcript lines;
  2. else a line the owner typed (not a long paste) that shares a word with the point;
  3. else a long paste (context, never linked) that shares one.

  Within each, the line sharing the most of the point's content words wins (the word check's measure, `validate.shared_words`), the earlier on a tie. A point that no line is linked to and that shares no word with any line (kept by its meaning alone) quotes nothing. The window shows the line in the point's quotes cell after its transcript lines, led by "From your notes"; `evra note` prints it under the point.
- **Consequences:**
  - No prompt changes: the links and the words are evidence Evra already has. If the pick is wrong, the point shows a neighbouring note line; the owner still sees their own words.
  - A paste shares more words by its length alone and usually sits at the top of the pad, so the typed lines come first (RB61): "From your notes" shows what the owner wrote. A point drawn from a pasted agenda therefore quotes a typed line that shares fewer of its words, whenever some typed line shares one.
