import json
import math
import re
import sqlite3
import zlib
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


def saved_meeting(
    conn: sqlite3.Connection, title: str, *, with_note: bool = True, with_transcript: bool = True
) -> str:
    """A finished meeting with a transcript and, unless asked not to, a saved note."""
    store = MeetingStore(conn)
    mid = store.create_meeting(
        title=title, mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = store.create_transcript_version(mid, kind="live", model="fake")
    spoken = [
        (1, 0, "The launch moves to October 14."),
        (0, 9_000, "I will send the designer proposal."),
    ]
    for channel, start_ms, text in spoken if with_transcript else []:
        store.add_utterance(
            version_id=vid,
            meeting_id=mid,
            channel=channel,
            start_ms=start_ms,
            end_ms=start_ms + 5_000,
            text=text,
        )
    if with_note:
        NoteStore(conn).save_generation(
            meeting_id=mid,
            transcript_version_id=vid,
            note=SAVED_NOTE,
            provider="fake",
            model="fake:1b",
            prompt_version="a0-v1+a1-v3",
            template="one_on_one",
            tokens_in=1,
            tokens_out=1,
        )
    return mid


def _hash_vector(text: str, dims: int = 64) -> list[float]:
    """A bag of words hashed into `dims` slots, unit length: shared words raise the cosine."""
    vector = [0.0] * dims
    for word in re.findall(r"[a-z0-9']+", text.lower()):
        vector[zlib.crc32(word.encode()) % dims] += 1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


class FakeProvider:
    name = "fake"

    def __init__(self, replies: list[str], tokens_in: int = 100, truncated: bool = False) -> None:
        self.replies = list(replies)
        self.truncated = truncated
        self.tokens_in = tokens_in
        self.calls: list[list[ChatMessage]] = []
        self.models = ["fake:1b"]
        self.loaded: list[str] = []
        self.embed_calls: list[list[str]] = []

    def load(self, model: str) -> None:
        self.loaded.append(model)

    def chat_json(
        self, model: str, messages: Sequence[ChatMessage], schema: Mapping[str, Any]
    ) -> ChatResult:
        self.calls.append(list(messages))
        return ChatResult(self.replies.pop(0), self.tokens_in, 50, 0.5, self.truncated)

    def embed(self, model: str, texts: Sequence[str]) -> list[list[float]]:
        self.embed_calls.append(list(texts))
        return [_hash_vector(t) for t in texts]

    def installed_models(self) -> list[str]:
        return list(self.models)


def utt(uid: str, channel: int, start: int, end: int, text: str, seq: int = 0) -> Utterance:
    return Utterance(uid, "v", "m", seq, channel, None, start, end, text, (), None)
