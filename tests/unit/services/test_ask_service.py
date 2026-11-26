import json
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from evra.config import LlmSettings
from evra.llm.provider import ChatMessage, ChatResult, LlmProvider, LlmUnavailable
from evra.notes.ask import build_ask_messages
from evra.notes.context import build_context, estimate_tokens
from evra.paths import AppPaths
from evra.services.ask import PREPARE_EVERY_S, AskService
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.migrate import migrate
from evra.store.questions import QuestionStore
from tests.unit.notes.fakes import FakeProvider

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


def test_answer_arrives_as_an_event(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    reply = h.service(FakeProvider([ANSWER])).ask(h.meeting_id, "  What did they ask?  ")
    assert reply["ok"] is True
    assert reply["question"]["state"] == "asking"
    assert reply["question"]["text"] == "What did they ask?"
    payload = h.wait_event()
    assert payload["meeting_id"] == h.meeting_id
    question = payload["question"]
    assert question["id"] == reply["question"]["id"]
    assert question["state"] == "answered"
    assert question["points"][0]["citations"] == [
        {"utterance_id": h.lines[0].id, "start_ms": 1_000}
    ]


def test_failed_question_reports_reason(tmp_path: Path) -> None:
    class Down(FakeProvider):
        def chat_json(
            self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
        ) -> ChatResult:
            raise LlmUnavailable("down")

    h = Harness(tmp_path)
    h.service(Down([])).ask(h.meeting_id, "q?")
    question = h.wait_event()["question"]
    assert (question["state"], question["reason"]) == ("failed", "ollama_down")
    assert [q.state for q in h.stored()] == ["failed"]


def test_unexpected_error_still_fails_the_question(tmp_path: Path) -> None:
    def boom(_s: LlmSettings) -> LlmProvider:
        raise RuntimeError("x")

    h = Harness(tmp_path)
    h.service(FakeProvider([]), provider_factory=boom).ask(h.meeting_id, "q?")
    question = h.wait_event()["question"]
    assert (question["state"], question["reason"]) == ("failed", "llm_error")


@pytest.mark.parametrize(
    ("meeting", "question"), [(5, "q"), ("id", 7), ("id", "   "), ("id", "x" * 501)]
)
def test_ask_refuses_bad_input(tmp_path: Path, meeting: object, question: object) -> None:
    h = Harness(tmp_path)
    service = h.service(FakeProvider([]))
    if meeting == "id":
        meeting = h.meeting_id
    assert service.ask(meeting, question) == {"ok": False, "reason": "invalid"}
    assert h.stored() == []


def test_ask_refused_while_recording(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    service = h.service(FakeProvider([]), recording_busy=lambda: True)
    assert service.ask(h.meeting_id, "q?") == {"ok": False, "reason": "recording"}
    assert h.stored() == []


def test_one_question_at_a_time(tmp_path: Path) -> None:
    release = threading.Event()

    class Blocking(FakeProvider):
        def chat_json(
            self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
        ) -> ChatResult:
            assert release.wait(10)
            return super().chat_json(model, messages, schema)

    h = Harness(tmp_path)
    service = h.service(Blocking([ANSWER, NOT_FOUND]))
    assert service.ask(h.meeting_id, "one?")["ok"] is True
    assert service.ask(h.meeting_id, "two?") == {"ok": False, "reason": "busy"}
    release.set()
    h.wait_event()
    assert service.ask(h.meeting_id, "three?")["ok"] is True
    h.wait_event()
    assert [q.text for q in h.stored()] == ["one?", "three?"]


def test_no_transcript(tmp_path: Path) -> None:
    h = Harness(tmp_path, with_lines=False)
    service = h.service(FakeProvider([]))
    assert service.ask(h.meeting_id, "q?") == {"ok": False, "reason": "no_transcript"}
    assert service.ask("unknown", "q?") == {"ok": False, "reason": "no_transcript"}
    assert h.stored() == []
    # a refusal frees the slot: the next one is "no_transcript" again, not "busy"
    assert service.ask(h.meeting_id, "q?")["reason"] == "no_transcript"


def test_shutdown_refuses_later_asks(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    service = h.service(FakeProvider([]))
    service.shutdown()
    assert service.ask(h.meeting_id, "q?") == {"ok": False, "reason": "busy"}


def test_history_reaches_the_prompt(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    provider = FakeProvider([ANSWER, NOT_FOUND])
    service = h.service(provider)
    service.ask(h.meeting_id, "What did they ask?")
    h.wait_event()
    service.ask(h.meeting_id, "And then?")
    h.wait_event()
    second_user = provider.calls[1][1].content
    assert "What did they ask?" in second_user
    assert "They will send the quote by Friday." in second_user


def _wait_calls(provider: FakeProvider, n: int) -> None:
    deadline = time.monotonic() + 10
    while len(provider.calls) < n:
        assert time.monotonic() < deadline
        time.sleep(0.01)


def test_prepare_once_per_window(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    provider = FakeProvider(['{"ready": true}', '{"ready": true}'])
    now = [1000.0]
    service = h.service(provider, clock=lambda: now[0])
    assert service.prepare(h.meeting_id) == {"ok": True}
    _wait_calls(provider, 1)
    now[0] += PREPARE_EVERY_S - 1
    assert service.prepare(h.meeting_id) == {"ok": False}
    assert len(provider.calls) == 1
    now[0] += 2
    assert service.prepare(h.meeting_id) == {"ok": True}
    _wait_calls(provider, 2)
    assert len(provider.calls) == 2
    assert provider.calls[0][1].content == 'Reply with {"ready": true}.'
    assert provider.calls[0][0].role == "system"
    conn = connect(h.paths.db_path)
    meeting = MeetingStore(conn).get_meeting(h.meeting_id)
    conn.close()
    assert provider.calls[0][0].content == build_context(meeting=meeting, utterances=h.lines).system


def test_prepare_refuses_unknown_recording_and_non_strings(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    assert h.service(FakeProvider([])).prepare("unknown") == {"ok": False}
    assert h.service(FakeProvider([])).prepare(3) == {"ok": False}
    busy = h.service(FakeProvider([]), recording_busy=lambda: True)
    assert busy.prepare(h.meeting_id) == {"ok": False}


def test_recover_marks_asking_questions_interrupted(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    conn = connect(h.paths.db_path)
    QuestionStore(conn).add(h.meeting_id, "q?")
    conn.close()
    assert h.service(FakeProvider([])).recover() == 1
    assert [(q.state, q.reason) for q in h.stored()] == [("failed", "interrupted")]


def test_slot_is_freed_after_a_failed_answer(tmp_path: Path) -> None:
    class Down(FakeProvider):
        def chat_json(
            self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
        ) -> ChatResult:
            raise LlmUnavailable("down")

    h = Harness(tmp_path)
    service = h.service(Down([]))
    service.ask(h.meeting_id, "one?")
    h.wait_event()
    assert service.ask(h.meeting_id, "two?")["ok"] is True
    h.wait_event()


def test_slot_is_freed_after_an_unexpected_error(tmp_path: Path) -> None:
    calls = [0]

    def flaky(_s: LlmSettings) -> LlmProvider:
        calls[0] += 1
        if calls[0] == 1:
            raise RuntimeError("x")
        return FakeProvider([ANSWER])

    h = Harness(tmp_path)
    service = h.service(FakeProvider([]), provider_factory=flaky)
    service.ask(h.meeting_id, "one?")
    h.wait_event()
    assert service.ask(h.meeting_id, "two?")["ok"] is True
    assert h.wait_event()["question"]["state"] == "answered"


def test_no_transcript_version_at_all(tmp_path: Path) -> None:
    h = Harness(tmp_path, with_version=False)
    assert h.service(FakeProvider([])).ask(h.meeting_id, "q?") == {
        "ok": False,
        "reason": "no_transcript",
    }


def test_a_thread_that_cannot_start_leaves_no_asking_row(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class NoStart(threading.Thread):
        def start(self) -> None:
            raise RuntimeError("can't start new thread")

    h = Harness(tmp_path)
    service = h.service(FakeProvider([ANSWER]))
    with monkeypatch.context() as patch:
        patch.setattr("evra.services.ask.threading.Thread", NoStart)
        assert service.ask(h.meeting_id, "q?") == {"ok": False, "reason": "busy"}
    assert [(q.state, q.reason) for q in h.stored()] == [("failed", "llm_error")]
    assert service.ask(h.meeting_id, "again?")["ok"] is True  # the slot was freed
    h.wait_event()


def test_the_window_hears_back_even_if_the_failure_cannot_be_stored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Down(FakeProvider):
        def chat_json(
            self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
        ) -> ChatResult:
            raise LlmUnavailable("down")

    def broken(self: QuestionStore, question_id: str, reason: str) -> None:
        raise RuntimeError("database is locked")

    h = Harness(tmp_path)
    service = h.service(Down([]))
    monkeypatch.setattr(QuestionStore, "fail", broken)
    reply = service.ask(h.meeting_id, "q?")
    question = h.wait_event()["question"]
    assert question["id"] == reply["question"]["id"]
    assert (question["state"], question["reason"], question["text"]) == (
        "failed",
        "ollama_down",
        "q?",
    )


def test_prepare_refused_while_a_question_is_pending(tmp_path: Path) -> None:
    release = threading.Event()

    class Blocking(FakeProvider):
        def chat_json(
            self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
        ) -> ChatResult:
            assert release.wait(10)
            return super().chat_json(model, messages, schema)

    h = Harness(tmp_path)
    provider = Blocking([ANSWER, '{"ready": true}'])
    service = h.service(provider)
    service.ask(h.meeting_id, "one?")
    assert service.prepare(h.meeting_id) == {"ok": False}
    release.set()
    h.wait_event()
    assert len(provider.calls) == 1


def test_prepare_does_nothing_when_the_meeting_does_not_fit(tmp_path: Path) -> None:
    h = Harness(tmp_path, filler_chars=20_000)
    provider = FakeProvider(['{"ready": true}'])
    service = h.service(provider, llm=lambda: LlmSettings(model="fake:1b", context_budget=1000))
    assert service.prepare(h.meeting_id) == {"ok": False}
    time.sleep(0.1)
    assert provider.calls == []


def test_prepare_counts_the_real_ask_prompt(tmp_path: Path) -> None:
    """A meeting that fits only without the question and its history is not prefilled whole:
    asking would take the excerpt path, so the warm cache would not match."""
    h = Harness(tmp_path, filler_chars=4_000)
    conn = connect(h.paths.db_path)
    meeting = MeetingStore(conn).get_meeting(h.meeting_id)
    conn.close()
    context = build_context(meeting=meeting, utterances=h.lines)
    ask_user = estimate_tokens(build_ask_messages(context, "x" * 500, [])[0][1].content)
    assert ask_user > estimate_tokens('Reply with {"ready": true}.')
    budget = context.estimated_tokens + ask_user - 1
    assert budget >= 1000
    provider = FakeProvider(['{"ready": true}'])
    service = h.service(provider, llm=lambda: LlmSettings(model="fake:1b", context_budget=budget))
    assert service.prepare(h.meeting_id) == {"ok": False}
    time.sleep(0.1)
    assert provider.calls == []
    roomy_llm = LlmSettings(model="fake:1b", context_budget=budget + 1)
    assert h.service(provider, llm=lambda: roomy_llm).prepare(h.meeting_id) == {"ok": True}


def test_a_second_prepare_waits_for_the_first_to_finish(tmp_path: Path) -> None:
    release = threading.Event()

    class Slow(FakeProvider):
        def chat_json(
            self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
        ) -> ChatResult:
            assert release.wait(10)
            return super().chat_json(model, messages, schema)

    h = Harness(tmp_path)
    other = h.meeting_id
    provider = Slow(['{"ready": true}', '{"ready": true}'])
    service = h.service(provider)
    assert service.prepare(other) == {"ok": True}
    conn = connect(h.paths.db_path)
    store = MeetingStore(conn)
    second = store.create_meeting(
        title="Other", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(second, kind="live", model="fake")
    store.add_utterance(
        version_id=vid, meeting_id=second, channel=0, start_ms=0, end_ms=1_000, text="Hello there."
    )
    conn.close()
    assert service.prepare(second) == {"ok": False}  # one pre-read at a time
    release.set()
    _wait_calls(provider, 1)
    # the slot is freed once the first call returns: the other meeting's pre-read now starts
    deadline = time.monotonic() + 10
    while service.prepare(second) != {"ok": True}:
        assert time.monotonic() < deadline, "the first pre-read never freed its slot"
        time.sleep(0.01)
    _wait_calls(provider, 2)
    conn = connect(h.paths.db_path)
    second_meeting = MeetingStore(conn).get_meeting(second)
    second_lines = MeetingStore(conn).utterances(vid)
    conn.close()
    second_system = build_context(meeting=second_meeting, utterances=second_lines).system
    assert provider.calls[1][0].content == second_system
    assert service.prepare(other) == {"ok": False}  # same meeting, still inside its window
    assert len(provider.calls) == 2


def test_answers_are_checked_by_meaning_with_the_embedding_model(tmp_path: Path) -> None:
    class AllAlike(FakeProvider):
        """Every text gets the same vector, so every pair means the same."""

        def __init__(self, replies: list[str]) -> None:
            super().__init__(replies)
            self.embedded_with: list[str] = []

        def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
            self.embedded_with.append(model)
            return [[1.0, 0.0] for _ in texts]

    point = "Them accepted the request."  # no word of "Yes, I will."
    reply = json.dumps({"found": True, "points": [{"text": point, "citations": ["u:2"]}]})
    h = Harness(tmp_path)
    provider = AllAlike([reply])
    h.service(provider).ask(h.meeting_id, "Did they agree?")
    question = h.wait_event()["question"]
    assert (question["state"], [p["text"] for p in question["points"]]) == ("answered", [point])
    assert provider.embedded_with == ["qwen3-embedding:0.6b"]
