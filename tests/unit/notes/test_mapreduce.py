"""A long call read in parts and combined (BUILD.md §7.4, A2/A3; rulings RB24-RB33)."""

import json
from collections.abc import Mapping, Sequence
from typing import Any

import pytest
import structlog

from evra.config import LlmSettings
from evra.llm.provider import ChatMessage, ChatResult
from evra.notes.context import ELLIPSIS, EN_DASH, NONE, build_context
from evra.notes.errors import NoteCutOff, NoteInvalid, NoteTooLong
from evra.notes.extract import Extraction
from evra.notes.job import generation_version
from evra.notes.mapreduce import COMBINE_NOTE, write_long_note
from evra.notes.semantic import Embedder, SemanticCheck
from evra.notes.templates import load_template
from evra.notes.validate import Grounder
from evra.notes.writer import NoteResult
from evra.store.meetings import Utterance
from tests.unit.notes.fakes import FakeProvider, utt

MEETING = {
    "id": "m",
    "title": "Weekly 1:1",
    "started_at": 1_790_000_000_000,
    "situation": "call_headphones",
    "template": "one_on_one",
}
TEMPLATE = load_template("one_on_one")
SAID = {  # line k is u:{k+1}; every line lasts 10 s and the speaker changes on every line
    4: "The Atlas beta moves to March 3.",
    19: "Can you write the postmortem by Friday?",
    20: "Sure, I'll write the postmortem by Friday.",
    56: "I'll update the deck and send it to Priya.",
    57: "Do we sunset the legacy API?",
    79: "We decided: we keep the legacy API until June.",
    84: "So to recap, I'll write the postmortem by Friday.",
}
# 15 minutes: part 1 is lines 0-59 (u:1-u:60, to 10:00), part 2 lines 54-89 (u:55-u:90, from 09:00)
LINES: list[Utterance] = [
    utt(f"k{k}", k % 2, k * 10_000, (k + 1) * 10_000, SAID.get(k, "Some small talk."), seq=k)
    for k in range(90)
]
CUT = "<cut off>"  # a reply that hit the output limit


def point(kind: str, text: str, cites: list[str], **kw: Any) -> dict[str, Any]:
    return {"kind": kind, "text": text, "citations": cites} | kw


def digest(index: int, *points: dict[str, Any]) -> str:
    return json.dumps({"window_index": index, "points": list(points)})


PART1 = digest(
    7,  # the model's own number: never trusted (RB33)
    point("topic", "The Atlas beta timing", ["u:5"]),  # p1
    point("decision", "The Atlas beta moves to March 3", ["u:5"]),  # p2
    point("commitment", "Write the postmortem", ["u:20", "u:21"], owner="You", due="by Friday"),
    point("commitment", "Update the deck", ["u:57"], owner="me"),  # p4
    point("commitment", "Send the deck to Priya", ["u:57"], owner="You"),  # p5
    point("question", "Do we sunset the legacy API?", ["u:58"], owner="Priya"),  # p6
    point("commitment", "Book the Lisbon venue", ["u:5"], owner="You"),  # p7: unsupported
)
PART2 = digest(
    1,
    point("commitment", "Update the deck", ["u:57", "u:56"], owner="You"),  # p8, the overlap
    point("commitment", "Send the deck to Priya", ["u:57"], owner="You"),  # p9
    point("question", "Do we sunset the legacy API?", ["u:58"]),  # p10
    point("decision", "Keep the legacy API until June", ["u:80"]),  # p11
    point(  # p12: the recap, in other words and from another line
        "commitment", "Write the postmortem for the outage", ["u:85"], owner="You", due="by Friday"
    ),
    point("point", "You recapped the postmortem", ["u:85"]),  # p13
)


def combined(**extra: Any) -> str:
    return json.dumps(
        {
            "summary": [{"text": "The Atlas beta moves to March 3.", "citations": ["u:5"]}],
            "sections": [
                {
                    "section_id": "discussion",
                    "title": "Discussion",
                    "bullets": [
                        {
                            "text": "Them asked whether to sunset the legacy API.",
                            "citations": ["u:58"],
                        }
                    ],
                }
            ],
        }
        | extra
    )


class Scripted(FakeProvider):
    """Replies in order (CUT is cut off at the output limit), and notes whether each request was
    a chat or an embedding."""

    def __init__(self, replies: list[str], tokens_in: int = 100) -> None:
        super().__init__(replies, tokens_in=tokens_in)
        self.order: list[str] = []

    def chat_json(
        self,
        model: str,
        messages: Sequence[ChatMessage],
        schema: Mapping[str, Any],
        *,
        max_output_tokens: int | None = None,
    ) -> ChatResult:
        self.order.append("chat")
        self.calls.append(list(messages))
        self.reply_room.append(max_output_tokens)
        reply = self.replies.pop(0)
        return ChatResult("{" if reply == CUT else reply, self.tokens_in, 50, 0.5, reply == CUT)

    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        self.order.append("embed")
        return super().embed(model, texts)


def run(
    provider: FakeProvider,
    *,
    settings: LlmSettings | None = None,
    semantic: SemanticCheck | None = None,
    user_notes: str = NONE,
    names: Mapping[str, str] | None = None,
    stages: list[str] | None = None,
) -> tuple[NoteResult, Extraction]:
    context = build_context(meeting=MEETING, utterances=LINES)
    grounder = Grounder(
        aliases=context.aliases, utterance_text=context.utterance_text, semantic=semantic
    )
    seen: list[str] = [] if stages is None else stages
    return write_long_note(
        provider,
        model="fake:1b",
        meeting=MEETING,
        utterances=LINES,
        template=TEMPLATE,
        settings=settings or LlmSettings(),
        grounder=grounder,
        user_notes=user_notes,
        on_stage=seen.append,
        names=names,
    )


def digests_in(call: list[ChatMessage]) -> list[dict[str, Any]]:
    user = call[1].content
    body = user.split("<digests>\n", 1)[1].split("\n</digests>", 1)[0]
    parsed: list[dict[str, Any]] = json.loads(body)
    return parsed


def shown(extraction: Extraction) -> list[tuple[str, str, str | None]]:
    return [(i.kind, i.text, i.owner) for i in extraction.items]


def test_long_note_parts_then_combine() -> None:
    provider = Scripted([PART1, PART2, combined()])
    stages: list[str] = []
    result, extraction = run(provider, stages=stages)
    assert stages == ["part:1:2", "part:2:2", "combining"]
    assert len(provider.calls) == 3
    first, second, combine = (call[0].content for call in provider.calls)
    assert (
        f"This is part 1 of 2 of the meeting (00:00{EN_DASH}10:00); {ELLIPSIS} marks lines"
        " left out." in first
    )
    assert "[u:60] [09:50]" in first and "[u:61]" not in first
    assert f"This is part 2 of 2 of the meeting (09:00{EN_DASH}15:00)" in second
    assert "[u:54]" not in second and "[u:55] [09:00]" in second and "[u:90]" in second
    for call, index in zip(provider.calls[:2], (1, 2), strict=True):
        task = call[1].content
        assert task.startswith("Summarise this part of the meeting for a later step")
        assert f"with window_index {index}." in task
    lines = combine.split("<transcript>\n", 1)[1].split("\n</transcript>", 1)[0]
    assert lines == COMBINE_NOTE + ELLIPSIS  # no line of the call itself
    task = provider.calls[2][1].content
    assert task.startswith(
        "Write the note for the meeting above from the summaries of its parts in <digests>."
    )
    parts = digests_in(provider.calls[2])
    assert [p["window_index"] for p in parts] == [1, 2]  # the code numbers the parts (RB33)
    numbered = [q for p in parts for q in p["points"]]
    assert [q["id"] for q in numbered] == [f"p{n}" for n in range(1, 14)]
    assert numbered[2] == {
        "id": "p3",
        "kind": "commitment",
        "text": "Write the postmortem",
        "owner": "You",
        "due": "by Friday",
        "citations": ["u:20", "u:21"],
    }
    assert [b.text for b in result.note.summary] == ["The Atlas beta moves to March 3."]
    assert result.note.kept == 2 and not result.items_only
    assert result.prompt_version == "a0-v1+a2-v1+a3-v2"
    assert generation_version(result, extraction) == "a0-v1+a2-v1+a3-v2"
    # every call is counted once, on the note (RB29)
    assert (result.tokens_in, result.tokens_out, result.seconds) == (300, 150, 1.5)
    assert (extraction.tokens_in, extraction.tokens_out, extraction.prompt_versions) == (0, 0, ())


def test_digest_items_merge_across_windows() -> None:
    """Points become records, checked like A4-A6's; an overlap repeat is kept once, its lines
    joined to the earliest; two tasks said in one overlap line stay two (RB24)."""
    _, extraction = run(Scripted([PART1, PART2, combined()]), names={"Them": "Priya"})
    assert shown(extraction) == [
        ("action_item", "Write the postmortem", "You"),
        ("action_item", "Update the deck", "You"),
        ("action_item", "Send the deck to Priya", "You"),
        ("action_item", "Write the postmortem for the outage", "You"),
        ("decision", "The Atlas beta moves to March 3", None),
        ("decision", "Keep the legacy API until June", None),
        ("open_question", "Do we sunset the legacy API?", "Them"),
    ]
    by_text = {i.text: i for i in extraction.items}
    assert by_text["Update the deck"].citations == ("k56", "k55")  # p4's line, then p8's
    assert by_text["Write the postmortem"].due == "by Friday"
    assert by_text["Write the postmortem"].confidence is None  # digests carry none
    assert extraction.dropped == 4
    assert dict(extraction.drop_reasons) == {"unsupported": 1, "duplicate": 3}
    assert (extraction.repeats_removed, extraction.answered_removed) == (0, 0)


def test_a3_prunes_answered_questions_and_repeats() -> None:
    """RB27: A3 only removes. A question it calls answered goes (with its overlap copy); a
    repeat goes when both are kept, of one kind and the other is earlier, its lines joining
    the earlier; anything else it lists is ignored."""
    reply = combined(
        repeats=[
            {"id": "p12", "of": "p3"},  # the recap of the postmortem: applied
            {"id": "p3", "of": "p12"},  # "of" is not earlier
            {"id": "p99", "of": "p3"},  # unknown
            {"id": "p6", "of": "p1"},  # a question and a topic
            {"id": "p7", "of": "p3"},  # p7 was dropped by the check
            {"id": "p11", "of": "p4"},  # a decision and a task
        ],
        answered=["p10", "p1", "p404"],  # a question, a topic, nothing
    )
    with structlog.testing.capture_logs() as logs:
        _, extraction = run(Scripted([PART1, PART2, reply]))
    assert shown(extraction) == [
        ("action_item", "Write the postmortem", "You"),
        ("action_item", "Update the deck", "You"),
        ("action_item", "Send the deck to Priya", "You"),
        ("decision", "The Atlas beta moves to March 3", None),
        ("decision", "Keep the legacy API until June", None),
    ]
    postmortem = extraction.items[0]
    assert postmortem.citations == ("k19", "k20", "k84")
    assert (extraction.repeats_removed, extraction.answered_removed) == (1, 2)
    assert extraction.dropped == 3  # p7 unsupported, p8 and p9 overlap repeats: no prunes
    logged = next(e for e in logs if e["event"] == "items_extracted")
    assert (logged["repeats"], logged["answered"]) == (1, 2)


def test_lists_only_fallback_prunes_nothing() -> None:
    """A3's JSON fails even after its repair: the note is the parts' items alone, and A3's
    lists, never used, remove nothing (RB27, RB28)."""
    provider = Scripted([PART1, PART2, "{", "{"])
    result, extraction = run(provider)
    assert result.items_only and result.note.kept == 0
    assert len(extraction.items) == 7
    assert result.prompt_version == "a0-v1"  # no A3 part: its reply was not used
    assert generation_version(result, extraction) == "a0-v1+a2-v1"
    assert (extraction.tokens_in, extraction.tokens_out) == (200, 100)  # the two parts
    nothing = digest(1, point("topic", "Small talk", ["u:2"]))
    with pytest.raises(NoteInvalid):  # and nothing listed either: the note fails
        run(Scripted([nothing, nothing, "{", "{"]))


def test_a_failed_part_is_left_out() -> None:
    provider = Scripted(["nope", "still nope", PART2, combined()])
    with structlog.testing.capture_logs() as logs:
        result, extraction = run(provider)
    failed = [e for e in logs if e["event"] == "note_part_failed"]
    assert failed == [
        {"event": "note_part_failed", "index": 1, "reason": "invalid", "log_level": "info"}
    ]
    parts = digests_in(provider.calls[-1])
    assert [p["window_index"] for p in parts] == [2]
    assert [q["id"] for q in parts[0]["points"]] == [f"p{n}" for n in range(1, 7)]
    assert {i.text for i in extraction.items} == {
        "Update the deck",
        "Send the deck to Priya",
        "Do we sunset the legacy API?",
        "Keep the legacy API until June",
        "Write the postmortem for the outage",
    }
    assert result.prompt_version == "a0-v1+a2-v1+a3-v2"
    cut = Scripted([PART1, CUT, combined()])
    with structlog.testing.capture_logs() as logs:
        run(cut)
    assert [(e["index"], e["reason"]) for e in logs if e["event"] == "note_part_failed"] == [
        (2, "cut_off")
    ]


def test_every_part_failing_raises_the_first_error() -> None:
    provider = Scripted(["nope", "still nope", CUT])
    with pytest.raises(NoteInvalid):
        run(provider)
    assert len(provider.calls) == 3  # no combining call


def test_a3_cut_off_or_too_long_raises() -> None:
    provider = Scripted([PART1, PART2, CUT], tokens_in=100)
    with pytest.raises(NoteCutOff):
        run(provider, semantic=SemanticCheck(Embedder(provider, "embed")))
    assert "embed" not in provider.order  # it stopped before any check
    many = [point("point", f"{n} " + "detail " * 30, ["u:2"]) for n in range(40)]
    wordy = digest(1, *many)
    too_long = Scripted([wordy, wordy])
    with pytest.raises(NoteTooLong):  # the parts fit; their digests together do not
        run(too_long, settings=LlmSettings(context_budget=6_000))
    assert len(too_long.calls) == 2


def test_a3_alone_gets_twice_the_reply_room() -> None:
    """RB45: the combining call may write twice the usual reply (its repair too), and its
    prompt must leave that room in the context, which stays the same size."""
    provider = Scripted([PART1, PART2, "nope", combined()])
    run(provider)
    assert provider.reply_room == [None, None, 8_192, 8_192]  # the parts keep the usual room
    many = [point("point", f"{n} " + "detail " * 30, ["u:2"]) for n in range(40)]
    wordy = digest(1, *many)
    small = LlmSettings(num_ctx=16_384)  # a part may use 12,288 tokens; A3 only 8,192
    with pytest.raises(NoteTooLong) as caught:
        run(Scripted([wordy, wordy]), settings=small)
    assert caught.value.limit == 8_192
    run(Scripted([wordy, wordy, combined()]))  # the same digests fit the usual context


def test_versions_mark_repairs() -> None:
    """RB29: "+a9-v1" follows a2-v1 when any part was repaired, a3's when A3 was."""
    result, extraction = run(Scripted(["nope", PART1, PART2, combined()]))
    assert generation_version(result, extraction) == "a0-v1+a2-v1+a9-v1+a3-v2"
    assert result.repaired
    result, extraction = run(Scripted([PART1, PART2, "nope", combined()]))
    assert generation_version(result, extraction) == "a0-v1+a2-v1+a3-v2+a9-v1"
    result, extraction = run(Scripted([PART1, "nope", PART2, "{", "{"]))
    assert generation_version(result, extraction) == "a0-v1+a2-v1+a9-v1"


def test_every_chat_comes_before_any_embedding() -> None:
    """RB30: every A2, then A3, then the items' check and the note's, each one batch."""
    provider = Scripted([PART1, PART2, combined()])
    run(provider, semantic=SemanticCheck(Embedder(provider, "embed")))
    assert provider.order[:3] == ["chat"] * 3
    assert provider.order[3:] and set(provider.order[3:]) == {"embed"}


def test_parts_carry_the_users_notes() -> None:
    """RB32: every part, and the combining call, sees all of the user's notes."""
    provider = Scripted([PART1, PART2, combined()])
    notes = "[n:1] (01:00) Atlas beta date"
    run(provider, user_notes=notes)
    assert all(f"<user_notes>\n{notes}\n</user_notes>" in c[0].content for c in provider.calls)


def test_nothing_is_logged_with_content() -> None:
    with structlog.testing.capture_logs() as logs:
        run(Scripted(["nope", "still nope", PART2, combined(answered=["p3"])]))
    text = json.dumps(logs, default=str)
    for said in ("postmortem", "deck", "legacy", "Atlas", "small talk"):
        assert said.lower() not in text.lower()
