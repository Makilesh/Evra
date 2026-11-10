import json

import pytest

from tests.unit.notes.fakes import FakeProvider
from tools.bakeoff_notes import FIXTURES, load_case
from tools.make_long_fixture import (
    Fact,
    Part,
    assign_times,
    expected_facts,
    generate_part,
    plant,
    split_long,
    to_json,
)

DANA = Fact("Dana starts on the 14th", ("dana", "14"), ((1, "Dana starts on the 14th."),))
LONG = FIXTURES / "one_on_one_60min_synthetic.json"


def test_a_fact_the_model_already_said_is_not_planted_again() -> None:
    lines = [(1, "So, uh, Dana starts on the 14th, right?"), (0, "Yeah.")]
    assert plant(lines, [DANA]) == (lines, 0)


def test_either_spelling_of_a_keyword_counts() -> None:
    beta = Fact("beta on March 3", ("beta", "march 3|3 march"), ((1, "Beta on March 3."),))
    lines = [(0, "So the beta is 3 March now.")]
    assert plant(lines, [beta]) == (lines, 0)


def test_a_missing_fact_is_planted_word_for_word_mid_part() -> None:
    lines = [(1, "a"), (0, "b"), (1, "c"), (0, "d")]
    assert plant(lines, [DANA]) == (
        [(1, "a"), (0, "b"), (1, "Dana starts on the 14th."), (1, "c"), (0, "d")],
        1,
    )


def test_a_generated_part_maps_speakers_to_channels_and_plants_missing_facts() -> None:
    reply = json.dumps(
        {
            "lines": [
                {"speaker": "Them", "text": "  Hi,   how was   the week? "},
                {"speaker": "You", "text": "Good."},
                {"speaker": "You", "text": "   "},
            ]
        }
    )
    provider = FakeProvider([reply])
    parts = [Part("small talk"), Part("hiring", (DANA,))]
    lines, planted = generate_part(provider, "fake:1b", parts, 1, words=700)
    assert lines == [(1, "Hi, how was the week?"), (1, "Dana starts on the 14th."), (0, "Good.")]
    assert planted == 1
    prompt = provider.calls[0][-1].content
    assert "hiring" in prompt
    assert "Dana starts on the 14th." in prompt


def test_a_cut_off_reply_is_an_error_not_a_short_part() -> None:
    provider = FakeProvider(['{"lines": [{"speaker": "You", "text": "Hi"}]}'], truncated=True)
    with pytest.raises(ValueError, match="cut off"):
        generate_part(provider, "fake:1b", [Part("small talk")], 0, words=700)


def test_long_lines_split_at_sentence_ends_like_speech_segments() -> None:
    text = (
        "Yeah, so the migration went fine. We moved every shard over the weekend, no trouble. Okay?"
    )
    assert split_long([(0, text)], max_words=8) == [
        (0, "Yeah, so the migration went fine."),
        (0, "We moved every shard over the weekend, no trouble."),
        (0, "Okay?"),
    ]


def test_short_sentences_stay_together_up_to_the_limit() -> None:
    assert split_long([(1, "Yeah. Okay. So the plan is set.")], max_words=8) == [
        (1, "Yeah. Okay. So the plan is set.")
    ]


def test_times_fill_the_meeting_in_order_with_speech_time_by_word_count() -> None:
    lines = [(1, "one two three"), (0, "yes")]
    utterances, wpm = assign_times(lines, total_ms=4_500, gap_ms=(500, 500))
    assert utterances == [
        {"ch": 1, "start_ms": 0, "end_ms": 3000, "text": "one two three"},
        {"ch": 0, "start_ms": 3500, "end_ms": 4500, "text": "yes"},
    ]
    assert wpm == 60.0


def test_each_fact_is_placed_at_the_minute_it_is_first_said() -> None:
    utterances = [
        {"ch": 1, "start_ms": 0, "end_ms": 4000, "text": "Hello."},
        {"ch": 1, "start_ms": 125_000, "end_ms": 128_000, "text": "Dana starts on the 14th."},
    ]
    assert expected_facts(utterances, [Part("intro"), Part("hiring", (DANA,))]) == [
        {"what": "Dana starts on the 14th", "keywords": ["dana", "14"], "minute": 2}
    ]


def test_the_fixture_file_reads_back_unchanged() -> None:
    fixture = {
        "synthetic": True,
        "title": "Weekly 1:1 (60 min)",
        "utterances": [{"ch": 0, "start_ms": 0, "end_ms": 900, "text": "Café, okay."}],
        "expected": [],
    }
    assert json.loads(to_json(fixture)) == fixture


def test_the_long_fixture_is_an_hour_with_facts_from_start_to_end() -> None:
    data = json.loads(LONG.read_text(encoding="utf-8"))
    assert data["synthetic"] is True
    case = load_case(LONG)
    assert 59 * 60_000 <= max(u.end_ms for u in case.utterances) <= 61 * 60_000
    minutes = [e["minute"] for e in data["expected"]]
    assert min(minutes) < 15
    assert max(minutes) >= 45
    texts = [u.text.lower() for u in case.utterances]
    for fact in case.expected:
        alternatives = [k.lower().split("|") for k in fact.keywords]
        said = any(all(any(a in t for a in alts) for alts in alternatives) for t in texts)
        assert said, fact.what
