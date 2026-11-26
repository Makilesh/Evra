# Complete Notes (Plan B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the note complete: a meaning check next to the word check (L7), action items / decisions / open questions from focused calls kept as records (L4), long calls read in parts and combined (L3), and a notepad whose lines steer the note (L6).

**Architecture:** Builds on Plan A's shared meeting context (A0), public `Grounder` and task prompts. Embeddings come from Ollama (`qwen3-embedding:0.6b`, `/api/embed`) and rescue points the word check calls unsupported. The note job becomes a pipeline on one context: align the notepad → A1 (synthesis sections only) → A4/A5/A6 (each reusing the cached context) → one embedding batch per list → save the generation and its records in one transaction → `note.ready`. Calls longer than a measured length run A2 per ~10-minute window and A3 to combine; the digests' typed points become the records.

**Tech Stack:** Python 3.12 (uv, pydantic v2, sqlite3, difflib, structlog, stdlib HTTP to Ollama 0.34.4), React 19 + TypeScript + Tailwind v4 + Vitest.

**Spec:** `docs/superpowers/specs/2026-11-26-ask-notes-promises-design.md` (§3.5–3.8, §4.3, §4.5–4.7, §5, §6, §8). BUILD.md §7.1–7.7, §8.2–8.4, §9.1, Appendix A/B. Plan A (`docs/superpowers/plans/2026-11-26-ask-a-meeting.md`) for the names it produced.

## Global Constraints

- Everything in Plan A's Global Constraints, with the branch `notes-complete` (created from `ask-meetings` once Plan A is complete; `git push -u origin notes-complete` the first time).
- Embedding model: `qwen3-embedding:0.6b` through Ollama `POST /api/embed` with `{"model", "input": [texts], "truncate": true, "keep_alive"}`; response `embeddings: [[float]]`, plus `prompt_eval_count`. Vectors are L2-normalised by Evra (Ollama does not document normalised output). Qwen3-Embedding's query format, from its model card: `f"Instruct: {task}\nQuery:{text}"`; documents carry no instruction.
- No new Python or npm dependency (fuzzy matching uses `difflib.SequenceMatcher`).
- D16: the note appears once, complete — every stage finishes before `note.ready`.
- §8.3: one note or answer job at a time; inside a job the LLM calls run back to back and the embedding calls run after them, batched (so Ollama never swaps models mid-way).
- An embedding failure never fails a note or an answer: the check falls back to the word check and logs `semantic_check_skipped` with the error type.
- A note line, a note point, an item and the user's notes are content: never logged above DEBUG.

## Review Focus

1. **Embedding model not installed or `/api/embed` failing:** the note is still written with the word check only; the log says `semantic_check_skipped`. Test: Task 2 `test_semantic_failure_keeps_lexical_verdicts`, Task 4 `test_note_written_without_embeddings`.
2. **Rewriting a note** keeps an action item that was ticked Done as Done, and one dismissed as dismissed, when the new item matches the old. Test: Task 4 `test_status_survives_a_rewrite`.
3. **A1's JSON fails twice:** the note is built from the records when there are any (§9.1), and fails `invalid` only when there are none. Test: Task 4 `test_fallback_note_from_items`.
4. **Window cuts:** every utterance lands in at least one window; consecutive windows overlap by about 60 s at speaker turns; a tail shorter than 3 minutes joins the last window; a call within one window plus that tail is one window. Test: Task 5 `test_windows_cover_every_line`, `test_short_tail_joins_last_window`.
5. **Notepad edge cases:** blank lines are not saved as notes; a paste over 500 characters is context and is not aligned; lines are saved before Stop starts the note (no lost last line); a line's time never changes when it is edited later. Tests: Task 6 `test_blank_lines_are_dropped`, `test_long_paste_is_context`; Task 7 `flushes notes before stop`, `keeps the first typed time`.

---

### Task 1: Embeddings through Ollama

**Files:**
- Create: `src/evra/notes/semantic.py`
- Modify: `src/evra/llm/provider.py` (Protocol `embed`), `src/evra/llm/ollama.py` (`embed`), `src/evra/config.py` (`LlmSettings.embedding_model`), `tests/unit/notes/fakes.py` (`FakeProvider.embed`), `BUILD.md` (§2 D17 row: "(changed 2026-11-26, DECISIONS)"), `DECISIONS.md`
- Test: `tests/unit/llm/test_ollama.py`, `tests/unit/notes/test_semantic.py` (new), `tests/integration/test_ollama_live.py` (one `-m hardware` case)

**Interfaces:**
- Produces:
  ```python
  # LlmProvider (Protocol)
  def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]: ...
  # OllamaProvider.embed: self._ensure_local(model); [] for no texts without a request; one POST /api/embed;
  #   LlmError("Ollama sent a reply without embeddings") when the count differs; 404 -> LlmModelMissing; vectors unit length.
  # LlmSettings
  embedding_model: str = "qwen3-embedding:0.6b"
  # evra.notes.semantic
  SUPPORT_COSINE = 0.55            # Task 2 may raise it from its calibration
  QUERY_TASK = "Given a statement from meeting notes, retrieve the transcript lines that say it"
  def as_query(text: str, task: str = QUERY_TASK) -> str           # f"Instruct: {task}\nQuery:{text}"
  def cosine(a: Sequence[float], b: Sequence[float]) -> float     # dot product of unit vectors
  class Embedder:
      def __init__(self, provider: LlmProvider, model: str, *, batch: int = 64) -> None
      def vectors(self, texts: Sequence[str]) -> list[list[float]]   # input order; each distinct text embedded once per instance
  class SemanticCheck:
      def __init__(self, embedder: Embedder, threshold: float = SUPPORT_COSINE) -> None
      threshold: float
      def similarities(self, pairs: Sequence[tuple[str, str]]) -> list[float]  # (claim, source): cosine(as_query(claim), source)
  ```
  `FakeProvider.embed` returns deterministic unit vectors (a bag-of-words hash into 64 dimensions, normalised), so shared words give a higher cosine; it records the texts.
- [ ] **Step 1: Pull and check the model:** `ollama pull qwen3-embedding:0.6b`; `ollama show qwen3-embedding:0.6b --license` (expect Apache-2.0, as on the Hugging Face card `Qwen/Qwen3-Embedding-0.6B`); note size and dimension (one `/api/embed` call). If the licence is not Apache-2.0, stop and report BLOCKED.
- [ ] **Step 2: Write the failing tests:** `test_embed_posts_inputs_and_normalises` (fake http returns `[[3, 4]]` → `[[0.6, 0.8]]`; request body has `input` list and `truncate: true`), `test_embed_refuses_cloud_models`, `test_embed_count_mismatch_is_an_error`, `test_embed_nothing_makes_no_request`; `test_semantic.py`: `test_embedder_batches_and_caches` (130 texts with 10 repeats → 2 calls with 64 + 56 distinct texts... exact: distinct texts split in batches of 64), `test_query_format` (`as_query("x") == "Instruct: Given a statement from meeting notes, retrieve the transcript lines that say it\nQuery:x"`), `test_similarities_pair_order`; the hardware test embeds two sentences and checks unit length.
- [ ] **Step 3:** run → FAIL; implement; run → PASS.
- [ ] **Step 4:** DECISIONS.md "D17 changed: embeddings through Ollama (2026-11-26)": context (no torch worker before M4; Ollama already manages VRAM and is the one local model server), evidence (model tag, size, licence, dimension, the `/api/embed` fields), decision, consequences (the torch worker still comes with M4; pyannote stays there).
- [ ] **Step 5:** `uv run python tools/check.py` → PASS. Commit `feat(llm): embeddings through Ollama (qwen3-embedding)` and push.

---

### Task 2: Meaning check in the Grounder, calibrated

**Files:**
- Create: `tools/calibrate_semantic.py`
- Modify: `src/evra/notes/validate.py` (`Grounder(..., semantic=None)`, `check_all`, `check_note(..., semantic=None)`, `CheckedNote.rescued`), `src/evra/notes/semantic.py` (`SUPPORT_COSINE` from the calibration), `src/evra/notes/writer.py` (passes the check through; logs `rescued`), `src/evra/notes/ask.py` (answers use `check_all` with the check), `DECISIONS.md`
- Test: `tests/unit/notes/test_validate.py`, `tests/unit/notes/test_writer.py`, `tests/unit/notes/test_ask.py`

**Interfaces:**
- Consumes: Task 1 (`SemanticCheck`).
- Produces: `Grounder.check_all(bullets: Sequence[NoteBullet]) -> list[tuple[CheckedBullet | None, str]]`. Order of checks per bullet is today's: citations → word overlap → numbers and names (with the nearby-line borrowing). A bullet whose citations are valid but whose word overlap is below 0.2 is a candidate; after the pass, when a check is set and there are candidates, one `similarities` call scores `(claim text, cited source text)` for all of them; a candidate at or above `threshold` continues to the numbers-and-names check, the rest stay `unsupported`. `check()` stays the single-bullet form (no semantic step). `CheckedNote.rescued: int = 0` counts bullets kept by the meaning check. `similarities` raising `LlmError` → log `semantic_check_skipped` (error type) and keep the word-check verdicts.
- `tools/calibrate_semantic.py MODEL`: for both note fixtures, writes the note with the check off, then embeds: (a) each kept bullet against its cited text ("supported"), (b) each kept bullet against 3 random lines that are neither cited nor within 3 lines of a cited one (seeded `random.Random(7)`; "mismatched"), (c) each `unsupported` bullet against its cited text. Prints p5/p50/p95 per group, the share of mismatched pairs at or above 0.55, 0.60, 0.65, 0.70 and 0.75, and lists group (c) with its cosine and cited text (synthetic fixtures only).
- [ ] **Step 1: Write the failing tests:** `test_meaning_check_rescues_a_paraphrase` (a bullet with < 20% shared words whose FakeProvider cosine is ≥ threshold is kept; `rescued == 1`), `test_rescued_bullet_still_needs_its_numbers` (paraphrase with a number not in the cited text → `number_not_cited`), `test_meaning_check_is_one_batch` (three candidates → one `embed` call path, i.e. one `similarities` call), `test_semantic_failure_keeps_lexical_verdicts`, `test_check_note_without_semantic_is_unchanged`.
- [ ] **Step 2:** run → FAIL; implement; run → PASS.
- [ ] **Step 3: Calibrate** with Ollama running: `uv run python tools/calibrate_semantic.py gemma4:12b`, output to `private/scratch/plan-b/calibrate.txt`. Rule: the threshold is the smallest of 0.55, 0.60, 0.65, 0.70, 0.75 at which at most 2% of mismatched pairs pass; set `SUPPORT_COSINE` to it. Read group (c): say in the DECISIONS entry how many dropped points the threshold would rescue and whether they are true (judge against the fixture).
- [ ] **Step 4:** DECISIONS.md "Meaning check threshold (2026-11-26)" with the table; `uv run python tools/check.py` → PASS. Commit `feat(notes): keep paraphrased points the transcript supports (meaning check)` and push.

---

### Task 3: Focused extraction (A4–A6)

**Files:**
- Create: `src/evra/llm/prompts/a4_actions.md`, `a5_decisions.md`, `a6_questions.md`, `src/evra/notes/extract.py`
- Modify: `src/evra/llm/schemas.py` (Appendix B: `ActionItem`, `ActionItems`, `Decision`, `Decisions`, `OpenQuestion`, `OpenQuestions`, each `extra="ignore"`)
- Test: `tests/unit/notes/test_extract.py`, `tests/unit/llm/test_schemas_and_prompts.py`

**Interfaces:**
- Consumes: `MeetingContext`, `Grounder` (+ `check_all`), `load_part`, A9 repair as in `writer.py`.
- Produces:
  ```python
  ItemKind = Literal["action_item", "decision", "open_question"]
  MIN_CONFIDENCE = 0.5
  @dataclass(frozen=True)
  class CheckedItem:
      kind: ItemKind; text: str; citations: tuple[str, ...]
      owner: str | None; due: str | None; confidence: float | None
  @dataclass(frozen=True)
  class Extraction:
      items: tuple[CheckedItem, ...]; dropped: int; drop_reasons: Mapping[str, int]
      prompt_versions: tuple[str, ...]; tokens_in: int; tokens_out: int; cached_tokens: int; seconds: float
      failed_kinds: tuple[ItemKind, ...]
  def normalise_owner(owner: str | None, *, names: Mapping[str, str] = {}) -> str | None
      # "you"/"me"/"i"/"owner" (any case) -> "You"; "them"/"they" -> "Them";
      # a value of `names` (label -> display name, case-insensitive) -> its label; anything else -> None
  def extract_items(provider: LlmProvider, *, model: str, context: MeetingContext, settings: LlmSettings, grounder: Grounder, kinds: Sequence[ItemKind] = ("action_item", "decision", "open_question")) -> Extraction
  ```
  One call per kind, in that order, each with `system=context.system` and the task part as the user message, so Ollama reuses the context. A9 repair once; a kind still invalid goes to `failed_kinds` and the others are kept. Every item goes through `grounder.check_all` (text + citations); action items below `MIN_CONFIDENCE` drop with reason `low_confidence`; an owner that `normalise_owner` cannot place becomes `None` (§7.5.5). Decisions keep `made_by` and questions `raised_by` as `owner`. Items of one kind that repeat (difflib ratio ≥ 0.9 on lowercased text, or a shared citation) are kept once.
- Prompt texts (exact; each file has a version line `a4-v1` / `a5-v1` / `a6-v1` and one `## Prompt` section):

````markdown
List the action items in the meeting above: specific tasks someone agreed to do or was asked to do.

Rules:
1. Each item has: text (an imperative under 20 words, without the owner: "Send the vendor quote"), owner ("You", "Them", or null when it is unclear who took it on), due (as it was said, for example "by Friday", or null), confidence (0 to 1), and citations: the lines where it was asked for and where it was accepted (u:<id>), or user for the user's notes.
2. The owner is the person who accepted the task or was given it, not the person who asked for it.
3. Include items in the user's notes marked "TODO", "->", "AI:" or similar.
4. Leave out vague intentions ("we should think about…") unless someone committed to them, and anything already done during the call.
5. List each item once. Return only JSON matching the ActionItems schema.

The ActionItems schema:
{schema}
````

````markdown
List the decisions made in the meeting above: explicit agreements, approvals or choices between options.

Rules:
1. Each decision has: statement (under 25 words), made_by ("You", "Them", or null when both agreed or it is unclear), and citations: the lines where it was agreed (u:<id>).
2. A proposal, a suggestion or a tentative plan ("maybe", "we could", "let's see") is not a decision.
3. List each decision once. Return only JSON matching the Decisions schema.

The Decisions schema:
{schema}
````

````markdown
List the questions raised in the meeting above that were not answered by the end of it, and the user's notes containing "?" that the transcript does not answer.

Rules:
1. Each question has: question (under 25 words), raised_by ("You", "Them", or null), and citations: the lines where it was raised (u:<id>), and user for the user's notes.
2. Leave out questions answered later in the meeting, rhetorical questions and small talk ("How are you?").
3. A topic someone wants to pick up next time is not an open question.
4. Return only JSON matching the OpenQuestions schema.

The OpenQuestions schema:
{schema}
````

- [ ] **Step 1: Write the failing tests:** `test_three_calls_share_the_context` (three calls; every system message equals `context.system`), `test_owner_is_normalised` (`"me"` → `"You"`, `"Priya"` with `names={"Them": "Priya"}` → `"Them"`, `"Dana"` → `None`), `test_low_confidence_is_dropped`, `test_unsupported_item_is_dropped`, `test_failed_kind_keeps_the_others` (decisions invalid twice → `failed_kinds == ("decision",)`, action items kept), `test_repeated_items_kept_once`.
- [ ] **Step 2:** run → FAIL; implement; run → PASS.
- [ ] **Step 3:** `uv run python tools/check.py` → PASS. Commit `feat(notes): focused extraction of action items, decisions and open questions (A4–A6)` and push.

---

### Task 4: Records, the note pipeline and Done boxes

**Files:**
- Create: `src/evra/store/migrations/0003_items.sql`, `src/evra/store/speakers.py`, `src/evra/store/items.py`
- Modify: `src/evra/notes/templates/__init__.py` (`TemplateSection.source: Literal["synthesis", "extraction"] = "synthesis"`, `Template.synthesis_sections()`), `src/evra/notes/templates/one_on_one.yaml` and `general.yaml` (`source: extraction` on `decisions`, `action_items`, `open_questions`), `src/evra/llm/prompts/a1_note.md` (v4: the template shown lists only synthesis sections; add rule "Leave decisions, action items and open questions out: they are listed separately."), `src/evra/notes/prompt_input.py`, `src/evra/notes/writer.py`, `src/evra/notes/job.py` (`write_and_save` pipeline), `src/evra/store/notes.py` (`save_generation(..., items=())` in the same transaction), `src/evra/services/meetings.py` (stage events), `src/evra/services/views.py` (extraction sections from records), `src/evra/bridge/api.py` (`set_item_status`), `frontend/src/bridge.ts`, `frontend/src/useEvra.ts`, `frontend/src/components/NoteView.tsx`, `frontend/src/components/PointRow.tsx`, `frontend/src/note.ts` (Markdown `- [x]` / `- [ ]`), `frontend/src/strings.ts`
- Test: `tests/unit/test_items_store.py`, `tests/unit/test_speakers_store.py`, `tests/unit/notes/test_job.py`, `tests/unit/services/test_views.py`, `tests/unit/test_bridge.py`, `frontend/src/components/NoteView.test.tsx`, `frontend/src/note.test.ts`

**Interfaces:**
- Consumes: Task 3 (`extract_items`, `CheckedItem`, `Extraction`), Task 2 (`check_all` with the meaning check), Plan A (`build_context`).
- Produces:
  - `0003_items.sql`: `ALTER TABLE action_item ADD COLUMN status_changed_at INTEGER;` and `CREATE INDEX action_item_status ON action_item(status, meeting_id);` (status values: `open`, `done`, `dismissed`).
  - `SpeakerStore(conn).one_on_one(meeting_id) -> OneOnOne(you: str, them: str)`: speaker ids, created on first use: one owner `person` (display name "You", `is_owner` 1) for the whole database, a `room` speaker labelled "You" linked to it and a `remote` speaker labelled "Them" (`source` "mode").
  - `ItemStore(conn)`: `save(*, meeting_id: str, generation_id: str, items: Sequence[CheckedItem]) -> None` (inside the caller's transaction; owner label → speaker id via `one_on_one`; an item matching one of the meeting's previous items of the same kind — difflib ratio ≥ 0.9 on lowercased text, or a shared citation — takes its `status`); `for_generation(generation_id) -> list[StoredItem]`; `set_status(item_id: str, status: str) -> bool` (only `open`/`done`/`dismissed`, stamps `status_changed_at`); `StoredItem(id, kind, text, owner, due, citations, status)`.
  - Pipeline in `write_and_save` (signature unchanged plus `semantic: SemanticCheck | None = None` and `on_stage: Callable[[str], None] = lambda s: None`): one context; A1 over synthesis sections (`on_stage("writing")`); `extract_items` (`on_stage("items")`); the meaning check batches; save generation + items together. A1 `NoteInvalid` with at least one item → save a note of the items only (prompt version without the A1 part, e.g. `a0-v1+a4-v1+a5-v1+a6-v1`); no items → raise. `NothingSupported` only when the note and the items keep nothing.
  - `MeetingService` passes a `SemanticCheck` built from `settings.llm.embedding_model` and emits `note.stage` with stage `items` between `writing` and ready.
  - `note_view`: sections in template order; an extraction section's blocks come from the generation's items: text `"{owner}: {text}"` when there is an owner, plus `" ({due})"` when there is a due date; each such block carries `item: {"id", "kind", "status", "owner", "due"}`. Dismissed items are left out.
  - `BridgeApi.set_item_status(item_id: str, status: str) -> {"ok": bool}`; TS `NoteBlock.item?: {id: string; kind: "action_item" | "decision" | "open_question"; status: "open" | "done" | "dismissed"; owner: string | null; due: string | null}`; `useEvra.setItemStatus(id, status)` updates the open note at once and reverts if the call fails.
  - NoteView: an action item row has a checkbox in its point cell (`aria-label={strings.markDone(text)}`), ticked when done, with the text struck through in muted ink when done. `strings.stages.items = "Listing action items…"`; `strings.markDone = (text) => \`Done: ${text}\``.
- [ ] **Step 1: Write the failing tests:** `test_speakers_created_once`, `test_items_saved_with_the_generation`, `test_status_survives_a_rewrite`, `test_set_status_only_known_values`, `test_pipeline_runs_note_then_items` (FakeProvider replies: A1, A4, A5, A6; stages `writing`, `items`), `test_fallback_note_from_items`, `test_note_written_without_embeddings` (embed raises → note saved), `test_note_view_items_carry_status`; Vitest `ticks an action item done`, `copies done items as checked`.
- [ ] **Step 2:** run → FAIL; implement; run → PASS.
- [ ] **Step 3:** Re-run the note bake-off (`uv run python tools/bakeoff_notes.py gemma4:12b --runs 2`, output to `private/scratch/plan-b/bakeoff-a1-v4.txt`); extend the tool to count items and report the planted commitments that reached an action item (a fact counts when its keywords are all in one item). If coverage of the synthesis sections fell below Plan A's numbers, find out why before going on.
- [ ] **Step 4:** `uv run python tools/check.py` → PASS. Commit `feat(notes): action items, decisions and open questions as records, with Done boxes` and push.

---

### Task 5: Long calls in parts (A2/A3)

**Files:**
- Create: `src/evra/notes/windows.py`, `src/evra/notes/mapreduce.py`, `src/evra/llm/prompts/a2_digest.md`, `src/evra/llm/prompts/a3_combine.md`
- Modify: `src/evra/llm/schemas.py` (`WindowPoint`, `WindowDigest` per Appendix B), `src/evra/notes/context.py` (`build_context(..., note: str | None = None)`: the text placed before the transcript lines; the excerpt note stays the default when `only` is given and `note` is None), `src/evra/notes/job.py` (path choice), `src/evra/config.py` (`LlmSettings.single_pass_minutes`), `src/evra/services/meetings.py` (stages), `tools/bakeoff_notes.py` (`--path single|windows|auto`, `--minutes 15,30,45,60` cuts of the 60-minute fixture, counting the facts planted before the cut), `frontend/src/strings.ts`
- Test: `tests/unit/notes/test_windows.py`, `tests/unit/notes/test_mapreduce.py`, `tests/unit/notes/test_job.py`

**Interfaces:**
- Produces:
  ```python
  WINDOW_MS, OVERLAP_MS, MIN_TAIL_MS = 600_000, 60_000, 180_000
  @dataclass(frozen=True) class Window: index: int; start_ms: int; end_ms: int; ids: tuple[str, ...]
  def split_windows(utterances: Sequence[Utterance]) -> list[Window]
  def choose_path(*, utterances: Sequence[Utterance], prompt_tokens: int, settings: LlmSettings) -> Literal["single", "windows"]
  def write_long_note(provider: LlmProvider, *, model: str, meeting: Mapping[str, Any], utterances: Sequence[Utterance], template: Template, settings: LlmSettings, grounder: Grounder, user_notes: str, on_stage: Callable[[str], None]) -> tuple[NoteResult, Extraction]
  ```
  - `split_windows`: utterances in time order. When the call spans at most `WINDOW_MS + MIN_TAIL_MS`, one window. Otherwise a window runs from its first utterance to the last utterance starting before `first.start_ms + WINDOW_MS`, extended to the end of that speaker's turn (following utterances on the same channel). When what is left spans less than `MIN_TAIL_MS`, the window takes it all and the split ends. The next window starts at the first utterance starting at or after `window.end_ms - OVERLAP_MS`, moved back to the first utterance of its speaker turn, but never at or before the previous window's first utterance.
  - `choose_path`: `windows` when the call is longer than `settings.single_pass_minutes` or the single-pass prompt estimate exceeds the budget; else `single`.
  - `write_long_note`: per window, a context with `only=window.ids` and `note=f"This is part {i} of {n} of the meeting ({start}–{end}); … marks lines left out.\n"`, then A2 (`on_stage(f"part:{i}:{n}")`); then A3 (`on_stage("combining")`) on a context with no lines and the note `"This meeting is long: its parts are summarised in <digests> below; the lines themselves are not shown.\n"`, with the digests as JSON. Digest points become items: `commitment` → action item (owner, due), `decision` → decision, `question` → open question, each checked by the Grounder and merged across windows (same kind and difflib ≥ 0.9, or a shared citation: keep the earliest, join citations).
  - `LlmSettings.single_pass_minutes: int` — the default comes from Step 4.
  - Strings: `strings.stages` handles `part:i:n` → `Reading part ${i} of ${n}…` and `combining` → `Putting the note together…`.
- A2 (`a2-v1`), exact text:

````markdown
Summarise this part of the meeting for a later step that combines every part into one note.

Rules:
1. Return points of these kinds: "topic" (what was discussed, one per topic), "point" (a specific thing said: a fact, number, date, update, problem or piece of feedback), "decision" (explicitly agreed), "commitment" (a task someone accepted or was given; owner "You" or "Them", due as it was said, else null) and "question" (raised and not answered in this part).
2. Each point is under 30 words, specific (who, what, when; numbers exactly as said) and cites the lines it came from (u:<id>), or user for the user's notes.
3. supports_notes lists the user's notes (n:<id>) this part supports.
4. Return only JSON matching the WindowDigest schema, with window_index {window_index}.

The WindowDigest schema:
{schema}
````
- A3 (`a3-v1`): the A1 v4 task text with its first line replaced by `Write the note for the meeting above from the summaries of its parts in <digests>. Citations inside the digests are valid: copy them through.`, and `<digests>\n{digests}\n</digests>` before the template block.
- [ ] **Step 1: Write the failing tests:** `test_short_call_is_one_window`, `test_windows_cover_every_line`, `test_windows_overlap_at_turns`, `test_short_tail_joins_last_window`, `test_choose_path`, `test_long_note_parts_then_combine` (FakeProvider: two A2 replies and one A3 reply; stages `part:1:2`, `part:2:2`, `combining`), `test_digest_items_merge_across_windows`.
- [ ] **Step 2:** run → FAIL; implement; run → PASS.
- [ ] **Step 3: Measure:** `uv run python tools/bakeoff_notes.py gemma4:12b --runs 2 --minutes 15,30,45,60 --path single` and the same with `--path windows`; output to `private/scratch/plan-b/bakeoff-windows.txt`. Record coverage and seconds per cut and path.
- [ ] **Step 4: Set `single_pass_minutes`:** the longest cut at which single-pass coverage is at least the windows path's in both runs (15 when windows win from 30 on). Record the table and the total time of a 60-minute note on each path in DECISIONS.md "Long calls: single pass up to N minutes, then parts (A2/A3)", against §9.5's 1.5-minute target; if the windows path is slower than the target, say so and add the BACKLOG item "digest windows while recording".
- [ ] **Step 5:** `uv run python tools/check.py` → PASS. Commit `feat(notes): read long calls in parts and combine them (A2/A3)` and push.

---

### Task 6: Notepad lines, alignment and the notes in the prompts

**Files:**
- Create: `src/evra/store/notepad.py`, `src/evra/notes/align.py`, `src/evra/notes/user_notes.py`
- Modify: `src/evra/bridge/api.py` (`save_notes`), `src/evra/services/views.py` (`meeting_detail(...)["notes"]`), `src/evra/notes/job.py` (align before the note; user notes into the context and the Grounder), `src/evra/notes/ask.py` (questions see the notes too), `src/evra/services/meetings.py` (stage `linking` when there are notes)
- Test: `tests/unit/test_notepad_store.py`, `tests/unit/notes/test_align.py`, `tests/unit/notes/test_user_notes.py`, `tests/unit/test_bridge.py`, `tests/unit/notes/test_job.py`

**Interfaces:**
- Produces:
  ```python
  # evra.store.notepad
  MAX_LINES, MAX_LINE_CHARS, CONTEXT_CHARS = 2000, 4000, 500
  @dataclass(frozen=True) class LineIn: id: str; text: str; captured_at: int | None; pasted: bool   # captured_at: epoch ms
  @dataclass(frozen=True) class NoteLine: id: str; position: int; text: str; captured_at_ms: int | None; phase: Literal["before", "during", "after"]; is_context: bool; aligned: tuple[tuple[str, float], ...]
  class NotepadStore:
      def replace(self, meeting_id: str, lines: Sequence[LineIn]) -> list[NoteLine]
      def lines(self, meeting_id: str) -> list[NoteLine]
      def set_alignment(self, meeting_id: str, aligned: Mapping[str, Sequence[tuple[str, float]]]) -> None
  # evra.notes.align  (BUILD.md §7.2)
  W_TIME, W_LEX, W_SEM, MIN_SCORE, MAX_PER_LINE = 0.4, 0.3, 0.3, 0.35, 5
  BEFORE_S, AFTER_S, PEAK_S, SPREAD_S = 90, 30, 15, 30
  ALIGN_TASK = "Given a note typed during a meeting, retrieve the transcript lines it was written about"
  def align(lines: Sequence[NoteLine], utterances: Sequence[Utterance], *, embedder: Embedder | None = None) -> dict[str, list[tuple[str, float]]]
  # evra.notes.user_notes
  def format_user_notes(lines: Sequence[NoteLine], aliases: Mapping[str, str]) -> str   # NONE when no lines
  def notes_text(lines: Sequence[NoteLine]) -> str                                      # the Grounder's user_notes
  ```
  - `replace`: drops lines whose text is blank; keeps a line's first `captured_at_ms` across saves (a later save never changes it); `captured_at_ms = captured_at - meeting.started_at` (None when `captured_at` is None); phase `during` when captured while the meeting had no `ended_at` or before it, `after` otherwise, `before` only for a time before `started_at`; `is_context` when `pasted` and the text is longer than `CONTEXT_CHARS`; ids match `[A-Za-z0-9-]{1,64}`; more than `MAX_LINES` lines or a line over `MAX_LINE_CHARS` → `ValueError`.
  - `align`: only `during` lines that are not context. Candidates: utterances whose `end_ms` lies in `[T − 90 s, T + 30 s]` (T = `captured_at_ms`); `dt = T − u.end` in seconds; `w_time = exp(−((dt − 15) / 30) ** 2)`; `w_lex` = BM25 (`notes/bm25.py`) of the line's tokens over the candidates, divided by the best candidate's score (0 when that is 0); `w_sem = max(0, cosine(as_query(line, ALIGN_TASK), utterance))`; score `0.4·w_time + 0.3·w_lex + 0.3·w_sem`, or `(0.4·w_time + 0.3·w_lex) / 0.7` without an embedder or when embedding fails. Keep score ≥ 0.35, best 5.
  - `format_user_notes`: one line per note in position order: `[n:{k}] ({mm:ss} | before | after) {text} || aligned: {u:aliases}` (k from 1; the aligned part left out when empty); context lines `[n:{k}] (context) {text}`; text through `as_data` and one line.
  - `BridgeApi.save_notes(meeting_id: str, lines: list) -> {"ok": bool}`: every entry a dict with string `id`, string `text`, `captured_at` int or null, `pasted` bool, else `{"ok": False}`.
- [ ] **Step 1: Write the failing tests:** `test_blank_lines_are_dropped`, `test_long_paste_is_context`, `test_first_capture_time_is_kept`, `test_phase_from_meeting_times`, `test_limits_raise`; `test_align_prefers_the_line_heard_just_before`, `test_align_uses_words_and_meaning`, `test_align_without_embeddings_reweights`, `test_context_lines_are_not_aligned`; `test_format_user_notes`; `test_save_notes_refuses_bad_shapes`; `test_job_aligns_then_writes_with_notes` (the A1 prompt's `<user_notes>` holds the formatted lines; `[user]` citations survive the check).
- [ ] **Step 2:** run → FAIL; implement; run → PASS.
- [ ] **Step 3:** Make `tests/fixtures/notes/one_on_one_60min_notes.json` (synthetic, committed): 12 note lines typed at plausible times after planted facts of the 60-minute fixture, each with the fixture utterance indices it is about. Add `tools/eval_alignment.py` (precision and recall at the kept threshold, time for the whole set) and run it with and without embeddings; record both in DECISIONS.md "Notepad alignment weights" against §7.2's acceptance (precision ≥ 0.80 at recall ≥ 0.60; < 5 s).
- [ ] **Step 4:** `uv run python tools/check.py` → PASS. Commit `feat(notes): the notepad's lines are aligned to the transcript and steer the note` and push.

---

### Task 7: My notes tab

**Files:**
- Create: `frontend/src/components/NotepadView.tsx`, `frontend/src/components/NotepadView.test.tsx`
- Modify: `frontend/src/bridge.ts` (`NoteLine`, `MeetingDetail.notes`, `save_notes`), `frontend/src/useEvra.ts` (notes per open meeting, saving 400 ms after the last change, flush before `stop_recording` and when the meeting changes), `frontend/src/components/MeetingView.tsx` (tabs Note | Transcript | Ask | My notes; My notes opens by default while live), `frontend/src/components/NoteView.tsx` / `PointRow.tsx` (a `user` citation shows the quote "From your notes" with the note's text), `frontend/src/strings.ts`, `DESIGN.md` (Components: My notes)
- Test: `NotepadView.test.tsx`, `MeetingView.test.tsx`, `useEvra.test.tsx`

**Interfaces:**
- TS: `interface NoteLine { id: string; text: string; captured_at: number | null; pasted: boolean; captured_ms?: number | null; aligned?: { utterance_id: string; start_ms: number }[] }`; `EvraApi.save_notes(meetingId: string, lines: { id: string; text: string; captured_at: number | null; pasted: boolean }[]): Promise<OkReply>`; `useEvra` adds `editNotes(meetingId, lines)` and `flushNotes(): Promise<void>`.
- UI: one row per line on the rule: an auto-growing textarea in the point cell (15px), the typed time as a time tab on the rule once the line has one (it jumps to the transcript at that time), and — after the note is written — the aligned transcript lines in the quotes cell. Enter adds a line below and moves to it; Backspace in an empty line removes it and moves to the end of the previous one; ArrowUp on a textarea's first line and ArrowDown on its last move between lines. A line gets `captured_at = Date.now()` the first time it gains non-blank text and keeps it. A paste longer than 500 characters marks the line `pasted`. While live, a strip under the pad shows the last two transcript lines and "Listening…". Empty: one empty line focused, with the placeholder `strings.notesPlaceholder`.
- Strings: `notesTab: "My notes"`, `notesPlaceholder: "Type a note. Each line is stamped with the time you wrote it."`, `notesSaveFailed: "Couldn't save your notes. They stay here; Evra tries again as you type."`, `stages.linking: "Linking your notes…"`, `fromYourNotes: "From your notes"`.
- [ ] **Step 1: Write the failing tests:** `adds a line on Enter`, `removes an empty line on Backspace`, `keeps the first typed time`, `marks a long paste`, `saves 400 ms after typing` (fake timers), `flushes notes before stop`, `opens My notes while live`, `shows the aligned lines after the note`.
- [ ] **Step 2:** run → FAIL; implement; run → PASS.
- [ ] **Step 3:** Look at it in Edge with the fake bridge (light, dark, 1100×720, 720×480, keyboard only) and against DESIGN.md; fix what is off.
- [ ] **Step 4:** `uv run python tools/check.py` → PASS. Commit `feat(ui): a My notes tab that stamps each line with its time` and push.

---

### Task 8: Measure the whole note, check the real window, write it down

**Files:**
- Modify: `BUILD.md` (§2 D17, §7.2–7.6, §8.2, §8.4, §9.1, Appendix A: A1 v4, A2, A3, A4–A6 as shipped; Appendix B), `DECISIONS.md`, `PROGRESS.md`, `BACKLOG.md`, `README.md` (pull `qwen3-embedding:0.6b` in setup)
- [ ] **Step 1: Measure** (Ollama running): the note bake-off on both fixtures, auto path, 2 runs: kept, dropped, rescued, coverage, items found for the planted commitments, total seconds from the first call to the saved note; the 60-minute call on each path. Output to `private/scratch/plan-b/bakeoff-final.txt`. Record against §9.5 (1:1 note after 60 min ≤ 1.5 min) and §7.8 (citation validity ≥ 97%).
- [ ] **Step 2: Real window:** build the UI; in a test data folder, load the 60-minute fixture as a meeting and write its note from the window; tick an action item Done, rewrite the note, see it stay Done; open My notes on a short live recording (talk for a minute, type two lines, Stop) and check the note cites `[user]` where it should. Capture only the Evra window, look, delete the capture. Confirm no note, item or note-line text reaches the INFO log.
- [ ] **Step 3: Docs:** the BUILD.md sections above, DECISIONS entries not yet written ("Extraction sorts, synthesis writes", "Fuzzy matching with difflib"), PROGRESS entry with hashes and numbers, BACKLOG (A7 topics and key moments; a "before" agenda pad per person; digest windows while recording if Step 1 missed the target).
- [ ] **Step 4:** `uv run python tools/check.py` → PASS. Commit `docs: complete notes — measurements, BUILD.md and decisions` and push.
