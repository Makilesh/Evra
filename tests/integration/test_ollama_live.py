"""A real Ollama round trip. Runs with `uv run pytest -m hardware` when Ollama is up and
one of the bake-off models is installed; skipped otherwise."""

from pathlib import Path

import pytest
from pydantic import BaseModel

from evra.config import LlmSettings
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import ChatMessage, LlmError
from evra.notes.title import MAX_WORDS, has_placeholder_title, name_meeting, title_settings
from evra.store.db import connect
from evra.store.migrate import migrate
from tests.unit.notes.fakes import saved_meeting

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


def test_a_real_model_names_a_meeting_from_its_note(tmp_path: Path) -> None:
    assert MODEL is not None
    conn = connect(tmp_path / "evra.db")
    try:
        migrate(conn)
        mid = saved_meeting(conn, "Recording 2026-11-11 15:25")
        llm = LlmSettings(model=MODEL, keep_alive="0s", num_ctx=4096)
        title = name_meeting(conn, mid, provider=OllamaProvider(title_settings(llm)), model=MODEL)
    finally:
        conn.close()
    assert title is not None and not has_placeholder_title(title)
    assert 1 <= len(title.split()) <= MAX_WORDS


def test_a_real_embedding_model_returns_unit_vectors() -> None:
    settings = LlmSettings(keep_alive="0s")
    provider = OllamaProvider(settings)
    if settings.embedding_model not in provider.installed_models():
        pytest.skip("embedding model not installed")
    vectors = provider.embed(settings.embedding_model, ["The launch moves.", "Send the proposal."])
    assert len(vectors) == 2
    assert len(vectors[0]) == len(vectors[1]) > 100
    assert abs(sum(x * x for x in vectors[0]) - 1.0) < 1e-3
