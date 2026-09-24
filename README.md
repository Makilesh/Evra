# Evra

Local-first meeting notes with an in-meeting expert. Evra records your microphone and your
computer's audio on your own machine, transcribes and separates speakers locally, lets you type
rough notes, and writes a cited meeting note with a local LLM.

**Status:** Phase 1 in development (Windows). See `BUILD.md` for the design and `PROGRESS.md` for progress.

## Development

Requirements: Windows 11, [uv](https://docs.astral.sh/uv/), Node.js 24, Git.

    uv sync
    npm ci --prefix frontend
    npm --prefix frontend run build
    uv run evra run

Checks: `uv run python tools/check.py`

Capture check (records mic + system audio, writes WAVs and a health report):

    uv run evra capture-test 60

## Licence

Evra's code: FSL-1.1-ALv2 (`LICENSE.md`). Third-party components: `THIRD_PARTY_LICENSES.md`.
