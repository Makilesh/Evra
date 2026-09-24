# CLAUDE.md — working on Evra

Evra: local-first Windows meeting-notes app (Python app process + model workers + React UI in pywebview).
**Source of truth: `BUILD.md`.** Read it fully before coding. `docs/archive/BUILD_PROMPT.v3.md` is reference only.

## Commands
- Setup: `uv sync` · `npm ci --prefix frontend`
- Run (built UI): `npm --prefix frontend run build` then `uv run evra run`
- Run (dev UI): `npm --prefix frontend run dev` and `uv run evra run --dev --debug`
- All checks: `uv run python tools/check.py` (must pass before every commit)
- Python only: `uv run pytest` · `uv run ruff check .` · `uv run ruff format --check .` · `uv run mypy`
- Frontend only: `npm --prefix frontend run lint|typecheck|test`
- Licences: `uv run python tools/license_gate.py [--write-register]`

## Rules (full list: BUILD.md §11)
- Work milestone by milestone (BUILD.md §10); plans live in `docs/superpowers/plans/`.
- After each completed feature: checks pass → Conventional Commit → `git push origin core` (D22). No force-push.
- Update `PROGRESS.md`, `DECISIONS.md`, `BACKLOG.md` as you go.
- Never change a §2 decision silently; write a DECISIONS.md entry.
- Licence gate before any new dependency or model.
- Never invent APIs; read installed source/docs or write a spike in `spikes/`.
- Never log transcript/note/document/audio content above DEBUG.
- Evra opens no network listener. pywebview gets only `file://` or the dev-server URL.
- Keep everything inside this folder (D23): app data in `.data/`, spikes in `spikes/`, scratch/research
  in `private/` (all git-ignored). Never use the system temp folder.
- Public repo: never commit real meeting data, keys, tokens, weights, or anything in `private/`.
  Describe goals as personal use, portfolio and distribution only.

## Layout
- `src/evra/` app package · `frontend/` React app (builds into `src/evra/ui/web/index.html`)
- `tools/` scripts · `tests/` pytest · `private/` git-ignored personal data
- Names (Evra, Hey Evra) only in `src/evra/constants.py`.
