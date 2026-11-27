import json
import threading
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest

from evra.config import LlmSettings
from evra.llm.provider import (
    ChatMessage,
    ChatResult,
    LlmProvider,
    LlmUnavailable,
)
from evra.notes.context import build_context
from evra.notes.user_notes import meeting_context
from evra.services.ask import PREPARE_EVERY_S, JobSlot
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.notepad import LineIn, NotepadStore
from evra.store.questions import QuestionStore
from tests.unit.notes.fakes import FakeProvider
from tests.unit.services.ask_harness import ANSWER, NOT_FOUND, Harness


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


def test_asking_waits_for_the_note(tmp_path: Path) -> None:
    """RC11: while the note job runs (speakers, linking, the note, its lists, its title), a
    question and the Ask tab's pre-read are refused before any model call, in the order invalid,
    recording, note, busy; once the note is done, asking works again."""
    h = Harness(tmp_path)
    provider = FakeProvider([NOT_FOUND])
    writing = [True]
    slot = JobSlot()
    service = h.service(provider, note_busy=lambda: writing[0], slot=slot)
    assert service.ask(5, "q?") == {"ok": False, "reason": "invalid"}
    assert service.ask(h.meeting_id, "q?") == {"ok": False, "reason": "note"}
    assert service.prepare(h.meeting_id) == {"ok": False}
    assert slot.take()  # a brief being written meanwhile: "note" still, not "busy"
    assert service.ask(h.meeting_id, "q?") == {"ok": False, "reason": "note"}
    slot.release()
    both = h.service(provider, recording_busy=lambda: True, note_busy=lambda: True)
    assert both.ask(h.meeting_id, "q?") == {"ok": False, "reason": "recording"}
    assert provider.calls == [] and h.stored() == []
    writing[0] = False
    assert service.ask(h.meeting_id, "q?")["ok"] is True
    assert h.wait_event()["question"]["state"] == "not_found"


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


def test_questions_see_the_notes_through_the_shared_context(tmp_path: Path) -> None:
    """RB1: the pre-read and the question send the meeting's one context, notes included, and a
    point from the notes passes the check."""
    h = Harness(tmp_path)
    conn = connect(h.paths.db_path)
    started = int(MeetingStore(conn).get_meeting(h.meeting_id)["started_at"])
    NotepadStore(conn).replace(h.meeting_id, [LineIn("n1", "Quote due Friday", started, False)])
    expected = meeting_context(conn, h.meeting_id)[0].system
    conn.close()
    from_notes = {"text": "The quote is due Friday.", "citations": ["user"]}
    provider = FakeProvider(
        ['{"ready": true}', json.dumps({"found": True, "points": [from_notes]})]
    )
    service = h.service(provider)
    assert service.prepare(h.meeting_id) == {"ok": True}
    _wait_calls(provider, 1)
    service.ask(h.meeting_id, "When is the quote due?")
    question = h.wait_event()["question"]
    assert "<user_notes>\n[n:1] (00:00) Quote due Friday\n</user_notes>" in expected
    assert [call[0].content for call in provider.calls] == [expected, expected]
    assert (question["state"], question["points"][0]["text"]) == ("answered", from_notes["text"])


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
