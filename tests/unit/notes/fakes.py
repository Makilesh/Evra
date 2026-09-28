from collections.abc import Mapping, Sequence
from typing import Any

from evra.llm.provider import ChatMessage, ChatResult
from evra.store.meetings import Utterance


class FakeProvider:
    name = "fake"

    def __init__(self, replies: list[str], tokens_in: int = 100, truncated: bool = False) -> None:
        self.replies = list(replies)
        self.truncated = truncated
        self.tokens_in = tokens_in
        self.calls: list[list[ChatMessage]] = []
        self.models = ["fake:1b"]

    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        self.calls.append(list(messages))
        return ChatResult(self.replies.pop(0), self.tokens_in, 50, 0.5, self.truncated)

    def installed_models(self) -> list[str]:
        return list(self.models)


def utt(uid: str, channel: int, start: int, end: int, text: str, seq: int = 0) -> Utterance:
    return Utterance(uid, "v", "m", seq, channel, None, start, end, text, (), None)
