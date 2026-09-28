from evra.llm.schemas import NoteBullet, NoteDraft, NoteSection
from evra.notes.templates import load_template
from evra.notes.validate import CheckedBullet, CheckedNote, check_note

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
