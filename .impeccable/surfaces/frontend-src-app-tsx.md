---
version: 1
slug: "frontend-src-app-tsx"
primary_target: "frontend/src/App.tsx"
related_targets: ["frontend/src/components"]
---

Mode: Operate. Surface: Evra's main window (pywebview/WebView2, 1100×720 default, 720×480 minimum).

Scope: the whole main window: rail (record, search, meetings by day, microphone), meeting header, Note and Transcript tabs, note sheet, live transcript, note progress and failures, empty states, light and dark.

Audience and job: the owner on daily 1:1 calls first, then developers and anyone who wants private notes. Record a call, watch it transcribe, get a note whose every point can be checked against what was said, copy it out.

## Direction contract

THESIS: Every note point sits beside the words it came from. The sheet refuses the category default (a summary card with tiny timestamp chips you must click to trust) and joins each point to its quote across one timed centre rule, so checking a note takes a glance.

OWN-WORLD: A reporter's steno pad: pale green pad (#E7EFDB), darker green bands for state, tan chipboard rail (#D3C8B3) owning the left edge, deep green rule (#2E6B4B) for structure, navy ink. Sofia Sans Extra Condensed caps for titles, heads and speakers; Libre Franklin at one reading size for all text. Colour fills whole areas, never thin outlines; red only for recording.

STORY: The owner presses Record, watches lines land, presses Stop; the note arrives once, they check any point by reading its quote on the same row, then copy it as Markdown. A developer trusts it because the stamp says where and how it was written.

FIRST VIEWPORT: 264px chipboard rail: wordmark, full-width ink Record button with red dot, search well (Ctrl K), meetings grouped by day, the selected one merging into the pad, microphone at the foot. Right: the pad: condensed title (~56px), date line beneath, provenance stamp top right, Note/Transcript tabs on a heavy ink rule with Copy as Markdown at its end, then THE NOTE | timed centre rule | WHERE IT CAME FROM. Under 600px of sheet the quotes fold beneath each point.

FORM: Steno pad, 3rd of 7 on my list, assigned by the roll. Raises kept: one reading size (timetable); rule from the real layout, detents at speaker changes (centre rail); provenance as one mark (annual); colour as area (garden map); a live line lands heavier and settles (specimen). Signature interaction: hover or focus a point and its whole row fills band green; a time tab opens the transcript at that line, filled the same. seed:69e0e32cb6b181a2

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

## Unresolved

- Per-meeting talk rhythm glyphs in the rail need a bridge field (not in list_meetings today).
- The time a note was written is not in the note view; the stamp shows model and checked points only.
