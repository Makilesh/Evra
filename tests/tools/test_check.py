from collections.abc import Callable, Sequence

from tools.check import Step, default_steps, main, run_steps


def _runner(fail: set[str]) -> tuple[Callable[[Sequence[str]], int], list[str]]:
    seen: list[str] = []

    def run(argv: Sequence[str]) -> int:
        joined = " ".join(argv)
        seen.append(joined)
        return 1 if any(f in joined for f in fail) else 0

    return run, seen


def test_default_steps_cover_every_check() -> None:
    names = [s.name for s in default_steps()]
    for expected in [
        "ruff lint",
        "ruff format",
        "mypy",
        "pytest",
        "frontend lint",
        "tsc",
        "vitest",
        "licence gate",
    ]:
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
