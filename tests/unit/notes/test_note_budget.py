"""The prompt-size estimate against gemma4:12b's real counts (Ollama's prompt_eval_count for
prompts a0-v1+a1-v4, measured 2026-11-27), and the default budget against an hour-long 1:1."""

import pytest

from evra.config import LlmSettings
from evra.llm.schemas import NoteDraft
from evra.notes.prompt_input import NotePrompt, build_note_prompt, note_prompt
from evra.notes.templates import load_template
from evra.notes.user_notes import notes_context
from tools.bakeoff_notes import FIXTURES, load_case
from tools.notes_fixture import linked_notes, with_notes


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
    [("one_on_one_synthetic", 1990), ("one_on_one_60min_synthetic", 27806)],
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


def test_the_hour_with_its_typed_notes_fits_the_default_budget() -> None:
    """RB64: the hour's 12 typed notes (linked here by time and words) took it over the old
    28,000; at 28,400 it is still read in one pass."""
    case = with_notes(load_case(FIXTURES / "one_on_one_60min_synthetic.json"))
    context = notes_context(
        meeting=case.meeting, utterances=case.utterances, notes=linked_notes(case, None)
    )
    estimated = note_prompt(
        context, template=load_template("one_on_one"), schema=NoteDraft.model_json_schema()
    ).estimated_tokens
    settings = LlmSettings()
    room = settings.num_ctx - settings.max_output_tokens
    assert 28_000 < estimated <= min(settings.context_budget, room)
