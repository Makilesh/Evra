# Phase 1 · Main window redesign: Steno pad — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the "Quiet paper" look (D19) with the owner's chosen "Steno pad" world across the whole main window, without changing what the window does.

**Architecture:**
- Frontend only. The Python bridge, events and `useEvra` state stay as they are; components are rebuilt in the new vocabulary and two small pure modules (`format.ts`, `note.ts`) carry the new logic.
- The note becomes a three-column sheet (point | timed centre rule | the quoted lines it came from) that folds to two columns below 600px of sheet width (CSS container query).
- The top bar goes away: recording, search, meetings and the microphone live in a chipboard rail on the left.

**Tech Stack:** React 19 + TypeScript 6 + Tailwind 4 + Vite 8 (single-file build), Vitest + Testing Library; `@fontsource-variable/libre-franklin` 5.3.0 and `@fontsource-variable/sofia-sans-extra-condensed` 5.3.0 (both OFL-1.1) replace Inter and Newsreader.

**Spec:** the direction contract in `.impeccable/surfaces/frontend-src-app-tsx.md` (owner chose it 2026-11-10 from four sketches; the chosen sketch is the composition to match), `PRODUCT.md`, `BUILD.md` §8.4, D16.

## Global Constraints

- Everything in the M3c plan's Global Constraints still applies (strict TS, oxlint, every string in `strings.ts`, every control named, text rendered as text, D22/D23, licence gate after npm changes).
- Tokens (light): pad `#E7EFDB`, band `#D6E4C6`, chip `#D3C8B3`, chip-edge `#BDB19A`, chip-well `#E2D9C8`, chip-ink `#5A5041`, ink `#1B2433`, muted `#536052`, rule `#2E6B4B`, you `#23407A`, them `#4A473C`, rec `#E0352B`. Dark tokens are derived in Task 1 and must keep every text pair ≥ 4.5:1.
- White text never sits on `#E0352B` (4.4:1); a red area that carries text uses a darker `rec-fill` (≥ 4.5:1).
- Faces: Sofia Sans Extra Condensed (caps, titles, heads, speakers, time tabs); Libre Franklin (everything else). One reading size for note points, quotes and transcript lines (15px); only the meeting title steps up.
- No label or kicker above a heading; no Unicode glyphs as icons (authored SVG, one stroke weight); no coloured border-left > 1px.
- Show only shortcuts that work: `Ctrl K` (focuses meeting search, added here) yes; `Ctrl Alt R` no (M6 hotkeys).
- Motion grammar "land and settle", and nothing else: a live transcript line lands at weight 640 and settles to 400; a cited line lands in deep band and settles to band. Both off under `prefers-reduced-motion`. Level meters move with `transform`, never `width`.
- Keep every existing accessible name the tests rely on (`Record`, `Stop`, `Loading…`, `Stopping…`, `Writing note…`, `Microphone`, `Recording time`, `You`, `Them`, `Search meetings`, `Note`, `Transcript`, `Rename meeting`, `Meeting title`, `Jump to MM:SS in the transcript`, `Write note`, `Retry`, `Dismiss`, `Capture notes`).
- Window sizes to verify: 1100×720 (default), 720×480 (minimum), 1600×900; light and dark.

## Review Focus

1. **A citation whose line is missing from the transcript** (stale id): the point still shows, with no quote and no crash. → Task 2 `noteQuotes skips unknown and repeated lines`, Task 5 `shows a point whose cited line is gone`.
2. **The clipboard is unavailable or refuses** (WebView2 without focus, older runtime): Copy falls back, and says "Couldn't copy" when both ways fail. → Task 4 `says when the note could not be copied`.
3. **The minimum window (720×480)**: the sheet folds, nothing overlaps or clips, the rail list scrolls. → Task 7 screenshots at 720×480.
4. **A recording running while another meeting is open**: the rail keeps the timer and Stop; only the live meeting's transcript grows; its list item says Recording. → existing App and `useEvra` tests, Task 3 `shows Stop, the time and both levels while recording`.
5. **Opening an old meeting's transcript** must not play the live-line animation on every line. → Task 6 `marks only lines that arrive while live as fresh`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `frontend/package.json` | swap the two font packages |
| `frontend/src/main.tsx` | import the latin variable fonts |
| `frontend/src/index.css` | tokens (light/dark), theme mapping, base, browser surfaces (selection, caret, scrollbars, focus), keyframes, reduced motion |
| `frontend/src/format.ts` | + `formatTime`, `dayLabel`, `meetingLine` |
| `frontend/src/note.ts` | new: `noteQuotes`, `pointCount`, `noteToMarkdown` |
| `frontend/src/strings.ts` | new copy for the rail, stamp, sheet, copy states, empty states |
| `frontend/src/components/icons.tsx` | new: authored SVG icons (pencil, close, copy, check, chevron, search) |
| `frontend/src/components/Rail.tsx` | new, replaces `TopBar.tsx`: wordmark, record block, start error, meetings, microphone |
| `frontend/src/components/LevelMeter.tsx` | restyled meter (transform fill) |
| `frontend/src/components/Banner.tsx` | filled notice block with SVG close |
| `frontend/src/components/MeetingList.tsx` | search with `Ctrl K`, meetings grouped by day |
| `frontend/src/components/MeetingView.tsx` | title + date line, stamp, capture notes, tabs, Copy as Markdown |
| `frontend/src/components/Stamp.tsx` | new: the provenance stamp |
| `frontend/src/components/NoteView.tsx` | the sheet, note progress (D16), failure, empty |
| `frontend/src/components/TranscriptView.tsx` | lines on the rule, detents at speaker turns, live settle |
| `frontend/src/App.tsx` | rail + pad shell, welcome when there are no meetings |
| tests beside each file | `Rail.test.tsx` replaces `TopBar.test.tsx`; `note.test.ts` new |

---

### Task 1: Tokens, faces and browser surfaces

**Files:** Modify `frontend/package.json`, `frontend/src/main.tsx`, `frontend/src/index.css`; register `THIRD_PARTY_LICENSES.md`.

**Produces:** Tailwind colours `pad band band-deep chip chip-edge chip-well chip-ink ink muted rule you them rec rec-fill rec-tint`, fonts `font-sans` (Libre Franklin Variable) and `font-display` (Sofia Sans Extra Condensed Variable), keyframes `settle` and `land`.

- [ ] **Step 1:** `npm --prefix frontend install @fontsource-variable/libre-franklin@5.3.0 @fontsource-variable/sofia-sans-extra-condensed@5.3.0` and uninstall `@fontsource/inter @fontsource/newsreader`; import only the latin `wght` files in `main.tsx`.
- [ ] **Step 2:** Write the tokens and base layer in `index.css` (dark tokens under `.dark`); theme `::selection`, `caret-color`, scrollbars, `:focus-visible`; `tabular-nums` on times; `@media (prefers-reduced-motion: reduce)` turns `settle`/`land` off.
- [ ] **Step 3:** `uv run python tools/license_gate.py --write-register` → PASS, register lists both faces as OFL-1.1.

### Task 2: Times, days and note helpers

**Files:** Modify `frontend/src/format.ts`, `frontend/src/format.test.ts`; create `frontend/src/note.ts`, `frontend/src/note.test.ts`.

**Produces:**
- `formatTime(epochMs: number): string` → `"14:02"`
- `dayLabel(epochMs: number, now: number): string` → `"Today"`, `"Yesterday"`, else `"Mon 3 Nov"`
- `meetingLine(m: MeetingSummary): string` → `"Mon 10 Nov · 14:02 · 4 min"`
- `noteQuotes(block: NoteBlock, byId: Map<string, Utterance>): Utterance[]` (cited lines in citation order, unknown ids skipped, repeats once)
- `pointCount(note: Note): number`
- `noteToMarkdown(title: string, line: string, note: Note): string`

- [ ] **Step 1: Tests** — `dayLabel` gives Today / Yesterday / `Mon 3 Nov` across midnight; `noteQuotes skips unknown and repeated lines`; `pointCount` counts blocks in every section; `noteToMarkdown` gives `# Title`, the line, `## Summary`, `- text (01:05)` and skips empty sections.
- [ ] **Step 2:** Run `npm --prefix frontend run test -- format note` → FAIL (missing exports).
- [ ] **Step 3:** Implement. Dates in `en-GB` (`weekday: "short", day: "numeric", month: "short"`).
- [ ] **Step 4:** Run again → PASS.

### Task 3: The rail

**Files:** Create `frontend/src/components/Rail.tsx`, `frontend/src/components/Rail.test.tsx`, `frontend/src/components/icons.tsx`; modify `LevelMeter.tsx`, `Banner.tsx`, `strings.ts`; delete `TopBar.tsx`, `TopBar.test.tsx`.

**Interfaces:**
- `Rail` props = the old `TopBar` props plus `children: ReactNode` (the meeting list, placed between the record block and the microphone).
- Icons: `PencilIcon`, `CloseIcon`, `CopyIcon`, `CheckIcon`, `ChevronIcon`, `SearchIcon`, each `(props: SVGProps<SVGSVGElement>) => JSX.Element`, 16px, stroke 1.75, `aria-hidden`.

- [ ] **Step 1: Tests** — port every `TopBar.test.tsx` case to `Rail` unchanged in intent, plus `shows the app name and that everything stays on this PC`.
- [ ] **Step 2:** Run → FAIL (no `Rail`).
- [ ] **Step 3:** Implement. Idle: ink button with a red dot, "Record". Recording: the block fills `rec-fill`; the timer (`aria-label="Recording time"`) and a pad-coloured "Stop" button sit inside; the two meters under it. Busy: disabled ink button with the phase label. Start error: `Banner` under the block. Microphone at the rail's foot.
- [ ] **Step 4:** Run → PASS.

### Task 4: Meetings by day, and the meeting header

**Files:** Modify `MeetingList.tsx`, `MeetingList.test.tsx`, `MeetingView.tsx`, `MeetingView.test.tsx`; create `Stamp.tsx`.

**Interfaces:** `MeetingList` gains `writingIds: string[]` and `now?: () => number`; `MeetingView` keeps its props (Markdown uses `detail`); `Stamp({ model, points }: { model: string; points: number })`.

- [ ] **Step 1: Tests** — `groups meetings under Today, Yesterday and their date`; `Ctrl K focuses the search`; `says Writing note… for a meeting whose note is being written`; `shows where and how the note was written` (stamp: "Written on this PC", `gemma4:12b`, "2 points checked against the transcript"); `copies the note as Markdown` (mock `navigator.clipboard.writeText`, then the button reads "Copied"); `says when the note could not be copied`; the Transcript tab's name stays "Transcript" with its line count hidden from the name.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Title is the `h1` (condensed, balanced, two lines at most), the date line under it, the stamp top right (wraps under the title when narrow), capture notes under the date line, tabs on a 2px ink rule with Copy at its end (Note tab, note present).
- [ ] **Step 4:** Run → PASS.

### Task 5: The note sheet

**Files:** Modify `NoteView.tsx`, `NoteView.test.tsx`.

**Interfaces:** `NoteView` gains `utterances: Utterance[]`.

- [ ] **Step 1: Tests** — `puts each point beside the lines it came from` (row holds the point, its time tab and the quoted line); existing jump, progress, failure, write cases; `shows a point whose cited line is gone`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. One `<section>` per non-empty section with its `h2`; one `<li>` row per point; the time tabs sit on the rule and keep their names; quotes are `<q>` with a caps speaker; rows fill `band` on hover and focus-within. Progress (D16) is a `role="status"` panel; failure is the `Banner`.
- [ ] **Step 4:** Run → PASS.

### Task 6: The transcript on the rule

**Files:** Modify `TranscriptView.tsx`, `TranscriptView.test.tsx`.

- [ ] **Step 1: Tests** — existing cases; `marks a detent where the speaker changes` (`data-turn` on the first line of each turn; the speaker name stays readable on every line); `marks only lines that arrive while live as fresh` (`data-fresh` on lines added after mount when `follow`, none on an old meeting).
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. Time on the rule for every line; detent square and speaker caps at each turn (screen-reader speaker on continuation lines); highlighted line lands in `band-deep` and settles to `band`.
- [ ] **Step 4:** Run → PASS.

### Task 7: The window, checked by eye

**Files:** Modify `App.tsx`, `App.test.tsx`.

- [ ] **Step 1:** Shell: rail + pad grid; welcome composition when there are no meetings; bridge-down notice on the pad. Update `App.test.tsx` for the new structure, keeping every behaviour it checks.
- [ ] **Step 2:** `npm --prefix frontend run lint`, `typecheck`, `test` → all PASS.
- [ ] **Step 3:** With `npm --prefix frontend run dev` and a fake bridge injected by `page.addInitScript` (synthetic fixture `tests/fixtures/notes/one_on_one_synthetic.json`), capture in Edge at 1100×720, 720×480 and 1600×900, light and dark: note, transcript with a cited line, recording, writing, failure, empty. Screenshots go to `.impeccable/review/` (git-ignored).
- [ ] **Step 4:** `impeccable detect --json` on `frontend/src`; fix mechanical findings.
- [ ] **Step 5:** Finish review (fresh `impeccable-finish-reviewer`) with the contract, screenshots and the chosen sketch; one fix batch; verdict.
- [ ] **Step 6:** `npm --prefix frontend run build`, then the built `index.html` in Edge with the same fake bridge: fonts render from the file, no network requests.

### Task 8: Record it

**Files:** `DECISIONS.md`, `BUILD.md` (§2 D19 row, §8.5, M6 row), `PRODUCT.md`, `DESIGN.md` + `.impeccable/design.json` (documenter), `PROGRESS.md`, `BACKLOG.md`, `THIRD_PARTY_LICENSES.md`.

- [ ] **Step 1:** DECISIONS entry "D19 replaced: Steno pad" (context, evidence: the four-sketch round, decision, consequences).
- [ ] **Step 2:** Documenter writes `DESIGN.md` and `.impeccable/design.json` from the built window.
- [ ] **Step 3:** `uv run python tools/check.py` → no `FAIL`; Conventional Commits; `git push` on `ui-redesign`.
