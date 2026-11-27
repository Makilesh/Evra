---
name: Evra
description: Local-first meeting notes for Windows, laid out as a reporter's steno pad.
colors:
  pad: "#e7efdb"
  band: "#d6e4c6"
  band-deep: "#c2d8ae"
  chip: "#d3c8b3"
  chip-edge: "#bdb19a"
  chip-well: "#e2d9c8"
  chip-ink: "#5a5041"
  ink: "#1b2433"
  muted: "#536052"
  rule: "#2e6b4b"
  rule-ink: "#24563c"
  you: "#23407a"
  them: "#7a4a1e"
  rec: "#e0352b"
  rec-fill: "#b42a21"
  on-rec: "#fff7f2"
typography:
  display:
    fontFamily: "Sofia Sans Extra Condensed Variable, Arial Narrow, sans-serif"
    fontSize: "clamp(2.25rem, 4.6vw, 3.75rem)"
    fontWeight: 800
    lineHeight: 0.95
  wordmark:
    fontFamily: "Sofia Sans Extra Condensed Variable, Arial Narrow, sans-serif"
    fontSize: "30px"
    fontWeight: 800
    lineHeight: 1
  timer:
    fontFamily: "Sofia Sans Extra Condensed Variable, Arial Narrow, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: "32px"
    fontFeature: "tnum"
  caps-head:
    fontFamily: "Sofia Sans Extra Condensed Variable, Arial Narrow, sans-serif"
    fontSize: "15px"
    fontWeight: 700
    lineHeight: "18px"
    letterSpacing: "0.05em"
  caps-speaker:
    fontFamily: "Sofia Sans Extra Condensed Variable, Arial Narrow, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    letterSpacing: "0.05em"
  caps-label:
    fontFamily: "Sofia Sans Extra Condensed Variable, Arial Narrow, sans-serif"
    fontSize: "13px"
    fontWeight: 700
    lineHeight: "16px"
    letterSpacing: "0.05em"
  time-tab:
    fontFamily: "Sofia Sans Extra Condensed Variable, Arial Narrow, sans-serif"
    fontSize: "14px"
    fontWeight: 700
    lineHeight: "18px"
    letterSpacing: "0.03em"
    fontFeature: "tnum"
  body:
    fontFamily: "Libre Franklin Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: "23px"
  body-strong:
    fontFamily: "Libre Franklin Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: "23px"
  meta:
    fontFamily: "Libre Franklin Variable, Segoe UI, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 500
    lineHeight: "18px"
    fontFeature: "tnum"
rounded:
  tab: "4px"
  stamp: "7px"
  control: "8px"
  well: "10px"
  block: "11px"
spacing:
  rail-w: "264px"
  rail-w-narrow: "232px"
  rail-inset: "18px"
  gutter: "44px"
  gutter-narrow: "24px"
  tab-gap: "28px"
  pad-top: "30px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.pad}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.control}"
    padding: "8px 16px"
  record-button:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.pad}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.block}"
    padding: "0 16px"
    height: "48px"
  record-button-writing:
    backgroundColor: "{colors.rule}"
    textColor: "{colors.pad}"
  recording-block:
    backgroundColor: "{colors.rec-fill}"
    textColor: "{colors.on-rec}"
    rounded: "{rounded.block}"
    padding: "12px"
  stop-button:
    backgroundColor: "{colors.on-rec}"
    textColor: "{colors.rec-fill}"
    typography: "{typography.body-strong}"
    rounded: "{rounded.control}"
    padding: "0 16px"
    height: "36px"
  copy-button:
    backgroundColor: "{colors.band}"
    textColor: "{colors.ink}"
    typography: "{typography.meta}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  copy-button-hover:
    backgroundColor: "{colors.band-deep}"
  search-well:
    backgroundColor: "{colors.chip-well}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.well}"
    height: "40px"
  meeting-item:
    textColor: "{colors.ink}"
    typography: "{typography.body-strong}"
    padding: "9px 18px 9px 6px"
  meeting-item-hover:
    backgroundColor: "{colors.chip-well}"
  meeting-item-selected:
    backgroundColor: "{colors.pad}"
  tab:
    textColor: "{colors.muted}"
    typography: "{typography.body-strong}"
    height: "42px"
  tab-selected:
    textColor: "{colors.ink}"
  time-tab:
    backgroundColor: "{colors.pad}"
    textColor: "{colors.rule}"
    typography: "{typography.time-tab}"
    rounded: "{rounded.tab}"
    padding: "2px 7px"
  time-tab-hover:
    backgroundColor: "{colors.rule}"
    textColor: "{colors.pad}"
  point-row-hover:
    backgroundColor: "{colors.band}"
    rounded: "{rounded.control}"
  done-box:
    textColor: "{colors.pad}"
    rounded: "{rounded.tab}"
    height: "16px"
  done-box-ticked:
    backgroundColor: "{colors.rule}"
    textColor: "{colors.pad}"
  notes-quote-label:
    textColor: "{colors.you}"
    typography: "{typography.caps-speaker}"
  notepad-line:
    textColor: "{colors.ink}"
    typography: "{typography.body}"
  notepad-row-typing:
    backgroundColor: "{colors.band}"
    rounded: "{rounded.control}"
  note-writing-row:
    backgroundColor: "{colors.band}"
    rounded: "{rounded.control}"
  note-failed-row:
    backgroundColor: "{colors.band-deep}"
    rounded: "{rounded.control}"
  ask-question:
    textColor: "{colors.ink}"
    typography: "{typography.body-strong}"
  ask-state-row:
    backgroundColor: "{colors.band}"
    rounded: "{rounded.control}"
  ask-failed-row:
    backgroundColor: "{colors.band-deep}"
    rounded: "{rounded.control}"
  ask-suggestion:
    backgroundColor: "{colors.band}"
    textColor: "{colors.ink}"
    typography: "{typography.meta}"
    rounded: "{rounded.control}"
    padding: "6px 12px"
  ask-suggestion-hover:
    backgroundColor: "{colors.band-deep}"
  ask-input:
    backgroundColor: "{colors.band}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    rounded: "{rounded.well}"
    height: "40px"
  banner:
    backgroundColor: "{colors.band-deep}"
    textColor: "{colors.ink}"
    rounded: "{rounded.well}"
    padding: "12px 16px"
  stamp:
    textColor: "{colors.rule}"
    rounded: "{rounded.stamp}"
    padding: "9px 13px 8px"
  settings-row:
    textColor: "{colors.rule}"
    typography: "{typography.caps-head}"
  theme-option-chosen:
    backgroundColor: "{colors.band-deep}"
    rounded: "14px"
  rail-settings-current:
    backgroundColor: "{colors.chip-well}"
    textColor: "{colors.ink}"
    rounded: "{rounded.well}"
---

# Design System: Evra

## Overview

**Creative North Star: "The Steno Pad"**

Evra's main window is a reporter's steno pad. A pale green pad holds the open meeting; a tan chipboard rail owns the left edge with the record control, the meetings by day and the microphone; one deep green rule runs down the middle of the note and the transcript, with the point on one side and the words it came from on the other. Navy ink carries the text. Checking a note takes a glance, because every point and its quote share a row across that rule.

The system is flat and quiet. Colour is laid down as whole areas: a darker green band fills a row when it is hovered, focused, being written or has failed; the selected meeting takes the pad's own colour and merges into it; recording turns the record block red. Type is two faces doing two jobs: condensed capitals for titles, section heads, speakers and labels, and one plain sans for everything that is read. Motion is short and purposeful: what just arrived lands emphasised and settles, a button gives a pixel when pressed, and a meeting comes in once from just below.

The world runs in light and dark. Light is the default; Dark, or Match Windows (which follows Windows' app mode), is chosen in Settings. At night the pad goes almost black-green, the chipboard goes brown, the rule and ink brighten; the roles and structure do not change.

**Key Characteristics:**
- A chipboard rail (264px) beside a pale green pad, no other panels.
- One timed centre rule (2px, rule green) drawn row by row, with square detents at section heads and speaker changes.
- State shown as filled areas in band greens, never as outlines.
- Red only while recording.
- Condensed uppercase display face for structure; Libre Franklin at 15px for reading and 13px for metadata.
- Provenance as one rotated rubber-stamp mark.

## Colors

A paper-and-board palette: two greens of pad, a tan board, a deep green rule, navy ink, two speaker inks and one red kept for recording. Every token has a dark-mode value (in the sidecar) under the same name.

### Primary
- **Steno Rule Green** (rule): the structural colour. Draws the centre rule, the detents, the time tabs, the stamp, the focus ring, the caret, the thin scrollbar and the record button while a note is being written. Section heads on the note sheet are set in it.
- **Deep Rule Green** (rule-ink): the same green a step darker, for the caps titles of the writing, reading and failed rows where they sit on a band fill.

### Secondary
- **Recording Red** (rec): the dot on the Record button and the live pip beside a meeting in the rail.
- **Recording Fill** (rec-fill): the whole record block while a call is being recorded, with the Stop button's text.
- **Warm White** (on-rec): text, level meters and the Stop button on the red block.

### Tertiary
- **Navy Speaker Ink** (you): the owner's speaker name in quotes and the transcript, and "From your notes" before a quote of the owner's own line.
- **Umber Speaker Ink** (them): the other side's speaker name.

### Neutral
- **Steno Pad** (pad): the main surface, the selected meeting in the rail, the background of time tabs and transcript times so they sit on the rule.
- **Pad Band** (band): row fill for hover and focus on note points, the highlighted transcript line, the writing row, the Copy button, the title being edited, the line being typed in My notes; on the Ask tab the input, the one-click questions and the reading, not-discussed and unchecked rows.
- **Deep Band** (band-deep): stronger fill for the failed-note row and a failed question, notices (banners), text selection, Copy and one-click hover, and the first frame of a landing line.
- **Chipboard** (chip): the rail.
- **Chipboard Edge** (chip-edge): the 1px line where the rail meets the pad and above the microphone.
- **Chipboard Well** (chip-well): wells cut into the rail (search, microphone) and meeting hover.
- **Chipboard Ink** (chip-ink): secondary text on the rail (claim, day heads, times, placeholder, icons).
- **Navy Ink** (ink): all primary text, the heavy rule under the tabs, primary buttons.
- **Muted Green-Grey** (muted): metadata, unselected tabs, quotes at rest, transcript times.

### Named Rules
**The Red Is Recording Rule.** Red appears only for recording: the Record dot, the red record block with its meters, and the live pip in the rail. Errors and failures are not red; they fill with Deep Band.

**The Colour As Area Rule.** A state fills the whole row or block it applies to (band on hover, focus and writing; band-deep on failure and notices; pad for the selected meeting). It is never a thin coloured border.

## Typography

**Display Font:** Sofia Sans Extra Condensed Variable (with Arial Narrow, sans-serif)
**Body Font:** Libre Franklin Variable (with Segoe UI, system-ui, sans-serif)

**Character:** Tall condensed capitals stamp the structure of the pad like printed headings on a form; a sturdy, plain sans carries everything a person reads. Both faces are bundled with the app, Latin only, and never fetched.

### Hierarchy
- **Display** (800, clamp(2.25rem, 4.6vw, 3.75rem), 0.95): the meeting title and the welcome title; balanced, at most two lines, max 18ch on the welcome.
- **Wordmark** (800, 30px, 1): the app name at the top of the rail.
- **Timer** (700, 28px, 32px, tabular): the elapsed time on the red record block.
- **Caps head** (700, 15px/18px, 0.05em, uppercase): note section heads (rule green), the stamp's first line, the writing and failed row titles.
- **Caps speaker** (700, 14px, 0.05em, uppercase): speaker names in quotes and at each transcript turn, "From your notes" before the owner's own line, the "where it came from" column head, "Listening…", day heads in the rail.
- **Caps label** (700, 13px/16px, 0.05em, uppercase): small rail labels (Microphone, Recording).
- **Time tab** (700, 14px/18px, 0.03em, tabular): the clickable times on the note's centre rule.
- **Body** (400, 15px/23px): note points, quotes, transcript lines, notices; body-strong (600) for tabs, buttons and meeting names.
- **Meta** (500 or 400, 13px/18px to 20px, tabular): the date line, meeting times and durations, the line count, the stamp's model and count, the Copy button, the transcript times, the keyboard hint.

### Named Rules
**The Two Sizes Rule.** Libre Franklin runs at two sizes only: 15px for anything read and 13px for metadata. Hierarchy comes from the condensed caps and from weight, not from more text sizes.

**The Caps Are Structure Rule.** The condensed face is always uppercase, bold and tracked (0.05em), and is used for names of things: titles, heads, speakers, labels. It never sets a sentence.

## Layout

A two-column window: the chipboard rail at a fixed width (264px, 232px below 860px wide) and the pad filling the rest. The rail stacks wordmark and claim, the record block, search, the meetings scrolling by day (fading out over the last 28px), and the microphone at the foot; its contents sit 18px in. On short windows (600px tall or less) the rail tightens: smaller top padding, a 44px record button, and the claim and microphone label become screen-reader only.

The pad has a gutter of 44px (24px below 860px wide) and starts 30px down: title and date line on the left, the stamp at the top right, then the tab bar at a fixed 42px minimum height with 28px between tabs and Copy as Markdown pushed to its end, so the heavy rule never moves between states.

The note sheet is a container-queried grid. At 600px of sheet or wider each row is point | rule cell (5.75rem) | quotes (0.9fr), with a column head over the quotes. Narrower, the rule cell (4.75rem) moves to the left and the quotes fold beneath the point. The transcript uses the same 4.75rem rule cell on the left with the time sitting on the rule, then a 4rem speaker column, then the words, so every wrapped line keeps one left edge. Extra space for a speaker turn is padded inside the cells so the rule runs through unbroken.

On a wide window a meeting's content stops at 66rem (the measure) and stays left-aligned on the pad, so a row never stretches too far to read across.

### Named Rules
**The One Rule Rule.** The centre rule is drawn by every row's middle cell (a 2px rule-green line), so it is continuous across sections and turns. Square 10px detents mark section heads on the note and speaker changes in the transcript.

## Elevation & Depth

Flat. There are no drop shadows anywhere. Depth comes from tonal areas: the chipboard rail against the pad, wells cut a step lighter into the rail, band greens over the pad. Lines are drawn, never shadowed into depth. The 2px ink rule under the tabs and the 5px ink bar under the selected tab are painted backgrounds (a gradient sized to the bottom edge), because at 150% display scaling an inset shadow leaves a hairline down a tab's side. The 1px chipboard edge on the rail and above the microphone is an inset box-shadow; those edges sit on whole pixels.

### Named Rules
**The Flat Pad Rule.** Nothing floats. If something needs to stand out, it gets an area of colour or a line, not a shadow.

## Shapes

Gently rounded, never pill-shaped except for dots and meters. Small marks (time tabs, keyboard hint) take 4px; the stamp 7px; buttons and sheet rows 8px; wells and banners 10px; the record block and rail meeting items 11px. A selected meeting is rounded on its left side only, so it opens into the pad. Recording and live indicators are full circles (8px and 12px). The stamp is the one rotated shape (-1.2deg), laid flat and wrapping when the window is narrow.

## Components

### Buttons
- **Shape:** gently curved (8px); the record button and record block 11px.
- **Primary:** navy ink fill with pad-coloured text, semibold, 8px 16px (Write note, Retry, banner action, Ask, Ask again); hover lightens the ink to 88%.
- **Primary, disabled:** ink at 40% with the same pad-coloured text and no hover (Ask and Ask again while an answer is being written or the meeting is recording).
- **Record:** full rail width, 48px tall (44px on short windows), ink fill, a 12px red dot then the word. While busy it is disabled and shows the stage; while a note is being written it fills rule green.
- **Recording block:** the record button becomes a red-filled block (rec-fill) with a "Recording" caps label, the running timer, a warm-white Stop button (36px) and two level meters (you, them).
- **Copy as Markdown:** band fill, 13px semibold with a 16px icon, 6px 12px; hover fills band-deep; the label changes to Copied or the failure text for 2 seconds.
- **Icon button:** 32px square, muted icon, fills band on hover (rename).

### Inputs / Fields
- **Style:** wells in the rail: chipboard-well fill, no border, 10px radius, 40px tall, ink text, chipboard-ink placeholder and icons. Search shows a Ctrl K keyboard hint (1px outline, 4px radius) that hides below 860px.
- **Title edit:** the title becomes an input in the same display type on a band fill.
- **Focus:** a 2px rule-green outline offset 2px, everywhere but the lines of My notes, where the row being typed in fills band instead (see My notes).

### Navigation
- **Meetings in the rail:** grouped under caps day heads; each item is the title (semibold) over a 13px meta line (time and duration). Hover fills chipboard-well; the selected item takes the pad colour and merges into the pad. A live meeting shows a red pip and "Recording"; a meeting whose note is being written shows a rule-green pip.
- **Tabs:** Note, Transcript (with a line count), Ask and My notes on a 2px ink rule; unselected muted (ink on hover), selected ink with a 5px ink bar that draws out from its middle over 220ms. Arrow keys cycle the tabs; only the selected tab is in the Tab order. A meeting being recorded opens on My notes, any other on its Note; when a note starts being written the Note tab comes forward. Copy as Markdown belongs to the Note tab only.
- **Settings in the rail:** at the foot, below the microphone, as Windows apps place it: the sliders icon, the word and a Ctrl , hint, in chipboard ink. Hover fills chipboard-well; while Settings is open it keeps that fill with ink text.

### The Note Sheet (signature)
Each note point sits on a row with its time tabs on the centre rule and its quotes on the far side, each quote led by a coloured caps speaker name, clamped to four lines. A point taken from the owner's notes also quotes the typed line it rests on, after the transcript lines, led by "From your notes" in navy caps. Hovering or focusing a row fills it band green, brings the quotes from muted to ink, and keeps the time tabs on the band. A time tab is a small rule-green outlined tab on the pad; hover and keyboard focus both fill it rule green with pad text (no second ring). Pressing one opens the transcript at that line, filled the same band.

An action item's point starts with a Done box on its first line, drawn like a time tab: 16px, a 1.5px rule-green line at 60%, 4px radius (full rule green on hover). Ticked, it fills rule green with a pad-coloured tick, and the point is struck through in muted ink. Keyboard focus draws the 2px rule-green ring around the box. Decisions and open questions have no box.

### Note States
The writing and failed states are drawn as rows on the sheet. Writing: a band row with a caps title in deep rule green, a sentence, and a short stretch of rule running down a faint one in the rule cell. Failed: a band-deep row with the reason and a Retry button.

### Transcript
Lines sit on the same rule with their time on it in 13px meta type; the speaker is named once per turn, in coloured caps in its own column, and an 8px detent sits on the rule in the space between turns. Hover fills a line with half a band. While live, a row below the last line says "Listening…" beside a pulsing rule-green dot, where the rule fades out; it shows before the first line too. A newly arrived line lands at heavier weight (640) and settles to 400 over 900ms; a cited line fills band-deep and settles to band over 1400ms.

### Ask
The meeting's questions as a thread on the note sheet, with a form fixed under it. Each question heads its rows in body-strong (15px, 600) with a square detent on the rule; its answer is note rows (point | time tabs on the rule | quotes), and when only the parts of a long call that match the question were read, a 13px muted line under the points says so. While the answer is being written, a band row shows a caps title in deep rule green over the progress rule; "Not discussed in this meeting." and an answer that couldn't be checked are band rows; a failure is a band-deep row with its reason and, where asking again can help (not for a question too long for the model's settings or a meeting with no transcript), an Ask again primary button. The thread fades out over its last 28px above the form. The form: one-click questions as band-filled buttons (like Copy as Markdown), then the input, a band well (10px radius, 40px tall) with an Ask primary button; Enter asks. Everything that asks is disabled (band at half strength, muted text) while an answer is pending or the meeting is recording, when the empty thread says so instead of its intro; a refusal is a 13px muted line under the input. The newest question scrolls into view when asked and again when its answer lands, stopping clear of the fade, and the input takes focus back. On short windows the form tightens and, once there are questions, the one-click questions step aside.

### My notes
The owner's notepad, on the note's sheet: one row per typed line. The line is an auto-growing field in the point cell, in body type with no box, so it reads as writing on the pad. The time it was first typed sits on the rule as a time tab once it has one, and pressing it opens the transcript on the line being said then; a line typed before or after the call has no tab. Once the note is written, the quotes cell shows the transcript lines the line was linked to, as on the note sheet. The row being typed in fills band from edge to edge, its quotes come up to ink and its time tab stays on the band; the field draws no ring of its own (as a time tab draws none) and the caret is rule green. Hover fills nothing, so the pointer resting on a line never reads as the line being typed in. An empty pad is one line with the placeholder in muted ink, focused when a recording opens it. Enter starts the next line, Backspace on an empty line goes back to the end of the one before, and Up and Down step between lines from a line's first or last row; a click below the lines carries on from the last one. While recording, the pad fades out over its last 28px above a strip on the same rule: the last two transcript lines on the far side (caps speaker, words in muted ink, two lines each and one on short windows) with their times on the rule in 13px meta type, then "Listening…" beside the pulsing dot where the rule fades out. A save that fails shows a banner above the tabs, so it is seen whichever tab is open; the lines stay on the pad.

### Stamp (signature)
Provenance as one mark: a 2px rule-green bordered box, 7px radius, rotated -1.2deg, in rule green, with a caps first line ("written on this PC"), the model, and the number of points checked against the transcript. Shown only once a note is settled.

### Banner
A notice that fills its row in band-deep, 10px radius, 12px 16px: a semibold message, an optional hint in ink at 80%, at most one primary action and an optional close.

### Settings
A page on the pad, never a dialog: the display title with a close icon button at the top right, then one row per setting on the timed rule. Each row has a detent, a caps head in rule green, an optional 13px muted line and its control. Theme shows the window in miniature, drawn in each theme's own tokens (the `.light` and `.dark` scopes); Match Windows shows both, split on a diagonal. The chosen option fills band-deep with a check, hover fills band. The note model is a band-filled select; when Ollama can't be asked it is disabled, with the reason and a Check again link. Changes apply at once; one that could not be saved shows a banner. A setting appears only when its feature exists.

### Icons
Authored inline SVG at 16px with a single 1.5px round-capped stroke in the text colour.

## Do's and Don'ts

### Do:
- **Do** put every note point on the same row as the words it came from, across the 2px rule-green centre rule.
- **Do** show hover, focus, progress, failure and selection by filling the whole row or block (band, band-deep, pad).
- **Do** keep Libre Franklin at 15px/23px for reading and 13px for metadata, and use the condensed bold uppercase face (0.05em) for titles, heads, speakers and labels.
- **Do** use tabular figures for every time, duration and count.
- **Do** keep motion on cubic-bezier(0.16, 1, 0.3, 1) at 140ms for state changes, and wrap anything longer in a reduced-motion check. The set: buttons move 1px down while pressed; a meeting, Settings and the welcome fade up 6px over 260ms when they open; the welcome steps follow 90ms apart; the recording pip and the listening dot pulse every 1.6s. Nothing moves because the pad scrolled.
- **Do** give every token its dark value under the same name, and check both modes.

### Don't:
- **Don't** use red for anything but recording; errors and failures fill band-deep.
- **Don't** mark state with a thin outline; the only outlines are the focus ring and the rule-green marks drawn in the rule's own line (time tabs, stamp, keyboard hint).
- **Don't** add drop shadows or floating cards.
- **Don't** put a small label above a heading.
- **Don't** add text sizes between 13px and 15px or above 15px for reading text.
