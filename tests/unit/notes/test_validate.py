from collections.abc import Sequence
from typing import Any

import pytest
import structlog

from evra.llm.provider import LlmModelMissing
from evra.llm.schemas import NoteBullet, NoteDraft, NoteSection
from evra.notes.semantic import Embedder, SemanticCheck
from evra.notes.templates import load_template
from evra.notes.validate import CheckedBullet, CheckedNote, Grounder, check_note
from tests.unit.notes.fakes import FakeProvider

UTTERANCES = {
    "id-1": "I finished the search migration on Tuesday.",
    "id-2": "We have twelve thousand dollars left for contractors this quarter.",
    "id-3": "I'll ask Priya directly tomorrow.",
}
ALIASES = {"u:1": "id-1", "u:2": "id-2", "u:3": "id-3"}
TEMPLATE = load_template("one_on_one")


def b(text: str, *citations: str) -> NoteBullet:
    return NoteBullet(text=text, citations=list(citations) or ["u:1"])


def check(*bullets: NoteBullet, summary: tuple[NoteBullet, ...] = ()) -> CheckedNote:
    draft = NoteDraft(
        summary=list(summary),
        sections=[NoteSection(section_id="discussion", title="Given", bullets=list(bullets))],
    )
    return check_note(draft, aliases=ALIASES, utterance_text=UTTERANCES, template=TEMPLATE)


def only_bullets(note: CheckedNote) -> list[CheckedBullet]:
    return [x for s in note.sections for x in s.bullets]


def test_a_supported_bullet_is_kept_with_real_ids() -> None:
    note = check(b("You finished the search migration on Tuesday.", "u:1"))
    assert [(x.text, x.citations) for x in only_bullets(note)] == [
        ("You finished the search migration on Tuesday.", ("id-1",))
    ]
    assert (note.kept, note.dropped) == (1, 0)


def test_unknown_or_malformed_citations_drop_the_bullet() -> None:
    note = check(b("You finished the migration.", "u:99", "u 1", "[u:77]"))
    assert only_bullets(note) == []
    assert note.drop_reasons == {"no_valid_citation": 1}


def test_inline_citations_are_moved_out_of_the_text() -> None:
    note = check(NoteBullet(text="You finished the search migration [u:1].", citations=["u:9"]))
    assert [(x.text, x.citations) for x in only_bullets(note)] == [
        ("You finished the search migration.", ("id-1",))
    ]


def test_bracketed_and_repeated_citations_are_normalised() -> None:
    note = check(b("You finished the search migration.", "[u:1]", " u:1 "))
    assert only_bullets(note)[0].citations == ("id-1",)


def test_an_unsupported_claim_is_dropped() -> None:
    note = check(b("The team celebrated the product launch with cake.", "u:1"))
    assert only_bullets(note) == []
    assert note.drop_reasons == {"unsupported": 1}


def test_numbers_must_come_from_the_cited_utterances() -> None:
    kept = check(b("There is 12,000 dollars left for contractors.", "u:2"))
    assert len(only_bullets(kept)) == 1  # "twelve thousand" supports 12,000
    dropped = check(b("There is 15,000 dollars left for contractors.", "u:2"))
    assert dropped.drop_reasons == {"number_not_cited": 1}


def test_names_must_come_from_the_cited_utterances() -> None:
    kept = check(b("Them will ask Priya directly.", "u:3"))
    assert len(only_bullets(kept)) == 1
    dropped = check(b("Them will ask Priya and Omar directly.", "u:3"))
    assert dropped.drop_reasons == {"name_not_cited": 1}


def test_user_citations_need_user_notes() -> None:
    note = check(b("You finished the search migration.", "user"))
    assert note.drop_reasons == {"no_valid_citation": 1}


def test_a_note_cited_by_its_label_is_a_user_citation() -> None:
    """A0 labels each typed note [n:k]: gemma4 cites one as n:3, or inline as user.3, both meaning
    the user's notes. In the 60-minute bake-off every point A3 wrote from a note read "... March 3
    [u:140, u:141, user.2]." and was dropped for the bracket's numbers."""
    notes = "Atlas beta moved to March 3"
    grounder = Grounder(aliases=ALIASES, utterance_text=UTTERANCES, user_notes=notes)
    for bullet in [
        NoteBullet(text="The Atlas beta moved to March 3 [u:1, user.2].", citations=["u:1"]),
        NoteBullet(text="The Atlas beta moved to March 3.", citations=["n:2"]),
        NoteBullet(text="The Atlas beta moved to March 3 [n:2].", citations=["user:2"]),
    ]:
        checked, reason = grounder.check(bullet)
        assert reason == "" and checked is not None, bullet
        assert checked.text == "The Atlas beta moved to March 3."
        assert "user" in checked.citations
    no_notes = Grounder(aliases=ALIASES, utterance_text=UTTERANCES)
    assert no_notes.check(b("The Atlas beta moved to March 3.", "n:2")) == (
        None,
        "no_valid_citation",
    )


def test_summary_bullets_are_checked_too() -> None:
    note = check(
        b("You finished the search migration.", "u:1"),
        summary=(b("Budget doubled to 50,000.", "u:2"), b("You finished the migration.", "u:1")),
    )
    assert [x.text for x in note.summary] == ["You finished the migration."]
    assert (note.kept, note.dropped) == (2, 1)


def test_sections_follow_the_template_and_empty_ones_disappear() -> None:
    draft = NoteDraft(
        summary=[],
        sections=[
            NoteSection(
                section_id="action_items",
                title="Todo",
                bullets=[b("Them will ask Priya directly.", "u:3")],
            ),
            NoteSection(
                section_id="decisions",
                title="Decisions",
                bullets=[b("Everyone loved the cake.", "u:1")],
            ),
            NoteSection(
                section_id="extra",
                title="Extra",
                bullets=[b("Twelve thousand dollars are left for contractors.", "u:2")],
            ),
            NoteSection(
                section_id="discussion",
                title="Talk",
                bullets=[b("You finished the search migration.", "u:1")],
            ),
            NoteSection(
                section_id="discussion",
                title="Talk again",
                bullets=[b("The migration finished on Tuesday.", "u:1")],
            ),
        ],
    )
    note = check_note(draft, aliases=ALIASES, utterance_text=UTTERANCES, template=TEMPLATE)
    assert [(s.section_id, s.title, len(s.bullets)) for s in note.sections] == [
        ("discussion", "Discussion", 2),
        ("action_items", "Action items", 1),
        ("extra", "Extra", 1),
    ]
    assert (note.kept, note.dropped) == (4, 1)


CONVERSATION = {
    "c-1": "How are things with Priya's team? You were waiting on their API limits.",
    "c-2": "Still waiting on them.",
    "c-3": "I'll ask Priya directly tomorrow.",
    "c-4": "Unrelated chat about lunch.",
    "c-5": "More chat.",
    "c-6": "Even more chat.",
    "c-7": "We have 12,000 dollars left, and the Berlin office is closed.",
}
CONVERSATION_ALIASES = {f"u:{i}": f"c-{i}" for i in range(1, 8)}


def check_conversation(bullet: NoteBullet) -> CheckedNote:
    draft = NoteDraft(
        summary=[bullet],
        sections=[],
    )
    return check_note(
        draft, aliases=CONVERSATION_ALIASES, utterance_text=CONVERSATION, template=TEMPLATE
    )


def test_a_name_from_a_nearby_line_adds_that_line_as_a_citation() -> None:
    note = check_conversation(b("Them will ask Priya directly about the API limits.", "u:3"))
    assert [(x.text, x.citations) for x in note.summary] == [
        ("Them will ask Priya directly about the API limits.", ("c-3", "c-1"))
    ]


def test_names_further_away_still_drop_the_bullet() -> None:
    note = check_conversation(b("Them will ask Priya directly about the Berlin office.", "u:3"))
    assert note.drop_reasons == {"name_not_cited": 1}


def test_thousands_shorthand_counts_as_the_number() -> None:
    note = check_conversation(b("There is $12k left.", "u:7"))
    assert [x.text for x in note.summary] == ["There is $12k left."]


def check_lines(lines: list[str], bullet: NoteBullet) -> CheckedNote:
    texts = {f"t-{i}": text for i, text in enumerate(lines, start=1)}
    aliases = {f"u:{i}": f"t-{i}" for i in range(1, len(lines) + 1)}
    draft = NoteDraft(summary=[bullet], sections=[])
    return check_note(draft, aliases=aliases, utterance_text=texts, template=TEMPLATE)


DECK = [
    "I'll send the budget deck to finance by Friday.",
    "Filler one about lunch.",
    "Filler two about lunch.",
    "Filler three about lunch.",
    "Filler four about lunch.",
    "Priya from legal still needs to sign off.",
]


@pytest.mark.parametrize(
    "claim",
    [
        "Priya will send the budget deck to finance by Friday.",
        "Marcus will send the budget deck to finance by Friday.",
        "Owner: Marcus. Send the budget deck to finance by Friday.",
        "Send the budget deck to finance by Friday; Marcus approved.",
        "Legal (Marcus) approved the budget deck for finance by Friday.",
    ],
)
def test_names_the_cited_line_never_said_are_dropped(claim: str) -> None:
    assert check_lines(DECK, b(claim, "u:1")).drop_reasons == {"name_not_cited": 1}


@pytest.mark.parametrize(
    "claim",
    [
        "Budget deck goes to finance by Friday.",
        "Deck: Send it to finance by Friday.",
        "Them: Inform finance about the budget deck by Friday.",
    ],
)
def test_ordinary_words_starting_a_point_are_not_names(claim: str) -> None:
    assert check_lines(DECK, b(claim, "u:1")).kept == 1


TICKETS = ["Support got two tickets and I answered them."]


@pytest.mark.parametrize(
    "claim", ["Support got three hundred tickets.", "Support got twelve tickets."]
)
def test_spelled_out_numbers_are_checked(claim: str) -> None:
    assert check_lines(TICKETS, b(claim, "u:1")).drop_reasons == {"number_not_cited": 1}


def test_spelled_out_numbers_that_match_are_kept() -> None:
    assert check_lines(TICKETS, b("Support got two tickets.", "u:1")).kept == 1
    assert check_lines(TICKETS, b("One of the tickets was answered.", "u:1")).kept == 1


@pytest.mark.parametrize(
    ("nearby", "claim"),
    [
        ("Query latency went up to about 180 milliseconds.", "Support got 180 tickets."),
        ("The one ticket that matters is slow.", "Support got 1 ticket."),
        ("Second, the tickets were slow.", "Support answered 2 tickets."),
    ],
)
def test_a_number_is_only_borrowed_from_a_nearby_line_about_the_same_thing(
    nearby: str, claim: str
) -> None:
    lines = [nearby, "Support answered the tickets."]
    assert check_lines(lines, b(claim, "u:2")).drop_reasons == {"number_not_cited": 1}


def test_a_date_is_borrowed_from_the_line_that_said_it() -> None:
    lines = [
        "Marketing wants to move the date to October 14.",
        "The export feature still needs another week of testing.",
    ]
    note = check_lines(
        lines, b("The launch moves to October 14 because testing needs a week.", "u:2")
    )
    assert note.summary[0].citations == ("t-2", "t-1")


def test_grounder_matches_check_note() -> None:
    bullets = [
        b("I finished the search migration on Tuesday.", "u:1"),
        b("I finished the search migration.", "u:9"),
        b("", "u:1"),
        b("Budget talk about weather.", "u:1"),
        b("We have thirty thousand dollars left for contractors.", "u:2"),
        b("I will ask Dmitri tomorrow.", "u:3"),
        b("We have twelve thousand dollars left for contractors this quarter.", "u:2"),
    ]
    grounder = Grounder(aliases=ALIASES, utterance_text=UTTERANCES)
    verdicts = [grounder.check(x) for x in bullets]
    note = check(*bullets)
    kept = [c for c, _ in verdicts if c is not None]
    assert kept == only_bullets(note)
    reasons: dict[str, int] = {}
    for c, reason in verdicts:
        if c is None:
            reasons[reason] = reasons.get(reason, 0) + 1
    assert reasons == dict(note.drop_reasons)


# The meaning check. FakeProvider embeds a bag of words, so in these tests a "paraphrase"
# shares only small words with the line it cites (none of its content words); the real
# model's threshold comes from tools/calibrate_semantic.py (DECISIONS.md).
PROMISE = "Yes, I will have it all done for you by then, as I said I would."
PARAPHRASE = "They will have the report done for you by then, as they said they would."
WITH_A_NUMBER = "They will have the 5 reports done for you by then, as they said they would."
UNRELATED = "The team celebrated the product launch with cake."
PROMISE_LINES = {"p-1": PROMISE, "p-2": "I finished the search migration on Tuesday."}
PROMISE_ALIASES = {"u:1": "p-1", "u:2": "p-2"}
LOOSE = 0.45  # what the fake's cosines allow; see SemanticCheck's default for the real one


def meaning(provider: FakeProvider | None = None) -> SemanticCheck:
    return SemanticCheck(Embedder(provider or FakeProvider([]), "embed"), threshold=LOOSE)


def check_promises(
    summary: Sequence[NoteBullet],
    *sections: tuple[str, Sequence[NoteBullet]],
    semantic: SemanticCheck | None = None,
) -> CheckedNote:
    draft = NoteDraft(
        summary=list(summary),
        sections=[NoteSection(section_id=s, title=s, bullets=list(b)) for s, b in sections],
    )
    return check_note(
        draft,
        aliases=PROMISE_ALIASES,
        utterance_text=PROMISE_LINES,
        template=TEMPLATE,
        semantic=semantic,
    )


def test_meaning_check_rescues_a_paraphrase() -> None:
    semantic = meaning()
    assert semantic.similarities([(PARAPHRASE, PROMISE)])[0] >= semantic.threshold
    # none of its content words is in the line it cites, so the words alone drop it
    assert check_promises([b(PARAPHRASE)]).drop_reasons == {"unsupported": 1}
    note = check_promises([b(PARAPHRASE)], semantic=semantic)
    assert [(x.text, x.citations) for x in note.summary] == [(PARAPHRASE, ("p-1",))]
    assert (note.kept, note.dropped, note.rescued) == (1, 0, 1)


def test_a_point_far_in_meaning_stays_unsupported() -> None:
    semantic = meaning()
    assert semantic.similarities([(UNRELATED, PROMISE)])[0] < semantic.threshold
    note = check_promises([b(UNRELATED)], semantic=semantic)
    assert (note.kept, note.drop_reasons, note.rescued) == (0, {"unsupported": 1}, 0)


def test_rescued_bullet_still_needs_its_numbers() -> None:
    semantic = meaning()
    assert semantic.similarities([(WITH_A_NUMBER, PROMISE)])[0] >= semantic.threshold
    note = check_promises([b(WITH_A_NUMBER)], semantic=semantic)
    assert (note.kept, note.drop_reasons, note.rescued) == (0, {"number_not_cited": 1}, 0)


def test_meaning_check_is_one_batch() -> None:
    provider = FakeProvider([])
    batches: list[int] = []

    class Counting(SemanticCheck):
        def similarities(self, pairs: Sequence[tuple[str, str]]) -> list[float]:
            batches.append(len(pairs))
            return super().similarities(pairs)

    note = check_promises(
        [b(PARAPHRASE)],
        ("discussion", [b(UNRELATED), b("You finished the search migration.", "u:2")]),
        ("action_items", [b(WITH_A_NUMBER)]),
        semantic=Counting(Embedder(provider, "embed"), threshold=LOOSE),
    )
    assert batches == [3]  # every candidate of the whole note in one call
    assert len(provider.embed_calls) == 1  # three claims and their one cited line
    assert (note.kept, note.dropped, note.rescued) == (2, 2, 1)


def test_semantic_failure_keeps_lexical_verdicts() -> None:
    class NoEmbeddingModel(FakeProvider):
        def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
            raise LlmModelMissing(model)

    bullets = [b(PARAPHRASE), b("You finished the search migration.", "u:2")]
    with structlog.testing.capture_logs() as logs:
        note = check_promises(bullets, semantic=meaning(NoEmbeddingModel([])))
    assert note == check_promises(bullets)
    assert (note.kept, note.drop_reasons, note.rescued) == (1, {"unsupported": 1}, 0)
    skipped = [e for e in logs if e["event"] == "semantic_check_skipped"]
    assert skipped == [
        {"event": "semantic_check_skipped", "error": "LlmModelMissing", "log_level": "info"}
    ]


def test_check_note_without_semantic_is_unchanged() -> None:
    """One pass over the whole note gives each bullet the verdict `check` gives it alone, and
    puts the kept ones back in their sections."""
    summary = [b(PARAPHRASE), b("You finished the search migration.", "u:2")]
    discussion = [b(WITH_A_NUMBER), b("", "u:1"), b("You finished it.", "u:9")]
    actions = [
        b("Priya will finish the search migration.", "u:2"),
        b("The migration finished on Tuesday.", "u:2"),
    ]
    note = check_promises(summary, ("discussion", discussion), ("action_items", actions))
    grounder = Grounder(aliases=PROMISE_ALIASES, utterance_text=PROMISE_LINES)
    assert [grounder.check(x) for x in summary] == [
        (None, "unsupported"),
        (note.summary[0], ""),
    ]
    assert [(s.section_id, s.bullets) for s in note.sections] == [
        ("action_items", (grounder.check(actions[1])[0],))
    ]
    assert note.drop_reasons == {
        "unsupported": 2,
        "empty": 1,
        "no_valid_citation": 1,
        "name_not_cited": 1,
    }
    assert (note.kept, note.dropped, note.rescued) == (2, 5, 0)


def test_single_check_has_no_meaning_step() -> None:
    provider = FakeProvider([])
    grounder = Grounder(
        aliases=PROMISE_ALIASES, utterance_text=PROMISE_LINES, semantic=meaning(provider)
    )
    assert grounder.check(b(PARAPHRASE)) == (None, "unsupported")
    assert provider.embed_calls == []
    assert grounder.check_all([b(PARAPHRASE)]) == [(CheckedBullet(PARAPHRASE, ("p-1",)), "meaning")]


def test_the_person_on_the_call_is_a_known_name() -> None:
    """C6: once the owner says who the 1:1 was with, every prompt names them, so a point may
    too: their name needs no line that says it; any other name still does."""
    common: dict[str, Any] = {
        "aliases": {"u:1": "t-1"},
        "utterance_text": {"t-1": DECK[0]},
        "template": TEMPLATE,
    }
    named = NoteDraft(summary=[b("Dana Lee will send the budget deck by Friday.")], sections=[])
    assert check_note(named, **common).drop_reasons == {"name_not_cited": 1}
    assert check_note(named, **common, people=["Dana Lee"]).kept == 1
    other = NoteDraft(summary=[b("Dana will ask Marcus for the deck by Friday.")], sections=[])
    assert check_note(other, **common, people=["Dana Lee"]).drop_reasons == {"name_not_cited": 1}
    grounder = Grounder(aliases={"u:1": "t-1"}, utterance_text=common["utterance_text"])
    assert grounder.check(b("Dana will send the budget deck by Friday."))[1] == "name_not_cited"
    known = Grounder(
        aliases={"u:1": "t-1"}, utterance_text=common["utterance_text"], people=["Dana"]
    )
    assert known.check(b("Dana will send the budget deck by Friday."))[1] == ""
    # a name with an apostrophe is read in pieces ("D'Souza" as "Souza"), and known all the same
    full = NoteDraft(summary=[b("Anita D'Souza will send the budget deck by Friday.")], sections=[])
    assert check_note(full, **common, people=["Anita D'Souza"]).kept == 1
    curly = f"O{chr(0x2019)}Brien will send the budget deck by Friday."  # a typographic one
    surname = NoteDraft(summary=[b(curly)], sections=[])
    assert check_note(surname, **common, people=["Sinead O'Brien"]).kept == 1
