"""Shared fixtures for the console-command tests."""

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from evra.llm.provider import ChatMessage, ChatResult, LlmUnavailable
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from tests.unit.notes.fakes import FakeProvider


def recorded(tmp_path: Path, *, with_utterances: bool = True) -> tuple[AppPaths, str]:
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


class DownProvider(FakeProvider):
    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        raise LlmUnavailable("down")

    def installed_models(self) -> list[str]:
        raise LlmUnavailable("down")
