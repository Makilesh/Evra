"""Note templates (BUILD.md §7.6): `notes/templates/<id>.yaml` (next to this file) = a name and
ordered sections. A section is written by the note itself (`synthesis`, A1) or filled from the
records the focused calls list (`extraction`: decisions, action items, open questions, A4-A6)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources
from typing import Literal

import yaml

_ID = re.compile(r"[a-z0-9_]+")
Source = Literal["synthesis", "extraction"]
_SOURCES: dict[str, Source] = {"synthesis": "synthesis", "extraction": "extraction"}


@dataclass(frozen=True)
class TemplateSection:
    id: str
    title: str
    instruction: str
    required: bool
    source: Source = "synthesis"


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    sections: tuple[TemplateSection, ...]

    def synthesis_sections(self) -> tuple[TemplateSection, ...]:
        """The sections the note writes itself (A1); the others come from the records."""
        return tuple(s for s in self.sections if s.source == "synthesis")

    def sections_yaml(self) -> str:
        rows = [
            {"id": s.id, "title": s.title, "instruction": s.instruction, "required": s.required}
            for s in self.sections
        ]
        return yaml.safe_dump(rows, sort_keys=False, allow_unicode=True).strip()


def template_ids() -> list[str]:
    folder = resources.files("evra.notes.templates")
    return sorted(e.name[:-5] for e in folder.iterdir() if e.name.endswith(".yaml"))


def load_template(template_id: str) -> Template:
    if not _ID.fullmatch(template_id) or template_id not in template_ids():
        raise KeyError(template_id)
    folder = resources.files("evra.notes.templates")
    data = yaml.safe_load(folder.joinpath(f"{template_id}.yaml").read_text("utf-8"))
    sections = tuple(
        TemplateSection(
            str(s["id"]),
            str(s["title"]),
            str(s["instruction"]),
            bool(s.get("required", False)),
            _source(s.get("source", "synthesis")),
        )
        for s in data["sections"]
    )
    return Template(template_id, str(data["name"]), sections)


def _source(value: object) -> Source:
    source = _SOURCES.get(str(value))
    if source is None:
        raise ValueError(f"a template section's source is synthesis or extraction, not {value!r}")
    return source
