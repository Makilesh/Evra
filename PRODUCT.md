# Product

<!-- impeccable:product-schema 1 -->

`BUILD.md` is the source of truth for scope and architecture; this file keeps the product facts that design work needs.

## Platform

web

(A React app in a pywebview window on Windows 11, rendered by Edge WebView2. Loaded from one local `index.html` over `file://`: no web server, no network fonts or assets.)

## Users

- **The owner first:** daily 1:1 calls on Windows, usually on headphones, with Evra's window open beside the call.
- **Then developers and anyone who wants private meeting notes.** Both audiences count equally: keyboard power and technical details are there for developers, never in the way of plain everyday use. (Confirmed 2026-11-10.)

## Product Purpose

Evra records a meeting's audio on the user's own PC (their microphone and the computer's output as two channels) without joining the call, transcribes it on the device, and writes a structured meeting note. The user's own typed notes steer what the note emphasises.

Success: the owner relies on it every day, it stands as a portfolio centrepiece, and it can be distributed (`BUILD.md` §1.2).

## Positioning

Recording, transcript and note never leave the PC, and every point in the note links to the moment in the conversation it came from. No bot joins the call. (Confirmed 2026-11-10.)

## Operating Context

- During a call, Evra sits beside the call window: the user glances to check both sides are being heard, reads the live transcript, and may type a rough note.
- After the call, the note is written automatically by a local model through Ollama (about 20–60 s for a 1:1). The user reads it, checks a point by jumping to the moment it cites, and copies action items elsewhere.
- Modes: **1:1** (default, the main use) and **Meeting**. English only in Phase 1. Light by default; Dark can be chosen in Settings.

## Capabilities and Constraints

- **The main window today:** Record/Stop with microphone picker, timer and two level meters (You, Them); meetings list with a title filter; the open meeting with Note and Transcript tabs; note points carry timestamp citations that jump to the transcript line; the note is written automatically after Stop, with stage progress and Retry; rename a meeting.
- **Data the UI has:** per meeting a title, start time, duration, state and note flag; utterances with channel (0 = You, 1 = Them), speaker label, start/end ms and text; note sections of points, each with citations (utterance id + start ms) and the model name.
- **Planned, not built** (`BUILD.md` §8.4): floating meeting window, onboarding, settings, tray, `Ctrl+K` palette, people and voiceprints, playing audio from a citation, version history.
- **Constraints:** works fully offline; fonts and assets bundled; one self-contained HTML file; the app opens no network listener; every shipped component licensed for commercial use (D11); while recording, the whole app stays light (≤ 25 % average CPU); live transcript lag ≤ 2 s.
- **Names:** "Evra" and "Hey Evra" are placeholders defined in one place; the visual identity must not depend on the name.

## Brand Commitments

- The note appears once, complete, after visible progress; never a draft that is replaced (D16).
- Recording must be unmistakable while it runs, and quiet enough not to compete with the call.
- The visual style is "Steno pad" (D19, chosen by the owner on 2026-11-10 from four sketches; it replaced "Quiet paper"): a green pad, a chipboard rail, a deep green rule, and every note point beside the words it came from.

## Evidence on Hand

- Synthetic 1:1 fixtures for demonstration and tests: `tests/fixtures/notes/one_on_one_synthetic.json` (about 4 minutes) and `one_on_one_60min_synthetic.json` (60 minutes).
- No logo, testimonials, customers or benchmarks exist; none may be invented. Real meeting data lives only in `private/` and never appears in the repository or in screenshots.

## Product Principles

1. **Private by construction:** show that everything happens on this PC; never imply a cloud.
2. **Grounded:** every point visibly leads back to the moment it was said.
3. **Calm during the call:** the window never competes with the conversation.
4. **Fast for power users, plain for everyone:** keyboard paths for every action, plain words on screen.
5. **Honest about state:** always show what Evra is doing (listening, transcribing, writing) and, when something fails, what happened and the one fix.

## Accessibility & Inclusion

Every control has an accessible name and works from the keyboard; motion respects the system's reduced-motion setting; text contrast holds in light and dark; every user-facing string goes through one strings layer for later translation (`BUILD.md` §8.4).
