# PROGRESS.md — what we did, what we built

Newest first. Each entry: date, what happened, and (once code exists) the commit hash.

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
