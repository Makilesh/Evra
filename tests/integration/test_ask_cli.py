import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from evra.config import LlmSettings, Settings, save_settings
from evra.llm.provider import ChatMessage, LlmModelMissing
from evra.notes.ask_cli import ask_command
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.questions import QuestionStore
from tests.integration.helpers import DownProvider, recorded
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
    paths, mid = recorded(tmp_path)
    assert ask_command(_args(), paths, provider=FakeProvider([ANSWER])) == 0
    assert "- You finished the search migration on Tuesday. [00:00]" in capsys.readouterr().out
    assert _stored(paths, mid) == [("answered", None)]


def test_not_discussed(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, mid = recorded(tmp_path)
    assert ask_command(_args(meeting_id=mid), paths, provider=FakeProvider([NOT_FOUND])) == 0
    assert "Not discussed in this meeting." in capsys.readouterr().out
    assert _stored(paths, mid) == [("not_found", None)]


def test_failure_exits_1_and_is_stored(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, mid = recorded(tmp_path)
    assert ask_command(_args(), paths, provider=DownProvider([])) == 1
    assert "Ollama is not running" in capsys.readouterr().err
    assert _stored(paths, mid) == [("failed", "ollama_down")]


def test_no_meetings_and_no_transcript(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert ask_command(_args(), AppPaths.under(tmp_path / "a"), provider=FakeProvider([])) == 2
    assert "No meetings yet" in capsys.readouterr().err
    paths, _ = recorded(tmp_path / "b", with_utterances=False)
    assert ask_command(_args(), paths, provider=FakeProvider([])) == 2
    assert "no transcript" in capsys.readouterr().err


class OneShot(FakeProvider):
    """Raises `error` from chat_json."""

    def __init__(self, error: BaseException) -> None:
        super().__init__([])
        self.error = error

    def chat_json(self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]):  # type: ignore[no-untyped-def]
        raise self.error


def test_ollama_down_before_a_model_is_chosen(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = recorded(tmp_path)
    save_settings(paths.settings_file, Settings(llm=LlmSettings(model="")))
    assert ask_command(_args(model=None), paths, provider=DownProvider([])) == 1
    assert "Ollama is not running" in capsys.readouterr().err
    assert _stored(paths, mid) == []


def test_missing_model_is_named(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, mid = recorded(tmp_path)
    provider = OneShot(LlmModelMissing("nope:1b"))
    assert ask_command(_args(model="nope:1b"), paths, provider=provider) == 1
    assert "ollama pull nope:1b" in capsys.readouterr().err
    assert _stored(paths, mid) == [("failed", "model_missing")]


def test_unexpected_error_is_stored_as_llm_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = recorded(tmp_path)
    assert ask_command(_args(), paths, provider=OneShot(RuntimeError("x"))) == 1
    assert capsys.readouterr().err.strip()
    assert _stored(paths, mid) == [("failed", "llm_error")]


def test_ctrl_c_stores_interrupted_and_exits_130(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = recorded(tmp_path)
    assert ask_command(_args(), paths, provider=OneShot(KeyboardInterrupt())) == 130
    assert "Stopped." in capsys.readouterr().err
    assert _stored(paths, mid) == [("failed", "interrupted")]


def _long_call(tmp_path: Path) -> tuple[AppPaths, str]:
    """The recorded meeting plus 400 filler lines, with a budget that makes it a long call."""
    paths, mid = recorded(tmp_path)
    conn = connect(paths.db_path)
    try:
        store = MeetingStore(conn)
        version_id = store.current_transcript_version(mid)
        assert version_id is not None
        for i in range(400):
            start = 10_000 + i * 1_000
            store.add_utterance(
                version_id=version_id,
                meeting_id=mid,
                channel=1,
                start_ms=start,
                end_ms=start + 900,
                text=f"Filler talk number {i}.",
            )
    finally:
        conn.close()
    save_settings(paths.settings_file, Settings(llm=LlmSettings(context_budget=2500)))
    return paths, mid


def test_a_long_call_with_no_matching_part_says_so_and_asks_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = _long_call(tmp_path)
    provider = FakeProvider([])
    assert ask_command(_args("zebra giraffe?"), paths, provider=provider) == 0
    out = capsys.readouterr().out
    assert "Not discussed in this meeting." in out
    assert (
        "This call is too long to read whole. "
        "Evra looked only at the parts that match the words of your question." in out
    )
    assert provider.calls == []
    assert _stored(paths, mid) == [("not_found", None)]


def test_a_long_call_answer_says_it_read_parts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, _ = _long_call(tmp_path)
    assert (
        ask_command(_args("search migration Tuesday"), paths, provider=FakeProvider([ANSWER])) == 0
    )
    out = capsys.readouterr().out
    assert "- You finished the search migration on Tuesday." in out
    assert "This call is too long to read whole, so Evra read the parts that match" in out


def test_too_long_uses_the_windows_words(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = _long_call(tmp_path)
    save_settings(
        paths.settings_file, Settings(llm=LlmSettings(num_ctx=2048, ask_output_tokens=1500))
    )
    assert ask_command(_args("search migration"), paths, provider=FakeProvider([])) == 1
    assert (
        "This question needs more room than the model's settings allow." in capsys.readouterr().err
    )
    assert _stored(paths, mid) == [("failed", "too_long")]
