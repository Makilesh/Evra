# Phase 1 · M0 Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A runnable, tested Evra skeleton on Windows: `evra --version`, a pywebview window showing the React app that talks to Python both ways, settings, logging, a migrated SQLite database, a licence gate, one-command checks and CI.

**Architecture:** A `src/evra` Python package (uv, Python 3.12) is the app process from `BUILD.md` §4. It owns paths, settings, logging, the SQLite store and a pywebview window. The React app in `frontend/` is built with Vite into **one self-contained `index.html`** under `src/evra/ui/web/`. pywebview loads that file with a `file://` URL, so no HTTP server ever starts. JS calls Python through `window.pywebview.api`; Python pushes events with `window.run_js("window.__evraEmit(...)")`.

**Tech Stack:** Python 3.12 (uv-managed), pywebview 6.2, pydantic 2, tomllib + tomli-w, structlog, platformdirs, sqlite3; React + TypeScript + Vite + Tailwind v4 + shadcn/ui conventions + vite-plugin-singlefile; Vitest + React Testing Library; ruff, mypy (strict), pytest; pip-licenses; GitHub Actions + gitleaks.

**Spec:** `BUILD.md` (v4). This plan covers `BUILD.md` §10 row **M0** and uses §2, §4, §8.2, §9.2–9.4 and §11.

## Global Constraints

- Python **3.12**, uv-managed interpreter only (`[tool.uv] python-preference = "only-managed"`). The existing `.venv` was built from the Microsoft Store Python and must be replaced.
- Package name `evra` (lowercase), `src/` layout. App name, id and wake phrase live **only** in `src/evra/constants.py`.
- Evra opens **no network listener**. Never pass pywebview a relative/local path URL, because that starts its built-in Bottle HTTP server. Use a `file://` URL (built app) or `http://127.0.0.1:5173` (Vite dev server, development only).
- **Keep everything inside the project folder during development** (owner's request, 2026-09-24):
  - Running from the source checkout, all app data goes to `<repo>/.data/`: `data/evra.db`, `data/models/`, `config/settings.toml`, `logs/evra.log` (rotating 10 × 5 MB).
  - Only an installed build uses the platformdirs locations (`%LOCALAPPDATA%\Evra\…`).
  - `evra run --data-dir PATH` overrides both.
  - Spikes live in `spikes/` and scratch or research files in `private/`; both are git-ignored.
  - Never write working files to the system temp folder.
- Never log transcript, note, document or audio content above DEBUG (`BUILD.md` §9.1, §11 rule 10).
- Licence policy (`BUILD.md` §9.2):
  - Runtime components may use: MIT, BSD, Apache-2.0, ISC, PSF, Unlicense, zlib, CC-BY-4.0, CC0, OFL.
  - MPL-2.0 is allowed for dev dependencies only.
  - LGPL is allowed only for explicitly listed packages.
  - Everything else fails.
- Type hints everywhere, `mypy --strict` on `src/` and `tools/`, TypeScript `strict`. Files stay under ~500 lines.
- **Git (D22):** after each task passes its checks, make one Conventional Commit and `git push origin core`. No force-push, no history rewrite, no pushes to `main`. Never commit anything listed in `BUILD.md` §9.3.
- **Public-repo wording:** repo files describe Evra's goals as personal use, portfolio and distribution only (§11 rule 11).
- Use `npm` for the frontend (CI uses it too). Smart App Control was switched off on the dev machine on 2026-09-24, after it had blocked `pnpm.exe`. If a downloaded tool is blocked again, record it in `DECISIONS.md`; don't work around it silently.
- Commit messages end with: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`

## Review Focus

These five situations are the ones most likely to hurt a real user. Each is pinned by a test in the task named.

1. **Paths with spaces or non-ASCII characters.** The repo lives at `D:\GEN AI\Evra`, and user folders can be non-ASCII. The UI `file://` URL must be percent-encoded and still load. → Task 6 `test_file_url_encodes_spaces_and_unicode`.
2. **Corrupt or hand-edited `settings.toml`.** The app must start with defaults and keep the bad file as `settings.toml.bad`, not crash. → Task 2 `test_invalid_toml_resets_to_defaults_and_keeps_backup` and `test_invalid_value_resets_to_defaults`.
3. **UI not built** (`evra run` before `npm run build`). The user needs a clear message and exit code 2, not a blank window or a traceback. → Task 6 `test_run_app_without_built_ui_exits_2_with_hint`.
4. **JS calling Python before pywebview is ready**, or the bridge never appearing. The UI must wait for `pywebviewready` and then show an error, not hang forever. → Task 5 `waits for pywebviewready` and `rejects when the bridge never appears`.
5. **Event payloads with quotes, newlines, `</script>` or non-Latin text** (future transcript snippets). Payloads must be escaped into valid JS and arrive unchanged. → Task 6 `test_emit_script_round_trips_awkward_payloads`.

---

## File Structure

| Path | Responsibility |
| --- | --- |
| `pyproject.toml`, `uv.lock`, `.python-version` | Python project, dependencies, tool config |
| `CLAUDE.md` | Short guide for Claude Code sessions (≤ 150 lines) |
| `README.md` | What Evra is, status, dev setup |
| `src/evra/__init__.py` | `__version__` |
| `src/evra/__main__.py` | CLI: `evra --version`, `evra run [--dev] [--debug]` |
| `src/evra/constants.py` | `APP_NAME`, `APP_ID`, `WAKE_PHRASE` |
| `src/evra/paths.py` | `AppPaths`: data/config/log/models dirs, db and settings paths |
| `src/evra/config.py` | `Settings` model; `load_settings`, `save_settings`, `debug_enabled` |
| `src/evra/logging_setup.py` | structlog JSON rotating logs + content redaction |
| `src/evra/store/db.py` | `connect()` with WAL, foreign keys, busy timeout |
| `src/evra/store/migrate.py` | `Migration`, `bundled_migrations()`, `migrate()` |
| `src/evra/store/migrations/0001_init.sql` | Phase 1 schema (`BUILD.md` §8.2) |
| `src/evra/bridge/api.py` | `BridgeApi`: methods React can call |
| `src/evra/bridge/events.py` | `EventBus`, `build_emit_script`: Python → React events |
| `src/evra/ui/window.py` | `resolve_ui_url`, `open_main_window` |
| `src/evra/app.py` | `App` container, `build_app()`, `run_app()` |
| `frontend/…` | Vite React TS app; `src/bridge.ts`, `src/theme.ts`, `src/lib/utils.ts`, `src/App.tsx` |
| `src/evra/ui/web/index.html` | **Build output** (git-ignored) |
| `models.yaml` | Model catalogue (empty in M0) |
| `tools/license_policy.yaml`, `tools/license_gate.py` | Licence gate + `THIRD_PARTY_LICENSES.md` generator |
| `tools/check.py` | Runs every check in one command |
| `.github/workflows/ci.yml` | Windows checks + gitleaks |
| `tests/unit/…`, `tests/tools/…`, `tests/conftest.py` | Python tests |

---

### Task 1: Python project skeleton and `evra --version`

**Files:**
- Create: `pyproject.toml`, `.python-version`, `CLAUDE.md`, `README.md`, `src/evra/__init__.py`, `src/evra/constants.py`, `src/evra/__main__.py`, `tests/__init__.py`, `tests/unit/__init__.py`, `tests/unit/test_cli.py`
- Delete: `.venv/` (Store-Python venv)

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `evra.__version__: str`
  - `evra.constants.APP_NAME = "Evra"`, `APP_ID = "evra"`, `WAKE_PHRASE = "Hey Evra"`
  - `evra.__main__.main(argv: Sequence[str] | None = None) -> int`
  - `evra.__main__.build_parser() -> argparse.ArgumentParser`

- [ ] **Step 1: Replace the Store-Python virtualenv**

Check it holds nothing but pip, then remove it:

```powershell
Get-ChildItem ".venv\Lib\site-packages" -Name
Remove-Item -Recurse -Force .venv
uv python install 3.12
uv python pin 3.12
```

Expected: `site-packages` lists only `pip*`. `.python-version` now contains `3.12`.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "evra"
version = "0.1.0"
description = "Local-first meeting notes with an in-meeting expert"
readme = "README.md"
license = "LicenseRef-FSL-1.1-ALv2"
license-files = ["LICENSE.md"]
requires-python = ">=3.12,<3.13"
dependencies = []

[project.scripts]
evra = "evra.__main__:main"

[build-system]
requires = ["hatchling>=1.27"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/evra"]

[tool.uv]
python-preference = "only-managed"

[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["frontend", "src/evra/ui/web", "docs/archive"]

[tool.ruff.lint]
select = ["E", "F", "W", "I", "UP", "B", "SIM", "RUF"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tools"]

[[tool.mypy.overrides]]
module = ["webview", "webview.*"]
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra"
```

Then add the dev tools (uv picks current versions and writes the bounds):

```powershell
uv add --dev pytest ruff mypy
```

Expected: `uv.lock` created, `.venv` recreated from the uv-managed 3.12 interpreter. Verify with `uv run python -c "import sys; print(sys.executable, sys.version)"`. The path must be under `.venv` and the version must be 3.12.x.

- [ ] **Step 3: Write the failing test** `tests/unit/test_cli.py` (plus empty `tests/__init__.py`, `tests/unit/__init__.py`)

```python
import pytest

import evra
from evra import constants
from evra.__main__ import main


def test_version_flag_prints_name_and_version(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert capsys.readouterr().out.strip() == f"Evra {evra.__version__}"


def test_version_comes_from_package_metadata() -> None:
    assert evra.__version__ == "0.1.0"


def test_names_live_in_constants() -> None:
    assert constants.APP_NAME == "Evra"
    assert constants.APP_ID == "evra"
    assert constants.WAKE_PHRASE == "Hey Evra"


def test_no_command_prints_help_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage:" in capsys.readouterr().out
```

- [ ] **Step 4: Run it to verify it fails**

Run: `uv run pytest tests/unit/test_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra'`.

- [ ] **Step 5: Implement**

`src/evra/__init__.py`:

```python
"""Evra — local-first meeting notes with an in-meeting expert."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("evra")
except PackageNotFoundError:  # running from a source tree that was never installed
    __version__ = "0.0.0+unknown"
```

`src/evra/constants.py`:

```python
"""The only place product names live (BUILD.md header). Change them here and nowhere else."""

APP_NAME = "Evra"
APP_ID = "evra"
WAKE_PHRASE = "Hey Evra"
```

`src/evra/__main__.py`:

```python
"""Command-line entry point: `evra` / `python -m evra`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from evra import __version__
from evra.constants import APP_ID, APP_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME} desktop app")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_subparsers(dest="command")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run tests and tools**

Run: `uv sync` then `uv run pytest -v`, `uv run evra --version`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`
Expected: 4 passed; `Evra 0.1.0`; ruff and mypy clean (run `uv run ruff format .` once if the format check complains).

- [ ] **Step 7: Write `CLAUDE.md`**

```markdown
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
```

`README.md`:

```markdown
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

## Licence

Evra's code: FSL-1.1-ALv2 (`LICENSE.md`). Third-party components: `THIRD_PARTY_LICENSES.md`.
```

- [ ] **Step 8: Commit and push**

Append to `PROGRESS.md` under a new heading `## 2026-09-24 — M0 Bootstrap`: `- Task 1: Python skeleton, uv-managed 3.12, \`evra --version\`, CLAUDE.md, README.`

```powershell
git add pyproject.toml uv.lock .python-version CLAUDE.md README.md src tests PROGRESS.md
git commit -m "feat: python project skeleton with evra --version" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin core
```

---

### Task 2: App paths and settings

**Files:**
- Create: `src/evra/paths.py`, `src/evra/config.py`, `tests/unit/test_paths.py`, `tests/unit/test_config.py`

**Interfaces:**
- Consumes: `evra.constants.APP_NAME`.
- Produces:
  - `AppPaths(data_dir: Path, config_dir: Path, log_dir: Path)` (frozen dataclass), with properties `models_dir`, `db_path`, `settings_file`, classmethods `for_user()` and `under(root: Path)`, and method `ensure() -> None`
  - `REPO_ROOT: Path`
  - `is_source_checkout(repo_root: Path = REPO_ROOT) -> bool`
  - `resolve_paths(data_dir: Path | None = None, *, repo_root: Path = REPO_ROOT) -> AppPaths`
  - `Settings` (pydantic) with fields `default_mode`, `default_situation`, `live_transcript`, `audio_retention`, `theme`, `llm: LlmSettings`
  - `load_settings(path: Path) -> Settings`
  - `save_settings(path: Path, settings: Settings) -> None`
  - `debug_enabled(environ: Mapping[str, str] | None = None) -> bool`

- [ ] **Step 1: Add dependencies**

```powershell
uv add pydantic platformdirs tomli-w structlog
```

- [ ] **Step 2: Write failing tests**

`tests/unit/test_paths.py`:

```python
import os
import sys
from pathlib import Path

import pytest

from evra.paths import REPO_ROOT, AppPaths, is_source_checkout, resolve_paths


def test_under_puts_everything_below_root(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path)
    assert paths.db_path == tmp_path / "data" / "evra.db"
    assert paths.settings_file == tmp_path / "config" / "settings.toml"
    assert paths.models_dir == tmp_path / "data" / "models"
    assert paths.log_dir == tmp_path / "logs"


def test_ensure_creates_directories(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path)
    paths.ensure()
    for d in (paths.data_dir, paths.config_dir, paths.log_dir, paths.models_dir):
        assert d.is_dir()


@pytest.mark.skipif(sys.platform != "win32", reason="Windows layout")
def test_for_user_uses_localappdata_on_windows() -> None:
    paths = AppPaths.for_user()
    local = Path(os.environ["LOCALAPPDATA"])
    assert paths.data_dir == local / "Evra"
    assert paths.db_path == local / "Evra" / "evra.db"


def _fake_checkout(root: Path) -> Path:
    (root / ".git").mkdir(parents=True)
    (root / "pyproject.toml").write_text('[project]\nname = "evra"\n', encoding="utf-8")
    return root


def test_source_checkout_keeps_data_inside_repo(tmp_path: Path) -> None:
    repo = _fake_checkout(tmp_path / "GEN AI" / "Evra")
    assert is_source_checkout(repo)
    paths = resolve_paths(repo_root=repo)
    assert paths == AppPaths.under(repo / ".data")
    assert paths.db_path == repo / ".data" / "data" / "evra.db"


def test_installed_build_uses_user_dirs(tmp_path: Path) -> None:
    not_a_repo = tmp_path / "site-packages"
    not_a_repo.mkdir()
    assert not is_source_checkout(not_a_repo)
    assert resolve_paths(repo_root=not_a_repo) == AppPaths.for_user()


def test_explicit_data_dir_wins(tmp_path: Path) -> None:
    repo = _fake_checkout(tmp_path / "repo")
    assert resolve_paths(tmp_path / "custom", repo_root=repo) == AppPaths.under(tmp_path / "custom")


def test_real_repo_is_detected_as_checkout() -> None:
    assert is_source_checkout(REPO_ROOT)
    assert (REPO_ROOT / "BUILD.md").exists()
```

`tests/unit/test_config.py`:

```python
from pathlib import Path

from evra.config import Settings, debug_enabled, load_settings, save_settings


def test_missing_file_gives_defaults(tmp_path: Path) -> None:
    s = load_settings(tmp_path / "settings.toml")
    assert s == Settings()
    assert s.default_mode == "one_on_one"
    assert s.audio_retention == "30d"
    assert s.live_transcript is True
    assert s.llm.provider == "ollama"


def test_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "cfg" / "settings.toml"
    s = Settings(default_mode="meeting", audio_retention="forever", theme="dark")
    save_settings(path, s)
    assert load_settings(path) == s


def test_invalid_toml_resets_to_defaults_and_keeps_backup(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text("this is = = not toml", encoding="utf-8")
    assert load_settings(path) == Settings()
    assert not path.exists()
    assert (tmp_path / "settings.toml.bad").read_text(encoding="utf-8") == "this is = = not toml"


def test_invalid_value_resets_to_defaults(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text('default_mode = "party"\n', encoding="utf-8")
    assert load_settings(path) == Settings()
    assert (tmp_path / "settings.toml.bad").exists()


def test_unknown_keys_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "settings.toml"
    path.write_text('future_option = 3\ntheme = "light"\n', encoding="utf-8")
    assert load_settings(path).theme == "light"


def test_debug_enabled_reads_only_evra_debug() -> None:
    assert debug_enabled({"EVRA_DEBUG": "1"}) is True
    assert debug_enabled({"EVRA_DEBUG": "0"}) is False
    assert debug_enabled({}) is False
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/unit/test_paths.py tests/unit/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.paths'`.

- [ ] **Step 4: Implement**

`src/evra/paths.py`:

```python
"""Where Evra keeps its files (BUILD.md §4.5, §8.2)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import platformdirs

from evra.constants import APP_NAME


@dataclass(frozen=True)
class AppPaths:
    data_dir: Path
    config_dir: Path
    log_dir: Path

    @property
    def models_dir(self) -> Path:
        return self.data_dir / "models"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "evra.db"

    @property
    def settings_file(self) -> Path:
        return self.config_dir / "settings.toml"

    @classmethod
    def for_user(cls) -> AppPaths:
        return cls(
            data_dir=Path(platformdirs.user_data_dir(APP_NAME, appauthor=False)),
            config_dir=Path(platformdirs.user_config_dir(APP_NAME, appauthor=False)),
            log_dir=Path(platformdirs.user_log_dir(APP_NAME, appauthor=False)),
        )

    @classmethod
    def under(cls, root: Path) -> AppPaths:
        """All paths below one root — for tests and portable runs."""
        return cls(data_dir=root / "data", config_dir=root / "config", log_dir=root / "logs")

    def ensure(self) -> None:
        for directory in (self.data_dir, self.config_dir, self.log_dir, self.models_dir):
            directory.mkdir(parents=True, exist_ok=True)


# src/evra/paths.py -> parents[2] is the repository root in a source checkout.
REPO_ROOT = Path(__file__).resolve().parents[2]


def is_source_checkout(repo_root: Path = REPO_ROOT) -> bool:
    return (repo_root / "pyproject.toml").is_file() and (repo_root / ".git").exists()


def resolve_paths(data_dir: Path | None = None, *, repo_root: Path = REPO_ROOT) -> AppPaths:
    """Explicit dir > `<repo>/.data` when running from source > per-user OS dirs."""
    if data_dir is not None:
        return AppPaths.under(data_dir)
    if is_source_checkout(repo_root):
        return AppPaths.under(repo_root / ".data")
    return AppPaths.for_user()
```

Append to the root `.gitignore`:

```
.data/
spikes/
```

`src/evra/config.py`:

```python
"""User settings persisted as TOML (BUILD.md §5.5, §6.2, §8.1)."""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

import structlog
import tomli_w
from pydantic import BaseModel, ConfigDict, Field, ValidationError

log = structlog.get_logger(__name__)

Mode = Literal["one_on_one", "meeting"]
Situation = Literal["call_headphones", "call_speakers", "in_person", "hybrid"]
Retention = Literal["7d", "30d", "90d", "forever"]
Theme = Literal["system", "light", "dark"]


class LlmSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    provider: Literal["ollama"] = "ollama"
    model: str = ""  # chosen by the M3 bake-off (BUILD.md D4)
    ollama_url: str = "http://127.0.0.1:11434"


class Settings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    default_mode: Mode = "one_on_one"
    default_situation: Situation = "call_headphones"
    live_transcript: bool = True
    audio_retention: Retention = "30d"
    theme: Theme = "system"
    llm: LlmSettings = Field(default_factory=LlmSettings)


def load_settings(path: Path) -> Settings:
    """Load settings; a corrupt or invalid file is moved aside and defaults are used."""
    if not path.exists():
        return Settings()
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        return Settings.model_validate(data)
    except (tomllib.TOMLDecodeError, ValidationError, UnicodeDecodeError):
        backup = path.with_suffix(".toml.bad")
        path.replace(backup)
        log.warning("settings_invalid_reset", backup=str(backup))
        return Settings()


def save_settings(path: Path, settings: Settings) -> None:
    """Write atomically: temp file, then replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".toml.tmp")
    tmp.write_text(tomli_w.dumps(settings.model_dump()), encoding="utf-8")
    tmp.replace(path)


def debug_enabled(environ: Mapping[str, str] | None = None) -> bool:
    """EVRA_DEBUG=1 is the only environment variable Evra reads."""
    env = os.environ if environ is None else environ
    return env.get("EVRA_DEBUG", "") == "1"
```

- [ ] **Step 5: Run tests and tools**

Run: `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`
Expected: all pass.

- [ ] **Step 6: Record the config decision**

The spec's M0 row says "pydantic-settings"; this plan uses pydantic + `tomllib` + `tomli-w` instead. The settings path is only known at runtime and must be injectable for tests, and only `EVRA_DEBUG` is read from the environment. Append to `DECISIONS.md`:

```markdown

## Config via pydantic + tomllib instead of pydantic-settings (2026-09-24)
- **Context:** BUILD.md §10 M0 lists pydantic-settings; settings live in a runtime-resolved TOML path and tests need to inject it.
- **Evidence:** pydantic-settings' TOML source is configured per class; injecting a path per call needs a workaround. Only `EVRA_DEBUG` comes from the environment.
- **Decision:** `Settings` is a plain pydantic model; `load_settings(path)`/`save_settings(path, s)` use `tomllib`/`tomli-w`; `debug_enabled()` reads `EVRA_DEBUG`.
- **Consequences:** one fewer dependency; corrupt files are moved to `settings.toml.bad` and defaults load.
```

- [ ] **Step 7: Commit and push**

Append to `PROGRESS.md`: `- Task 2: AppPaths (platformdirs) and TOML settings with safe reset on corrupt files.`

```powershell
git add .gitignore pyproject.toml uv.lock src/evra/paths.py src/evra/config.py tests/unit/test_paths.py tests/unit/test_config.py DECISIONS.md PROGRESS.md
git commit -m "feat: app paths and TOML settings" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin core
```

---

### Task 3: Logging with content redaction

**Files:**
- Create: `src/evra/logging_setup.py`, `tests/conftest.py`, `tests/unit/test_logging.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `configure_logging(log_dir: Path, *, debug: bool) -> Path` (returns the log file path)
  - `shutdown_logging() -> None`
  - `redact_content(logger, method_name, event_dict) -> event_dict`
  - `CONTENT_KEYS: frozenset[str]`, `REDACTED = "[redacted]"`

- [ ] **Step 1: Write failing tests**

`tests/conftest.py`:

```python
from collections.abc import Iterator

import pytest

from evra.logging_setup import shutdown_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    shutdown_logging()  # release log files so Windows can delete tmp dirs
```

`tests/unit/test_logging.py`:

```python
import json
import logging
from pathlib import Path
from typing import Any

import structlog

from evra.logging_setup import configure_logging


def _lines(log_file: Path) -> list[dict[str, Any]]:
    for handler in logging.getLogger().handlers:
        handler.flush()
    text = log_file.read_text(encoding="utf-8").strip()
    return [json.loads(line) for line in text.splitlines()] if text else []


def test_info_redacts_meeting_content(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=False)
    structlog.get_logger("t").info("utterance_saved", text="secret words", meeting_id="m1")
    [line] = _lines(log_file)
    assert line["event"] == "utterance_saved"
    assert line["text"] == "[redacted]"
    assert line["meeting_id"] == "m1"
    assert line["level"] == "info"
    assert "secret words" not in log_file.read_text(encoding="utf-8")


def test_debug_calls_keep_content_when_debug_enabled(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=True)
    structlog.get_logger("t").debug("asr_segment", text="hello there")
    [line] = _lines(log_file)
    assert line["text"] == "hello there"


def test_debug_calls_dropped_when_debug_disabled(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=False)
    structlog.get_logger("t").debug("asr_segment", text="hello there")
    assert _lines(log_file) == []


def test_reconfigure_does_not_duplicate_file_handlers(tmp_path: Path) -> None:
    configure_logging(tmp_path, debug=False)
    configure_logging(tmp_path, debug=False)
    names = [h.get_name() for h in logging.getLogger().handlers]
    assert names.count("evra-file") == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_logging.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.logging_setup'`.

- [ ] **Step 3: Implement** `src/evra/logging_setup.py`

```python
"""Structured JSON logs in rotating files, with meeting content redacted (BUILD.md §9.1)."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import structlog
from structlog.typing import EventDict, Processor, WrappedLogger

HANDLER_NAME = "evra-file"
LOG_FILE_NAME = "evra.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 10
REDACTED = "[redacted]"
CONTENT_KEYS = frozenset(
    {
        "text", "transcript", "note", "notes", "document", "audio", "pcm",
        "content", "question", "answer", "prompt", "response",
    }
)


def redact_content(_logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Replace meeting content with a marker unless this is a DEBUG call."""
    if method_name == "debug":
        return event_dict
    for key in CONTENT_KEYS.intersection(event_dict):
        event_dict[key] = REDACTED
    return event_dict


def shutdown_logging() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() == HANDLER_NAME:
            root.removeHandler(handler)
            handler.close()


def configure_logging(log_dir: Path, *, debug: bool) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE_NAME
    shutdown_logging()

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            redact_content,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    return log_file
```

If mypy rejects a structlog type name, check it in the installed source (`uv run python -c "import structlog.typing, inspect; print(inspect.getsource(structlog.typing))"`). Don't guess.

- [ ] **Step 4: Run tests and tools**

Run: `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`
Expected: all pass.

- [ ] **Step 5: Commit and push**

Append to `PROGRESS.md`: `- Task 3: structlog JSON rotating logs (10 × 5 MB) with content redaction above DEBUG.`

```powershell
git add src/evra/logging_setup.py tests/conftest.py tests/unit/test_logging.py PROGRESS.md
git commit -m "feat: structured logging with content redaction" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin core
```

---

### Task 4: SQLite store and migrations

**Files:**
- Create: `src/evra/store/__init__.py`, `src/evra/store/db.py`, `src/evra/store/migrate.py`, `src/evra/store/migrations/__init__.py`, `src/evra/store/migrations/0001_init.sql`, `tests/unit/test_store.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `connect(db_path: Path) -> sqlite3.Connection` (autocommit mode, `Row` factory, WAL, foreign keys, busy timeout 5 s)
  - `Migration(version: int, name: str, sql: str)` (frozen dataclass)
  - `bundled_migrations() -> list[Migration]`
  - `current_version(conn) -> int`
  - `migrate(conn, migrations: Sequence[Migration] | None = None) -> int`

- [ ] **Step 1: Write failing tests** `tests/unit/test_store.py`

```python
import sqlite3
from pathlib import Path

import pytest

from evra.store.db import connect
from evra.store.migrate import Migration, bundled_migrations, current_version, migrate

EXPECTED_TABLES = {
    "meeting", "audio_segment", "gap", "transcript_version", "utterance", "person",
    "voiceprint", "speaker", "note_block", "generation", "output_block", "action_item",
    "decision", "open_question", "topic", "job",
}


def _tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {r[0] for r in rows}


def test_fresh_database_gets_phase1_schema(tmp_path: Path) -> None:
    conn = connect(tmp_path / "evra.db")
    assert migrate(conn) == 1
    assert current_version(conn) == 1
    assert _tables(conn) == EXPECTED_TABLES
    indexes = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'")}
    assert {"utt_meeting", "job_ready"} <= indexes


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    conn = connect(tmp_path / "evra.db")
    migrate(conn)
    assert migrate(conn) == 1


def test_connection_pragmas(tmp_path: Path) -> None:
    conn = connect(tmp_path / "evra.db")
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert conn.execute("PRAGMA busy_timeout").fetchone()[0] == 5000


def test_deleting_meeting_cascades_to_dependents(tmp_path: Path) -> None:
    conn = connect(tmp_path / "evra.db")
    migrate(conn)
    conn.execute(
        "INSERT INTO meeting (id, title, started_at, template, state, created_at, updated_at)"
        " VALUES ('m1', 'Sync', 0, 'one_on_one', 'ready', 0, 0)"
    )
    conn.execute(
        "INSERT INTO transcript_version (id, meeting_id, kind, model, created_at)"
        " VALUES ('v1', 'm1', 'live', 'parakeet', 0)"
    )
    conn.execute(
        "INSERT INTO utterance (id, version_id, meeting_id, seq, channel, start_ms, end_ms, text)"
        " VALUES ('u1', 'v1', 'm1', 0, 0, 0, 1000, 'hello')"
    )
    conn.execute(
        "INSERT INTO note_block (id, meeting_id, position, text, phase)"
        " VALUES ('n1', 'm1', 0, 'budget?', 'during')"
    )
    conn.execute("DELETE FROM meeting WHERE id = 'm1'")
    for table in ("transcript_version", "utterance", "note_block"):
        assert conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0


def test_failed_migration_rolls_back_and_keeps_version(tmp_path: Path) -> None:
    conn = connect(tmp_path / "evra.db")
    good = Migration(1, "good", "CREATE TABLE a (x INTEGER);")
    bad = Migration(2, "bad", "CREATE TABLE b (y INTEGER); THIS IS NOT SQL;")
    with pytest.raises(sqlite3.Error):
        migrate(conn, [good, bad])
    assert current_version(conn) == 1
    assert "b" not in _tables(conn)
    assert not conn.in_transaction


def test_reader_not_blocked_by_open_write_transaction(tmp_path: Path) -> None:
    db = tmp_path / "evra.db"
    writer = connect(db)
    migrate(writer)
    reader = connect(db)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO person (id, display_name) VALUES ('p1', 'Asha')")
    assert reader.execute("SELECT count(*) FROM person").fetchone()[0] == 0
    writer.execute("COMMIT")
    assert reader.execute("SELECT count(*) FROM person").fetchone()[0] == 1


def test_bundled_migrations_are_numbered_without_gaps() -> None:
    versions = [m.version for m in bundled_migrations()]
    assert versions == list(range(1, len(versions) + 1))
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/test_store.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'evra.store'`.

- [ ] **Step 3: Write `src/evra/store/migrations/0001_init.sql`**

First line: `-- 0001_init: Phase 1 schema. Source: BUILD.md §8.2 (keep in sync).`
Then paste the SQL between the ```` ```sql ```` fences in `BUILD.md` §8.2 **verbatim**: all `CREATE TABLE` statements from `meeting` to `job`, plus `CREATE INDEX utt_meeting` and `CREATE INDEX job_ready`. Create an empty `src/evra/store/migrations/__init__.py` and an empty `src/evra/store/__init__.py`.

- [ ] **Step 4: Implement** `src/evra/store/db.py`

```python
"""SQLite connections (BUILD.md §8.2): WAL, foreign keys, one connection per thread."""

from __future__ import annotations

import sqlite3
from pathlib import Path

BUSY_TIMEOUT_MS = 5000


def connect(db_path: Path) -> sqlite3.Connection:
    """Open the database in autocommit mode; callers manage transactions explicitly."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=BUSY_TIMEOUT_MS / 1000, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
    return conn
```

`src/evra/store/migrate.py`:

```python
"""Forward-only schema migrations tracked in PRAGMA user_version."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from importlib import resources

_FILE_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str


def bundled_migrations() -> list[Migration]:
    found: list[Migration] = []
    for entry in resources.files("evra.store.migrations").iterdir():
        match = _FILE_NAME.match(entry.name)
        if match:
            found.append(
                Migration(int(match.group(1)), match.group(2), entry.read_text(encoding="utf-8"))
            )
    found.sort(key=lambda m: m.version)
    versions = [m.version for m in found]
    if versions != list(range(1, len(found) + 1)):
        raise RuntimeError(f"migrations must be numbered 1..N without gaps, got {versions}")
    return found


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def migrate(conn: sqlite3.Connection, migrations: Sequence[Migration] | None = None) -> int:
    """Apply every migration newer than the database; each one is atomic."""
    pending = bundled_migrations() if migrations is None else list(migrations)
    version = current_version(conn)
    for migration in pending:
        if migration.version <= version:
            continue
        try:
            conn.executescript(
                f"BEGIN;\n{migration.sql}\nPRAGMA user_version = {migration.version};\nCOMMIT;"
            )
        except sqlite3.Error:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        version = migration.version
    return version
```

- [ ] **Step 5: Run tests and tools**

Run: `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`
Expected: all pass.

- [ ] **Step 6: Commit and push**

Append to `PROGRESS.md`: `- Task 4: SQLite store (WAL, FKs) with forward-only migrations; 0001 Phase 1 schema.`

```powershell
git add src/evra/store tests/unit/test_store.py PROGRESS.md
git commit -m "feat: sqlite store with migrations and phase 1 schema" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin core
```

---

### Task 5: Frontend scaffold, bridge client and bootstrap screen

**Files:**
- Create (via template, then edit): `frontend/` (Vite react-ts)
- Create: `frontend/components.json`, `frontend/src/lib/utils.ts`, `frontend/src/bridge.ts`, `frontend/src/theme.ts`, `frontend/src/test/setup.ts`, `frontend/src/bridge.test.ts`, `frontend/src/theme.test.ts`, `frontend/src/lib/utils.test.ts`, `frontend/src/App.test.tsx`
- Modify: `frontend/vite.config.ts`, `frontend/tsconfig.app.json`, `frontend/tsconfig.json`, `frontend/package.json` (scripts), `frontend/index.html` (title), `frontend/src/main.tsx`, `frontend/src/App.tsx`, `frontend/src/index.css`, `.gitignore`
- Delete: `frontend/src/App.css`, `frontend/src/assets/`, `frontend/public/vite.svg` (template demo files)

**Interfaces:**
- Consumes: the Python methods `ping(message) -> {reply}`, `app_info() -> {name, version}` and `request_hello() -> null`, and the event `app.hello` (all implemented in Task 6).
- Produces (TypeScript):
  - `interface EvraApi { ping(message: string): Promise<PingReply>; app_info(): Promise<AppInfo>; request_hello(): Promise<null> }`
  - `getApi(timeoutMs?: number): Promise<EvraApi>`
  - `onEvent(name: string, handler: (payload: unknown) => void): () => void`
  - `emit(name: string, payload: unknown): void`, exposed as `window.__evraEmit`
  - `setApiForTests(api: EvraApi | null): void`
  - `applyTheme(dark: boolean, root?: HTMLElement): void`, `followSystemTheme(): () => void`
  - `cn(...inputs: ClassValue[]): string`
  - Build output `src/evra/ui/web/index.html` (single file)

- [ ] **Step 1: Create the Vite app**

```powershell
npm create vite@latest frontend -- --template react-ts --no-interactive
```

If the CLI rejects `--no-interactive`, run it without that flag and answer **No** to any "install/start now" prompt. Then:

```powershell
npm install --prefix frontend
npm install --prefix frontend clsx tailwind-merge
npm install --prefix frontend -D tailwindcss @tailwindcss/vite vite-plugin-singlefile vitest jsdom @testing-library/react @testing-library/jest-dom @testing-library/user-event @types/node
```

Delete the template demo files listed above. Keep the template's `eslint.config.js` and the React plugin it chose.

- [ ] **Step 2: Configure Vite, TypeScript, scripts and gitignore**

`frontend/vite.config.ts` (keep the template's React plugin import if it differs):

```ts
/// <reference types="vitest/config" />
import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { viteSingleFile } from "vite-plugin-singlefile";

// The build is ONE self-contained index.html so pywebview can load it via file://
// without starting an HTTP server (BUILD.md §4.3, D6).
export default defineConfig({
  plugins: [react(), tailwindcss(), viteSingleFile()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  build: { outDir: "../src/evra/ui/web", emptyOutDir: true },
  server: { host: "127.0.0.1", port: 5173, strictPort: true },
  test: { environment: "jsdom", setupFiles: ["./src/test/setup.ts"] },
});
```

In `frontend/tsconfig.app.json` and `frontend/tsconfig.json`, add under `compilerOptions`: `"paths": { "@/*": ["./src/*"] }`. Make sure `"strict": true` is present in `tsconfig.app.json`.

`frontend/package.json` scripts: keep `dev` and `build` from the template, and set:

```json
"lint": "eslint .",
"typecheck": "tsc -b",
"test": "vitest run"
```

In `frontend/index.html`, set `<title>Evra</title>` and remove the vite.svg favicon link.

Append to the root `.gitignore`:

```
src/evra/ui/web/
frontend/dist/
```

- [ ] **Step 3: Write failing tests**

`frontend/src/test/setup.ts`:

```ts
import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach } from "vitest";

afterEach(() => cleanup());
```

`frontend/src/bridge.test.ts`:

```ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { emit, getApi, onEvent, setApiForTests, type EvraApi } from "@/bridge";

const fakeApi: EvraApi = {
  ping: async (m) => ({ reply: `pong: ${m}` }),
  app_info: async () => ({ name: "Evra", version: "0.1.0" }),
  request_hello: async () => null,
};

afterEach(() => {
  setApiForTests(null);
  delete window.pywebview;
});

describe("getApi", () => {
  it("returns the test override immediately", async () => {
    setApiForTests(fakeApi);
    await expect(getApi()).resolves.toBe(fakeApi);
  });

  it("waits for pywebviewready", async () => {
    const pending = getApi(1000);
    window.pywebview = { api: fakeApi };
    window.dispatchEvent(new Event("pywebviewready"));
    await expect(pending).resolves.toBe(fakeApi);
  });

  it("rejects when the bridge never appears", async () => {
    await expect(getApi(10)).rejects.toThrow("Python bridge not available");
  });
});

describe("events", () => {
  it("delivers emitted payloads and supports unsubscribe", () => {
    const handler = vi.fn();
    const off = onEvent("app.hello", handler);
    emit("app.hello", { n: 1 });
    off();
    emit("app.hello", { n: 2 });
    expect(handler).toHaveBeenCalledTimes(1);
    expect(handler).toHaveBeenCalledWith({ n: 1 });
  });

  it("is reachable from Python via window.__evraEmit", () => {
    const handler = vi.fn();
    const off = onEvent("x.y", handler);
    window.__evraEmit?.("x.y", "ok");
    off();
    expect(handler).toHaveBeenCalledWith("ok");
  });
});
```

`frontend/src/theme.test.ts`:

```ts
import { expect, it } from "vitest";
import { applyTheme } from "@/theme";

it("toggles the dark class", () => {
  const root = document.createElement("div");
  applyTheme(true, root);
  expect(root.classList.contains("dark")).toBe(true);
  applyTheme(false, root);
  expect(root.classList.contains("dark")).toBe(false);
});
```

`frontend/src/lib/utils.test.ts`:

```ts
import { expect, it } from "vitest";
import { cn } from "@/lib/utils";

it("merges conflicting tailwind classes", () => {
  expect(cn("px-2", "px-4", false && "hidden")).toBe("px-4");
});
```

`frontend/src/App.test.tsx`:

```tsx
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, it } from "vitest";
import App from "@/App";
import { emit, setApiForTests, type EvraApi } from "@/bridge";

const fakeApi: EvraApi = {
  ping: async (m) => ({ reply: `pong: ${m}` }),
  app_info: async () => ({ name: "Evra", version: "0.1.0" }),
  request_hello: async () => null,
};

afterEach(() => setApiForTests(null));

it("shows the app name and version from Python", async () => {
  setApiForTests(fakeApi);
  render(<App />);
  expect(await screen.findByRole("heading", { name: "Evra 0.1.0" })).toBeInTheDocument();
});

it("pings Python and shows the reply", async () => {
  setApiForTests(fakeApi);
  render(<App />);
  await userEvent.click(screen.getByRole("button", { name: "Ping Python" }));
  expect(await screen.findByRole("status")).toHaveTextContent("pong: hello");
});

it("shows events pushed from Python", async () => {
  setApiForTests(fakeApi);
  render(<App />);
  await screen.findByRole("heading", { name: "Evra 0.1.0" });
  act(() => emit("app.hello", { message: "Python is connected" }));
  expect(screen.getByTestId("last-event")).toHaveTextContent("Python is connected");
});

it("shows an error when the bridge is unavailable", async () => {
  setApiForTests({
    ...fakeApi,
    app_info: async () => {
      throw new Error("boom");
    },
  });
  render(<App />);
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
});
```

- [ ] **Step 4: Run to verify failure**

Run: `npm --prefix frontend run test`
Expected: FAIL. The modules `@/bridge`, `@/theme` and `@/lib/utils` don't exist yet.

- [ ] **Step 5: Implement**

`frontend/src/bridge.ts`:

```ts
// Python <-> React bridge (BUILD.md §4, D5).
// JS -> Python: window.pywebview.api.<method>(...) returns a Promise.
// Python -> JS: Python runs window.__evraEmit(name, payload).

export interface AppInfo {
  name: string;
  version: string;
}

export interface PingReply {
  reply: string;
}

export interface EvraApi {
  ping(message: string): Promise<PingReply>;
  app_info(): Promise<AppInfo>;
  request_hello(): Promise<null>;
}

type Handler = (payload: unknown) => void;

declare global {
  interface Window {
    pywebview?: { api: EvraApi };
    __evraEmit?: (name: string, payload: unknown) => void;
  }
}

const handlers = new Map<string, Set<Handler>>();
let apiOverride: EvraApi | null = null;

export function setApiForTests(api: EvraApi | null): void {
  apiOverride = api;
}

export function getApi(timeoutMs = 10_000): Promise<EvraApi> {
  if (apiOverride) return Promise.resolve(apiOverride);
  if (window.pywebview?.api) return Promise.resolve(window.pywebview.api);
  return new Promise((resolve, reject) => {
    const onReady = () => {
      window.clearTimeout(timer);
      if (window.pywebview?.api) resolve(window.pywebview.api);
      else reject(new Error("pywebviewready fired without an api"));
    };
    const timer = window.setTimeout(() => {
      window.removeEventListener("pywebviewready", onReady);
      reject(new Error("Python bridge not available"));
    }, timeoutMs);
    window.addEventListener("pywebviewready", onReady, { once: true });
  });
}

export function onEvent(name: string, handler: Handler): () => void {
  const set = handlers.get(name) ?? new Set<Handler>();
  handlers.set(name, set);
  set.add(handler);
  return () => {
    set.delete(handler);
  };
}

export function emit(name: string, payload: unknown): void {
  handlers.get(name)?.forEach((handler) => handler(payload));
}

window.__evraEmit = emit;
```

`frontend/src/theme.ts`:

```ts
export function applyTheme(dark: boolean, root: HTMLElement = document.documentElement): void {
  root.classList.toggle("dark", dark);
}

export function followSystemTheme(): () => void {
  const query = window.matchMedia("(prefers-color-scheme: dark)");
  applyTheme(query.matches);
  const onChange = (event: MediaQueryListEvent) => applyTheme(event.matches);
  query.addEventListener("change", onChange);
  return () => query.removeEventListener("change", onChange);
}
```

`frontend/src/lib/utils.ts`:

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

`frontend/components.json` (shadcn/ui conventions; components are added with the shadcn CLI from M3 on):

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "new-york",
  "rsc": false,
  "tsx": true,
  "tailwind": { "config": "", "css": "src/index.css", "baseColor": "stone", "cssVariables": true, "prefix": "" },
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "iconLibrary": "lucide"
}
```

`frontend/src/index.css` ("Quiet paper" tokens, BUILD.md §8.5; fonts are bundled in M6, system fallbacks until then):

```css
@import "tailwindcss";

@custom-variant dark (&:where(.dark, .dark *));

:root {
  --paper: #faf9f6;
  --ink: #1c1b19;
  --muted-ink: #6b6760;
  --accent: #0f6e6e;
  --rec: #d64545;
  --line: #e7e4dd;
}

.dark {
  --paper: #161514;
  --ink: #edeae4;
  --muted-ink: #9a958c;
  --accent: #4fb3ae;
  --rec: #f06a6a;
  --line: #2a2826;
}

@theme inline {
  --color-paper: var(--paper);
  --color-ink: var(--ink);
  --color-muted-ink: var(--muted-ink);
  --color-accent: var(--accent);
  --color-rec: var(--rec);
  --color-line: var(--line);
  --font-sans: "Inter", ui-sans-serif, system-ui, sans-serif;
  --font-serif: "Newsreader", "Source Serif 4", ui-serif, Georgia, serif;
}

body {
  @apply bg-paper text-ink font-sans antialiased;
}
```

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";
import { followSystemTheme } from "./theme";

followSystemTheme();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

`frontend/src/App.tsx`:

```tsx
import { useEffect, useState } from "react";
import { getApi, onEvent, type AppInfo } from "@/bridge";

// M0 bootstrap screen: proves both bridge directions. Replaced by the real UI from M3.
export default function App() {
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [reply, setReply] = useState("");
  const [lastEvent, setLastEvent] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const off = onEvent("app.hello", (payload) => setLastEvent(JSON.stringify(payload)));
    getApi()
      .then(async (api) => {
        setInfo(await api.app_info());
        await api.request_hello();
      })
      .catch((e: unknown) => setError(e instanceof Error ? e.message : String(e)));
    return off;
  }, []);

  async function handlePing() {
    try {
      const api = await getApi();
      setReply((await api.ping("hello")).reply);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  }

  return (
    <main className="mx-auto max-w-xl p-10">
      <h1 className="font-serif text-3xl">{info ? `${info.name} ${info.version}` : "Evra"}</h1>
      <p className="mt-2 text-muted-ink">Bootstrap check: the window talks to Python.</p>
      <button
        type="button"
        onClick={handlePing}
        className="mt-6 rounded-md bg-accent px-4 py-2 text-paper"
      >
        Ping Python
      </button>
      {reply && (
        <p role="status" className="mt-4">
          {reply}
        </p>
      )}
      {lastEvent && (
        <p data-testid="last-event" className="mt-2 text-sm text-muted-ink">
          {lastEvent}
        </p>
      )}
      {error && (
        <p role="alert" className="mt-4 text-rec">
          {error}
        </p>
      )}
    </main>
  );
}
```

- [ ] **Step 6: Run tests, lint, typecheck and build**

Run: `npm --prefix frontend run test`, `npm --prefix frontend run lint`, `npm --prefix frontend run typecheck`, `npm --prefix frontend run build`
Expected:
- Tests: all pass.
- Lint and typecheck: clean.
- Build: writes exactly one file, `src/evra/ui/web/index.html`, with JS and CSS inlined. Check with `Get-ChildItem src/evra/ui/web`, which should show only `index.html`.

If lint flags `react-refresh/only-export-components` on `bridge.ts`/`theme.ts`, that rule only applies to component files; fix it through the ESLint config's file globs, not by restructuring the code.

- [ ] **Step 7: Commit and push**

Append to `PROGRESS.md`: `- Task 5: React/TS/Tailwind v4 frontend with bridge client, theme, shadcn conventions; single-file build into src/evra/ui/web.`

```powershell
git add frontend .gitignore PROGRESS.md
git status --short   # confirm no node_modules or src/evra/ui/web files are staged
git commit -m "feat: react frontend scaffold with python bridge client" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin core
```

---

### Task 6: Python bridge, event bus, window and `evra run`

**Files:**
- Create: `src/evra/bridge/__init__.py`, `src/evra/bridge/api.py`, `src/evra/bridge/events.py`, `src/evra/ui/__init__.py`, `src/evra/ui/window.py`, `src/evra/app.py`, `tests/unit/test_bridge.py`, `tests/unit/test_window.py`, `tests/unit/test_app.py`
- Modify: `src/evra/__main__.py` (add the `run` subcommand), `tests/unit/test_cli.py`

**Interfaces:**
- Consumes:
  - From Task 2: `AppPaths`, `load_settings`, `debug_enabled`.
  - From Task 3: `configure_logging`.
  - From Task 4: `connect`, `migrate`.
  - From Task 5: the JS contract `window.__evraEmit(name, payload)` and the `EvraApi` method names.
- Produces:
  - `BridgeApi(*, app_name: str, version: str, bus: EventBus)` with public methods `ping(message: str) -> PingReply`, `app_info() -> AppInfoDict` and `request_hello() -> None`
  - `EventBus` with `attach(runner: JsRunner) -> None` and `emit(name: str, payload: Mapping[str, Any]) -> bool`
  - `build_emit_script(name: str, payload: Mapping[str, Any]) -> str`
  - `resolve_ui_url(*, dev: bool, web_dir: Path = WEB_DIR) -> str`
  - `UiNotBuiltError`
  - `open_main_window(*, url: str, api: BridgeApi, bus: EventBus, debug: bool) -> None`
  - `App` dataclass and `build_app(paths: AppPaths, *, debug: bool) -> App`
  - `run_app(*, dev: bool, debug: bool, paths: AppPaths | None = None, web_dir: Path | None = None, opener: WindowOpener = open_main_window) -> int`. When `paths` is `None` it uses `resolve_paths()` from Task 2, so a source checkout writes to `<repo>/.data`.
  - CLI: `evra run [--dev] [--debug] [--data-dir PATH]`

- [ ] **Step 1: Add pywebview**

```powershell
uv add pywebview
```

- [ ] **Step 2: Write failing tests**

`tests/unit/test_bridge.py`:

```python
import json
from typing import Any

import pytest

from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus, build_emit_script


class FakeWindow:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def run_js(self, script: str) -> Any:
        self.scripts.append(script)
        return None


def _payload_from(script: str) -> Any:
    prefix = 'window.__evraEmit && window.__evraEmit("app.hello", '
    assert script.startswith(prefix) and script.endswith(");")
    return json.loads(script[len(prefix) : -2])


def test_api_surface_is_only_the_intended_methods() -> None:
    api = BridgeApi(app_name="Evra", version="0.1.0", bus=EventBus())
    public = sorted(n for n in dir(api) if not n.startswith("_"))
    assert public == ["app_info", "ping", "request_hello"]


def test_ping_and_app_info() -> None:
    api = BridgeApi(app_name="Evra", version="0.1.0", bus=EventBus())
    assert api.ping("hello") == {"reply": "pong: hello"}
    assert api.app_info() == {"name": "Evra", "version": "0.1.0"}


def test_request_hello_pushes_event_to_window() -> None:
    bus = EventBus()
    window = FakeWindow()
    bus.attach(window)
    BridgeApi(app_name="Evra", version="0.1.0", bus=bus).request_hello()
    [script] = window.scripts
    assert _payload_from(script) == {"message": "Python is connected"}


def test_emit_without_window_returns_false() -> None:
    assert EventBus().emit("app.hello", {"a": 1}) is False


@pytest.mark.parametrize(
    "payload",
    [
        {"text": 'she said "stop"'},
        {"text": "line one\nline two\r\n\ttab"},
        {"text": "</script><script>alert(1)</script>"},
        {"text": "தமிழ் हिन्दी 中文 🎙️", "sep": "\u2028\u2029"},
        {"nested": {"list": [1, 2.5, None, True]}},
    ],
)
def test_emit_script_round_trips_awkward_payloads(payload: dict[str, Any]) -> None:
    script = build_emit_script("app.hello", payload)
    assert script.isascii()
    assert _payload_from(script) == payload


@pytest.mark.parametrize("name", ["", "App.Hello", "a b", "x" * 65, "1abc", "a;alert(1)"])
def test_invalid_event_names_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        build_emit_script(name, {})
```

`tests/unit/test_window.py`:

```python
from pathlib import Path

import pytest
from webview.util import is_local_url

from evra.ui.window import DEV_SERVER_URL, UiNotBuiltError, resolve_ui_url


def test_dev_mode_uses_vite_dev_server() -> None:
    assert resolve_ui_url(dev=True) == DEV_SERVER_URL == "http://127.0.0.1:5173"


def test_built_mode_uses_file_url(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    url = resolve_ui_url(dev=False, web_dir=tmp_path)
    assert url.startswith("file:///")
    assert url.endswith("/index.html")


def test_file_url_encodes_spaces_and_unicode(tmp_path: Path) -> None:
    web = tmp_path / "GEN AI" / "Mākil"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<html></html>", encoding="utf-8")
    url = resolve_ui_url(dev=False, web_dir=web)
    assert " " not in url
    assert "GEN%20AI" in url
    assert url.isascii()


def test_missing_build_raises_with_hint(tmp_path: Path) -> None:
    with pytest.raises(UiNotBuiltError, match="npm --prefix frontend run build"):
        resolve_ui_url(dev=False, web_dir=tmp_path)


def test_our_urls_never_start_pywebviews_http_server(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    assert not is_local_url(resolve_ui_url(dev=False, web_dir=tmp_path))
    assert not is_local_url(resolve_ui_url(dev=True))
```

`tests/unit/test_app.py`:

```python
from pathlib import Path

import pytest

from evra.app import build_app, run_app
from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.migrate import current_version


def test_build_app_creates_dirs_logs_and_migrated_db(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path)
    app = build_app(paths, debug=False)
    assert paths.db_path.exists()
    assert current_version(connect(paths.db_path)) == 1
    assert (paths.log_dir / "evra.log").exists()
    assert app.api.app_info()["name"] == "Evra"


def test_run_app_without_built_ui_exits_2_with_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_app(
        dev=False, debug=False, paths=AppPaths.under(tmp_path), web_dir=tmp_path / "missing"
    )
    assert code == 2
    assert "npm --prefix frontend run build" in capsys.readouterr().err


def test_run_app_opens_window_with_file_url(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html></html>", encoding="utf-8")
    calls: list[str] = []

    def fake_opener(*, url: str, api: BridgeApi, bus: EventBus, debug: bool) -> None:
        calls.append(url)

    code = run_app(
        dev=False,
        debug=False,
        paths=AppPaths.under(tmp_path / "home"),
        web_dir=web,
        opener=fake_opener,
    )
    assert code == 0
    assert len(calls) == 1 and calls[0].startswith("file:///")
```

Add `from pathlib import Path` to the imports of `tests/unit/test_cli.py`, then add:

```python
def test_run_subcommand_is_registered() -> None:
    from evra.__main__ import build_parser

    args = build_parser().parse_args(["run", "--dev", "--debug", "--data-dir", "D:/x y"])
    assert args.command == "run" and args.dev is True and args.debug is True
    assert str(args.data_dir) == str(Path("D:/x y"))


def test_run_without_data_dir_defaults_to_none() -> None:
    from evra.__main__ import build_parser

    assert build_parser().parse_args(["run"]).data_dir is None
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run pytest tests/unit -v`
Expected: the new tests FAIL with `ModuleNotFoundError: No module named 'evra.bridge'`, and the CLI test fails because the `run` subcommand is missing.

- [ ] **Step 4: Implement**

`src/evra/bridge/events.py`:

```python
"""Python -> React events: window.__evraEmit(name, payload) (see frontend/src/bridge.ts)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Protocol

_EVENT_NAME = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")


class JsRunner(Protocol):
    def run_js(self, script: str) -> Any: ...


def build_emit_script(name: str, payload: Mapping[str, Any]) -> str:
    """Serialise to ASCII-only JSON, which is also a valid JS expression."""
    if not _EVENT_NAME.match(name):
        raise ValueError(f"invalid event name: {name!r}")
    body = json.dumps(dict(payload), ensure_ascii=True, separators=(",", ":"))
    body = body.replace("</", "<\\/")
    return f"window.__evraEmit && window.__evraEmit({json.dumps(name)}, {body});"


class EventBus:
    def __init__(self) -> None:
        self._runner: JsRunner | None = None

    def attach(self, runner: JsRunner) -> None:
        self._runner = runner

    def emit(self, name: str, payload: Mapping[str, Any]) -> bool:
        """Push an event to the UI. Returns False if no window is attached yet."""
        script = build_emit_script(name, payload)
        if self._runner is None:
            return False
        self._runner.run_js(script)
        return True
```

Note: `"<\\/"` is still valid JSON (`\/` is an allowed escape), so `json.loads` round-trips it. That's what the `</script>` test case checks.

`src/evra/bridge/api.py`:

```python
"""Methods React can call as window.pywebview.api.<name>(...).

pywebview exposes every public attribute, so keep state in underscore attributes.
"""

from __future__ import annotations

from typing import TypedDict

from evra.bridge.events import EventBus


class PingReply(TypedDict):
    reply: str


class AppInfoDict(TypedDict):
    name: str
    version: str


class BridgeApi:
    def __init__(self, *, app_name: str, version: str, bus: EventBus) -> None:
        self._app_name = app_name
        self._version = version
        self._bus = bus

    def ping(self, message: str) -> PingReply:
        return {"reply": f"pong: {message}"}

    def app_info(self) -> AppInfoDict:
        return {"name": self._app_name, "version": self._version}

    def request_hello(self) -> None:
        """Proves the Python -> React push path."""
        self._bus.emit("app.hello", {"message": "Python is connected"})
```

`src/evra/ui/window.py`:

```python
"""The pywebview main window (BUILD.md §4.3). Never start pywebview's HTTP server (D6)."""

from __future__ import annotations

from pathlib import Path

from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus
from evra.constants import APP_NAME

DEV_SERVER_URL = "http://127.0.0.1:5173"
WEB_DIR = Path(__file__).parent / "web"
PAPER = "#FAF9F6"


class UiNotBuiltError(RuntimeError):
    pass


def resolve_ui_url(*, dev: bool, web_dir: Path = WEB_DIR) -> str:
    if dev:
        return DEV_SERVER_URL
    index = web_dir / "index.html"
    if not index.is_file():
        raise UiNotBuiltError(
            f"The UI is not built ({index} is missing). Run: npm --prefix frontend run build"
        )
    return index.resolve().as_uri()


def open_main_window(*, url: str, api: BridgeApi, bus: EventBus, debug: bool) -> None:
    import webview  # imported here: loads pythonnet/WebView2 only when a window is needed
    from webview.util import is_local_url

    if is_local_url(url):
        raise RuntimeError(f"refusing {url!r}: it would start pywebview's HTTP server")
    window = webview.create_window(
        APP_NAME,
        url=url,
        js_api=api,
        width=1100,
        height=720,
        min_size=(720, 480),
        background_color=PAPER,
    )
    if window is None:
        raise RuntimeError("pywebview did not create a window")
    bus.attach(window)
    webview.start(debug=debug, private_mode=True)
```

`src/evra/app.py`:

```python
"""Application container and startup (BUILD.md §4)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import structlog

from evra import __version__
from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus
from evra.config import Settings, debug_enabled, load_settings
from evra.constants import APP_NAME
from evra.logging_setup import configure_logging
from evra.paths import AppPaths, resolve_paths
from evra.store.db import connect
from evra.store.migrate import migrate
from evra.ui.window import WEB_DIR, UiNotBuiltError, open_main_window, resolve_ui_url

log = structlog.get_logger(__name__)


class WindowOpener(Protocol):
    def __call__(self, *, url: str, api: BridgeApi, bus: EventBus, debug: bool) -> None: ...


@dataclass
class App:
    paths: AppPaths
    settings: Settings
    bus: EventBus
    api: BridgeApi
    debug: bool


def build_app(paths: AppPaths, *, debug: bool) -> App:
    paths.ensure()
    configure_logging(paths.log_dir, debug=debug)
    settings = load_settings(paths.settings_file)
    conn = connect(paths.db_path)
    try:
        schema = migrate(conn)
    finally:
        conn.close()
    bus = EventBus()
    api = BridgeApi(app_name=APP_NAME, version=__version__, bus=bus)
    log.info("app_started", version=__version__, schema_version=schema)
    return App(paths=paths, settings=settings, bus=bus, api=api, debug=debug)


def run_app(
    *,
    dev: bool,
    debug: bool,
    paths: AppPaths | None = None,
    web_dir: Path | None = None,
    opener: WindowOpener = open_main_window,
) -> int:
    try:
        url = resolve_ui_url(dev=dev, web_dir=web_dir or WEB_DIR)
    except UiNotBuiltError as exc:
        print(exc, file=sys.stderr)
        return 2
    app = build_app(paths or resolve_paths(), debug=debug or debug_enabled())
    opener(url=url, api=app.api, bus=app.bus, debug=app.debug)
    return 0
```

Update `src/evra/__main__.py`: replace `build_parser` and `main` with:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME} desktop app")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    commands = parser.add_subparsers(dest="command")
    run = commands.add_parser("run", help="open the Evra window")
    run.add_argument("--dev", action="store_true", help="load the Vite dev server (development)")
    run.add_argument("--debug", action="store_true", help="DEBUG logs and WebView devtools")
    run.add_argument(
        "--data-dir", type=Path, default=None,
        help="keep all app data here (default: <repo>/.data from source, else per-user dirs)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        from evra.app import run_app  # keeps `evra --version` fast
        from evra.paths import resolve_paths

        return run_app(dev=args.dev, debug=args.debug, paths=resolve_paths(args.data_dir))
    parser.print_help()
    return 0
```

Add `from pathlib import Path` to the imports of `src/evra/__main__.py`. Create empty `src/evra/bridge/__init__.py` and `src/evra/ui/__init__.py`.

- [ ] **Step 5: Run tests and tools**

Run: `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`
Expected: all pass.

- [ ] **Step 6: Manual smoke test — built UI via `file://`, no listening socket**

```powershell
npm --prefix frontend run build
$p = Start-Process -PassThru uv -ArgumentList "run","evra","run"
Start-Sleep 8
Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
  Where-Object { (Get-Process -Id $_.OwningProcess).Name -like "python*" }
```

Expected:
- The window shows **"Evra 0.1.0"** in serif type on the paper background.
- It shows the pushed event `{"message":"Python is connected"}`.
- Clicking **Ping Python** shows `pong: hello`.
- The `Get-NetTCPConnection` command prints **nothing**, meaning no Python listening socket.

Close the window.

**If the window is blank** (WebView2 refused the `file://` page), do not fall back to a relative URL. Write a spike in `spikes/virtual_host.py` that maps a virtual host to `src/evra/ui/web` using WebView2's `CoreWebView2.SetVirtualHostNameToFolderMapping`, reached through pywebview's `window.native` object. Read `webview/platforms/edgechromium.py` in the installed package to find the `CoreWebView2` instance. Then load `https://evra.local/index.html`, record an ADR in `DECISIONS.md`, and move the working code into `open_main_window`.

- [ ] **Step 7: Manual smoke test — dev mode**

```powershell
Start-Process npm -ArgumentList "--prefix","frontend","run","dev"
uv run evra run --dev --debug
```

Expected: the same screen, with DevTools available. Editing `App.tsx` hot-reloads. Stop the dev server afterwards.

- [ ] **Step 8: Commit and push**

Append to `PROGRESS.md`: `- Task 6: pywebview window loads the single-file UI via file:// (no listener, verified); bridge both ways; \`evra run [--dev] [--debug]\`.`

```powershell
git add src/evra tests PROGRESS.md pyproject.toml uv.lock
git commit -m "feat: pywebview window with python-react bridge and evra run" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin core
```

---

### Task 7: Licence gate, model catalogue and third-party register

**Files:**
- Create: `models.yaml`, `tools/__init__.py`, `tools/license_policy.yaml`, `tools/license_gate.py`, `tests/tools/__init__.py`, `tests/tools/test_license_gate.py`, `THIRD_PARTY_LICENSES.md` (generated)

**Interfaces:**
- Consumes: `uv.lock` / the environment (via `pip-licenses` and `uv export`), `frontend/package-lock.json`, `models.yaml`.
- Produces:
  - `Component(kind: Literal["python", "npm", "model"], name: str, version: str, licence: str, runtime: bool, attribution: str = "")`
  - `Policy.load(path: Path) -> Policy`
  - `licence_ok(expression: str, allowed: frozenset[str], aliases: Mapping[str, str]) -> bool`
  - `evaluate(component: Component, policy: Policy) -> str | None` (the reason for a violation, or `None`)
  - `python_components(pip_licenses_json: str, runtime_names: set[str]) -> list[Component]`
  - `npm_components(lock: Mapping[str, Any]) -> list[Component]`
  - `model_components(catalogue: Mapping[str, Any]) -> list[Component]`
  - `render_register(components: Sequence[Component]) -> str`
  - `main(argv: Sequence[str] | None = None) -> int`

- [ ] **Step 1: Add dev dependencies**

```powershell
uv add --dev pip-licenses pyyaml types-PyYAML
```

- [ ] **Step 2: Write `models.yaml` and `tools/license_policy.yaml`**

`models.yaml`:

```yaml
# Every model Evra downloads (BUILD.md §4.5). Weights are never committed.
# Entry shape:
#   - id: parakeet-tdt-0.6b-v3-int8
#     source: {type: huggingface, repo: owner/name}      # or {type: url, url: ...}
#     licence: CC-BY-4.0
#     files: [{name: model.onnx, sha256: <hex>}]
#     size_mb: 640
#     loaded: during_meeting | after_meeting | on_demand
#     attribution: "Speech recognition uses ... (CC BY 4.0)."
models: []
```

`tools/license_policy.yaml`:

```yaml
# Licence policy (BUILD.md §9.2). SPDX ids. Anything not allowed fails.
allowed_runtime:
  - MIT
  - BSD
  - BSD-2-Clause
  - BSD-3-Clause
  - 0BSD
  - Apache-2.0
  - ISC
  - PSF-2.0
  - Python-2.0
  - Unlicense
  - Zlib
  - CC-BY-4.0
  - CC0-1.0
  - OFL-1.1
  - BlueOak-1.0.0
allowed_dev_extra:
  - MPL-2.0
# LGPL only for these packages (dynamically linked, replaceable). Name: reason.
lgpl_allowed: {}
# Free-text licence strings seen in package metadata -> SPDX id.
aliases:
  "MIT License": MIT
  "BSD License": BSD
  "Apache Software License": Apache-2.0
  "Apache 2.0": Apache-2.0
  "Apache License 2.0": Apache-2.0
  "Apache License, Version 2.0": Apache-2.0
  "ISC License (ISCL)": ISC
  "Python Software Foundation License": PSF-2.0
  "Mozilla Public License 2.0 (MPL 2.0)": MPL-2.0
  "The Unlicense (Unlicense)": Unlicense
  "zlib/libpng License": Zlib
# When metadata is missing or wrong: {kind: {name: {licence: SPDX, source: URL}}}.
# Only record what the project's own LICENSE file says, with the URL you checked.
overrides:
  python: {}
  npm: {}
```

- [ ] **Step 3: Write failing tests** `tests/tools/test_license_gate.py` (plus empty `tests/tools/__init__.py`, `tools/__init__.py`)

```python
import json
from pathlib import Path

import pytest

from tools.license_gate import (
    Component,
    Policy,
    evaluate,
    licence_ok,
    model_components,
    npm_components,
    python_components,
    render_register,
)

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def policy() -> Policy:
    return Policy.load(ROOT / "tools" / "license_policy.yaml")


def _c(licence: str, *, runtime: bool = True, name: str = "pkg") -> Component:
    return Component(kind="python", name=name, version="1.0", licence=licence, runtime=runtime)


@pytest.mark.parametrize(
    ("expr", "ok"),
    [
        ("MIT", True),
        ("MIT License", True),
        ("Apache Software License; BSD License", True),
        ("MIT OR GPL-3.0-only", True),
        ("MIT AND GPL-3.0-only", False),
        ("GPL-3.0-only", False),
        ("AGPL-3.0", False),
        ("CC-BY-NC-4.0", False),
        ("UNKNOWN", False),
        ("", False),
        ("(MIT OR Apache-2.0)", True),
    ],
)
def test_licence_expressions(policy: Policy, expr: str, ok: bool) -> None:
    assert licence_ok(expr, policy.allowed_runtime, policy.aliases) is ok


def test_mpl_is_dev_only(policy: Policy) -> None:
    assert evaluate(_c("MPL-2.0", runtime=False), policy) is None
    reason = evaluate(_c("MPL-2.0", runtime=True), policy)
    assert reason is not None and "runtime" in reason


def test_lgpl_only_for_listed_packages(policy: Policy) -> None:
    listed = Policy(
        allowed_runtime=policy.allowed_runtime,
        allowed_dev_extra=policy.allowed_dev_extra,
        lgpl_allowed={"pyside6": "dynamically linked Qt"},
        aliases=policy.aliases,
        overrides=policy.overrides,
    )
    assert evaluate(_c("LGPL-3.0-only", name="pyside6"), listed) is None
    assert evaluate(_c("LGPL-3.0-only", name="other"), listed) is not None


def test_override_replaces_metadata(policy: Policy) -> None:
    overridden = Policy(
        allowed_runtime=policy.allowed_runtime,
        allowed_dev_extra=policy.allowed_dev_extra,
        lgpl_allowed=policy.lgpl_allowed,
        aliases=policy.aliases,
        overrides={"python": {"weird": {"licence": "MIT", "source": "https://x"}}, "npm": {}},
    )
    assert evaluate(_c("UNKNOWN", name="weird"), overridden) is None


def test_python_components_marks_runtime() -> None:
    data = json.dumps(
        [
            {"Name": "Pydantic", "Version": "2.0", "License": "MIT"},
            {"Name": "pytest", "Version": "9.0", "License": "MIT License"},
        ]
    )
    comps = {c.name: c for c in python_components(data, runtime_names={"pydantic"})}
    assert comps["pydantic"].runtime is True
    assert comps["pytest"].runtime is False


def test_npm_components_from_lockfile() -> None:
    lock = {
        "packages": {
            "": {"name": "evra-frontend"},
            "node_modules/react": {"version": "19.3.0", "license": "MIT"},
            "node_modules/vitest": {"version": "5.0.1", "license": "MIT", "dev": True},
            "node_modules/@scope/pkg": {"version": "1.0.0"},
        }
    }
    comps = {c.name: c for c in npm_components(lock)}
    assert comps["react"].runtime is True
    assert comps["vitest"].runtime is False
    assert comps["@scope/pkg"].licence == ""


def test_model_components_and_register() -> None:
    catalogue = {
        "models": [
            {
                "id": "vad",
                "source": {"type": "url", "url": "https://example"},
                "licence": "MIT",
                "files": [],
                "size_mb": 2,
                "loaded": "during_meeting",
                "attribution": "Silero VAD (MIT).",
            }
        ]
    }
    [model] = model_components(catalogue)
    assert model.kind == "model" and model.runtime is True
    register = render_register([model, _c("MIT", name="pydantic")])
    assert "Silero VAD (MIT)." in register
    assert "| pydantic | 1.0 | MIT |" in register
```

- [ ] **Step 4: Run to verify failure**

Run: `uv run pytest tests/tools -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.license_gate'`.

- [ ] **Step 5: Implement** `tools/license_gate.py`

```python
"""Licence gate (BUILD.md §9.2): Python + npm packages + models; writes THIRD_PARTY_LICENSES.md.

Usage:
    uv run python tools/license_gate.py                    # check (CI and tools/check.py)
    uv run python tools/license_gate.py --write-register   # regenerate THIRD_PARTY_LICENSES.md
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import yaml

ROOT = Path(__file__).resolve().parents[1]
REGISTER = ROOT / "THIRD_PARTY_LICENSES.md"
Kind = Literal["python", "npm", "model"]


@dataclass(frozen=True)
class Component:
    kind: Kind
    name: str
    version: str
    licence: str
    runtime: bool
    attribution: str = ""


@dataclass(frozen=True)
class Policy:
    allowed_runtime: frozenset[str]
    allowed_dev_extra: frozenset[str]
    lgpl_allowed: Mapping[str, str]
    aliases: Mapping[str, str]
    overrides: Mapping[str, Mapping[str, Mapping[str, str]]] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> Policy:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
        return cls(
            allowed_runtime=frozenset(raw["allowed_runtime"]),
            allowed_dev_extra=frozenset(raw["allowed_dev_extra"]),
            lgpl_allowed=dict(raw.get("lgpl_allowed") or {}),
            aliases=dict(raw.get("aliases") or {}),
            overrides={k: dict(v or {}) for k, v in (raw.get("overrides") or {}).items()},
        )


def _normalise_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _term_ok(term: str, allowed: frozenset[str], aliases: Mapping[str, str]) -> bool:
    term = term.strip().strip("()").strip()
    return bool(term) and aliases.get(term, term) in allowed


def licence_ok(expression: str, allowed: frozenset[str], aliases: Mapping[str, str]) -> bool:
    """OR-alternatives: any may pass. Within one alternative, AND / ';' parts must all pass."""
    expression = expression.strip()
    if not expression:
        return False
    if aliases.get(expression, expression) in allowed:
        return True
    for alternative in re.split(r"\s+OR\s+", expression.strip("()")):
        parts = re.split(r"\s+AND\s+|;", alternative)
        if all(_term_ok(p, allowed, aliases) for p in parts):
            return True
    return False


def evaluate(component: Component, policy: Policy) -> str | None:
    override = policy.overrides.get(component.kind, {}).get(component.name)
    licence = override["licence"] if override else component.licence
    if "LGPL" in licence.upper() and component.name in policy.lgpl_allowed:
        return None
    allowed = policy.allowed_runtime
    if not component.runtime:
        allowed = allowed | policy.allowed_dev_extra
    if licence_ok(licence, allowed, policy.aliases):
        return None
    use = "runtime" if component.runtime else "dev"
    return f"licence {licence!r} is not allowed for {use} use"


def python_components(pip_licenses_json: str, runtime_names: set[str]) -> list[Component]:
    runtime = {_normalise_name(n) for n in runtime_names}
    out: list[Component] = []
    for row in json.loads(pip_licenses_json):
        name = _normalise_name(row["Name"])
        out.append(
            Component("python", name, row["Version"], row["License"], name in runtime)
        )
    return out


def npm_components(lock: Mapping[str, Any]) -> list[Component]:
    out: list[Component] = []
    for key, meta in lock.get("packages", {}).items():
        if not key.startswith("node_modules/"):
            continue
        name = key.rsplit("node_modules/", 1)[1]
        licence = meta.get("license", "")
        if isinstance(licence, dict):  # very old package.json style {"type": "MIT"}
            licence = str(licence.get("type", ""))
        out.append(
            Component("npm", name, str(meta.get("version", "")), str(licence), not meta.get("dev"))
        )
    return out


def model_components(catalogue: Mapping[str, Any]) -> list[Component]:
    return [
        Component(
            "model",
            str(m["id"]),
            str(m.get("source", {}).get("repo") or m.get("source", {}).get("url", "")),
            str(m["licence"]),
            True,
            str(m.get("attribution", "")),
        )
        for m in catalogue.get("models") or []
    ]


def render_register(components: Sequence[Component]) -> str:
    lines = [
        "# Third-party licences",
        "",
        "Generated by `tools/license_gate.py --write-register`. Do not edit by hand.",
        "",
    ]
    for kind, title in (("model", "Models"), ("python", "Python packages"), ("npm", "npm packages")):
        rows = sorted((c for c in components if c.kind == kind and c.runtime), key=lambda c: c.name)
        if not rows:
            continue
        lines += [f"## {title}", ""]
        if kind == "model":
            lines += ["| Model | Source | Licence | Attribution |", "| --- | --- | --- | --- |"]
            lines += [f"| {c.name} | {c.version} | {c.licence} | {c.attribution} |" for c in rows]
        else:
            lines += ["| Package | Version | Licence |", "| --- | --- | --- |"]
            lines += [f"| {c.name} | {c.version} | {c.licence} |" for c in rows]
        lines.append("")
    return "\n".join(lines)


def _run(argv: list[str]) -> str:
    return subprocess.run(argv, check=True, capture_output=True, text=True, cwd=ROOT).stdout


def _runtime_python_names() -> set[str]:
    uv = shutil.which("uv") or "uv"
    text = _run(
        [uv, "export", "--no-dev", "--no-hashes", "--no-emit-project",
         "--format", "requirements-txt"]
    )
    names = set()
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==", line.strip())
        if match:
            names.add(match.group(1))
    return names


def collect(root: Path = ROOT) -> list[Component]:
    pip_json = _run([sys.executable, "-m", "piplicenses", "--format=json", "--from=mixed"])
    comps = python_components(pip_json, _runtime_python_names())
    lock_file = root / "frontend" / "package-lock.json"
    if lock_file.exists():
        comps += npm_components(json.loads(lock_file.read_text(encoding="utf-8")))
    catalogue = yaml.safe_load((root / "models.yaml").read_text(encoding="utf-8")) or {}
    comps += model_components(catalogue)
    return comps


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-register", action="store_true")
    args = parser.parse_args(argv)

    policy = Policy.load(ROOT / "tools" / "license_policy.yaml")
    comps = [c for c in collect() if c.name != "evra"]
    failures = [(c, r) for c in comps if (r := evaluate(c, policy)) is not None]
    for comp, reason in failures:
        print(f"FAIL {comp.kind}:{comp.name} {comp.version} — {reason}")

    register = render_register(comps)
    if args.write_register:
        REGISTER.write_text(register, encoding="utf-8")
        print(f"wrote {REGISTER.name}")
    elif not REGISTER.exists() or REGISTER.read_text(encoding="utf-8") != register:
        print("FAIL THIRD_PARTY_LICENSES.md is stale: run tools/license_gate.py --write-register")
        failures.append((Component("python", "register", "", "", False), "stale"))

    print(f"licence gate: {len(comps)} components, {len(failures)} problems")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Run the unit tests**

Run: `uv run pytest tests/tools -v`
Expected: all pass.

- [ ] **Step 7: Run the real gate and resolve findings**

Run: `uv run python tools/license_gate.py --write-register` then `uv run python tools/license_gate.py`

For each `FAIL`:
1. Open the package's own repository `LICENSE` file (PyPI "Homepage"/"Source" link, or the npm package page).
2. If the real licence is allowed and only the metadata string is odd, add it to `aliases` (if the string is generic) or `overrides` (with the `source` URL you checked).
3. If the real licence is **not** allowed (GPL, AGPL, non-commercial, unknown), stop. Remove or replace the dependency and write a `DECISIONS.md` entry. Never override a disallowed licence.

Expected end state: `licence gate: N components, 0 problems`, with `THIRD_PARTY_LICENSES.md` written.

- [ ] **Step 8: Run all Python tools**

Run: `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy`
Expected: all pass.

- [ ] **Step 9: Commit and push**

Append to `PROGRESS.md`: `- Task 7: licence gate (python + npm + models), policy file, models.yaml, generated THIRD_PARTY_LICENSES.md.`

```powershell
git add models.yaml tools tests/tools THIRD_PARTY_LICENSES.md pyproject.toml uv.lock PROGRESS.md
git commit -m "feat: licence gate and third-party licence register" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin core
```

---

### Task 8: One-command checks (`tools/check.py`)

**Files:**
- Create: `tools/check.py`, `tests/tools/test_check.py`

**Interfaces:**
- Consumes: the npm scripts `lint`, `typecheck` and `test` (Task 5) and `tools/license_gate.py` (Task 7).
- Produces:
  - `Step(name: str, argv: list[str])`
  - `default_steps() -> list[Step]`
  - `run_steps(steps: Sequence[Step], runner: Runner = _subprocess_runner) -> list[tuple[str, bool]]`
  - `main(argv: Sequence[str] | None = None, runner: Runner = _subprocess_runner) -> int`

- [ ] **Step 1: Write failing tests** `tests/tools/test_check.py`

```python
from collections.abc import Sequence

from tools.check import Step, default_steps, main, run_steps


def _runner(fail: set[str]):  # type: ignore[no-untyped-def]
    seen: list[str] = []

    def run(argv: Sequence[str]) -> int:
        seen.append(" ".join(argv))
        return 1 if any(f in " ".join(argv) for f in fail) else 0

    return run, seen


def test_default_steps_cover_every_check() -> None:
    names = [s.name for s in default_steps()]
    for expected in ["ruff lint", "ruff format", "mypy", "pytest", "eslint", "tsc", "vitest",
                     "licence gate"]:
        assert expected in names


def test_run_steps_reports_each_result() -> None:
    run, _ = _runner(fail={"bad"})
    results = run_steps([Step("a", ["ok"]), Step("b", ["bad"])], runner=run)
    assert results == [("a", True), ("b", False)]


def test_main_fails_if_any_step_fails_and_runs_all() -> None:
    run, seen = _runner(fail={"mypy"})
    assert main([], runner=run) == 1
    assert len(seen) >= 8  # later steps still ran


def test_main_skip() -> None:
    run, seen = _runner(fail={"mypy"})
    assert main(["--skip", "mypy"], runner=run) == 0
    assert not any("mypy" in s for s in seen)
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/tools/test_check.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.check'`.

- [ ] **Step 3: Implement** `tools/check.py`

```python
"""Run every check (BUILD.md §9.2). Must pass before every commit (D22).

    uv run python tools/check.py [--skip NAME ...]
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
Runner = Callable[[Sequence[str]], int]


@dataclass(frozen=True)
class Step:
    name: str
    argv: list[str]


def _subprocess_runner(argv: Sequence[str]) -> int:
    return subprocess.run(list(argv), cwd=ROOT, check=False).returncode


def default_steps() -> list[Step]:
    uv = shutil.which("uv") or "uv"
    npm = shutil.which("npm") or "npm"
    steps = [
        Step("ruff lint", [uv, "run", "ruff", "check", "."]),
        Step("ruff format", [uv, "run", "ruff", "format", "--check", "."]),
        Step("mypy", [uv, "run", "mypy"]),
        Step("pytest", [uv, "run", "pytest", "-q"]),
        Step("eslint", [npm, "--prefix", "frontend", "run", "lint"]),
        Step("tsc", [npm, "--prefix", "frontend", "run", "typecheck"]),
        Step("vitest", [npm, "--prefix", "frontend", "run", "test"]),
        Step("licence gate", [uv, "run", "python", "tools/license_gate.py"]),
    ]
    gitleaks = shutil.which("gitleaks")
    if gitleaks:
        steps.append(Step("gitleaks", [gitleaks, "git", "--redact", "--no-banner", str(ROOT)]))
    return steps


def run_steps(
    steps: Sequence[Step], runner: Runner = _subprocess_runner
) -> list[tuple[str, bool]]:
    results: list[tuple[str, bool]] = []
    for step in steps:
        print(f"\n=== {step.name} ===", flush=True)
        results.append((step.name, runner(step.argv) == 0))
    return results


def main(argv: Sequence[str] | None = None, runner: Runner = _subprocess_runner) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip", action="append", default=[], help="step name to skip")
    args = parser.parse_args(argv)
    steps = [s for s in default_steps() if s.name not in set(args.skip)]
    if not any(s.name == "gitleaks" for s in steps) and "gitleaks" not in args.skip:
        print("note: gitleaks not installed locally; it runs in CI")
    results = run_steps(steps, runner)
    print("\n=== summary ===")
    for name, ok in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}")
    return 0 if all(ok for _, ok in results) else 1


if __name__ == "__main__":
    sys.exit(main())
```

Note: `gitleaks git` is the current subcommand. If the installed gitleaks only knows `detect`, run `gitleaks help` and switch to `detect --redact --no-banner`.

- [ ] **Step 4: Run tests, then the real thing**

Run: `uv run pytest tests/tools -v`, then `uv run python tools/check.py`
Expected: tests pass, and every step prints `PASS` in the summary.

- [ ] **Step 5: Commit and push**

Append to `PROGRESS.md`: `- Task 8: tools/check.py runs lint, format, types, tests (py + ts) and the licence gate in one command.`

```powershell
git add tools/check.py tests/tools/test_check.py PROGRESS.md
git commit -m "feat: one-command check runner" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin core
```

---

### Task 9: CI and secret scanning

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `DECISIONS.md`, `BUILD.md` §9.3 (one line; see Step 4)

**Interfaces:**
- Consumes: `tools/check.py` (Task 8), `uv.lock`, `frontend/package-lock.json`.
- Produces: GitHub Actions checks on every push and pull request.

- [ ] **Step 1: Check current action versions**

Open each action's README and use its current major version: `actions/checkout`, `astral-sh/setup-uv`, `actions/setup-node`, `gitleaks/gitleaks-action`. The versions below are the ones known when this plan was written; bump any that have a newer major.

- [ ] **Step 2: Write `.github/workflows/ci.yml`**

```yaml
name: ci

on:
  push:
  pull_request:

permissions:
  contents: read

jobs:
  check:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v6
      - uses: actions/setup-node@v4
        with:
          node-version: 24
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - run: uv python install 3.12
      - run: uv sync --frozen
      - run: npm ci --prefix frontend
      - run: npm --prefix frontend run build
      - run: uv run python tools/check.py --skip gitleaks

  secrets:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 3: Try local gitleaks**

```powershell
winget install --id Gitleaks.Gitleaks -e --accept-source-agreements --accept-package-agreements
gitleaks version
```

Expected: a version string (Smart App Control is off, so the binary should run). Then run `uv run python tools/check.py`, which now includes the gitleaks step. It must report no leaks.
If the command still gets blocked, uninstall it. Local scanning is then unavailable and CI is the gate; use the "blocked" wording in Step 4.

- [ ] **Step 4: Record the outcome**

Append to `DECISIONS.md` (choose the matching sentence):

```markdown

## Secret scanning: CI always, local when available (2026-09-24)
- **Context:** BUILD.md §9.3 asks for gitleaks in CI and before commits.
- **Evidence:** Smart App Control blocked pnpm.exe on 2026-09-24 and was then switched off. Local gitleaks: write "runs (version X)" or "blocked", whichever Step 3 showed.
- **Decision:** gitleaks runs in CI on every push (full history). `tools/check.py` runs it locally whenever `gitleaks` is on PATH.
- **Consequences:** if blocked locally, a secret could reach GitHub before CI flags it; the §9.3 never-commit list and `.gitignore` remain the first line of defence.
```

In `BUILD.md` §9.3, replace the line `- **gitleaks** secret scanning runs in CI and as a pre-commit hook.` with `- **gitleaks** secret scanning runs in CI on every push, and locally through \`tools/check.py\` when gitleaks is installed.`

- [ ] **Step 5: Commit, push, and confirm CI**

Append to `PROGRESS.md`: `- Task 9: GitHub Actions (Windows checks + gitleaks); local gitleaks via tools/check.py.` (Add "— blocked locally, CI only" if Step 3 showed that.)

```powershell
git add .github DECISIONS.md BUILD.md PROGRESS.md
git commit -m "ci: windows checks and gitleaks secret scanning" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git push origin core
```

Then ask the human to open `https://github.com/Makilesh/Evra/actions` and confirm both jobs are green (the `gh` CLI isn't installed). If a job fails, fix it, push again, and repeat.

---

### Task 10: M0 wrap-up

**Files:**
- Modify: `PROGRESS.md`, `BUILD.md` §0 (status line), `CLAUDE.md` (only if commands changed)

**Interfaces:**
- Consumes: everything above.
- Produces: tag `p1-m0-done`.

- [ ] **Step 1: Verify the Definition of Done**

Run: `uv run python tools/check.py`
Expected: all PASS.

Run: `uv run evra --version`
Expected: `Evra 0.1.0`.

Run: `uv run evra run`
Expected: the window works as in Task 6 Step 6.

CI: both jobs green (confirmed by the human).

- [ ] **Step 2: Update tracking**

In `PROGRESS.md` under `## 2026-09-24 — M0 Bootstrap`, add:
- the commit hashes for Tasks 1–9 (`git log --oneline`)
- the line `- **M0 done:** CI green; window round-trips calls both ways; no network listener (verified with Get-NetTCPConnection).`
- `- Next: M1 Windows capture (plan to be written).`

In `BUILD.md` §0, add one line under the table: `Build status: Phase 1 M0 done (tag p1-m0-done).`

- [ ] **Step 3: Commit, tag and push**

```powershell
git add PROGRESS.md BUILD.md CLAUDE.md
git commit -m "docs: record M0 completion" -m "Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>"
git tag -a p1-m0-done -m "Phase 1 M0 bootstrap done"
git push origin core
git push origin p1-m0-done
```
