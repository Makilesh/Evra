"""The ask service under test: a meeting with two lines in a fresh data folder, and the
events the service sends. Shared by test_ask_service.py and test_ask_long_calls.py."""

import json
import threading
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from evra.config import LlmSettings
from evra.llm.provider import LlmProvider
from evra.paths import AppPaths
from evra.services.ask import AskService
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.migrate import migrate
from evra.store.questions import QuestionStore

ANSWER = json.dumps(
    {
        "found": True,
        "points": [{"text": "They will send the quote by Friday.", "citations": ["u:1"]}],
    }
)
NOT_FOUND = json.dumps({"found": False, "points": []})


class Harness:
    def __init__(
        self,
        tmp_path: Path,
        *,
        with_lines: bool = True,
        with_version: bool = True,
        filler_chars: int = 0,
    ) -> None:
        self.paths = AppPaths.under(tmp_path)
        self.paths.ensure()
        conn = connect(self.paths.db_path)
        migrate(conn)
        store = MeetingStore(conn)
        self.meeting_id = store.create_meeting(
            title="Weekly 1:1",
            mode="one_on_one",
            situation="call_headphones",
            template="one_on_one",
        )
        self.lines: list[Utterance] = []
        if with_version:
            vid = store.create_transcript_version(self.meeting_id, kind="live", model="fake")
            spoken = [
                (1, 1_000, "Can you send me the vendor quote by Friday?"),
                (0, 5_000, "Yes, I will."),
            ]
            if filler_chars:
                spoken.append((1, 9_000, "word " * (filler_chars // 5)))
            for channel, start, text in spoken if with_lines else []:
                self.lines.append(
                    store.add_utterance(
                        version_id=vid,
                        meeting_id=self.meeting_id,
                        channel=channel,
                        start_ms=start,
                        end_ms=start + 2_000,
                        text=text,
                    )
                )
        conn.close()
        self.events: list[tuple[str, Mapping[str, Any]]] = []
        self.got = threading.Event()

    def emit(self, name: str, payload: Mapping[str, Any]) -> bool:
        self.events.append((name, payload))
        self.got.set()
        return True

    def service(self, provider: LlmProvider, **kw: Any) -> AskService:
        args: dict[str, Any] = {
            "paths": self.paths,
            "llm": lambda: LlmSettings(model="fake:1b"),
            "emit": self.emit,
            "recording_busy": lambda: False,
            "provider_factory": lambda _s: provider,
        }
        args.update(kw)
        return AskService(**args)

    def wait_event(self) -> Mapping[str, Any]:
        assert self.got.wait(10)
        self.got.clear()
        name, payload = self.events[-1]
        assert name == "question.updated"
        return payload

    def stored(self) -> list[Any]:
        conn = connect(self.paths.db_path)
        try:
            return QuestionStore(conn).for_meeting(self.meeting_id)
        finally:
            conn.close()
