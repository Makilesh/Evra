"""Why a note or an answer could not be written. Messages never carry prompt or reply text."""

from __future__ import annotations


class NoteError(Exception):
    """The note could not be written."""


class NoTranscript(NoteError):
    """There is nothing to write a note from."""


class NoteTooLong(NoteError):
    def __init__(self, estimated: int, limit: int) -> None:
        super().__init__(f"about {estimated} prompt tokens, limit {limit}")
        self.estimated = estimated
        self.limit = limit


class NoteCutOff(NoteError):
    def __init__(self, limit: int) -> None:
        super().__init__(f"the reply hit the {limit}-token output limit")
        self.limit = limit


class NoteInvalid(NoteError):
    def __init__(self, model: str) -> None:
        super().__init__(f"{model} returned invalid JSON twice")
        self.model = model
