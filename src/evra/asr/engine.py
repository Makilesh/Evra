"""Speech-to-text engine interface (BUILD.md §6.1)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Protocol

from evra.audio.frames import Int16Array


@dataclass(frozen=True)
class Word:
    start_ms: int
    end_ms: int
    text: str


@dataclass(frozen=True)
class Segment:
    start_ms: int  # relative to the audio passed in
    end_ms: int
    text: str
    words: tuple[Word, ...]


class AsrEngine(Protocol):
    name: str
    languages: frozenset[str]

    def transcribe(
        self, pcm16k: Int16Array, language: str = "en", keywords: list[str] | None = None
    ) -> list[Segment]: ...


def segment_to_dict(segment: Segment) -> dict[str, Any]:
    return asdict(segment)


def segment_from_dict(data: dict[str, Any]) -> Segment:
    words = tuple(Word(**w) for w in data["words"])
    return Segment(data["start_ms"], data["end_ms"], data["text"], words)
