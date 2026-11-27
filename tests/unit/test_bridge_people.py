"""The People pages' bridge (Plan C Task 3): everyone named with their last 1:1, a person's page
and their brief through the people service. Beside test_bridge.py, whose helpers it shares."""

import sqlite3
from pathlib import Path
from typing import Any

from evra.store.db import connect
from evra.store.meetings import MeetingStore
from tests.unit.test_bridge import _api, _meeting


class StubPeople:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def person_page(self, person_id: object) -> dict[str, Any] | None:
        self.calls.append(("person_page", person_id))
        return {"person": {"id": person_id, "name": "Priya"}}

    def write_brief(self, person_id: object) -> dict[str, Any]:
        self.calls.append(("write_brief", person_id))
        return {"ok": True}


def _started(db: Path, meeting_id: str) -> int:
    conn: sqlite3.Connection = connect(db)
    try:
        return int(MeetingStore(conn).get_meeting(meeting_id)["started_at"])
    finally:
        conn.close()


def test_people_are_listed_with_their_last_1on1(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    first, second, third = _meeting(db, "Budget check"), _meeting(db, "Weekly 1:1"), _meeting(db)
    priya = api.set_meeting_person(first, "Priya")["with"]
    assert api.set_meeting_person(second, "priya")["with"] == priya
    sam = api.set_meeting_person(third, "Sam")["with"]
    assert api.list_people() == [  # by name, each with when their newest 1:1 started
        {**priya, "last_met": max(_started(db, first), _started(db, second))},
        {**sam, "last_met": _started(db, third)},
    ]
    assert api.set_meeting_person(first, None)["ok"] and api.set_meeting_person(second, None)["ok"]
    assert api.list_people()[0] == {**priya, "last_met": None}  # named, but no 1:1 linked now


def test_a_person_page_and_brief_go_to_the_people_service(tmp_path: Path) -> None:
    people = StubPeople()
    api = _api(tmp_path, people=people)[0]
    assert api.person_page("p1") == {"person": {"id": "p1", "name": "Priya"}}
    assert api.write_brief("p1") == {"ok": True}
    assert people.calls == [("person_page", "p1"), ("write_brief", "p1")]
    assert api.person_page(5) is None  # type: ignore[arg-type]
    assert api.write_brief(None) == {"ok": False, "reason": "invalid"}  # type: ignore[arg-type]
    assert people.calls == [("person_page", "p1"), ("write_brief", "p1")]
    alone = _api(tmp_path / "alone")[0]  # no people service: nothing to show or write
    assert alone.person_page("p1") is None
    assert alone.write_brief("p1") == {"ok": False, "reason": "invalid"}
