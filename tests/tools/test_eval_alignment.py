import json

import pytest

from evra.store.notepad import NoteLine
from tools.bakeoff_notes import FIXTURES, load_case
from tools.bakeoff_parts import LONG_FIXTURE
from tools.eval_alignment import main, score, spread
from tools.notes_fixture import NOTES_FIXTURE, load_notes


def test_the_notes_fixture_is_synthetic_and_labelled() -> None:
    assert json.loads(NOTES_FIXTURE.read_text(encoding="utf-8"))["synthetic"] is True
    case = load_case(FIXTURES / LONG_FIXTURE)
    notes = load_notes(NOTES_FIXTURE, case.utterances)
    assert len(notes.lines) == 12 and len({line.id for line in notes.lines}) == 12
    assert [line.position for line in notes.lines] == list(range(12))
    ends = {u.id: u.end_ms for u in case.utterances}
    for line in notes.lines:
        assert (line.phase, line.is_context, line.aligned) == ("during", False, ())
        about = notes.about[line.id]
        assert about and line.captured_at_ms is not None
        # typed after every line it notes, at most 45 s after the first of them ended
        assert all(ends[uid] < line.captured_at_ms for uid in about)
        assert line.captured_at_ms - min(ends[uid] for uid in about) <= 45_000


def test_precision_and_recall_over_every_note() -> None:
    linked = {"n1": [("a", 0.9), ("x", 0.5)], "n2": [("c", 0.4)]}
    about = {"n1": frozenset({"a", "b"}), "n2": frozenset({"c"}), "n3": frozenset({"d"})}
    result = score(linked, about)
    assert (result.kept, result.labelled, result.hits) == (3, 4, 2)
    assert (result.precision, result.recall) == (pytest.approx(2 / 3), 0.5)
    assert score({}, about).precision is None  # nothing linked: no precision to speak of


def test_the_timing_spreads_lines_over_the_call() -> None:
    lines = [
        NoteLine("a", 0, "Budget", 1_000, "during", False, ()),
        NoteLine("b", 1, "Dana", 2_000, "during", False, ()),
    ]
    assert [(n.id, n.position, n.text, n.captured_at_ms) for n in spread(lines, 4, 60_000)] == [
        ("t0", 0, "Budget", 7_500),
        ("t1", 1, "Dana", 22_500),
        ("t2", 2, "Budget", 37_500),
        ("t3", 3, "Dana", 52_500),
    ]


def test_the_evaluation_runs_by_time_and_words_alone(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--no-embed", "--sweep"]) == 0
    out = capsys.readouterr().out
    assert "precision" in out and "recall" in out
    assert "50 lines" in out  # §7.2's timing: 50 lines over the hour
