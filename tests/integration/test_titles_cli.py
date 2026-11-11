import argparse
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from evra.__main__ import build_parser
from evra.llm.provider import ChatMessage, ChatResult, LlmUnavailable
from evra.notes.cli import titles_command
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from tests.unit.notes.fakes import FakeProvider, saved_meeting, title_reply


def _paths(tmp_path: Path) -> AppPaths:
    paths = AppPaths.under(tmp_path)
    paths.ensure()
    return paths


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {"model": "fake:1b", "data_dir": None}
    values.update(overrides)
    return argparse.Namespace(**values)


def test_titles_is_a_command() -> None:
    args = build_parser().parse_args(["titles", "--model", "qwen3.5:9b"])
    assert (args.command, args.model) == ("titles", "qwen3.5:9b")


def test_titles_names_noted_meetings_that_still_have_their_placeholder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = _paths(tmp_path)
    conn = connect(paths.db_path)
    migrate(conn)
    noted = saved_meeting(conn, "Recording 2026-10-02 21:31")
    kept = saved_meeting(conn, "Weekly 1:1")
    bare = saved_meeting(conn, "Recording 2026-10-02 13:16", with_note=False)
    conn.close()
    provider = FakeProvider([title_reply("Launch date and designer proposal")])
    assert titles_command(_args(), paths, provider=provider) == 0
    assert len(provider.calls) == 1
    out = capsys.readouterr().out
    assert "Recording 2026-10-02 21:31 -> Launch date and designer proposal" in out
    assert "-- 1 of 1 named" in out
    conn = connect(paths.db_path)
    try:
        store = MeetingStore(conn)
        assert store.get_meeting(noted)["title"] == "Launch date and designer proposal"
        assert store.get_meeting(kept)["title"] == "Weekly 1:1"
        assert store.get_meeting(bare)["title"] == "Recording 2026-10-02 13:16"
    finally:
        conn.close()


def test_titles_says_so_when_ollama_is_not_running(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    class Down(FakeProvider):
        def chat_json(
            self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
        ) -> ChatResult:
            raise LlmUnavailable("down")

    paths = _paths(tmp_path)
    conn = connect(paths.db_path)
    migrate(conn)
    saved_meeting(conn, "Recording 2026-10-02 21:31")
    conn.close()
    assert titles_command(_args(), paths, provider=Down([])) == 2
    assert "Ollama is not running" in capsys.readouterr().err
