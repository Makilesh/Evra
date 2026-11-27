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

- Meaning check (cosine ≥ 0.55, §7.5, shipped 2026-11-26): re-measure the threshold with `tools/calibrate_semantic.py` on real meetings. On the synthetic calls, gemma4:12b's points the word check dropped scored 0.51–0.53, just under 0.55, and all were true; at 0.50, 2 of 159 mismatched pairs passed (1.3%) in a run that counted it (DECISIONS "Meaning check threshold").
- Plain bullet-list fallback note after a failed repair (§9.1), built from extraction results (M5).
- Spoken years ("twenty twenty-six") in the number check.
- Map-reduce (per-window notes, A2/A3) — needed from about 30 minutes, not only over the budget: planted facts reaching a single-pass note were 30 min 3/6, 60 min 5–6/13 (2026-11-07).
- Flaky under heavy load: `tests/unit/capture/test_session.py::test_clean_start_needs_no_drift_corrections` failed once while a 14B model ran (timing-based); make its timing tolerant.
- Final-review minors (M3b): hints for Ollama HTTP 500 (out of memory) / 400 (`--think` on a non-thinking model); pass A9's `bad_output` through `as_data`; "Ollama is not running" should also say "or install it from ollama.com"; names that are also common words ("Will", "Mark") pass the name check; `FALLBACK_MODEL` in `notes/cli.py` duplicates the `llm.model` default.

## M3c follow-ups (2026-10-02)

- Floating meeting window (always on top, never steals focus) after the M2 focus spike. pywebview 6 already has `on_top` and `focus=False` (Windows: `WS_EX_NOACTIVATE`), but a no-activate window can't take typing, and the notepad needs it: the spike's real question is "appear without taking focus, take it when clicked".
- Record while a note is still being written (today Record waits until the note is done).
- Offer WASAPI-only microphones if one is ever missing from the picker.
- Delete a meeting from the window (with its audio and keys, BUILD.md §8.2).
- Mic picker: long names are cut by the picker's width; show the full name on hover or widen it.
- Note chips: two citations at the same second (one per speaker) show two identical time chips; label them You/Them or merge.
- Final-review minors (M3c): closing during "Stopping…" should wait for the transcript to drain before stopping the ASR worker; closing while capture opens can keep an empty meeting; add a `seq` to `recording.state` so stale events are ignored; buffer live lines that arrive before the open meeting has loaded; restore note progress after a window reload; harden the service's `emit` and start the level ticker before announcing "recording"; give crash-recovered meetings a length from their last utterance; rename: keep edits on blur and say when a title is refused; avoid the brief "No note yet" flash after `note.ready`; check the mic name before first-use loading; catch bridge errors in Stop and Write note.
- HC3 follow-ups (2026-10-02): when "No system audio arrived", log which render endpoint each app's audio session is on (device and process names only; `spikes/audio_sessions.py`) so a repeat of the 17:35 silent-loopback call can be diagnosed; teach speech recognition the owner's and contacts' names (sherpa-onnx hotwords / contextual biasing) — "Makilesh" was heard as "Maggie"/"Magiless".

## M3 finish follow-ups (2026-11-07)

- Sorting into decisions / action items / next time is unreliable on gemma4:12b even with A1 v2 (a "maybe" filed as a decision; a promise left in Discussion; a topic for later dropped): BUILD.md's focused extraction calls (A4–A6) instead of one synthesis pass sorting everything.
- Name check over long calls: a name said more than 3 lines before the cited line drops a true point (a project named once, then "the beta"; "her first week" after "Dana starts"). Consider a longer look-back for names that are not the owner of an action item. It is most of why the 60-minute synthetic call's note misses §7.8's 97% citation validity (2026-11-27): 89–94% of its own points kept in one pass and 92% in parts, the drops mostly "Atlas", "PRs", "Slack" or "API" said away from the lines cited. Every point shown has passed the check.
- Short replies: if models keep citing only "Yeah, I can do that.", let the overlap check borrow the line just before a short reply.
- Bake-off coverage matches keywords exactly ("hardware refresh" for "laptop refresh" is a miss): allow alternative keywords per fact.

## Steno pad follow-ups (2026-11-10)

- Rail: a small who-spoke-when mark per meeting (the chosen sketch had one); needs `list_meetings` to carry a short talk summary per meeting.
- Stamp: the time the note was written; needs the note view to carry its generation time.
- Record button: show `Ctrl Alt R` once the global hotkey exists (M6); `Ctrl K` grows into the palette (M6).
- Frontend end-to-end checks (BUILD.md §9.2): the fake bridge used to look at the redesign (`window.pywebview` injected before load, synthetic fixture) can become a Playwright suite in `frontend/e2e/`.
- Jumping from a time tab to the transcript leaves keyboard focus on the page body (it did before the redesign too); move focus to the highlighted line.
## Settings, later (2026-11-10)

Each one arrives with its feature, never before it (DECISIONS: Settings, first set).
- Note language: the most-requested setting in this category (Phase 1 is English only).
- Choosing the meetings folder, which means moving the database and audio safely.
- Retention (D13, M5). Shortening it deletes data, so it must be confirmed with the consequence named ("Delete audio older than 7 days").
  - Add **Don't keep** to the choices. Make it the default if the audio serves nothing once the note exists (no replay, no re-transcription).
  - Keep it to audio only: deleting transcripts would stop notes from being regenerated.
- In the recording flow, not in Settings:
  - A non-blocking reminder when recording starts, telling the other person they are being recorded, with notice text to copy (no bot ever tells them).
  - An automatic stop after a long silence, with no setting. Granola stops after 15 minutes, and a Meetily user's forgotten recording ran for about 24 hours.
- About: links to the licences and the repository.
- Templates (M5), hotkeys and start with Windows (M6), People (M4).
- Live transcript off for slow PCs: record now, transcribe after. `live_transcript` is already in the settings file.
- After a theme switch, WebView2's background behind a resizing window keeps the startup colour until the next start.

## Asking, later (2026-11-26)

- **Questions across meetings** (Phase 2): they need search, then a fixed plan → read-only lookups → answer flow.
- **Asking during a recording:** Evra Live (Phase 3). Refused for now.
- **Keeping an answer in the note:** turn a checked answer into a note point.
- **Saved custom questions** next to the four one-click ones.
- **Citations by time:** gemma4 once cited lines as `u:15:46` (the line's time) instead of their id, so a right answer had no valid citation. Map a `u:mm:ss` citation to the line that starts then, or say in A0 that the id is the number before the time.
- **Broad questions drop paraphrases:** "What did I promise?" lost points whose detail sat in lines they didn't cite (only the short reply "Yeah, I can do that."). The meaning check (2026-11-26) keeps a point that says what its cited line says in other words, but not a short reply whose meaning is in the line before ("Right. I'll get on that." was dropped on the 2-hour call): the short-reply rule (M3 finish follow-ups) still covers that.
- **The asking bake-off asks each question alone;** add a run with the window's three-turn history (the call too long for one prompt is measured since 2026-11-26: `--hours 2`).
- **Design sidecar:** `.impeccable/design.json` has no Ask component yet (DESIGN.md has the section).
- **Asking timeout covers the pre-read:** the 180-second asking timeout also applies to the pre-read, so a cold read of a long call on a slow GPU could time out.
- **Refused pre-read not retried:** a pre-read refused because another one is running is not retried.
- **Long calls read a full excerpt every time:** with meaning, every window scores above zero, so each question on a 2-hour call reads 8,200–9,050 tokens, against 0–8,700 by words alone. Follow-ups take a median of 7.5 s in all against 5.9 s (the windows themselves are now embedded once per meeting; DECISIONS "Long-call asking reads by meaning"). A score cut-off could let a question that words match narrowly read fewer lines.

## Complete notes, later (2026-11-27)

- **A list that couldn't be made:** when A4, A5 or A6 still returns invalid JSON after its repair (or runs out of room), its section of the note is simply empty, and only the log says so (`note_items_failed`, with the kinds). Say in the note that Evra couldn't list them, with a way to try again.
- **A note of the lists alone:** when A1's JSON fails even after its repair, the note is built from the action items, decisions and open questions (BUILD.md §9.1). `evra note` says so; the window shows the lists without saying the summary and discussion couldn't be written.
- **Say when a part of a long call couldn't be read:** a part whose digest (A2) is still invalid JSON after its repair, or runs out of room, is left out, so the note silently misses about 10 minutes; only the log says so (`note_part_failed`, with the part's number and the reason). Say it in the note, with a way to try again (DECISIONS "Long calls: single pass up to 60 minutes, then parts").
- **Digest windows while recording:** Parts take about 5 s per minute of call (623–637 s for 2 hours): digest parts while recording. Written in parts, a 60-minute note takes about 5 minutes (7 parts of 23–44 s, then A3 about 92–96 s; 304–317 s in all, measured again 2026-11-27), over three times §9.5's 1.5 minutes. So calls up to an hour stay one pass (79 s with the model loaded, 113–115 s with its load; with 12 typed notes 69–107 s, since the budget moved to 28,400), and only longer ones, or ones past the budget, use parts. Read each part once its 10 minutes are recorded, so only the last part and A3 are left after Stop; then parts could start earlier than an hour (DECISIONS "Long calls: single pass up to 60 minutes, then parts").
- **A3's note runs long:** A3 copies most digest points (45–68 kept at 45–120 min): a long call needs a combine that compresses (two rounds, or a per-section cap the model plans for), measured on a 3-hour call; a schema cap was ruled out because it cuts the note's later topics silently.
- **Combine in rounds when the digests don't fit** (calls over about four hours): A3 reads every part's digest in one prompt, so a call whose digests together pass the context budget fails `too_long`. Combine the parts in groups first, then the groups.
- **Re-tune the alignment cut-offs on the owner's own labelled lines (BUILD.md §7.2):** 0.60 with meaning and 0.65 by time and words alone were chosen on 12 synthetic lines we labelled ourselves (95% / 86% and 85% / 81%). Label 30–50 of the owner's own lines, run `tools/eval_alignment.py --sweep` on them, and choose both again (DECISIONS "Notepad alignment weights").
- **Typed notes can send a call to parts,** now only past the 28,400 budget or past 60 minutes (DECISIONS "Budget 28,400 with parts when Ollama cuts the prompt"). The 60-minute synthetic call's 12 notes take its A1 estimate from 27,738 to 28,070, which used to send it to parts under the old 28,000 (304–309 s, 46% / 69% coverage); at 28,400 it stays in one pass (69–107 s, 85–92%). Ollama counted 28,217 (28,460 when every note linked 5 lines) of the 28,672 tokens left after the reply, and when it cuts a one-pass prompt anyway, the call is read in parts after one wasted A1 call. Ideas: count the prompt's tokens exactly instead of estimating 2.7 characters a token, so the budget can sit at the room; leave short backchannel lines ("Yeah.", "Right.") out of a call near the budget; measure the estimate's error on more calls.
- **A note cited by its label:** check the point against that note alone, and keep its number so the window quotes that note (RB40 picks a line today).
- **Topics and key moments (A7):** BUILD.md §7.4's fourth list: the call's 3–10 topics with their times and salience, and at most three key moments (Appendix A's A7 is still v3's text, and the `topic` table is unused). Until then the general template's Key moments section is written by A1.
- **An agenda pad per person:** lines typed before a call are that meeting's `before` notes. A pad that belongs to the person, carried from one 1:1 with them to the next (what to raise next time), needs people (plan C, spec §9).
- **Agreed dates filed as tasks:** a4-v2 lists some agreed dates and times as action items. On the 60-minute synthetic call, the Atlas beta date (March 3) and the standup move (10:30) were tasks in both runs, so their decision copies were left out (RB20) and they show only as tasks with a Done box. No owner rule separates them: they carry owners Them and You, as real tasks do (RB39).
- **Items lose a name or a number:** a4-v2 wrote the laptop task as "Request a budget for a laptop refresh", without "finance" ("I'll ask finance about the laptop refresh this week"), so the bake-off's keywords miss that planted commitment. a6-v2 shortened the 4-minute call's API question to "What are the API limits from Priya's team?", without "500 requests per minute, or do we need batching". A v3 wording that keeps names and numbers fixed both, and the agreed dates above, but lost three open questions and one run's postmortem task (DECISIONS "Extraction sorts, synthesis writes").
- **Judge prompt changes on a larger synthetic set:** two rounds of A4–A6 wording on 2 fixtures traded gains for losses at temperature 0. Measure a change on more calls (and more than one run each) before keeping it.
- **A GPU that can't hold both models (BUILD.md §8.3):** inside a job the chat calls run back to back and the embedding batches after them, so Ollama never swaps models mid-way while gemma4:12b (32k) and qwen3-embedding (1,536) fit together, about 9.2 GiB here. On a smaller GPU, a long call's question swaps twice (its parts are ranked by meaning before the answer, and checked after), and a note with typed notes swaps once more (linking comes before the chats, RB35). Measure on such a GPU; link and rank by words alone there if the swaps cost too much.
- **Typed notes on a call read in parts** (since the 28,400 budget, a call over an hour or over the budget, with typed notes; RB66):
  - **Coverage.** On the 60-minute synthetic call read in parts, its 12 typed notes lowered coverage instead of raising it (2026-11-27, 2 runs each): from 62% to 46% of the facts in the note's own points, and from 100% to 69% with the records. In one pass the same notes raise it from 46% to 85–92%.
  - **TODO lines.** A4's rule 3 turns the owner's lines marked "TODO", "->" or "AI:" into action items, and the parts path's prompts, A2 and A3, have no such rule. In the real window, two TODO lines typed after that call reached every part's and A3's prompt, but neither became an item or a point. The same kind of lines on the 4-minute call, in one pass, became two action items quoting them.
  - **Next:** a prompt change (A2 and A3 handling the notes and their TODO lines), measured in its own round on a long call with notes.
- **Save the notes when the window closes:** the pad saves 400 ms after the last change and is flushed before Stop, Write note, Retry and a meeting change, but not when the window closes, so a line typed in its last 400 ms is lost. First check what pywebview still delivers while the window closes (a spike: never invent the API), then flush there.

## From the competitor review (2026-11-10)
The full list (100 features, with links) is in `private/research/reports/`.
- **Switch the microphone during a recording.** The picker is locked while recording, so a headset that drops can't be swapped mid-call.
- **Gaps with no plan yet** that comparable apps cover: one action-item list across meetings, exporting files (PDF, text, Markdown), importing an older audio file, and detecting a meeting and asking first.
