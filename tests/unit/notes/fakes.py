import json
import sqlite3
from collections.abc import Mapping, Sequence
from typing import Any

from evra.llm.provider import ChatMessage, ChatResult
from evra.notes.validate import CheckedBullet, CheckedNote, CheckedSection
from evra.store.meetings import MeetingStore, Utterance
from evra.store.notes import NoteStore

SAVED_NOTE = CheckedNote(
    summary=(CheckedBullet("The launch moves to October 14.", ("u1",)),),
    sections=(
        CheckedSection(
            "action_items",
            "Action items",
            (CheckedBullet("You: send the designer proposal by Thursday.", ("u2",)),),
        ),
    ),
    kept=2,
    dropped=0,
    drop_reasons={},
)


def title_reply(title: str) -> str:
    return json.dumps({"title": title})


def saved_meeting(conn: sqlite3.Connection, title: str, *, with_note: bool = True) -> str:
    """A finished meeting with a transcript version and, unless asked not to, a saved note."""
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title=title, mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    if with_note:
        NoteStore(conn).save_generation(
            meeting_id=mid,
            transcript_version_id=vid,
            note=SAVED_NOTE,
            provider="fake",
            model="fake:1b",
            prompt_version="a1-v2",
            template="one_on_one",
            tokens_in=1,
            tokens_out=1,
        )
    return mid


class FakeProvider:
    name = "fake"

    def __init__(self, replies: list[str], tokens_in: int = 100, truncated: bool = False) -> None:
        self.replies = list(replies)
        self.truncated = truncated
        self.tokens_in = tokens_in
        self.calls: list[list[ChatMessage]] = []
        self.models = ["fake:1b"]

    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        self.calls.append(list(messages))
        return ChatResult(self.replies.pop(0), self.tokens_in, 50, 0.5, self.truncated)

    def installed_models(self) -> list[str]:
        return list(self.models)


def utt(uid: str, channel: int, start: int, end: int, text: str, seq: int = 0) -> Utterance:
    return Utterance(uid, "v", "m", seq, channel, None, start, end, text, (), None)
