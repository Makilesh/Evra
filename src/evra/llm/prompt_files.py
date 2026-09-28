"""Prompt files (BUILD.md Appendix A): `llm/prompts/<id>.md` = a version line, `## System`,
`## User`. Placeholders are `{lower_snake}`, filled in one pass (data is never re-scanned)."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from importlib import resources

_VERSION = re.compile(r"^<!--\s*version:\s*(\S+)\s*-->\s*$", re.MULTILINE)
_SECTION = re.compile(r"^## (System|User)\s*$", re.MULTILINE)
_PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


@dataclass(frozen=True)
class Prompt:
    id: str
    version: str
    system: str
    user: str

    def render(self, **values: str) -> tuple[str, str]:
        return _fill(self.system, values), _fill(self.user, values)


def _fill(text: str, values: Mapping[str, str]) -> str:
    def value(match: re.Match[str]) -> str:
        key = match.group(1)
        if key not in values:
            raise KeyError(f"prompt placeholder {{{key}}} has no value")
        return values[key]

    return _PLACEHOLDER.sub(value, text)


def load_prompt(prompt_id: str) -> Prompt:
    text = resources.files("evra.llm.prompts").joinpath(f"{prompt_id}.md").read_text("utf-8")
    version = _VERSION.search(text)
    parts = _SECTION.split(text)  # [preamble, "System", body, "User", body]
    if version is None or len(parts) != 5 or parts[1] != "System" or parts[3] != "User":
        raise ValueError(f"prompt {prompt_id} needs a version line, then ## System and ## User")
    return Prompt(prompt_id, version.group(1), parts[2].strip(), parts[4].strip())
