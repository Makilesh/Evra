"""The prep brief (A13, Plan C): one call over the notes of a person's recent 1:1s, each point
checked against the notes it cites as m:<n>."""

import json
from datetime import datetime

import pytest
import structlog

from evra.config import LlmSettings
from evra.llm.schemas import NoteBullet, PrepBrief
from evra.notes.brief import BRIEF_MEETINGS, BriefSource, brief_settings, write_brief
from evra.notes.context import LOOKALIKE_GT, LOOKALIKE_LT
from evra.notes.errors import NoteTooLong
from evra.notes.validate import CheckedBullet, Grounder
from tests.unit.notes.fakes import FakeProvider

LAST = datetime(2026, 11, 24, 10, 0).timestamp() * 1000
BEFORE = datetime(2026, 11, 17, 10, 0).timestamp() * 1000
SOURCES = [
    BriefSource(
        "m:1",
        "meeting-1",
        "Launch date and the designer",
        int(LAST),
        "- The launch moves to October 14.\n- You will send the designer proposal by Thursday.",
    ),
    BriefSource(
        "m:2",
        "meeting-2",
        "Budget <check>",
        int(BEFORE),
        "- Twelve thousand dollars are left for contractors this quarter.",
    ),
]
SETTINGS = LlmSettings(model="fake:1b")


def reply(*points: tuple[str, list[str]]) -> str:
    return json.dumps({"points": [{"text": t, "citations": c} for t, c in points]})


def test_brief_cites_meetings() -> None:
    provider = FakeProvider(
        [
            reply(
                ("The launch moves to October 14.", ["m:1"]),
                ("Twelve thousand dollars are left for contractors.", ["m:2"]),
                ("The designer costs 4,000 dollars.", ["m:1"]),  # no note says 4,000: dropped
            )
        ]
    )
    result = write_brief(
        provider,
        model="fake:1b",
        person="Priya",
        sources=SOURCES,
        open_items=["You: Send the designer proposal (due by Thursday)", "Priya: Tell marketing"],
        settings=SETTINGS,
    )
    assert result.state == "written"
    assert result.points == (
        CheckedBullet("The launch moves to October 14.", ("m:1",)),
        CheckedBullet("Twelve thousand dollars are left for contractors.", ("m:2",)),
    )
    assert result.sources == tuple(SOURCES)
    assert (result.model, result.prompt_version) == ("fake:1b", "a13-v1")  # no A0: not one meeting
    [call] = provider.calls
    system, user = call
    assert (system.role, user.role) == ("system", "user")
    # each meeting's note is a <notes> block headed [m:k] {title} · {date}, its text made inert
    assert (
        "<notes>\n[m:1] Launch date and the designer · 2026-11-24\n"
        "- The launch moves to October 14.\n- You will send the designer proposal by Thursday.\n"
        "</notes>"
    ) in system.content
    assert f"[m:2] Budget {LOOKALIKE_LT}check{LOOKALIKE_GT} · 2026-11-17" in system.content
    assert system.content.index("[m:1]") < system.content.index("[m:2]")  # newest first
    assert user.content.startswith(
        "Prepare the owner for their next 1:1 with Priya, from the notes of their recent 1:1s"
    )
    assert (
        "4. Open promises still on the owner's list: "
        "You: Send the designer proposal (due by Thursday); Priya: Tell marketing\n"
    ) in user.content
    assert json.dumps(PrepBrief.model_json_schema(), separators=(",", ":")) in user.content


def test_a_point_may_name_the_person() -> None:
    """RC3: a note written before the owner said who the 1:1 was with says "Them"; a point that
    names the person still passes, as the note's own check lets it."""
    notes = [BriefSource("m:1", "m", "Weekly 1:1", int(LAST), "- Them: ask about the API limits.")]
    provider = FakeProvider([reply(("Priya will ask about the API limits.", ["m:1"]))])
    result = write_brief(
        provider,
        model="fake:1b",
        person="Priya Shah",
        sources=notes,
        open_items=[],
        settings=SETTINGS,
    )
    assert [p.text for p in result.points] == ["Priya will ask about the API limits."]
    assert "4. Open promises still on the owner's list: none\n" in provider.calls[0][1].content


def test_a_brief_with_no_point_kept_is_unchecked() -> None:
    provider = FakeProvider([reply(("Marcus approved a 9,000 dollar budget.", ["m:1", "u:3"]))])
    result = write_brief(
        provider, model="fake:1b", person="Priya", sources=SOURCES, open_items=[], settings=SETTINGS
    )
    assert (result.state, result.points) == ("unchecked", ())


def test_a_repaired_brief_says_so_in_its_version() -> None:
    provider = FakeProvider(["not json", reply(("The launch moves to October 14.", ["m:1"]))])
    result = write_brief(
        provider, model="fake:1b", person="Priya", sources=SOURCES, open_items=[], settings=SETTINGS
    )
    assert (result.state, result.prompt_version) == ("written", "a13-v1+a9-v1")


def test_a_prompt_ollama_cut_is_too_long() -> None:
    room = SETTINGS.num_ctx - SETTINGS.max_output_tokens
    provider = FakeProvider([reply(("The launch moves to October 14.", ["m:1"]))], tokens_in=room)
    with pytest.raises(NoteTooLong):
        write_brief(
            provider,
            model="fake:1b",
            person="Priya",
            sources=SOURCES,
            open_items=[],
            settings=SETTINGS,
        )


def test_the_brief_logs_counts_never_names_or_text() -> None:
    provider = FakeProvider([reply(("The launch moves to October 14.", ["m:1"]))])
    with structlog.testing.capture_logs() as logs:
        write_brief(
            provider,
            model="fake:1b",
            person="Priya",
            sources=SOURCES,
            open_items=["Priya: Tell marketing"],
            settings=SETTINGS,
        )
    assert [e["event"] for e in logs] == ["brief_written"]
    assert logs[0]["kept"] == 1 and logs[0]["meetings"] == 2
    dumped = json.dumps(logs).lower()
    assert "priya" not in dumped and "launch" not in dumped and "marketing" not in dumped


def test_the_brief_reads_three_meetings_with_a_short_reply_and_wait() -> None:
    llm = LlmSettings(model="fake:1b", timeout_s=600, ask_timeout_s=180, max_output_tokens=4096)
    settings = brief_settings(llm)
    assert BRIEF_MEETINGS == 3
    assert (settings.max_output_tokens, settings.timeout_s) == (1024, 180)
    # the model, its context size and its keep-alive stay the note's: Ollama never reloads it
    assert (settings.model, settings.num_ctx, settings.keep_alive) == ("fake:1b", 32768, "30s")
    thinking = brief_settings(llm.model_copy(update={"think": True}))
    assert thinking.max_output_tokens == 4096  # thinking needs the note's room


def test_grounder_without_nearby() -> None:
    """Lines of one call sit next to each other, so a name said a line away is cited from there;
    a brief's sources are meetings, not lines, and its check turns that off (nearby=0). The
    brief's m:<n> pass as aliases, in the list or in brackets in the text, and stay m:<n> (a
    note's n:<k> is read as the owner's notes)."""
    lines = {"a": "We should ship the export.", "b": "Marcus agreed."}
    point = NoteBullet(text="Marcus will ship the export.", citations=["u:1"])
    near = Grounder(aliases={"u:1": "a", "u:2": "b"}, utterance_text=lines)
    assert near.check(point) == (CheckedBullet("Marcus will ship the export.", ("a", "b")), "")
    alone = Grounder(aliases={"u:1": "a", "u:2": "b"}, utterance_text=lines, nearby=0)
    assert alone.check(point) == (None, "name_not_cited")

    notes = {"m:1": "- The export ships on Friday.", "m:2": "- Marcus owns the export."}
    named = NoteBullet(text="Marcus ships the export on Friday.", citations=["m:1"])
    # with the rule on, m:2 would count as the line after m:1
    lined_up = Grounder(aliases={k: k for k in notes}, utterance_text=notes).check(named)
    assert lined_up == (CheckedBullet("Marcus ships the export on Friday.", ("m:1", "m:2")), "")
    brief = Grounder(aliases={k: k for k in notes}, utterance_text=notes, nearby=0)
    assert brief.check(named) == (None, "name_not_cited")
    inline = NoteBullet(text="The export ships on Friday [m:1].", citations=["m:1"])
    assert brief.check(inline) == (CheckedBullet("The export ships on Friday.", ("m:1",)), "")
    label = NoteBullet(text="The export ships on Friday.", citations=["n:1"])
    assert brief.check(label) == (None, "no_valid_citation")  # the owner's notes, not given here
