import pytest
import yaml

from evra.notes.templates import load_template, template_ids


def test_both_phase_one_templates_ship() -> None:
    assert {"one_on_one", "general"} <= set(template_ids())


def test_one_on_one_sections_in_order() -> None:
    template = load_template("one_on_one")
    assert template.name == "1:1"
    assert [s.id for s in template.sections] == [
        "discussion",
        "decisions",
        "action_items",
        "open_questions",
        "next_time",
    ]
    assert template.sections[0].required


def test_sections_yaml_round_trips() -> None:
    template = load_template("general")
    data = yaml.safe_load(template.sections_yaml())
    assert [d["id"] for d in data] == [s.id for s in template.sections]


@pytest.mark.parametrize("bad", ["nope", "../one_on_one", "One_On_One", ""])
def test_unknown_or_unsafe_ids_are_key_errors(bad: str) -> None:
    with pytest.raises(KeyError):
        load_template(bad)
