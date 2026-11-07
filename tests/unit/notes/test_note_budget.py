"""The prompt-size estimate against gemma4:12b's real counts (Ollama's prompt_eval_count for
prompt a1-v2, measured 2026-11-07), and the default budget against an hour-long 1:1."""

import pytest

from evra.config import LlmSettings
from evra.llm.schemas import NoteDraft
from evra.notes.prompt_input import NotePrompt, build_note_prompt
from evra.notes.templates import load_template
from tools.bakeoff_notes import FIXTURES, load_case


def _prompt(fixture: str) -> NotePrompt:
    case = load_case(FIXTURES / f"{fixture}.json")
    return build_note_prompt(
        meeting=case.meeting,
        utterances=case.utterances,
        template=load_template(str(case.meeting["template"])),
        schema=NoteDraft.model_json_schema(),
    )


@pytest.mark.parametrize(
    ("fixture", "ollama_count"),
    [("one_on_one_synthetic", 2062), ("one_on_one_60min_synthetic", 27878)],
)
def test_the_size_estimate_never_falls_far_below_the_real_count(
    fixture: str, ollama_count: int
) -> None:
    estimated = _prompt(fixture).estimated_tokens
    assert ollama_count * 0.98 <= estimated <= ollama_count * 1.3


def test_an_hour_long_1_1_at_the_owners_pace_fits_the_default_budget() -> None:
    settings = LlmSettings()
    room = settings.num_ctx - settings.max_output_tokens
    limit = min(settings.context_budget, room)
    assert _prompt("one_on_one_60min_synthetic").estimated_tokens <= limit
