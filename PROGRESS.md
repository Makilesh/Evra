# PROGRESS.md — what we did, what we built

Newest first. Each entry: date, what happened, and (once code exists) the commit hash.

## 2026-09-24 — M1 Windows capture (branch `windows-capture`)

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
- 60-minute soak on the fixed code: running (built-in mic + speaker loopback).

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
