import argparse
import json
from pathlib import Path

import pytest

from evra.notes.ask_cli import ask_command
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.questions import QuestionStore
from tests.integration.test_note_cli import DownProvider, _recorded
from tests.unit.notes.fakes import FakeProvider

ANSWER = json.dumps(
    {
        "found": True,
        "points": [{"text": "You finished the search migration on Tuesday.", "citations": ["u:1"]}],
    }
)
NOT_FOUND = json.dumps({"found": False, "points": []})


def _args(question: str = "What did you finish?", **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "question": question,
        "meeting_id": None,
        "model": "fake:1b",
        "data_dir": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _stored(paths: AppPaths, mid: str) -> list[tuple[str, str | None]]:
    conn = connect(paths.db_path)
    try:
        return [(q.state, q.reason) for q in QuestionStore(conn).for_meeting(mid)]
    finally:
        conn.close()


def test_prints_the_point_with_its_time(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, mid = _recorded(tmp_path)
    assert ask_command(_args(), paths, provider=FakeProvider([ANSWER])) == 0
    assert "- You finished the search migration on Tuesday. [00:00]" in capsys.readouterr().out
    assert _stored(paths, mid) == [("answered", None)]


def test_not_discussed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, mid = _recorded(tmp_path)
    assert ask_command(_args(meeting_id=mid), paths, provider=FakeProvider([NOT_FOUND])) == 0
    assert "Not discussed in this meeting." in capsys.readouterr().out
    assert _stored(paths, mid) == [("not_found", None)]


def test_failure_exits_1_and_is_stored(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, mid = _recorded(tmp_path)
    assert ask_command(_args(), paths, provider=DownProvider([])) == 1
    assert "Ollama is not running" in capsys.readouterr().err
    assert _stored(paths, mid) == [("failed", "ollama_down")]


def test_no_meetings_and_no_transcript(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert ask_command(_args(), AppPaths.under(tmp_path / "a"), provider=FakeProvider([])) == 2
    assert "No meetings yet" in capsys.readouterr().err
    paths, _ = _recorded(tmp_path / "b", with_utterances=False)
    assert ask_command(_args(), paths, provider=FakeProvider([])) == 2
    assert "no transcript" in capsys.readouterr().err
