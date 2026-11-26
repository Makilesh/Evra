"""Asking a call too long to read whole: the pre-read embeds its parts, and each meeting
keeps its embedder for the session (two meetings at a time)."""

import threading
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pytest
import structlog

from evra.config import LlmSettings
from evra.llm.provider import (
    ChatMessage,
    ChatResult,
    LlmModelMissing,
)
from evra.notes.ask import AskResult, Exchange, build_ask_messages, window_texts
from evra.notes.context import MeetingContext, build_context, estimate_tokens
from evra.notes.validate import CheckedBullet
from evra.store.db import connect
from evra.store.meetings import MeetingStore, Utterance
from evra.store.questions import QuestionStore
from tests.unit.notes.fakes import FakeProvider
from tests.unit.services.ask_harness import ANSWER, NOT_FOUND, Harness


class Watching(FakeProvider):
    """Records the order of loads, chats and embeddings; `embedded` is set once every text of
    `expected` has been embedded, `chatted` once a chat call has returned."""

    def __init__(self, replies: list[str], expected: Sequence[str] = ()) -> None:
        super().__init__(replies)
        self.expected = set(expected)
        self.embedded = threading.Event()
        self.chatted = threading.Event()
        self.order: list[str] = []

    def load(self, model: str) -> None:
        self.order.append("load")
        super().load(model)

    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        self.order.append("chat")
        result = super().chat_json(model, messages, schema)
        self.chatted.set()
        return result

    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        self.order.append("embed")
        vectors = super().embed(model, texts)
        if self.expected <= {t for call in self.embed_calls for t in call}:
            self.embedded.set()
        return vectors


def test_prepare_reads_a_long_meeting_by_its_parts(tmp_path: Path) -> None:
    """A meeting too long to read whole is not prefilled whole (the cache would not match the
    excerpt a question reads): the model is loaded, then the windows are embedded."""
    h = Harness(tmp_path, filler_chars=20_000)
    provider = Watching(['{"ready": true}'], window_texts(h.lines))
    service = h.service(provider, llm=lambda: LlmSettings(model="fake:1b", context_budget=1000))
    assert service.prepare(h.meeting_id) == {"ok": True}
    assert provider.embedded.wait(10)
    assert provider.order[0] == "load" and "chat" not in provider.order
    assert provider.loaded == ["fake:1b"] and provider.calls == []


def _whole_context(h: Harness) -> MeetingContext:
    conn = connect(h.paths.db_path)
    meeting = MeetingStore(conn).get_meeting(h.meeting_id)
    conn.close()
    return build_context(meeting=meeting, utterances=h.lines)


def _ask_tokens(context: MeetingContext, history: Sequence[Exchange] = ()) -> int:
    """The longest question's A12 message, as the pre-read sizes it."""
    return estimate_tokens(build_ask_messages(context, "x" * 500, history)[0][1].content)


def test_prepare_counts_the_real_ask_prompt(tmp_path: Path) -> None:
    """A meeting that fits only without the question is not prefilled whole: asking would take
    the excerpt path, so the warm cache would not match. One token more and it is."""
    h = Harness(tmp_path, filler_chars=4_000)
    context = _whole_context(h)
    ask_user = _ask_tokens(context)
    assert ask_user > estimate_tokens('Reply with {"ready": true}.')
    budget = context.estimated_tokens + ask_user - 1
    assert budget >= 1000
    parts = Watching(['{"ready": true}'], window_texts(h.lines))
    service = h.service(parts, llm=lambda: LlmSettings(model="fake:1b", context_budget=budget))
    assert service.prepare(h.meeting_id) == {"ok": True}  # its parts, not the whole
    assert parts.embedded.wait(10)
    assert parts.order[0] == "load" and parts.calls == []
    whole = Watching(['{"ready": true}'])
    roomy_llm = LlmSettings(model="fake:1b", context_budget=budget + 1)
    assert h.service(whole, llm=lambda: roomy_llm).prepare(h.meeting_id) == {"ok": True}
    assert whole.chatted.wait(10)
    assert whole.calls[0][0].content == context.system and whole.embed_calls == []


def _answered(h: Harness, question: str, answer: str) -> None:
    """An earlier question about the harness meeting, answered with one point."""
    conn = connect(h.paths.db_path)
    try:
        questions = QuestionStore(conn)
        stored = questions.add(h.meeting_id, question)
        version_id = MeetingStore(conn).current_transcript_version(h.meeting_id)
        assert version_id is not None
        point = CheckedBullet(answer, (h.lines[0].id,))
        result = AskResult("answered", (point,), False, "fake:1b", "a0-v1+a12-v1", 1, 1, 0.1, 0)
        questions.answer(stored.id, result, transcript_version_id=version_id)
    finally:
        conn.close()


def test_prepare_reads_a_call_whole_when_only_its_history_tips_it(tmp_path: Path) -> None:
    """Questions drop the oldest exchanges before they read parts, so a meeting that fits with
    no history is read whole by every question: its pre-read is the A0 prefill, not the parts."""
    h = Harness(tmp_path, filler_chars=4_000)
    for n in range(3):
        _answered(h, f"Question {n}?", "word " * 300)
    context = _whole_context(h)
    conn = connect(h.paths.db_path)
    history = QuestionStore(conn).history(h.meeting_id)
    conn.close()
    budget = context.estimated_tokens + _ask_tokens(context)  # fits with no history
    assert context.estimated_tokens + _ask_tokens(context, history) > budget  # not with it
    provider = Watching(['{"ready": true}'], window_texts(h.lines))
    service = h.service(provider, llm=lambda: LlmSettings(model="fake:1b", context_budget=budget))
    assert service.prepare(h.meeting_id) == {"ok": True}
    assert provider.chatted.wait(10), "no A0 prefill: the pre-read took the parts path"
    assert provider.calls[0][0].content == context.system
    assert provider.order == ["chat"] and provider.embed_calls == []


LONG = 400  # filler lines: far more than long_call_llm's budget reads whole


def long_call_llm() -> LlmSettings:
    return LlmSettings(model="fake:1b", context_budget=2000)


def long_meeting(h: Harness, title: str = "Weekly 1:1") -> tuple[str, list[Utterance]]:
    """Another meeting of LONG lines, each naming the title, so its windows are its own."""
    conn = connect(h.paths.db_path)
    try:
        store = MeetingStore(conn)
        mid = store.create_meeting(
            title=title, mode="one_on_one", situation="call_headphones", template="one_on_one"
        )
        vid = store.create_transcript_version(mid, kind="live", model="fake")
        lines = [
            store.add_utterance(
                version_id=vid,
                meeting_id=mid,
                channel=i % 2,
                start_ms=i * 1_000,
                end_ms=i * 1_000 + 900,
                text=f"Filler talk number {i} about {title}.",
            )
            for i in range(LONG)
        ]
    finally:
        conn.close()
    return mid, lines


def filler_lines(h: Harness) -> None:
    """LONG filler lines after the harness meeting's two lines, so it is a long call."""
    conn = connect(h.paths.db_path)
    try:
        store = MeetingStore(conn)
        vid = store.current_transcript_version(h.meeting_id)
        assert vid is not None
        for i in range(LONG):
            start = 10_000 + i * 1_000
            store.add_utterance(
                version_id=vid,
                meeting_id=h.meeting_id,
                channel=1,
                start_ms=start,
                end_ms=start + 900,
                text=f"Filler talk number {i}.",
            )
    finally:
        conn.close()


def embedded_since(provider: FakeProvider, start: int) -> list[str]:
    return [t for call in provider.embed_calls[start:] for t in call]


def test_a_second_question_on_a_long_call_embeds_no_window_again(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    mid, lines = long_meeting(h)
    windows = set(window_texts(lines))
    provider = FakeProvider([NOT_FOUND, NOT_FOUND])
    service = h.service(provider, llm=long_call_llm)
    service.ask(mid, "What did I promise?")
    assert h.wait_event()["question"]["excerpt"] is True
    assert windows <= set(embedded_since(provider, 0))  # the first question embedded them
    first = len(provider.embed_calls)
    service.ask(mid, "What did they promise?")
    h.wait_event()
    later = embedded_since(provider, first)
    assert later and not windows & set(later)  # only its own query (and check)


def test_after_prepare_the_first_question_embeds_no_window(tmp_path: Path) -> None:
    h = Harness(tmp_path)
    mid, lines = long_meeting(h)
    windows = window_texts(lines)
    provider = Watching([NOT_FOUND], windows)
    service = h.service(provider, llm=long_call_llm)
    assert service.prepare(mid) == {"ok": True}
    assert provider.embedded.wait(10)
    assert provider.order[0] == "load"  # the model first, the embeddings after (§8.3)
    start = len(provider.embed_calls)
    service.ask(mid, "What did I promise?")
    h.wait_event()
    later = embedded_since(provider, start)
    assert later and not set(windows) & set(later)


def test_a_failing_embed_in_prepare_still_answers(tmp_path: Path) -> None:
    attempted = threading.Event()

    class NoEmbeddingModel(FakeProvider):
        def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
            attempted.set()
            raise LlmModelMissing(model)

    h = Harness(tmp_path)
    filler_lines(h)
    provider = NoEmbeddingModel([ANSWER])
    service = h.service(provider, llm=long_call_llm)
    with structlog.testing.capture_logs() as logs:
        assert service.prepare(h.meeting_id) == {"ok": True}
        assert attempted.wait(10)
        service.ask(h.meeting_id, "What about the vendor quote?")  # found by its words alone
        question = h.wait_event()["question"]
    assert (question["state"], question["excerpt"]) == ("answered", True)
    skipped = [e for e in logs if e["event"] == "semantic_check_skipped"]
    assert skipped and all(e["error"] == "LlmModelMissing" for e in skipped)


def test_the_embedders_are_kept_for_two_meetings(tmp_path: Path) -> None:
    """The two meetings asked most recently keep their embedders: asking Alpha again makes it
    more recent than Bravo, so Charlie's arrival lets Bravo go, not Alpha."""
    h = Harness(tmp_path)
    meetings = {name: long_meeting(h, name) for name in ("Alpha", "Bravo", "Charlie")}
    provider = FakeProvider([NOT_FOUND] * 6)
    service = h.service(provider, llm=long_call_llm)

    def ask(name: str) -> set[str]:
        """The windows of `name` this question embedded."""
        start = len(provider.embed_calls)
        service.ask(meetings[name][0], "What did I promise?")
        h.wait_event()
        return set(window_texts(meetings[name][1])) & set(embedded_since(provider, start))

    assert ask("Alpha") and ask("Bravo")
    assert not ask("Alpha")  # kept, and now the most recent
    assert ask("Charlie")  # Bravo, asked longest ago, is let go
    assert not ask("Alpha")
    assert ask("Bravo")


def test_a_question_during_a_prepare_waits_for_its_embedding(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-read is embedding a long call's windows when a question about it arrives: the
    question waits on that meeting's embedder and then embeds only its query."""
    contended = threading.Event()

    class ObservedLock:
        """A lock that says when a second caller has to wait for it."""

        def __init__(self) -> None:
            self._lock = threading.Lock()

        def __enter__(self) -> "ObservedLock":
            if not self._lock.acquire(blocking=False):
                contended.set()
                self._lock.acquire()
            return self

        def __exit__(self, *exc: object) -> None:
            self._lock.release()

    monkeypatch.setattr("evra.notes.semantic.Lock", ObservedLock)
    h = Harness(tmp_path)
    mid, lines = long_meeting(h)
    windows = set(window_texts(lines))
    in_embed, release = threading.Event(), threading.Event()

    class Gated(FakeProvider):
        def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
            if windows & set(texts) and not in_embed.is_set():
                in_embed.set()  # the pre-read's first batch waits here
                assert release.wait(10)
            return super().embed(model, texts)

    provider = Gated([NOT_FOUND])
    service = h.service(provider, llm=long_call_llm)
    assert service.prepare(mid) == {"ok": True}
    assert in_embed.wait(10)
    assert service.ask(mid, "What did I promise?")["ok"] is True
    assert contended.wait(10), "the question did not wait for the pre-read's embedding"
    release.set()
    assert h.wait_event()["question"]["excerpt"] is True
    embedded = [t for t in embedded_since(provider, 0) if t in windows]
    assert sorted(embedded) == sorted(windows)  # every window once
