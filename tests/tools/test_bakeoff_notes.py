import json
from dataclasses import replace

from evra.config import LlmSettings
from evra.notes.extract import CheckedItem
from evra.notes.validate import CheckedBullet, CheckedNote, CheckedSection
from tests.unit.notes.fakes import FakeProvider
from tools.bakeoff_notes import (
    FIXTURES,
    Dropped,
    Expected,
    Row,
    covered,
    format_drops,
    format_table,
    in_items,
    load_case,
    run_case,
)

FIXTURE = FIXTURES / "one_on_one_synthetic.json"
NO_ITEMS = json.dumps({"items": []})


def test_fixture_is_synthetic_and_complete() -> None:
    assert json.loads(FIXTURE.read_text(encoding="utf-8"))["synthetic"] is True
    case = load_case(FIXTURE)
    assert len(case.utterances) == 27
    assert len(case.expected) == 10
    assert case.utterances[6].text.startswith("Good. Let's talk about the launch.")
    assert [u.channel for u in case.utterances[:2]] == [1, 0]
    assert [e.what for e in case.expected if e.commitment] == [
        "Them tells marketing",
        "You send the designer proposal by Thursday",
        "Them asks Priya about API limits",
    ]


def _note(*texts: str) -> CheckedNote:
    bullets = tuple(CheckedBullet(t, ("x",)) for t in texts)
    return CheckedNote(
        (), (CheckedSection("discussion", "Discussion", bullets),), len(bullets), 0, {}
    )


def test_a_fact_is_covered_when_one_bullet_holds_every_keyword() -> None:
    fact = Expected("proposal by Thursday", ("proposal", "thursday|thu"))
    assert covered(_note("You send the proposal by Thursday."), fact)
    assert not covered(_note("You send the proposal.", "Due Thursday."), fact)


def test_a_commitment_is_found_in_one_action_item_as_it_is_shown() -> None:
    fact = Expected("proposal by Thursday", ("proposal", "thursday|thu"), commitment=True)
    item = CheckedItem("action_item", "Send the proposal", ("x",), "You", "by Thursday", 0.9)
    assert in_items([item], fact, kind="action_item")  # its due date counts, as shown
    assert not in_items([item], fact, kind="decision")
    assert not in_items([replace(item, due=None)], fact)


def test_run_case_scores_a_fake_model_as_the_window_writes_the_note() -> None:
    reply = json.dumps(
        {
            "summary": [
                {"text": "The launch moves to October 14.", "citations": ["u:9"]},
                {"text": "Everyone loved the cake.", "citations": ["u:9"]},
            ],
            "sections": [],
        }
    )
    proposal = {
        "text": "Send the designer proposal",
        "owner": "me",
        "due": "by Thursday",
        "confidence": 0.9,
        "citations": ["u:13", "u:14"],
    }
    provider = FakeProvider([reply, json.dumps({"items": [proposal]}), NO_ITEMS, NO_ITEMS])
    row = run_case(provider, "fake:1b", load_case(FIXTURE), LlmSettings())
    assert (row.kept, row.dropped, row.error) == (1, 1, "")
    assert row.validity == 0.5
    assert row.coverage == 0.1  # the launch date, in the note's own points
    assert row.with_items == 0.2  # and the proposal, as an action item
    assert (row.items, row.commitments) == ((1, 0, 0), (1, 3))
    assert row.tasks_as_decisions == 0
    assert row.reasons == {"unsupported": 1}
    assert row.drops == (
        Dropped(
            "Everyone loved the cake.",
            "unsupported",
            ("u:9: Then let's agree on October 14. I'll tell marketing today.",),
        ),
    )
    assert provider.embed_calls  # checked by meaning too, as the window does


def test_run_case_reports_errors_instead_of_raising() -> None:
    provider = FakeProvider(["{", "{", NO_ITEMS, NO_ITEMS, NO_ITEMS])
    row = run_case(provider, "fake:1b", load_case(FIXTURE), LlmSettings())
    assert row.error == "NoteInvalid"
    assert row.coverage is None


def test_table_has_a_row_per_run() -> None:
    rows = [
        Row(
            "a",
            "c",
            12.3,
            4000,
            600,
            False,
            18,
            2,
            0.8,
            1.0,
            rescued=1,
            total_seconds=40.5,
            items=(3, 2, 1),
            with_items=0.9,
            commitments=(2, 3),
        ),
        Row("b", "c", 0.0, 0, 0, False, 0, 0, None, None, "LlmTimeout"),
    ]
    lines = format_table(rows)
    assert lines[0].startswith("| model |")
    assert lines[1].count("---") == lines[0].count("|") - 1
    assert len(lines) == 4
    assert lines[2] == (
        "| a | c | 12.3 | 40.5 | 4000/600 | no | 18 | 2 | 1 | 90% | 80% | 90% | 3/2/1 | 2/3"
        " | 100% |  |"
    )
    assert lines[3].endswith("| LlmTimeout |")


def test_drops_are_listed_with_reasons_and_what_they_cite() -> None:
    drop = Dropped("Dana starts on the 14th.", "name_not_cited", ("u:3: She starts soon.",))
    row = Row(
        "a",
        "c",
        1.0,
        1,
        1,
        False,
        1,
        1,
        None,
        None,
        reasons={"name_not_cited": 1},
        drops=(drop,),
        tasks_as_decisions=2,
    )
    assert format_drops(row) == [
        "  dropped: name_not_cited 1",
        "    - [name_not_cited] Dana starts on the 14th.",
        "        u:3: She starts soon.",
        "  decisions that repeated an action item: 2",
    ]
    assert format_drops(Row("a", "c", 1.0, 1, 1, False, 1, 0, None, None)) == [
        "  dropped: none",
        "  decisions that repeated an action item: 0",
    ]
