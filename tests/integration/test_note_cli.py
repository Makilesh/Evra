import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from evra.__main__ import build_parser
from evra.config import LlmSettings, Settings, save_settings
from evra.llm.provider import ChatMessage, ChatResult, LlmModelMissing
from evra.notes.cli import note_command
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.notes import NoteStore, StoredNote
from tests.integration.helpers import DownProvider, recorded
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
NO_ITEMS = json.dumps({"items": []})
ASK_PRIYA = {
    "text": "Ask Priya directly",
    "owner": "Them",
    "due": "tomorrow",
    "confidence": 0.9,
    "citations": ["u:2"],
}
LISTS = [json.dumps({"items": [ASK_PRIYA]}), NO_ITEMS, NO_ITEMS]  # A4-A6 after the note (A1)


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


def _current(paths: AppPaths, mid: str) -> StoredNote | None:
    conn = connect(paths.db_path)
    try:
        return NoteStore(conn).current_note(mid)
    finally:
        conn.close()


class MissingModelProvider(FakeProvider):
    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        raise LlmModelMissing(model)


def test_writes_prints_and_stores_the_note(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = recorded(tmp_path)
    assert note_command(_args(), paths, provider=FakeProvider([GOOD, *LISTS])) == 0
    out = capsys.readouterr().out
    assert "# Weekly 1:1" in out
    assert "## Summary\n- You finished the search migration on Tuesday. [00:00]" in out
    # the action items come from their own list (A4), not from the note's sections
    assert "## Action items\n- Them: Ask Priya directly (tomorrow) [00:05]" in out
    assert "Them will ask Priya directly." not in out
    assert "2 points kept, 0 dropped" in out
    stored = _current(paths, mid)
    assert stored is not None and len(stored.blocks) == 1


def test_meeting_id_argument_and_template_override(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = recorded(tmp_path)
    args = _args(meeting_id=mid, template="general")
    assert note_command(args, paths, provider=FakeProvider([GOOD, *LISTS])) == 0
    stored = _current(paths, mid)
    assert stored is not None and stored.template == "general"
    capsys.readouterr()


def test_no_meetings_yet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = AppPaths.under(tmp_path)
    assert note_command(_args(), paths, provider=FakeProvider([GOOD])) == 2
    assert "No meetings yet" in capsys.readouterr().err


def test_unknown_meeting_or_template(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, _ = recorded(tmp_path)
    assert note_command(_args(meeting_id="nope"), paths, provider=FakeProvider([GOOD])) == 2
    assert "No meeting with id nope" in capsys.readouterr().err
    assert note_command(_args(template="nope"), paths, provider=FakeProvider([GOOD])) == 2
    assert "Unknown template 'nope'" in capsys.readouterr().err


def test_no_transcript(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths, _ = recorded(tmp_path, with_utterances=False)
    assert note_command(_args(), paths, provider=FakeProvider([GOOD])) == 2
    assert "no transcript" in capsys.readouterr().err


def test_no_model_chosen_lists_installed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, _ = recorded(tmp_path)
    save_settings(paths.settings_file, Settings(llm=LlmSettings(model="")))  # no default model
    assert note_command(_args(model=None), paths, provider=FakeProvider([GOOD])) == 2
    err = capsys.readouterr().err
    assert "--model" in err and "Installed: fake:1b" in err


def test_ollama_not_running_leaves_the_meeting_untouched(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = recorded(tmp_path)
    assert note_command(_args(), paths, provider=DownProvider([])) == 2
    assert "Ollama is not running" in capsys.readouterr().err
    assert _current(paths, mid) is None


def test_missing_model_says_how_to_pull_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, _ = recorded(tmp_path)
    assert note_command(_args(), paths, provider=MissingModelProvider([])) == 2
    assert "ollama pull fake:1b" in capsys.readouterr().err


def test_invalid_json_twice_fails_cleanly(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = recorded(tmp_path)
    provider = FakeProvider(["{", "{", NO_ITEMS, NO_ITEMS, NO_ITEMS])
    assert note_command(_args(), paths, provider=provider) == 1
    assert "did not return a valid note" in capsys.readouterr().err
    assert _current(paths, mid) is None


def test_a_note_of_the_lists_alone_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = recorded(tmp_path)
    assert note_command(_args(), paths, provider=FakeProvider(["{", "{", *LISTS])) == 0
    out = capsys.readouterr().out
    assert "## Action items\n- Them: Ask Priya directly (tomorrow) [00:05]" in out
    assert "only the action items, decisions and open questions" in out
    stored = _current(paths, mid)
    assert stored is not None and stored.blocks == ()


def test_a_note_with_nothing_supported_is_not_saved_and_keeps_the_previous_one(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = recorded(tmp_path)
    assert note_command(_args(), paths, provider=FakeProvider([GOOD, *LISTS])) == 0
    good = _current(paths, mid)
    capsys.readouterr()
    provider = FakeProvider([UNSUPPORTED, NO_ITEMS, NO_ITEMS, NO_ITEMS])
    assert note_command(_args(), paths, provider=provider) == 1
    err = capsys.readouterr().err
    assert "Nothing in the note could be checked" in err and "nothing saved" in err
    assert _current(paths, mid) == good


def test_parser_accepts_the_note_command() -> None:
    args = build_parser().parse_args(["note", "abc", "--model", "m", "--no-think"])
    assert (args.command, args.meeting_id, args.model, args.think) == ("note", "abc", "m", False)
    assert build_parser().parse_args(["note"]).meeting_id is None


def test_a_cut_off_note_says_why_and_stores_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths, mid = recorded(tmp_path)
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
    paths, mid = recorded(tmp_path)
    assert note_command(_args(), paths, provider=InterruptedProvider([])) == 130
    assert "Stopped; nothing saved." in capsys.readouterr().err
    assert _current(paths, mid) is None
