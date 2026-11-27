# PROGRESS.md — what we did, what we built

Newest first. Each entry: date, what happened, and (once code exists) the commit hash.

## 2026-11-27 — Complete notes (branch `notes-complete`)

- **Planned:** plan B updated from plan A's results (`1d83b00`).
- **Embeddings through Ollama** (`0ab41cb`): `qwen3-embedding:0.6b` (639 MB, 1,024 dimensions; Apache-2.0 on its Hugging Face card) through `/api/embed`, vectors normalised in Evra. D17 now runs in Ollama instead of a torch worker (DECISIONS.md).
- **The meaning check** (`c506afe`, `98a9155`): a point whose words fall short of the lines it cites is kept when its embedding is close enough to theirs (cosine ≥ 0.55, from `tools/calibrate_semantic.py`), and still needs its numbers and names. Long-call asking ranks a call's parts by words and meaning: one embedder per meeting, the Ask tab pre-reads a long call's parts, and a 1,536-token embedding context saves 0.58 GiB of VRAM (`e71849a`); a call every question reads whole gets the whole-call pre-read (`ac5250b`).
- **Action items, decisions and open questions as records** (`dfd0136`, `8e55599`, `81da8e7`): A1 v4 writes the note's own sections, and A4–A6 (v2) list the records on the same meeting context. They are checked like note points, saved with the note (`0003_items.sql`) and shown in their sections; each action item has a Done box, and the tick survives a rewrite (DECISIONS "Extraction sorts, synthesis writes", "Fuzzy matching with difflib").
- **Long calls in parts** (`fc734a9`, `0d3c221`, `acc858c`): parts of about 10 minutes cut at speaker turns (A2), combined by A3 (v2, with twice the reply room). One pass up to 60 minutes (`llm.single_pass_minutes`), parts beyond that or over the budget, so a long transcript no longer fails `too_long`. After a long silence the next part starts after it (DECISIONS "Long calls: single pass up to 60 minutes, then parts (A2/A3)").
- **The notepad steers the note** (`e512247`, `178d877`, `6e2f59e`, `0cec96d`): the owner's typed lines are stored, linked to the transcript lines they were written about (time, words and meaning; cut-offs 0.60 with meaning, 0.65 without), shown in every prompt about the meeting, and the `[user]` points are checked against them. A long call's part gets the notes about its stretch (DECISIONS "Notepad alignment weights", "Typed notes in the note, and a note cited by its label").
- **The My notes tab** (`460bde5`, `5304439`, `a8aff1d`): one field per line, the typed time as a time tab, the pad saved 400 ms after typing and flushed before Stop, Write note and a meeting change (a failed save is sent again), and the linked lines beside each line once the note is written. A point from the owner's notes quotes the typed line ("From your notes"; DECISIONS "A point from your notes quotes your line"). Its tests took the frontend from 144 to 175 and Python from 777 to 784; looked at in Edge with the fake bridge (light, dark, 1100×720, 720×480, keyboard and mouse).
- **Measured** (gemma4:12b, Ollama 0.34.4, RTX 5070 Ti Laptop 12 GB, the app's defaults; `tools/bakeoff_notes.py`, 2 runs a call unless noted, the first with the model load; validity is the share of the note's own points the check kept; coverage counts the planted facts in the note's own points, then with the records):

  | call | path | in all, s | kept / dropped (validity) | coverage, own / with records | items a/d/q | planted commitments |
  | --- | --- | --- | --- | --- | --- | --- |
  | 4 minutes | one pass | 29.8, 30.2 | 10/0, 11/0 (100%) | 80% / 100% | 5/1/2 | 3/3 |
  | 60 minutes | one pass | 115.4, 78.9 | 16/1, 17/2 (94.1%, 89.5%) | 46% / 77%, 46% / 62% | 19/7/3 | 2/3 |
  | 60 minutes | parts (forced), 7 | 317.0, 308.5 | 59/5 (92.2%) | 62% / 100% | 25/6/1 | 3/3 |
  | 60 minutes + 12 typed notes | parts (estimate 28,070 over the 28,000 budget) | 308.5, 304.0 | 61/2 (96.8%) | 46% / 69% | 18/5/0 | 2/3 |
  | the same, budget raised to 28,400 for the measurement | one pass | 121.1, 71.2 | 21/1, 14/1 | 92% / 92%, 85% / 85% | 14/7/3, 16/7/3 | 2/3, 3/3 |
  | 2 hours (the hour said twice) | parts, 13 | 637.3 (one run) | 68/3 (95.8%) | 54% / 85% | 36/16/1 | 3/3 |

  - Against §9.5 (a 1:1 note after 60 minutes in at most 1.5 minutes): met in one pass with the model loaded, as Stop leaves it (78.9 s); not with the load counted (115.4 s), and not in parts (304–317 s), which is also how the hour is read once 12 typed notes take it over the budget. BACKLOG keeps "Digest windows while recording".
  - Against §7.8 (citation validity of at least 97%): met on the 4-minute call; on the hour 89.5–96.8%, the drops mostly names said away from the lines cited (BACKLOG "Name check over long calls"). Every point shown has passed the check.
  - Typed notes, the hour: in parts 5 of 5 points written from them were kept; in one pass all 12 were, and coverage of the note's own points went from 46% to 85–92%. That is what the 28,000 budget costs a call this close to it (BACKLOG "Typed notes can send a call to parts").
  - In one pass the second run differs from the first even at temperature 0, while runs in parts repeat exactly; the 2-hour call was run once, so its spread is not measured.
  - The meaning check's 0.55 still holds on A1 v4's notes (`tools/calibrate_semantic.py`): no mismatched pair reaches it (75 pairs, highest 0.506), every supported pair does (25, median 0.809), and the one point the words dropped scores 0.550, true of the call, its detail partly in a line it doesn't cite.
  - Linking typed notes (`tools/eval_alignment.py`, the 12 synthetic lines): 95% precision at 86% recall with meaning (cut-off 0.60), 85% at 81% by time and words (0.65); 12 lines in 1.1 s, 50 lines over the hour in 4.4 s (§7.2 met).
- **Checked in the real window.** Setup: `python -m evra run` on a test data folder holding only the synthetic 60-minute call and its 12 typed lines, beside the owner's own instance. The window was driven through Windows UI Automation (one real mouse click), with no microphone or speakers. Captures were of the Evra window only, looked at, then deleted. The test instance was closed afterwards.
  - **Write note:** the band showed "Linking your notes…", then "Reading part 1 of 7…" through "Reading part 7 of 7…", then "Putting the note together…", and the note appeared once, 300 s after Write note. Six points quote the typed line they came from ("From your notes"), each the right one.
  - **My notes:** each line shows its time tab and, after the note, its 1–3 linked transcript lines (19 in all). A time tab opens the transcript at the line being said.
  - **Done:** a tick fills the box rule green and strikes the point through. Hover fills the row band and the box's line full rule green, and keyboard focus draws the 2px rule-green ring (seen once the page was scrolled back; see Found). At 840 px the sheet folds with the boxes in place.
  - **Rewrites:** the window offers Write note only when there is no note, so the note was rewritten twice with `evra note --data-dir` (291 s and 320 s). Both ticked items stayed done, once onto a reworded item ("Move tickets over…" for "Move the tickets over…").
  - **Two lines typed in My notes:** both saved through the bridge, with ids from `crypto.randomUUID` under `file://`, phase `after`, and their first time kept. They reached every prompt of the next rewrite, but on this call, read in parts, neither became a point or an item; in one pass, the same kind of lines became action items (BACKLOG "TODO lines on a call read in parts").
  - **The log:** 35 INFO lines of codes and counts; a search for 752 content words from the note, its items, the typed lines and the transcript found none.
  - **Found:**
    - Ticking or tabbing onto a Done box scrolls the whole window to an empty stretch. The boxes' visually hidden inputs escape the note's scroller and make the page about 22 screens tall. Left for the final review.
    - A time-tab jump to the transcript shifts the page about 85 px; it predates this work (M3c, BACKLOG).
- **Docs:**
  - BUILD.md: D17 and §4 (embeddings in Ollama); §7.1–7.6 as built (My notes, the linking cut-offs, stages, one pass or parts, extraction, the meaning check, templates); §8.2 (`0003_items.sql`, `note_block`); §8.3 (both models in Ollama); §8.4 (the Note view with Done boxes, My notes); §9.1 (the new failure rows); Appendix A (A1–A6 as shipped) and B (the schemas as shipped).
  - DECISIONS.md: "Extraction sorts, synthesis writes" and "Fuzzy matching with difflib".
  - BACKLOG.md: the deferred items, including A7 and an agenda pad per person.
  - README.md: `ollama pull qwen3-embedding:0.6b`.
- Tests: Python 784 passed (+170 on this branch), frontend 175 (+38).

## 2026-11-26 — Asking a meeting (branch `ask-meetings`)

- **Planned:** the design for asking a meeting, complete notes and open promises (`docs/superpowers/specs/2026-11-26-ask-notes-promises-design.md`) and plan A (`d4cff45`); plans B and C written ahead of their branches (`d8d9d5c`). The owner put this work before M4 (DECISIONS.md).
- **Checks run through `python -m`** (`111f86e`): Smart App Control blocks uv's `.exe` launchers on this PC.
- **Cloud models refused** (`5041023`): a model Ollama would run in its cloud is never offered and fails with `cloud_model` before any text is sent (DECISIONS.md).
- **Shared meeting context (A0)** and the note on it (A1 v3, prompt version `a0-v1+a1-v3`; `510cb15`, `1576e3b`): the transcript, gaps, notes and metadata are one system message; the note's rules and template are the user message. Measured against v2 on gemma4:12b (2 runs): short call 15 kept, 0 dropped, 10/10 facts both times; 60-minute call validity 86% and 91% (v2: 81% and 73%), facts 46% and 54% (v2: 38% and 46%). v3 kept (DECISIONS.md).
- **Asking a meeting** (A12; `a9e227d`, `6b1dacc`): one to four cited points per question, each checked like a note point, stored in a new `question` table; a call too long for one prompt reads its best-matching windows. Notes and answers share one parse-and-repair step.
- **From the window and the console** (`b1f5aa8`, `e125c12`): one question at a time on a background thread, refused while recording, answered through `question.updated`; opening the Ask tab pre-reads the meeting; questions a closed app left unanswered become "interrupted"; `python -m evra ask "QUESTION"`.
- **The Ask tab** (`722fb7c`, `1c57ae8`): the questions as a thread on the note sheet, four one-click questions and a typed one, band rows for "not discussed", unchecked and failed (with Ask again), announcements for screen readers.
- **Measured** with `tools/bakeoff_ask.py` on the 60-minute synthetic 1:1 (13 fact questions, 3 topics it never mentions), against the spec's targets (≥ 12/13 correct, 3/3 "not discussed", ≥ 11/13 passing the check, follow-ups ≤ 3 s median, the first question after the note reusing its prompt). All met when the question follows the note directly; in the window's order see the title bullet:
  - gemma4:12b: 13/13 correct (12/13 still correct after the check), 3/3, 12/13 checked; first question 20.1 s cold; right after the note 2.3 s with 98% of the 27,417-token prompt reused; follow-ups 1.7 s median, 5.3 s worst.
  - qwen3.5:9b: 13/13 (13/13), 3/3, 13/13; 30.5 s cold; 1.5 s after the note (98% reused); follow-ups 2.0 s median, 4.1 s worst.
  - In the window's own order (note, title, first question) the first question first re-read the call (16.6 s, nothing reused) because the title had its own prompt; the title bullet below shows the first question after that change.
- **The title keeps the meeting's prompt warm** (A8 v2 on A0): the title call sends the meeting's context as its system message. Measured in the window's order (note, title, first question) on gemma4:12b: title 1.0 s, first question 2.1 s with 26,904 of 27,417 prompt tokens reused (98%), against 16.6 s and 0 reused. Re-measured: the first-question target (about 2-3 s, at least 95% reused), on gemma4:12b (the default), by the bake-off in the window's order; the other targets were measured with the question right after the note, and qwen3.5:9b was not re-measured in the window's order. DECISIONS.md.
- **Final review fixes** (branch `ask-meetings`): a long call with no matching part answers "not discussed" without a model call and says so; the title prompt is `a8-v3` with the note as data; asking has its own 3-minute wait, room for thinking, a cut-prompt guard, and drops the oldest exchanges before reading parts; one pre-read at a time; Ask again hides when the same question was asked later; clearer missing-model text.
- **Checked in the real window** (`python -m evra run` on a test data folder holding only the synthetic 60-minute call, its note written by `python -m evra note`; the window driven through Windows UI Automation; captures of the Evra window only, looked at, then deleted): the Ask tab's intro and one-click questions; "Reading the meeting…" with everything that asks disabled; "What did they promise?" and "What did I promise?" answered in 5.6 s and 6.1 s; the typed follow-up "And when is it due?" read through the conversation and answered in 5.5 s with the owner's due dates (the postmortem by Friday among them). Each question reused about 27,000 of its 27,400–27,550 prompt tokens. Focus went back to the box and the thread scrolled to each answer. The log held five INFO lines with codes, counts and seconds, and no question or answer text.
- Tests: Python 614 passed (+125 on this branch), frontend 137 passed (+36).

## 2026-11-26 — UI polish (branch `ui-polish`)

- **Built:** a craft pass over the whole window, in the Steno pad world (DESIGN.md updated):
  - **Transcript:** time | speaker | words, with the speaker named once per turn in its own column, so wrapped lines line up. The detent now sits between turns, not on top of the time. While recording, a "Listening…" row waits below the last line.
  - **Tabs:** the underline draws out when a tab is chosen; arrow keys move between Note and Transcript.
  - **Motion:** buttons give a pixel when pressed; a meeting, Settings and the welcome fade up once when opened; the recording pips pulse. All of it is off under reduced motion.
  - **Wide windows:** content stops at a 66rem measure.
  - **Time tabs:** a lighter 1px outline.
  - **Welcome:** shows the Ctrl K and Ctrl , shortcuts.
- **Skills used:** taste-skill (its hover and press rules; the rest is for marketing sites); GSAP ScrollTrigger (read, not used: GSAP's licence is not on the allow list, and nothing in the window should move because it scrolled); HyperFrames makes videos, not app UI.
- Tests: frontend 101 (+4).

## 2026-11-11 — Small fixes (branch `small-fixes`)

- **Merged** `meeting-titles` (PR #9) into `main`; `evra titles` named the 6 older recordings that had a note.
- **Fixed a false "dropout":** when nothing was playing as Record was pressed, the first system audio after the start-up silence was logged as a 100 ms dropout, which failed the recording's health check and showed an "audio lost" hint. The first audio now always aligns as first audio. The timing-sensitive test that caught this race now runs on a manual clock, and it checks the slow-start promise it was written for.
- **The PC stays awake while recording:** `SetThreadExecutionState` on a thread of its own, from open devices to closed devices. The power manager confirmed the hold and its release.
- **The note model loads when Stop is pressed,** while the transcript drains: live, a cold call took 7.5 s and the same call after the load 0.5 s.
- **Not done here:** switching the microphone mid-recording. It needs a test with real devices, swapped during a live call.
- Tests: Python 494 (+16), frontend 97.

## 2026-11-11 — Meetings name themselves (branch `meeting-titles`)

- **Merged** `settings` (PR #8) into `main`.
- **Built:** once a meeting's note is written, the note's model names the meeting from that note (A8, prompt `a8-v1`), the way a chat app names a chat.
  - Only the placeholder "Recording <date> <time>" is replaced. A name the user gave always wins, even one typed while the model runs.
  - It runs after the note is shown and Record is back, so neither waits. The window gets `meeting.renamed` and updates the list and the header in place.
  - If the model fails, the placeholder stays, with no message.
  - `uv run evra titles` names older meetings that already have a note.
- **Checked live** with gemma4:12b and the app's defaults on the synthetic 1:1: the note in 37.1 s, then the title in 1.0 s: "Search migration results and project launch planning".
- Tests: Python 478 (+25), frontend 97 (+2); a live A8 test runs with `-m hardware`.

## 2026-11-10 — Settings, first set (branch `settings`)

- **Merged** `one-on-one-polish` (PR #6) and `ui-redesign` (PR #7) into `main`.
- **Research:** five angles run in parallel; notes and report are in `private/research/`.
  - Comparable apps: Granola, Jamie, Bluedot, Notion and Krisp; Otter, Fireflies, Fathom, tl;dv, Zoom and Teams; MacWhisper, Anarlog, Meetily and other local-first apps.
  - What users ask for and complain about.
  - Microsoft, Apple and NN/g guidance on settings screens and theme defaults.
  - Result: the most-requested settings belong to features Evra doesn't have yet, and the defaults people complain about (bots, auto-sharing) don't exist here.
- **Built:** Settings on the pad, opened from the foot of the rail or with `Ctrl ,`.
  - Theme: Light by default, Dark, or Match Windows (follows Windows' light or dark mode live), each shown as the window in miniature.
  - Note model: the models installed in Ollama, with the default marked "recommended".
    - Disabled, with the reason and Check again, while Ollama doesn't answer.
    - A pull hint when the chosen model isn't installed.
  - Meetings folder with Open folder, and About (the version; no accounts, no analytics).
  - Changes apply at once and survive a restart. Settings edited in the file meanwhile are kept.
  - The window opens in the saved theme with no flash: `#theme=dark`, and the dark pad as WebView2's background.
- **Checked in Edge** with the fake bridge: light, dark, Ollama quiet, model missing, 720×480 and keyboard focus.
- **Checked in the real window** at 150% scaling:
  - It opens light on a dark Windows.
  - With Ollama off, the reason shows; with it on, its 9 models are listed.
  - Choosing a model and Dark wrote `settings.toml`, and a restart opened dark with the model kept.
  - Open folder opened Explorer on the folder.
  - With Match Windows saved, the window opened at `#theme=system` and was dark from its first frame, matching this PC's dark Windows mode.
  - It also caught a bug: .NET's `Uri` turned `index.html?theme=dark` into `index.html%3Ftheme=dark`, so a dark window showed an error page. Fixed with a fragment, plus a test that uses .NET's own `Uri`.
- Tests: Python 453 (+18), frontend 95 (+17).

## 2026-11-10 — Main window redesign: "Steno pad" (branch `ui-redesign`)

- **Tools for UI work** installed at user scope (outside the repo): Impeccable, Taste Skill, GSAP skills, Playwright CLI, transitions.dev skills, designlang; React Bits is reachable as a shadcn registry (`frontend/components.json`).
- **Direction round:** `PRODUCT.md` written; Impeccable dealt a direction (Operate mode) plus catalog challengers; four first-viewport sketches built from the synthetic 1:1 fixture went on a local decision page (Steno pad, Mission transcript, Catalog sleeve, the category standard). The owner chose **Steno pad**; D19 replaced (DECISIONS).
- **Built** (`15a4b64` + fixes):
  - A chipboard rail holds the wordmark, the Record block (it turns red while recording, with the timer and both levels side by side), search (`Ctrl K`), meetings grouped by day, and the microphone.
  - The meeting header has a condensed title, a date line and a provenance stamp (model + points checked against the transcript), then the tabs with Copy as Markdown.
  - The note is a sheet: each point, a timed centre rule whose time tabs open the transcript at that line, and the quoted lines on the same row; it folds below 600px.
  - The transcript sits on the same rule, with a detent at each speaker turn; live lines land heavier and settle.
  - Note progress and failures are band rows on the sheet. A first-run welcome and a night version round it out.
- **Faces:** Libre Franklin and Sofia Sans Extra Condensed (OFL-1.1, Latin only) replace Inter and Newsreader. The built `index.html` is 390 kB and inlines both faces; loading it makes exactly one request, the page itself.
- **Checked** in Edge (WebView2's engine) with a fake bridge and synthetic data at 1100×720, 720×480 and 1600×900, in light and dark, across every state (note, hover, keyboard focus, `Ctrl K`, cited line, recording, writing, failure, empty, long title).
  - Impeccable detector: no findings.
  - Fresh finish reviewer: **fix**, with 7 material fixes (red only for recording, no label above a heading, a fixed tab-bar height, one reading size, focus that fills like hover, note states as bands, a tighter short-window rail), all applied. A verdict pass found one regression from the batch (the narrow stamp clipped at 720px); it was fixed, then **ship**.
- Frontend tests: 77 (Rail, meetings by day, `Ctrl K`, stamp, Copy as Markdown and its failure, sheet rows, missing cited lines, speaker-turn detents, live-only settle, note helpers, day labels). `DESIGN.md` + `.impeccable/design.json` written from the built window.
- **Checked in the real window** (`uv run evra run` on a separate test data folder, WebView2 at 150% display scaling). Two recordings went end to end: the owner's own one-minute recording, and a two-voice test call played through the speakers. Covered: live lines from both sides, both meters, Stop, the note being written, the stamp, a jump to a quoted line, Copy as Markdown from `file://`, rename, light and dark. Three fixes followed:
  - The tab underlines are now painted backgrounds. An inset shadow left a hairline beside the selected tab at 150% scaling.
  - Dates and times in a title never break at a hyphen. A default title had wrapped as `Recording 2026-` / `11-10 18:09`.
  - The window's own background is the pad colour for the Windows theme, not the old off-white that flashed in dark mode.
  - Tests: 78 frontend, plus 4 for the window background.

## 2026-11-07 — M3 finish: real-length 1:1s (branch `one-on-one-polish`)

- **60-minute test call:** `tools/make_long_fixture.py` has gemma4:12b write a synthetic 1:1 in 24 parts, with 13 facts planted word for word from minute 5 to 58 (the model said all of them itself). 840 lines, 9,616 words: about the density of the owner's real call (158 words a minute).
- **§9.5 1:1 timing measured:** the note for a 60-minute 1:1 is ready 58.5 s after the call from a cold model (35–39 s warm; loading gemma4:12b takes ~20 s); target ≤ 1.5 min. The prompt is 27,878 tokens of the 28,672 the model has room for: an hour of dense talk fits in one pass, about 65 minutes does not.
- **Note quality falls off with length.** Planted facts that reach a single-pass note: 15 min 1/2, 30 min 3/6, 45 min 2/8, 60 min 5–6/13. The model's citations stay accurate; the misses are facts it never wrote (an approved budget, a start date, a promotion deadline) and true points the checker drops. Long 1:1s need the per-window path (A2/A3).
- **Note prompt a1-v2:** a summary of one to three bullets that doesn't repeat the sections; one specific point per bullet with no "Topic:" label; decisions only when explicit; both lines cited for a question and its short answer. Bake-off: short fixture 15 kept / 0 dropped (v1 14/1), 10/10 facts; the 60-minute fixture keeps 73–81% of points (v1 58–62%). On the owner's 8 Oct call: a one-line summary and specific discussion points; sorting into decisions / action items / next time is still unreliable (BACKLOG).
- **Size check:** the estimate undercounted gemma4:12b's real prompt size by 23% on long calls; it now uses the measured 2.7 characters a token. The default budget is 28,000 (24,000 would refuse an hour-long 1:1 once the estimate is right), and a prompt larger than the model's room is refused before calling.
- **Capture log:** the stop line carries per-channel counts and levels (dropouts, overflows, dropped chunks, seconds, rms, share of the call with no system audio), so a not-OK recording can be explained afterwards.
- **Settings** save only values that differ from the defaults, so a new default reaches settings nobody changed.

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
- **HC3 with a real second person (owner, 2026-10-08), Bluetooth earbuds, from the window:** 2 min 44 s call; 53 lines (19 You, 34 Them) with no line duplicated across channels (overlaps are only short back-channel replies); drift 0.8 ms; note ready 37 s after Stop (gemma4:12b, 2,347 tokens in, 914 out), 10 points kept and 1 dropped; owners in the note ("You: …") match who spoke. Weak spots: the summary repeats the discussion section almost point for point; a tentative "maybe meet tomorrow" was filed as a decision; "For next time" stayed empty while a follow-up topic went to open questions; names still misheard. Capture health reported not-OK, but which problem (likely Bluetooth mic dropouts) is not in the log. **HC3 passed.**

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
