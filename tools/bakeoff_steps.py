"""The window's steps around asking, for the asking bake-off: naming a meeting after its note
(A8), the Ask tab's pre-read of a long call, and unloading a model so the next call is cold."""

from __future__ import annotations

import contextlib
import time
from collections.abc import Sequence

from evra.config import LlmSettings
from evra.llm.ollama import OllamaProvider
from evra.llm.provider import LlmError, LlmProvider
from evra.llm.schemas import MeetingTitle
from evra.notes.ask import embed_parts
from evra.notes.context import build_context
from evra.notes.semantic import Embedder
from evra.notes.structured import parse_reply
from evra.notes.title import clean_generated_title, title_messages, title_settings
from evra.notes.validate import CheckedNote
from evra.store.meetings import Utterance
from tools.bakeoff_notes import Case


def title_after_note(
    llm: LlmSettings, model: str, case: Case, note: CheckedNote
) -> tuple[str | None, float]:
    """The window's next step: the title call (A8) on the meeting's shared context, from the
    note just written. Returns the cleaned title and the seconds it took."""
    bullets = [b.text for b in note.summary] + [b.text for s in note.sections for b in s.bullets]
    text = "\n".join("- " + " ".join(b.split()) for b in bullets)
    context = build_context(meeting=case.meeting, utterances=case.utterances)
    messages, _ = title_messages(context, text)
    started = time.monotonic()
    reply = OllamaProvider(title_settings(llm)).chat_json(
        model, messages, MeetingTitle.model_json_schema()
    )
    seconds = time.monotonic() - started
    raw, _ = parse_reply(MeetingTitle, reply.content)
    return (None if raw is None else clean_generated_title(raw.title)), seconds


def pre_read(
    provider: LlmProvider, model: str, embedder: Embedder, utterances: Sequence[Utterance]
) -> float:
    """The Ask tab's pre-read of a call too long to read whole, as the app does it: the model
    loaded first, then the call's parts embedded into the meeting's embedder. Returns seconds."""
    started = time.monotonic()
    with contextlib.suppress(LlmError):
        provider.load(model)
    embed_parts(embedder, utterances)
    return time.monotonic() - started


def unload(provider: OllamaProvider, model: str) -> None:
    """Unload the model and wait until Ollama no longer lists it, so the next call is cold."""
    with contextlib.suppress(LlmError):
        provider.unload(model)
        for _ in range(60):
            if provider.gpu_share(model) is None:
                return
            time.sleep(0.25)
