import json

import pytest

from evra.config import LlmSettings
from evra.notes.templates import load_template
from evra.notes.writer import NoteInvalid, NoteResult, NoteTooLong, NoTranscript, write_note
from evra.store.meetings import Utterance
from tests.unit.notes.fakes import FakeProvider, utt

MEETING = {
    "id": "m",
    "title": "Weekly 1:1",
    "started_at": 1_790_000_000_000,
    "situation": "call_headphones",
    "template": "one_on_one",
}
UTTERANCES = [
    utt("a", 0, 0, 4_000, "I finished the search migration on Tuesday.", seq=0),
    utt("b", 1, 5_000, 8_000, "I'll ask Priya directly tomorrow.", seq=1),
]
GOOD = json.dumps(
    {
        "summary": [
            {"text": "You finished the search migration on Tuesday.", "citations": ["u:1"]}
        ],
        "sections": [
            {
                "section_id": "action_items",
                "title": "Action items",
                "bullets": [{"text": "Them will ask Priya directly.", "citations": ["u:2"]}],
            }
        ],
        "language": "en",
    }
)
TEMPLATE = load_template("one_on_one")


def write(
    provider: FakeProvider,
    settings: LlmSettings | None = None,
    utterances: list[Utterance] = UTTERANCES,
) -> NoteResult:
    return write_note(
        provider,
        model="fake:1b",
        meeting=MEETING,
        utterances=utterances,
        template=TEMPLATE,
        settings=settings or LlmSettings(),
    )


def test_a_valid_reply_becomes_a_checked_note() -> None:
    provider = FakeProvider([GOOD])
    result = write(provider)
    assert (result.note.kept, result.note.dropped, result.repaired) == (2, 0, False)
    assert result.prompt_version == "a1-v1"
    assert (result.tokens_in, result.tokens_out) == (100, 50)
    assert result.template == "one_on_one"
    system, user = provider.calls[0]
    assert system.role == "system" and user.role == "user"
    assert "[u:1] [00:00] You: I finished" in user.content


def test_fenced_json_is_accepted() -> None:
    result = write(FakeProvider(["```json\n" + GOOD + "\n```"]))
    assert (result.note.kept, result.repaired) == (2, False)


def test_invalid_json_gets_one_repair() -> None:
    provider = FakeProvider(['{"summary": [', GOOD])
    result = write(provider)
    assert result.repaired
    assert result.prompt_version == "a1-v1+a9-v1"
    assert result.tokens_in == 200
    repair_user = provider.calls[1][1].content
    assert "<error>" in repair_user and '{"summary": [' in repair_user


def test_a_second_invalid_reply_fails_without_leaking_content() -> None:
    provider = FakeProvider(['{"summary": "SECRET-PLAN"}', "```json\nstill SECRET-PLAN\n```"])
    with pytest.raises(NoteInvalid) as caught:
        write(provider)
    assert "SECRET" not in str(caught.value)
    assert len(provider.calls) == 2


def test_too_long_is_refused_before_calling() -> None:
    provider = FakeProvider([GOOD])
    long = [utt(str(i), i % 2, i * 1000, i * 1000 + 900, "word " * 40, seq=i) for i in range(100)]
    with pytest.raises(NoteTooLong) as caught:
        write(provider, LlmSettings(context_budget=1000), long)
    assert caught.value.limit == 1000 and caught.value.estimated > 1000
    assert provider.calls == []


def test_a_truncated_prompt_is_detected() -> None:
    provider = FakeProvider([GOOD], tokens_in=32768 - 4096)
    with pytest.raises(NoteTooLong):
        write(provider)


def test_no_transcript() -> None:
    with pytest.raises(NoTranscript):
        write(FakeProvider([GOOD]), utterances=[])
