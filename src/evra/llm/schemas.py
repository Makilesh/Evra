"""LLM output schemas (BUILD.md Appendix B). Ollama gets `model_json_schema()` as `format`.

Citation strings are checked per bullet by `evra.notes.validate`, so one malformed citation
drops one bullet instead of failing the whole note.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class NoteBullet(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str = Field(max_length=600)
    citations: list[str] = Field(min_length=1)


class NoteSection(BaseModel):
    model_config = ConfigDict(extra="ignore")

    section_id: str
    title: str
    bullets: list[NoteBullet]


class NoteDraft(BaseModel):
    model_config = ConfigDict(extra="ignore")

    summary: list[NoteBullet] = Field(max_length=6)
    sections: list[NoteSection]
    language: str = "en"
