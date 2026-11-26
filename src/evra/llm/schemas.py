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


class MeetingTitle(BaseModel):
    """A8. `evra.notes.title` tidies the title and checks its length."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(max_length=120)


class MeetingAnswer(BaseModel):
    """A12. Every point is checked against the transcript by `evra.notes.ask`."""

    model_config = ConfigDict(extra="ignore")

    found: bool
    points: list[NoteBullet] = Field(default_factory=list, max_length=4)


class ActionItem(BaseModel):
    """A4. `evra.notes.extract` checks each item against the transcript."""

    model_config = ConfigDict(extra="ignore")

    text: str = Field(max_length=200)
    owner: str | None
    due: str | None
    confidence: float = Field(ge=0, le=1)
    citations: list[str] = Field(min_length=1)


class ActionItems(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[ActionItem]


class Decision(BaseModel):
    model_config = ConfigDict(extra="ignore")

    statement: str = Field(max_length=250)
    made_by: str | None
    citations: list[str] = Field(min_length=1)


class Decisions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[Decision]


class OpenQuestion(BaseModel):
    model_config = ConfigDict(extra="ignore")

    question: str = Field(max_length=250)
    raised_by: str | None
    citations: list[str] = Field(min_length=1)


class OpenQuestions(BaseModel):
    model_config = ConfigDict(extra="ignore")

    items: list[OpenQuestion]
