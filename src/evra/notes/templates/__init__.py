"""Note templates (BUILD.md §7.6): `notes/templates/<id>.yaml` (next to this file) = a name and
ordered sections."""

from __future__ import annotations

import re
from dataclasses import dataclass
from importlib import resources

import yaml

_ID = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class TemplateSection:
    id: str
    title: str
    instruction: str
    required: bool


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    sections: tuple[TemplateSection, ...]

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
            str(s["id"]), str(s["title"]), str(s["instruction"]), bool(s.get("required", False))
        )
        for s in data["sections"]
    )
    return Template(template_id, str(data["name"]), sections)
