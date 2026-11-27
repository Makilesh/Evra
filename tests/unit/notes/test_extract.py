import json
from typing import Any

import structlog

from evra.config import LlmSettings
from evra.notes.context import MeetingContext, build_context
from evra.notes.extract import (
    Extraction,
    ItemKind,
    extract_items,
    is_repeat,
    normalise_owner,
)
from evra.notes.semantic import Embedder, SemanticCheck
from evra.notes.validate import Grounder
from tests.unit.notes.fakes import FakeProvider, utt

MEETING = {
    "id": "m",
    "title": "Weekly 1:1",
    "started_at": 1_790_000_000_000,
    "situation": "call_headphones",
    "template": "one_on_one",
}
LINES = [
    utt("a", 1, 0, 3_000, "Can you send the vendor quote to Priya by Friday?", seq=0),
    utt("b", 0, 3_100, 4_000, "Sure, I'll send the vendor quote by Friday.", seq=1),
    utt("c", 1, 4_100, 6_000, "So we go with the annual plan, agreed.", seq=2),
    utt("d", 0, 6_100, 8_000, "Who owns the security review next quarter?", seq=3),
    utt("e", 0, 8_100, 10_000, "Sure, I'll update the deck and send it to Priya.", seq=4),
]
CONTEXT = build_context(meeting=MEETING, utterances=LINES)
ALL: tuple[ItemKind, ...] = ("action_item", "decision", "open_question")


def grounder(context: MeetingContext = CONTEXT, semantic: SemanticCheck | None = None) -> Grounder:
    return Grounder(
        aliases=context.aliases, utterance_text=context.utterance_text, semantic=semantic
    )


def action(text: str, cites: list[str], **kw: Any) -> dict[str, Any]:
    item = {"text": text, "owner": "me", "due": None, "confidence": 0.9, "citations": cites}
    return item | kw


def items_reply(*items: dict[str, Any]) -> str:
    return json.dumps({"items": list(items)})


QUOTE = action("Send the vendor quote", ["u:1", "u:2"], due="by Friday")
DECISION = json.dumps(
    {"items": [{"statement": "Go with the annual plan.", "made_by": None, "citations": ["u:3"]}]}
)
QUESTION = json.dumps(
    {
        "items": [
            {
                "question": "Who owns the security review next quarter?",
                "raised_by": "me",
                "citations": ["u:4"],
            }
        ]
    }
)


def run(
    provider: FakeProvider,
    *,
    grounder_: Grounder | None = None,
    kinds: tuple[ItemKind, ...] = ALL,
    names: dict[str, str] | None = None,
) -> Extraction:
    return extract_items(
        provider,
        model="fake:1b",
        context=CONTEXT,
        settings=LlmSettings(),
        grounder=grounder_ or grounder(),
        kinds=kinds,
        names=names,
    )


def test_three_calls_share_the_context() -> None:
    provider = FakeProvider([items_reply(QUOTE), DECISION, QUESTION])
    result = run(provider)
    assert len(provider.calls) == 3
    assert all(
        call[0].role == "system" and call[0].content == CONTEXT.system for call in provider.calls
    )
    assert "action items" in provider.calls[0][1].content
    assert "decisions" in provider.calls[1][1].content
    assert "questions" in provider.calls[2][1].content
    assert [i.kind for i in result.items] == ["action_item", "decision", "open_question"]
    assert result.prompt_versions == ("a4-v2", "a5-v2", "a6-v2")
    assert (result.tokens_in, result.tokens_out) == (300, 150)
    assert result.failed_kinds == ()
    first = result.items[0]
    assert (first.owner, first.due, first.confidence) == ("You", "by Friday", 0.9)
    assert first.text == "Send the vendor quote"
    assert first.citations == ("a", "b")
    assert result.items[1].owner is None and result.items[2].owner == "You"


def test_owner_is_normalised() -> None:
    assert normalise_owner("me") == "You"
    assert normalise_owner("OWNER") == "You"
    assert normalise_owner("They") == "Them"
    assert normalise_owner("Priya", names={"Them": "Priya"}) == "Them"
    assert normalise_owner("priya", names={"Them": "Priya"}) == "Them"
    assert normalise_owner("Dana") is None
    assert normalise_owner(None) is None
    assert normalise_owner("  ") is None
    result = run(
        FakeProvider([items_reply(action("Send the vendor quote", ["u:1"], owner="Dana"))]),
        kinds=("action_item",),
    )
    assert result.items[0].owner is None


def test_low_confidence_is_dropped() -> None:
    reply = items_reply(QUOTE, action("Update the deck", ["u:5"], confidence=0.3))
    result = run(FakeProvider([reply]), kinds=("action_item",))
    assert [i.text for i in result.items] == ["Send the vendor quote"]
    assert (result.dropped, dict(result.drop_reasons)) == (1, {"low_confidence": 1})


def test_unsupported_item_is_dropped() -> None:
    reply = items_reply(QUOTE, action("Book the Lisbon offsite venue", ["u:3"]))
    result = run(FakeProvider([reply]), kinds=("action_item",))
    assert len(result.items) == 1
    assert (result.dropped, dict(result.drop_reasons)) == (1, {"unsupported": 1})


def test_failed_kind_keeps_the_others() -> None:
    provider = FakeProvider([items_reply(QUOTE), "nope", "still nope", QUESTION])
    result = run(provider)
    assert result.failed_kinds == ("decision",)
    assert [i.kind for i in result.items] == ["action_item", "open_question"]
    assert result.prompt_versions == ("a4-v2", "a6-v2")


def test_cut_off_kind_is_failed_not_raised() -> None:
    result = run(FakeProvider(["{"], truncated=True), kinds=("decision",))
    assert result.failed_kinds == ("decision",) and result.items == ()


def test_repaired_kind_adds_its_version() -> None:
    provider = FakeProvider(["nope", items_reply(QUOTE), DECISION, QUESTION])
    result = run(provider)
    assert result.prompt_versions == ("a4-v2+a9-v1", "a5-v2", "a6-v2")


def test_repeated_items_kept_once() -> None:
    reply = items_reply(
        QUOTE,
        action("Send the vendor quote", ["u:1"]),
        action("Send Priya the vendor quote", ["u:2"], due="by Friday"),
    )
    result = run(FakeProvider([reply]), kinds=("action_item",))
    assert [i.text for i in result.items] == ["Send the vendor quote"]
    assert dict(result.drop_reasons) == {"duplicate": 2}
    assert is_repeat("Send the vendor quote", ["a"], "send the vendor quote", ["z"])
    assert is_repeat("Send the vendor quote", ["a"], "Send Priya the vendor quote", ["a"])
    assert not is_repeat("Send the vendor quote", ["a"], "Send Priya the vendor quote", ["b"])


def test_a_repeat_adds_its_lines_to_the_item_kept() -> None:
    """RB24/RB25: one merge for a single pass and for a long call's parts: the earliest is
    kept, citing the lines its repeats cite too (in order, once each)."""
    reply = items_reply(
        action("Send the vendor quote", ["u:2"]),
        action("Send the vendor quote", ["u:1", "u:2"]),
    )
    result = run(FakeProvider([reply]), kinds=("action_item",))
    assert [(i.text, i.citations) for i in result.items] == [("Send the vendor quote", ("b", "a"))]
    assert dict(result.drop_reasons) == {"duplicate": 1}


def test_two_tasks_from_one_line_are_both_kept() -> None:
    reply = items_reply(
        action("Update the deck", ["u:5"]), action("Send the deck to Priya", ["u:5"])
    )
    result = run(FakeProvider([reply]), kinds=("action_item",))
    assert [i.text for i in result.items] == ["Update the deck", "Send the deck to Priya"]


def test_a_decision_that_restates_a_task_is_left_to_the_task() -> None:
    """RB20: "You will send the vendor quote by Friday" is the action item already listed, not
    a decision; an unrelated decision stays. The removal is counted, and is not a drop."""
    restated = {
        "statement": "You will send the vendor quote by Friday.",
        "made_by": "me",
        "citations": ["u:2"],
    }
    annual = {"statement": "Go with the annual plan.", "made_by": None, "citations": ["u:3"]}
    decisions = json.dumps({"items": [restated, annual]})
    with structlog.testing.capture_logs() as logs:
        result = run(FakeProvider([items_reply(QUOTE), decisions, json.dumps({"items": []})]))
    assert [(i.kind, i.text) for i in result.items] == [
        ("action_item", "Send the vendor quote"),
        ("decision", "Go with the annual plan."),
    ]
    assert result.tasks_as_decisions == 1
    assert (result.dropped, dict(result.drop_reasons)) == (0, {})
    extracted = next(e for e in logs if e["event"] == "items_extracted")
    assert extracted["tasks_as_decisions"] == 1


def test_due_date_must_be_in_the_cited_lines() -> None:
    reply = items_reply(
        action("Send the vendor quote", ["u:1", "u:2"], due="by Friday"),
        action("Send the quote to Priya", ["u:1", "u:2"], due="by Monday"),
    )
    result = run(FakeProvider([reply]), kinds=("action_item",))
    assert [i.due for i in result.items] == ["by Friday"]
    assert result.dropped == 1


def test_items_are_checked_after_all_three_calls() -> None:
    provider = FakeProvider([])
    order: list[str] = []
    real_chat, real_embed = provider.chat_json, provider.embed

    def chat(*a: Any, **k: Any) -> Any:
        order.append("chat")
        return real_chat(*a, **k)

    def embed(*a: Any, **k: Any) -> Any:
        order.append("embed")
        return real_embed(*a, **k)

    provider.chat_json = chat  # type: ignore[method-assign]
    provider.embed = embed  # type: ignore[method-assign]
    unsupported = action("Book the Lisbon offsite venue", ["u:3"])
    provider.replies = [items_reply(unsupported), DECISION, QUESTION]
    semantic = SemanticCheck(Embedder(provider, "embed"), threshold=0.99)
    run(provider, grounder_=grounder(semantic=semantic))
    assert order == ["chat", "chat", "chat", "embed"]
    assert len(provider.embed_calls) == 1


def test_nothing_is_logged_with_content() -> None:
    with structlog.testing.capture_logs() as logs:
        run(FakeProvider([items_reply(QUOTE), DECISION, "x", "y"]))
    text = json.dumps(logs, default=str)
    assert "vendor quote" not in text and "annual plan" not in text
