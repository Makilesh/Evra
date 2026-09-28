"""LLM provider interface (BUILD.md D4). Structured calls only: every reply is JSON for a schema.

Errors never carry prompt or reply text, only what went wrong.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class LlmError(Exception):
    """Base class for LLM failures."""


class LlmUnavailable(LlmError):
    """The LLM server is not running or went away."""


class LlmModelMissing(LlmError):
    def __init__(self, model: str) -> None:
        super().__init__(f"model {model!r} is not installed")
        self.model = model


class LlmTimeout(LlmError):
    """No answer within the configured time."""


class LlmConfigError(LlmError):
    """The LLM settings are not allowed (for example a non-local server)."""


@dataclass(frozen=True)
class ChatMessage:
    role: str  # system | user | assistant
    content: str


@dataclass(frozen=True)
class ChatResult:
    content: str
    tokens_in: int
    tokens_out: int
    seconds: float
    truncated: bool  # the reply hit the output-token limit


class LlmProvider(Protocol):
    name: str

    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult: ...

    def installed_models(self) -> list[str]: ...
