import json
import sqlite3
from pathlib import Path

import pytest

from evra.notes.ask import AnswerState, AskResult, Exchange
from evra.notes.validate import CheckedBullet
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.questions import QuestionStore

Env = tuple[sqlite3.Connection, QuestionStore, str, str]


def _result(state: AnswerState = "answered", points: tuple[CheckedBullet, ...] = ()) -> AskResult:
    return AskResult(
        state=state,
        points=points,
        excerpt=True,
        model="m:1",
        prompt_version="a0-v1+a12-v1",
        tokens_in=10,
        tokens_out=5,
        cached_tokens=3,
        seconds=1.5,
        dropped=2,
    )


@pytest.fixture
def env(tmp_path: Path) -> Env:
    conn = connect(tmp_path / "evra.db")
    migrate(conn)
    meetings = MeetingStore(conn)
    mid = meetings.create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    vid = meetings.create_transcript_version(mid, kind="live", model="fake")
    return conn, QuestionStore(conn), mid, vid


def test_add_starts_asking(env: Env) -> None:
    _, store, mid, _ = env
    q = store.add(mid, "When?")
    assert (q.state, q.text, q.points, q.meeting_id) == ("asking", "When?", (), mid)
    assert store.get(q.id) == q


def test_answer_stores_points_and_state(env: Env) -> None:
    conn, store, mid, vid = env
    q = store.add(mid, "When?")
    done = store.answer(
        q.id,
        _result(points=(CheckedBullet("Friday.", ("u1", "user")),)),
        transcript_version_id=vid,
    )
    assert done.state == "answered" and done.excerpt is True and done.model == "m:1"
    assert done.points == (CheckedBullet("Friday.", ("u1", "user")),)
    row = conn.execute("SELECT * FROM question WHERE id = ?", (q.id,)).fetchone()
    assert json.loads(row["answer_json"]) == [{"text": "Friday.", "citations": ["u1", "user"]}]
    assert (row["dropped_claims"], row["transcript_version_id"], row["tokens_in"]) == (2, vid, 10)


def test_fail_keeps_the_reason(env: Env) -> None:
    _, store, mid, _ = env
    q = store.add(mid, "When?")
    failed = store.fail(q.id, "unavailable")
    assert (failed.state, failed.reason) == ("failed", "unavailable")


def test_history_is_the_newest_settled_turns_oldest_first(env: Env) -> None:
    _, store, mid, vid = env
    for i in range(5):
        q = store.add(mid, f"q{i}")
        if i == 1:
            store.fail(q.id, "x")
        elif i == 2:
            store.answer(q.id, _result("not_found"), transcript_version_id=vid)
        elif i == 3:
            store.answer(q.id, _result("unchecked"), transcript_version_id=vid)
        else:
            point = (CheckedBullet(f"a{i}", ("u1",)),)
            store.answer(q.id, _result(points=point), transcript_version_id=vid)
    store.add(mid, "pending")
    assert store.history(mid) == [
        Exchange("q0", ("a0",)),
        Exchange("q2", ()),
        Exchange("q4", ("a4",)),
    ]
    assert store.history(mid, limit=1) == [Exchange("q4", ("a4",))]
    assert len(store.for_meeting(mid)) == 6
    assert store.for_meeting(mid)[0].text == "q0"


def test_interrupted_marks_asking_rows(env: Env) -> None:
    _, store, mid, _ = env
    a = store.add(mid, "a")
    assert store.interrupted() == 1
    got = store.get(a.id)
    assert (got.state, got.reason) == ("failed", "interrupted")
    assert store.interrupted() == 0


def test_deleting_the_meeting_deletes_its_questions(env: Env) -> None:
    conn, store, mid, _ = env
    store.add(mid, "a")
    conn.execute("DELETE FROM meeting WHERE id = ?", (mid,))
    assert conn.execute("SELECT COUNT(*) FROM question").fetchone()[0] == 0
