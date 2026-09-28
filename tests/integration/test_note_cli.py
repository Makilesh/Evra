import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from evra.__main__ import build_parser
from evra.config import LlmSettings, Settings, save_settings
from evra.llm.provider import ChatMessage, ChatResult, LlmModelMissing, LlmUnavailable
from evra.notes.cli import note_command
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore, StoredNote
from tests.unit.notes.fakes import FakeProvider

GOOD = json.dumps(
    {
        "summary": [
            {"text": "You finished the search migration on Tuesday.", "citations": ["u:1"]}
        ],
        "sections": [
            {
                "section_id": "action_items",
                "title": "Action items",
                "bullets": [{"text": "Them will ask Priya directly.", "citations": ["u:2"]}],
            }
        ],
    }
)
UNSUPPORTED = json.dumps(
    {"summary": [{"text": "Everyone loved the cake.", "citations": ["u:1"]}], "sections": []}
)


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "meeting_id": None,
        "model": "fake:1b",
        "template": None,
        "think": None,
        "data_dir": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _recorded(tmp_path: Path, *, with_utterances: bool = True) -> tuple[AppPaths, str]:
    paths = AppPaths.under(tmp_path)
    paths.ensure()
    conn = connect(paths.db_path)
    migrate(conn)
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title="Weekly 1:1", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    if with_utterances:
        store.add_utterance(
            version_id=vid,
            meeting_id=mid,
            channel=0,
            start_ms=0,
            end_ms=4_000,
            text="I finished the search migration on Tuesday.",
        )
        store.add_utterance(
            version_id=vid,
            meeting_id=mid,
            channel=1,
            start_ms=5_000,
            end_ms=8_000,
            text="I'll ask Priya directly tomorrow.",
        )
    conn.close()
    return paths, mid


def _current(paths: AppPaths, mid: str) -> StoredNote | None:
    conn = connect(paths.db_path)
    try:
        return NoteStore(conn).current_note(mid)
    finally:
        conn.close()


class DownProvider(FakeProvider):
    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        raise LlmUnavailable("down")

    def installed_models(self) -> list[str]:
        raise LlmUnavailable("down")


class MissingModelProvider(FakeProvider):
    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        raise LlmModelMissing(model)


def test_writes_prints_and_stores_the_note(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = _recorded(tmp_path)
    assert note_command(_args(), paths, provider=FakeProvider([GOOD])) == 0
    out = capsys.readouterr().out
    assert "# Weekly 1:1" in out
    assert "## Summary\n- You finished the search migration on Tuesday. [00:00]" in out
    assert "## Action items\n- Them will ask Priya directly. [00:05]" in out
    assert "2 points kept, 0 dropped" in out
    stored = _current(paths, mid)
    assert stored is not None and len(stored.blocks) == 2


def test_meeting_id_argument_and_template_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = _recorded(tmp_path)
    args = _args(meeting_id=mid, template="general")
    assert note_command(args, paths, provider=FakeProvider([GOOD])) == 0
    stored = _current(paths, mid)
    assert stored is not None and stored.template == "general"
    capsys.readouterr()


def test_no_meetings_yet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = AppPaths.under(tmp_path)
    assert note_command(_args(), paths, provider=FakeProvider([GOOD])) == 2
    assert "No meetings yet" in capsys.readouterr().err


def test_unknown_meeting_or_template(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, _ = _recorded(tmp_path)
    assert note_command(_args(meeting_id="nope"), paths, provider=FakeProvider([GOOD])) == 2
    assert "No meeting with id nope" in capsys.readouterr().err
    assert note_command(_args(template="nope"), paths, provider=FakeProvider([GOOD])) == 2
    assert "Unknown template 'nope'" in capsys.readouterr().err


def test_no_transcript(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, _ = _recorded(tmp_path, with_utterances=False)
    assert note_command(_args(), paths, provider=FakeProvider([GOOD])) == 2
    assert "no transcript" in capsys.readouterr().err


def test_no_model_chosen_lists_installed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, _ = _recorded(tmp_path)
    save_settings(paths.settings_file, Settings(llm=LlmSettings(model="")))  # no default model
    assert note_command(_args(model=None), paths, provider=FakeProvider([GOOD])) == 2
    err = capsys.readouterr().err
    assert "--model" in err and "Installed: fake:1b" in err


def test_ollama_not_running_leaves_the_meeting_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = _recorded(tmp_path)
    assert note_command(_args(), paths, provider=DownProvider([])) == 2
    assert "Ollama is not running" in capsys.readouterr().err
    assert _current(paths, mid) is None


def test_missing_model_says_how_to_pull_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, _ = _recorded(tmp_path)
    assert note_command(_args(), paths, provider=MissingModelProvider([])) == 2
    assert "ollama pull fake:1b" in capsys.readouterr().err


def test_invalid_json_twice_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = _recorded(tmp_path)
    assert note_command(_args(), paths, provider=FakeProvider(["{", "{"])) == 1
    assert "did not return a valid note" in capsys.readouterr().err
    assert _current(paths, mid) is None


def test_a_note_with_nothing_supported_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, _ = _recorded(tmp_path)
    assert note_command(_args(), paths, provider=FakeProvider([UNSUPPORTED])) == 0
    out = capsys.readouterr().out
    assert "0 points kept, 1 dropped" in out
    assert "nothing in the note could be checked" in out


def test_parser_accepts_the_note_command() -> None:
    args = build_parser().parse_args(["note", "abc", "--model", "m", "--no-think"])
    assert (args.command, args.meeting_id, args.model, args.think) == ("note", "abc", "m", False)
    assert build_parser().parse_args(["note"]).meeting_id is None


def test_a_cut_off_note_says_why_and_stores_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = _recorded(tmp_path)
    assert note_command(_args(), paths, provider=FakeProvider([GOOD[:120]], truncated=True)) == 1
    assert "ran out of output room" in capsys.readouterr().err
    assert _current(paths, mid) is None


class InterruptedProvider(FakeProvider):
    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        raise KeyboardInterrupt


def test_ctrl_c_while_waiting_stops_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = _recorded(tmp_path)
    assert note_command(_args(), paths, provider=InterruptedProvider([])) == 130
    assert "Stopped; nothing saved." in capsys.readouterr().err
    assert _current(paths, mid) is None
