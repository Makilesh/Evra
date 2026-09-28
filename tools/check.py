"""Run every check (BUILD.md §9.2). Must pass before every commit (D22).

Usage: uv run python tools/check.py [--skip NAME ...]
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
        Step("frontend lint", [npm, "--prefix", "frontend", "run", "lint"]),
        Step("tsc", [npm, "--prefix", "frontend", "run", "typecheck"]),
        Step("vitest", [npm, "--prefix", "frontend", "run", "test"]),
        Step("licence gate", [uv, "run", "python", "tools/license_gate.py"]),
    ]
    gitleaks = shutil.which("gitleaks")
    if gitleaks:
        steps.append(Step("gitleaks", [gitleaks, "git", "--redact", "--no-banner", str(ROOT)]))
    return steps


def run_steps(steps: Sequence[Step], runner: Runner = _subprocess_runner) -> list[tuple[str, bool]]:
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
