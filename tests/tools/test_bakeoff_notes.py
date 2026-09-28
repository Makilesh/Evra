import json

from evra.config import LlmSettings
from evra.notes.validate import CheckedBullet, CheckedNote, CheckedSection
from tests.unit.notes.fakes import FakeProvider
from tools.bakeoff_notes import FIXTURES, Expected, Row, covered, format_table, load_case, run_case

FIXTURE = FIXTURES / "one_on_one_synthetic.json"


def test_fixture_is_synthetic_and_complete() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8"))["synthetic"] is True
    case = load_case(FIXTURE)
    assert len(case.utterances) == 27
    assert len(case.expected) == 10
    assert case.utterances[6].text.startswith("Good. Let's talk about the launch.")
    assert [u.channel for u in case.utterances[:2]] == [1, 0]


def _note(*texts: str) -> CheckedNote:
    bullets = tuple(CheckedBullet(t, ("x",)) for t in texts)
    return CheckedNote(
        (), (CheckedSection("discussion", "Discussion", bullets),), len(bullets), 0, {}
    )


def test_a_fact_is_covered_when_one_bullet_holds_every_keyword() -> None:
    fact = Expected("proposal by Thursday", ("proposal", "thursday|thu"))
    assert covered(_note("You send the proposal by Thursday."), fact)
    assert not covered(_note("You send the proposal.", "Due Thursday."), fact)


def test_run_case_scores_a_fake_model() -> None:
    reply = json.dumps(
        {
            "summary": [{"text": "The launch moves to October 14.", "citations": ["u:9"]}],
            "sections": [],
        }
    )
    row = run_case(FakeProvider([reply]), "fake:1b", load_case(FIXTURE), LlmSettings())
    assert (row.kept, row.dropped, row.error) == (1, 0, "")
    assert row.validity == 1.0
    assert row.coverage == 0.1


def test_run_case_reports_errors_instead_of_raising() -> None:
    row = run_case(FakeProvider(["{", "{"]), "fake:1b", load_case(FIXTURE), LlmSettings())
    assert row.error == "NoteInvalid"
    assert row.coverage is None


def test_table_has_a_row_per_run() -> None:
    rows = [
        Row("a", "c", 12.3, 4000, 600, False, 18, 2, 0.8, 1.0),
        Row("b", "c", 0.0, 0, 0, False, 0, 0, None, None, "LlmTimeout"),
    ]
    lines = format_table(rows)
    assert lines[0].startswith("| model |")
    assert len(lines) == 4
    assert lines[2] == "| a | c | 12.3 | 4000/600 | no | 18 | 2 | 90% | 80% | 100% |  |"
    assert lines[3].endswith("| LlmTimeout |")
