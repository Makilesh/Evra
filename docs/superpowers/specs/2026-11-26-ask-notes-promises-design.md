# Ask a meeting, complete notes, open promises — design (2026-11-26)

Owner request (26 Nov 2026): build the seven changes L1–L7 from the "how Evra uses its language
model" review, in the best way possible. This document is the spec the three implementation
plans argue from. BUILD.md stays the source of truth: each plan updates the BUILD.md sections it
changes, and every deviation gets a DECISIONS.md entry.

## 1. Why

Today the local model does one job: after Stop it reads the whole call once and writes the note
(A1), then names the meeting (A8). Measured on the committed synthetic 60-minute 1:1 (13 planted
facts), the single-pass note keeps 5–6 of the 13 facts, and recall falls with length (15 min 1/2,
30 min 3/6, 45 min 2/8). Asked about each fact directly, the same model (gemma4:12b, whole
transcript in the prompt, JSON schema, temperature 0) answered 13/13 and said "not discussed" for
all 3 topics the call never mentions; follow-up questions took 1–2 s because Ollama reuses the
prompt it has already read. A note has to choose what to keep; a question tells the model what to
look for. Evra should offer both, and the 1:1 use case wants the promises made in the call kept as
records, not only as note text.

## 2. What changes for the owner

| Code | Change | Where it shows |
| --- | --- | --- |
| L1 | Evra refuses any model Ollama would run in its cloud | Settings never offers one; a note or answer with one fails with a plain reason |
| L2 | **Ask this meeting**: typed questions and one-click questions, answered from the transcript as cited points | An **Ask** tab on every finished meeting |
| L3 | Long calls are read in ~10-minute parts, then combined (A2/A3) | The note of a long call keeps more; no one-hour ceiling |
| L4 | Action items, decisions and open questions are extracted by focused calls (A4–A6) and kept as records | Those note sections come from the records; action items get a Done box |
| L5 | Open promises across meetings, people, and a prep brief before the next 1:1 | **Promises** and **People** pages in the rail |
| L6 | A notepad during the call; its lines steer the note | A **My notes** tab, open by default while recording |
| L7 | A meaning check next to the word check (Qwen3-Embedding) | Fewer true points dropped; notes align to the transcript |

## 3. Decisions (made for the owner; each gets a DECISIONS.md entry)

1. **Order.** This work runs before M4 (speakers). The 1:1 path needs no diarization, and the
   research found promises and continuity matter more in 1:1s than voiceprints. M4 is unchanged.
2. **One shared meeting context (A0).** Every call about one meeting (note, extraction, asking)
   sends the same system message: data rules, then the transcript, gaps, the user's notes and the
   meeting's metadata, in that order. The task (A1, A4–A6, A12) is the user message. Ollama keeps
   the processed prompt between calls, so the second and later calls about a meeting read only
   their task text. The transcript comes first because it never changes once the call ends; the
   title (renamed by A8 right after the note) and the user's notes come after it, so changing them
   costs only the tail. Every call uses the same `num_ctx`, so the loaded model is never reloaded.
3. **Asking is per meeting in Phase 1.** Questions across meetings need search (Phase 2) and a
   fixed plan → read-only lookups → answer flow; they stay in the backlog. Asking during a
   recording is Evra Live (Phase 3) and is refused for now.
4. **Answers go through the note's checker.** An answer is one to four points, each with
   citations; the same grounding (§7.5) keeps or drops each point. A question the meeting does not
   answer says so; an answer whose every point fails the check is not shown.
5. **Long calls.** A note is single-pass when the call fits the budget and is shorter than a
   measured length (Plan B sets it from recall at 30/45/60 minutes); otherwise map-reduce (A2 per
   window, A3 combine). Asking a call that does not fit reads only the windows that best match
   the question (BM25, plus embeddings once L7 lands) and says so.
6. **Extraction sorts, synthesis writes.** A1 keeps the summary, discussion and "for next time";
   decisions, action items and open questions come from the focused calls A4–A6 and are stored as
   records (BUILD.md §8.2 tables). In map-reduce mode the window digests carry the same kinds and
   are merged (dedupe at ratio ≥ 0.9 with the standard library's `difflib`, or overlapping
   citations; no new dependency). If A1's JSON fails after its repair, the note is built from the
   extraction records (§9.1's plain fallback).
7. **Embeddings through Ollama (changes D17).** `qwen3-embedding:0.6b` (Apache-2.0, 639 MB, Q8_0)
   served by Ollama's `/api/embed`, instead of a torch worker: no torch dependency yet, Ollama
   already manages VRAM, the same loopback-only client. Vectors are L2-normalised client-side
   (Ollama does not document normalised output). The torch worker still arrives with M4.
8. **People without voiceprints.** In 1:1 mode each meeting gets two speaker rows (room "You",
   remote "Them"); "who was this with" links the remote speaker to a `person`. M4's identity work
   later fills the same rows from voiceprints.
9. **Keep-alive.** Notes keep Ollama's 30 s keep-alive. Asking uses 5 minutes, so follow-ups stay
   fast while the owner reads; opening the Ask tab pre-reads the meeting in the background.

## 4. Architecture

### 4.1 Cloud guard (L1)
`OllamaProvider` refuses a model before any chat, load or embed call when its name's tag is
`cloud` or ends in `-cloud`, or when Ollama's `/api/tags` lists it with `remote_host` or
`remote_model` (fields verified in Ollama's `api/types.go`). `installed_models()` never returns
such a model. The failure code is `cloud_model`. README tells users that `OLLAMA_NO_CLOUD=1`
turns off Ollama's cloud features server-wide.

### 4.2 Prompt shape
- `a0_context.md` (new, A0): the shared system message.
- Task prompts are single-part files (`## Prompt`) loaded with `load_part`: A1 v3 (note), A12
  (ask), later A2, A3, A4–A6, A13. A8 and A9 keep their System/User files.
- `generation.prompt_version` and `question.prompt_version` record `a0-v1+a1-v3` and so on.

### 4.3 Grounding
`notes/validate.py` exposes one `Grounder` (aliases, utterance text, user notes) used by the note,
the answers and the extracted items. Plan B adds the semantic rescue (cosine ≥ 0.55 per §7.5, or
the threshold the calibration measures) for points the word check calls unsupported. Numbers and
names must still appear in the cited lines.

### 4.4 Asking (L2)
- Prompt: A0 + A12 with the last three exchanges of this meeting as `<conversation>` and the
  question (made inert) as `<question>`. Schema `MeetingAnswer {found, points: NoteBullet[≤4]}`.
- States: `asking`, `answered`, `not_found`, `unchecked` (every point failed the check), `failed`
  (reason code). Stored in a `question` table; a row left `asking` by a closed app becomes
  `failed` / `interrupted` at the next start.
- One question at a time; refused while a recording is loading, running or stopping.
- The bridge returns at once; the answer arrives as a `question.updated` event.
- `evra ask "QUESTION" [--meeting-id ID] [--model M]` for the console.

### 4.5 Extraction and records (L4, Plan B)
A4 action items (owner You / Them / null, due as said, confidence), A5 decisions, A6 open
questions, each validated by the Grounder and the owner rule (§7.5.5). Items below confidence 0.5
are dropped (recorded). Records carry the generation id; when a note is rewritten, a new item that
matches an old one keeps its Done or Dismissed status.

### 4.6 Map-reduce (L3, Plan B)
Windows of about 10 minutes, cut at speaker turns, with 60 s of overlap; prompt aliases stay
global (`u:1…u:N` over the whole call) so citations and the nearby-line rule keep working. A2
gives a `WindowDigest` per window; A3 combines digests into the `NoteDraft`; digest points of kind
decision / commitment / question become the records after the merge. The note view shows "Reading
part 2 of 6…" while it runs.

### 4.7 Notepad and alignment (L6, Plan B)
Lines typed in **My notes** are saved 400 ms after the last keystroke as `note_block` rows with
`captured_at_ms` (first non-blank text while recording; never changed) and a phase. After Stop,
`notes/align.py` scores each line against the utterances that end in `[T − 90 s, T + 30 s]`:
`0.4·w_time + 0.3·w_lex + 0.3·w_sem` (§7.2, BM25 k1 = 1.5, b = 0.75; without embeddings the
weights become 4/7 and 3/7), keeping score ≥ 0.35, at most 5. The lines go into A0's
`<user_notes>` with their aligned utterance ids.

### 4.8 People, promises and the prep brief (L5, Plan C)
- **With:** the meeting header names who the 1:1 was with (find-or-create a person); the
  transcript and quotes then show that name instead of "Them".
- **Promises:** every open action item across meetings, split into "You promised" and "They
  promised", each with its meeting, person, due date, a Done box, "Not a promise" and a time tab
  that opens the line.
- **Prep brief:** a person's page shows the open promises both ways, what was left for next time
  and still-open questions from their last 1:1, and an optional "Catch me up" brief (A13, cited
  to the meetings it came from, checked like every other point).

## 5. Data (migrations, forward only)
- `0002_questions.sql` (Plan A): `question(id, meeting_id → meeting ON DELETE CASCADE, asked_at,
  text, state, answer_json, reason, excerpt, llm_model, prompt_version, transcript_version_id,
  tokens_in, tokens_out, dropped_claims, seconds)` + index on (meeting_id, asked_at).
- Plan B: item status timestamps and carried status for `action_item`; `note_block` is used as
  specified in §8.2.
- Plan C: `brief(id, person_id → person ON DELETE CASCADE, created_at, points_json, meetings_json,
  llm_model, prompt_version)`.

## 6. UI (DESIGN.md, Steno pad)
- **Ask tab:** each question is a heading row on the timed rule; its points are note rows (point |
  time tabs | quotes). Thinking is a band row with the progress rule; "Not discussed in this
  meeting" is a band row; a failure is a band-deep row with the reason and Ask again. One-click
  questions are band-filled buttons above a well-style input; Enter asks.
- **My notes:** one line per row on the rule, each with the time it was typed as a tab; a two-line
  live strip under it while recording.
- **Promises / People:** rail links above the meetings, styled like the Settings link; pages on the
  pad with rows on the rule.
- No new colours, no shadows, red only for recording, two text sizes, caps only for names.

## 7. Phasing

| Plan | Branch | Contents |
| --- | --- | --- |
| A | `ask-meetings` (from `ui-polish` + `small-fixes`) | checks via `python -m`; L1; A0 + A1 v3; Grounder; L2 backend, Ask tab, `evra ask`, bake-off tool, docs |
| B | `notes-complete` (from A) | L7 embeddings; L4 extraction + records; L3 map-reduce; L6 notepad + alignment; docs |
| C | `promises` (from B) | L5 people, promises page, prep brief; docs |

Plans B and C are written when the plan before them is done, from what its measurements showed.

## 8. Measurement and acceptance
- **A1 v3** must not be worse than v2 on the bake-off (gemma4:12b, both fixtures, 2 runs): short
  fixture ≥ 14 kept with 10/10 facts; 60-minute fixture validity within 5 points of v2 and facts ≥
  v2's lower run. Otherwise A1 keeps v2's order and only asking uses A0.
- **Asking** (new `tools/bakeoff_ask.py`, 60-minute fixture, 13 fact questions + 3 absent topics):
  ≥ 12/13 correct, 3/3 "not discussed", ≥ 11/13 answers passing the checker, follow-ups ≤ 3 s
  median warm; the first question right after the note reuses the note's prompt (Ollama reports
  only the new tokens).
- Plan B: recall gain of map-reduce at 30/45/60 minutes; action items found for the planted
  commitments; the cosine threshold separates true from mismatched pairs on the fixtures; a
  60-minute note's total time recorded against §9.5's 1.5 minutes.

## 9. Non-goals (BACKLOG)
Questions across meetings; asking during a recording; keeping an answer in the note (Q3); A7
topics and key moments; a "before" agenda pad per person; calendar-driven prep; voiceprints (M4).

## 10. Risks
- The A0 order may change note quality: measured before it is kept (§8).
- Ollama may evict the note model to load the embedding model on a 12 GB GPU: embeddings run in
  one batch after the LLM calls, and the live check records VRAM.
- Prompt caching is Ollama behaviour, not an API promise: everything stays correct without it,
  only slower.
