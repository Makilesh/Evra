"""A real Ollama round trip. Runs with `uv run pytest -m hardware` when Ollama is up and
one of the bake-off models is installed; skipped otherwise."""

import pytest
from pydantic import BaseModel

from evra.config import LlmSettings
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import ChatMessage, LlmError

CANDIDATES = ("gemma4:12b", "qwen3.5:9b", "ministral-3:14b")


def _installed_candidate() -> str | None:
    try:
        installed = OllamaProvider(LlmSettings(timeout_s=2)).installed_models()
    except LlmError:
        return None
    return next((m for m in CANDIDATES if m in installed), None)


MODEL = _installed_candidate()
pytestmark = [
    pytest.mark.hardware,
    pytest.mark.skipif(MODEL is None, reason="Ollama not running or no bake-off model installed"),
]


class Greeting(BaseModel):
    greeting: str


def test_structured_reply_from_a_real_model() -> None:
    assert MODEL is not None
    provider = OllamaProvider(LlmSettings(keep_alive="0s", num_ctx=2048))
    result = provider.chat_json(
        MODEL, [ChatMessage("user", "Greet me in three words.")], Greeting.model_json_schema()
    )
    assert Greeting.model_validate_json(result.content).greeting
    assert result.tokens_in > 0
