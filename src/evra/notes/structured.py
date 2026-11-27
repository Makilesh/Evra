"""One structured LLM call (BUILD.md §7.4-7.5): a call, a cut-off check, and at most one A9
repair. Every note, answer and extraction pass goes through here. Nothing logs or raises with
prompt or reply text."""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import structlog
from pydantic import BaseModel, ValidationError

from evra.llm.prompt_files import load_prompt
from evra.llm.provider import ChatMessage, ChatResult, LlmProvider
from evra.notes.context import as_data
from evra.notes.errors import NoteCutOff, NoteInvalid

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class Structured[T]:
    value: T
    calls: tuple[ChatResult, ...]
    repair_version: str | None  # "a9-v1" when a repair was needed

    @property
    def repaired(self) -> bool:
        return self.repair_version is not None

    @property
    def tokens_in(self) -> int:
        return sum(c.tokens_in for c in self.calls)

    @property
    def tokens_out(self) -> int:
        return sum(c.tokens_out for c in self.calls)

    @property
    def cached_tokens(self) -> int:
        return sum(c.cached_tokens for c in self.calls)

    @property
    def seconds(self) -> float:
        return sum(c.seconds for c in self.calls)


def strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        stripped = stripped.rstrip().removesuffix("```")
    return stripped.strip()


def parse_reply[T: BaseModel](model_cls: type[T], content: str) -> tuple[T | None, str]:
    """The parsed reply, or None and what was wrong with it (never the reply itself)."""
    try:
        return model_cls.model_validate_json(strip_fences(content)), ""
    except ValidationError as exc:
        problems = [
            f"{'.'.join(str(p) for p in e['loc']) or 'document'}: {e['msg']}"
            for e in exc.errors(include_input=False, include_url=False)
        ]
        return None, "; ".join(problems)[:2000]


def chat_structured[T: BaseModel](
    provider: LlmProvider,
    model: str,
    messages: Sequence[ChatMessage],
    model_cls: type[T],
    *,
    max_output_tokens: int,
    invalid_event: str,
    after_first: Callable[[ChatResult], None] | None = None,
    reply_tokens: int | None = None,
) -> Structured[T]:
    """A truncated reply raises NoteCutOff (a cut-off reply would be "repaired" into a shortened
    one); invalid JSON gets one A9 repair, then NoteInvalid. `after_first` may raise on the first
    reply, before it is parsed. `reply_tokens` asks the provider for that much room for this
    call's replies (the repair's too) instead of its own setting."""
    schema = model_cls.model_json_schema()

    def call(chat: Sequence[ChatMessage]) -> ChatResult:
        if reply_tokens is None:
            result = provider.chat_json(model, chat, schema)
        else:
            result = provider.chat_json(model, chat, schema, max_output_tokens=reply_tokens)
        if result.truncated:
            raise NoteCutOff(max_output_tokens)
        return result

    first = call(messages)
    if after_first is not None:
        after_first(first)
    value, error = parse_reply(model_cls, first.content)
    if value is not None:
        return Structured(value, (first,), None)
    repair = load_prompt("a9_repair")
    system, user = repair.render(
        schema=json.dumps(schema, separators=(",", ":")),
        error=as_data(error),
        bad_output=as_data(first.content),
    )
    second = call([ChatMessage("system", system), ChatMessage("user", user)])
    value, error = parse_reply(model_cls, second.content)
    if value is None:
        log.warning(invalid_event, model=model, error=error)
        raise NoteInvalid(model)
    return Structured(value, (first, second), repair.version)
