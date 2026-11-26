import json

from evra.config import LlmSettings
from tests.unit.notes.fakes import FakeProvider
from tools.bakeoff_ask import (
    Phase,
    Probe,
    Recorder,
    Row,
    answer_text,
    ask_one,
    correct,
    load_probes,
    summary,
)
from tools.bakeoff_notes import FIXTURES, load_case

LONG = FIXTURES / "one_on_one_60min_synthetic.json"
OUTAGE = Probe("How long was the outage?", ("47",))
CRM = Probe("Which CRM did we choose?", ())


def test_correct_needs_every_keyword_and_takes_either_spelling() -> None:
    keywords = ("atlas", "march 3|3 march")
    assert correct("The Atlas beta moves to March 3.", keywords)
    assert correct("ATLAS is on 3 March now.", keywords)
    assert not correct("The beta moves to March 3.", keywords)
    assert not correct("", keywords)


def test_answer_text_drops_inline_citations() -> None:
    text = answer_text(["Dana starts soon [u:140].", "She joins the [u:3, u:4] team."])
    assert text == "Dana starts soon. She joins the team."
    assert not correct(text, ("dana", "14"))


def test_every_fact_has_a_question_that_does_not_give_the_answer_away() -> None:
    probes = load_probes(LONG)
    facts = [p for p in probes if not p.absent]
    assert len(facts) == 13
    assert [p.question for p in probes if p.absent] == [
        "What salary increase did we agree on?",
        "What did we decide about moving to a new office?",
        "Which CRM did we choose?",
    ]
    assert facts[0] == Probe(
        "How many customers have signed up for the beta so far?", ("38", "customer")
    )
    for probe in facts:
        assert not correct(probe.question, probe.keywords), probe.question


def test_the_note_bakeoff_still_reads_the_fixture() -> None:
    case = load_case(LONG)
    assert len(case.expected) == 13
    assert case.expected[0].keywords == ("38", "customer")


def _row(
    phase: Phase,
    keywords: tuple[str, ...] = ("38", "customer"),
    state: str = "answered",
    answer: str = "",
    shown: str = "",
    *,
    seconds: float = 1.0,
    cached: int = 0,
    kept: int = 1,
    dropped: int = 0,
    error: str = "",
) -> Row:
    return Row(
        model="m",
        phase=phase,
        question="q?",
        keywords=keywords,
        state=state,
        answer=answer,
        shown=shown,
        kept=kept,
        dropped=dropped,
        seconds=seconds,
        tokens_in=27000,
        cached_tokens=cached,
        excerpt=False,
        error=error,
    )


def test_summary_scores_facts_absent_topics_checks_and_times() -> None:
    said = "38 customers signed up for the beta."
    raise_ = "A 5% raise."
    after_note = _row("after_note", answer=said, shown=said, seconds=3.5, cached=26700)
    rows = [
        _row("cold", answer=said, shown=said, seconds=30.0),
        _row("warm", ("dana", "14"), "not_found", kept=0, seconds=2.0, cached=26900),
        _row("warm", ("47",), "unchecked", "47.", kept=0, dropped=1, seconds=3.0, cached=26900),
        _row("warm", (), "not_found", kept=0, seconds=1.0, cached=26900),
        _row("warm", (), "answered", raise_, raise_, seconds=4.0, cached=26800),
        _row("warm", ("lisbon",), "failed", kept=0, seconds=0.0, error="LlmTimeout"),
        after_note,
    ]
    s = summary(rows)
    assert (s.facts, s.correct, s.shown_correct, s.checked) == (4, 2, 1, 1)
    assert (s.absent, s.not_discussed) == (2, 1)
    assert (s.kept, s.dropped, s.errors) == (1, 1, 1)
    assert s.cold_seconds == 30.0
    assert (s.follow_ups, s.follow_up_median, s.follow_up_worst) == (4, 2.5, 4.0)
    assert s.follow_up_reused == 26900
    assert s.after_note is after_note
    assert s.excerpt is False


def test_summary_of_a_failed_run_has_no_times() -> None:
    s = summary([_row("cold", state="failed", kept=0, error="LlmUnavailable")])
    assert (s.facts, s.correct, s.errors) == (1, 0, 1)
    assert s.cold_seconds is None
    assert (s.follow_ups, s.follow_up_median, s.after_note) == (0, None, None)


def test_a_question_is_scored_on_the_models_answer_before_the_check() -> None:
    reply = json.dumps(
        {
            "found": True,
            "points": [{"text": "The outage lasted 47 minutes.", "citations": ["u:1"]}],
        }
    )
    provider = Recorder(FakeProvider([reply]))
    row = ask_one(provider, "fake:1b", load_case(LONG), OUTAGE, LlmSettings(), "warm")
    assert (row.state, row.kept, row.dropped) == ("unchecked", 0, 1)  # u:1 is a greeting
    assert row.correct
    assert (row.answer, row.shown) == ("The outage lasted 47 minutes.", "")
    assert (row.tokens_in, row.cached_tokens, row.excerpt) == (100, 0, False)


def test_an_absent_topic_is_right_only_when_not_discussed() -> None:
    not_found = json.dumps({"found": False, "points": []})
    row = ask_one(
        Recorder(FakeProvider([not_found])), "fake:1b", load_case(LONG), CRM, LlmSettings(), "warm"
    )
    assert (row.state, row.correct, row.answer) == ("not_found", True, "")


def test_a_failed_question_is_a_row_not_a_crash() -> None:
    provider = Recorder(FakeProvider(["{", "{"]))
    row = ask_one(provider, "fake:1b", load_case(LONG), OUTAGE, LlmSettings(), "cold")
    assert (row.state, row.error, row.correct) == ("failed", "NoteInvalid", False)
    assert len(provider.replies) == 2  # the reply and its one repair
