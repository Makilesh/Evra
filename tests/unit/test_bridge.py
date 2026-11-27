import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
import structlog

from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus, build_emit_script
from evra.capture.devices import MicList
from evra.config import Settings
from evra.notes.extract import CheckedItem
from evra.notes.validate import CheckedNote
from evra.store.db import connect
from evra.store.items import ItemStore
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.store.notes import NoteStore


class FakeWindow:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def run_js(self, script: str) -> Any:
        self.scripts.append(script)
        return None


class StubControl:
    mic_name = "Headset (realme Buds Air7)"

    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    def start(self, mic_name: str) -> dict[str, Any]:
        self.calls.append(("start", mic_name))
        return {"ok": True, "meeting_id": "m"}

    def stop(self) -> dict[str, Any]:
        self.calls.append(("stop", None))
        return {"ok": True}

    def write_note(self, meeting_id: str) -> dict[str, Any]:
        self.calls.append(("write_note", meeting_id))
        return {"ok": True}

    def state(self) -> dict[str, Any]:
        return {"state": "idle"}

    @property
    def settings(self) -> Settings:
        return Settings()

    def set_theme(self, theme: str) -> bool:
        self.calls.append(("set_theme", theme))
        return True

    def set_note_model(self, model: str) -> bool:
        self.calls.append(("set_note_model", model))
        return True

    def note_models(self) -> dict[str, Any]:
        return {"ok": True, "models": ["gemma4:12b", "qwen3.5:9b"]}


def _api(tmp_path: Path, bus: EventBus | None = None, **kwargs: Any) -> tuple[BridgeApi, Path]:
    db = tmp_path / "evra.db"
    conn = connect(db)
    migrate(conn)
    conn.close()
    api = BridgeApi(
        app_name="Evra",
        version="0.1.0",
        bus=bus or EventBus(),
        control=kwargs.pop("control", StubControl()),
        db_path=db,
        **kwargs,
    )
    return api, db


def _meeting(db: Path, title: str = "Weekly 1:1") -> str:
    conn: sqlite3.Connection = connect(db)
    try:
        return MeetingStore(conn).create_meeting(
            title=title, mode="one_on_one", situation="call_headphones", template="one_on_one"
        )
    finally:
        conn.close()


def _payload_from(script: str) -> Any:
    prefix = 'window.__evraEmit && window.__evraEmit("app.hello", '
    assert script.startswith(prefix) and script.endswith(");")
    return json.loads(script[len(prefix) : -2])


def test_api_surface_is_only_the_intended_methods(tmp_path: Path) -> None:
    api = _api(tmp_path)[0]
    public = sorted(n for n in dir(api) if not n.startswith("_"))
    assert public == [
        "app_info",
        "ask_meeting",
        "get_meeting",
        "get_settings",
        "list_meetings",
        "list_mics",
        "list_note_models",
        "list_people",
        "open_data_folder",
        "ping",
        "prepare_ask",
        "recording_state",
        "remove_person",
        "rename_meeting",
        "rename_person",
        "request_hello",
        "save_notes",
        "set_item_status",
        "set_meeting_person",
        "set_note_model",
        "set_theme",
        "start_recording",
        "stop_recording",
        "write_note",
    ]


def test_ping_and_app_info(tmp_path: Path) -> None:
    api = _api(tmp_path)[0]
    assert api.ping("hello") == {"reply": "pong: hello"}
    assert api.app_info() == {"name": "Evra", "version": "0.1.0"}


def test_request_hello_pushes_event_to_window(tmp_path: Path) -> None:
    bus = EventBus()
    window = FakeWindow()
    bus.attach(window)
    _api(tmp_path, bus=bus)[0].request_hello()
    [script] = window.scripts
    assert _payload_from(script) == {"message": "Python is connected"}


def test_emit_without_window_returns_false() -> None:
    assert EventBus().emit("app.hello", {"a": 1}) is False


@pytest.mark.parametrize(
    "payload",
    [
        {"text": 'she said "stop"'},
        {"text": "line one\nline two\r\n\ttab"},
        {"text": "</script><script>alert(1)</script>"},
        {"text": "தமிழ் हिन्दी 中文 🎙️", "sep": "\u2028\u2029"},
        {"nested": {"list": [1, 2.5, None, True]}},
    ],
)
def test_emit_script_round_trips_awkward_payloads(payload: dict[str, Any]) -> None:
    script = build_emit_script("app.hello", payload)
    assert script.isascii()
    assert _payload_from(script) == payload


@pytest.mark.parametrize("name", ["", "App.Hello", "a b", "x" * 65, "1abc", "a;alert(1)"])
def test_invalid_event_names_rejected(name: str) -> None:
    with pytest.raises(ValueError):
        build_emit_script(name, {})


def test_meetings_are_listed_and_opened_as_json(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid = _meeting(db)
    [summary] = api.list_meetings()
    assert (summary["id"], summary["title"], summary["has_note"]) == (mid, "Weekly 1:1", False)
    detail = api.get_meeting(mid)
    assert detail is not None and detail["meeting"]["id"] == mid
    json.dumps(detail)
    assert api.get_meeting("nope") is None
    assert api.get_meeting(42) is None  # type: ignore[arg-type]


def test_mics_include_the_remembered_choice(tmp_path: Path) -> None:
    api, _ = _api(tmp_path, mic_lister=lambda: MicList("Headset", ("Headset", "Array")))
    assert api.list_mics() == {
        "default": "Headset",
        "mics": ["Headset", "Array"],
        "chosen": "Headset (realme Buds Air7)",
    }


def test_mics_that_cannot_be_listed_fall_back_to_the_default(tmp_path: Path) -> None:
    def broken() -> MicList:
        raise OSError("PortAudio not initialised")

    api, _ = _api(tmp_path, mic_lister=broken)
    assert api.list_mics() == {"default": "", "mics": [], "chosen": "Headset (realme Buds Air7)"}


def test_rename_tidies_the_title_and_refuses_bad_input(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid = _meeting(db)
    assert api.rename_meeting(mid, "  Sync   with Priya ") == {"ok": True}
    assert api.list_meetings()[0]["title"] == "Sync with Priya"
    assert api.rename_meeting(mid, "   ") == {"ok": False}
    assert api.rename_meeting(mid, 5) == {"ok": False}  # type: ignore[arg-type]
    assert api.rename_meeting("nope", "x") == {"ok": False}


def test_an_item_is_ticked_and_bad_input_is_refused(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid = _meeting(db)
    conn = connect(db)
    try:
        vid = MeetingStore(conn).create_transcript_version(mid, kind="live", model="fake")
        generation = NoteStore(conn).save_generation(
            meeting_id=mid,
            transcript_version_id=vid,
            note=CheckedNote((), (), 0, 0, {}),
            provider="fake",
            model="fake:1b",
            prompt_version="a0-v1+a4-v1",
            template="one_on_one",
            tokens_in=1,
            tokens_out=1,
            items=[CheckedItem("action_item", "Send the quote", ("u1",), "You", None, 0.9)],
        )
        [item] = ItemStore(conn).for_generation(generation)
    finally:
        conn.close()
    assert api.set_item_status(item.id, "done") == {"ok": True}
    for item_id, status in [(item.id, "finished"), ("nope", "open"), (5, "done"), (item.id, None)]:
        assert api.set_item_status(item_id, status) == {"ok": False}  # type: ignore[arg-type]
    conn = connect(db)
    try:
        assert ItemStore(conn).for_generation(generation)[0].status == "done"
    finally:
        conn.close()


NOTE_LINE = {
    "id": "l1",
    "text": "Budget approved",
    "captured_at": 1_790_600_005_000,
    "pasted": False,
}


def test_save_notes_refuses_bad_shapes(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid = _meeting(db)
    refused_lists: list[Any] = [None, "l1", {"lines": [NOTE_LINE]}, (NOTE_LINE,)]
    refused_entries: list[Any] = [
        "Budget approved",
        5,
        None,
        NOTE_LINE | {"id": 5},
        NOTE_LINE | {"text": None},
        NOTE_LINE | {"captured_at": "now"},
        NOTE_LINE | {"captured_at": 1.5},
        NOTE_LINE | {"captured_at": True},
        NOTE_LINE | {"pasted": "yes"},
        NOTE_LINE | {"pasted": 1},
        {k: v for k, v in NOTE_LINE.items() if k != "pasted"},
        NOTE_LINE | {"id": "has space"},  # the store's own rules
        NOTE_LINE | {"text": "x" * 4_001},
    ]
    with structlog.testing.capture_logs() as logs:
        for lines in refused_lists:
            assert api.save_notes(mid, lines) == {"ok": False}
        for entry in refused_entries:
            assert api.save_notes(mid, [entry]) == {"ok": False}
        assert api.save_notes(5, [NOTE_LINE]) == {"ok": False}  # type: ignore[arg-type]
        assert api.save_notes("nope", [NOTE_LINE]) == {"ok": False}
    assert "budget" not in json.dumps(logs).lower()  # a note line is content (RB37)
    detail = api.get_meeting(mid)
    assert detail is not None and detail["notes"] == []  # nothing refused was saved


def test_notes_are_saved_and_come_back_with_the_meeting(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid = _meeting(db)
    untimed = NOTE_LINE | {"id": "l2", "text": "Ask about Dana", "captured_at": None}
    with structlog.testing.capture_logs() as logs:
        assert api.save_notes(mid, [NOTE_LINE, untimed]) == {"ok": True}
    assert "budget" not in json.dumps(logs).lower()  # never the lines themselves (RB43)
    detail = api.get_meeting(mid)
    assert detail is not None
    assert [(n["id"], n["text"], n["pasted"]) for n in detail["notes"]] == [
        ("l1", "Budget approved", False),
        ("l2", "Ask about Dana", False),
    ]
    assert api.save_notes(mid, []) == {"ok": True}  # every line deleted
    again = api.get_meeting(mid)
    assert again is not None and again["notes"] == []


def test_who_a_1on1_was_with_is_set_by_name(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid, other = _meeting(db), _meeting(db, "Design review")
    reply = api.set_meeting_person(mid, "  Priya ")
    priya = reply["with"]
    assert reply == {"ok": True, "with": {"id": priya["id"], "name": "Priya"}}
    assert api.set_meeting_person(other, "PRIYA") == {"ok": True, "with": priya}  # the same one
    assert api.list_people() == [priya]
    detail = api.get_meeting(mid)
    assert detail is not None and detail["with"] == priya
    assert [m["with_name"] for m in api.list_meetings()] == ["Priya", "Priya"]
    assert api.set_meeting_person(mid, "") == {"ok": True, "with": None}
    assert api.set_meeting_person(other, None) == {"ok": True, "with": None}
    assert [m["with_name"] for m in api.list_meetings()] == [None, None]
    assert api.list_people() == [priya]  # unlinked, not forgotten: removing is its own call


def test_set_meeting_person_refuses_you_and_bad_names(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid = _meeting(db)
    assert api.set_meeting_person(mid, " you ") == {"ok": False, "reason": "reserved"}
    for bad in ["   ", "x" * 81, 5, ["Priya"]]:
        assert api.set_meeting_person(mid, bad) == {"ok": False, "reason": "invalid"}  # type: ignore[arg-type]
    assert api.set_meeting_person(5, "Priya") == {"ok": False}  # type: ignore[arg-type]
    assert api.set_meeting_person("nope", "Priya") == {"ok": False}  # no such meeting
    assert api.list_people() == []  # a refused call leaves no one behind


def test_people_are_renamed_and_removed(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    mid = _meeting(db)
    priya = api.set_meeting_person(mid, "Priya")["with"]
    sam = api.set_meeting_person(_meeting(db), "Sam")["with"]
    for person_id, name, reason in [
        (sam["id"], " priya", "taken"),
        (priya["id"], "YOU", "reserved"),
        (priya["id"], "  ", "invalid"),
        (priya["id"], None, "invalid"),
        ("nope", "Dana", "unknown"),
        (5, "Dana", "unknown"),
    ]:
        assert api.rename_person(person_id, name) == {"ok": False, "reason": reason}  # type: ignore[arg-type]
    assert api.rename_person(priya["id"], "Priya  Shah") == {"ok": True}
    detail = api.get_meeting(mid)
    assert detail is not None and detail["with"] == {"id": priya["id"], "name": "Priya Shah"}
    assert api.remove_person(priya["id"]) == {"ok": True}
    assert api.remove_person(priya["id"]) == {"ok": False}
    assert api.remove_person(5) == {"ok": False}  # type: ignore[arg-type]
    assert api.list_people() == [sam]
    detail = api.get_meeting(mid)
    assert detail is not None and detail["with"] is None


def test_names_never_reach_the_log(tmp_path: Path) -> None:
    """A person's name is content: the people calls log ids and counts only."""
    api, db = _api(tmp_path)
    mid = _meeting(db)
    with structlog.testing.capture_logs() as logs:
        person = api.set_meeting_person(mid, "Priya")["with"]
        api.set_meeting_person(mid, "You")
        api.list_people()
        api.rename_person(person["id"], "Priyanka")
        api.get_meeting(mid)
        api.list_meetings()
        api.remove_person(person["id"])
    assert [e["event"] for e in logs] == ["meeting_person_set"]
    assert "priya" not in json.dumps(logs).lower()


def test_recording_calls_go_to_the_service_and_bad_input_is_refused(tmp_path: Path) -> None:
    control = StubControl()
    api, _ = _api(tmp_path, control=control)
    assert api.start_recording("Headset") == {"ok": True, "meeting_id": "m"}
    assert api.start_recording(None) == {"ok": False, "reason": "invalid"}  # type: ignore[arg-type]
    assert api.stop_recording() == {"ok": True}
    assert api.write_note("m") == {"ok": True}
    assert api.write_note(["m"]) == {"ok": False}  # type: ignore[arg-type]
    assert api.recording_state() == {"state": "idle"}
    assert control.calls == [("start", "Headset"), ("stop", None), ("write_note", "m")]


def test_events_after_the_window_is_gone_are_dropped(tmp_path: Path) -> None:
    class ClosedWindow:
        def run_js(self, script: str) -> Any:
            raise RuntimeError("window destroyed")

    bus = EventBus()
    bus.attach(ClosedWindow())
    assert bus.emit("recording.state", {"state": "idle"}) is False
    window = FakeWindow()
    bus.attach(window)
    bus.detach()
    assert bus.emit("recording.state", {"state": "idle"}) is False
    assert window.scripts == []


def test_event_text_cannot_close_the_script() -> None:
    script = build_emit_script("transcript.utterance", {"text": "</script><b>x</b>"})
    assert "</script>" not in script


def test_settings_show_the_theme_note_model_folder_and_version(tmp_path: Path) -> None:
    api, db = _api(tmp_path)
    assert api.get_settings() == {
        "theme": "light",
        "note_model": "gemma4:12b",
        "default_note_model": "gemma4:12b",
        "data_dir": str(db.parent),
        "version": "0.1.0",
    }


def test_the_theme_is_light_dark_or_match_windows(tmp_path: Path) -> None:
    control = StubControl()
    api, _ = _api(tmp_path, control=control)
    assert api.set_theme("dark") == {"ok": True}
    assert api.set_theme("system") == {"ok": True}
    assert api.set_theme("sepia") == {"ok": False}
    assert api.set_theme(1) == {"ok": False}  # type: ignore[arg-type]
    assert control.calls == [("set_theme", "dark"), ("set_theme", "system")]


def test_note_model_names_are_checked_before_they_are_saved(tmp_path: Path) -> None:
    control = StubControl()
    api, _ = _api(tmp_path, control=control)
    assert api.set_note_model("qwen3.5:9b") == {"ok": True}
    assert api.set_note_model("hf.co/someone/model:Q4_K_M") == {"ok": True}
    for bad in ["", " gemma", "x" * 201, "rm -rf /", "a\nb", 5]:
        assert api.set_note_model(bad) == {"ok": False}  # type: ignore[arg-type]
    assert control.calls == [
        ("set_note_model", "qwen3.5:9b"),
        ("set_note_model", "hf.co/someone/model:Q4_K_M"),
    ]


def test_note_models_come_from_ollama_through_the_service(tmp_path: Path) -> None:
    api, _ = _api(tmp_path)
    assert api.list_note_models() == {"ok": True, "models": ["gemma4:12b", "qwen3.5:9b"]}


def test_the_data_folder_opens_where_the_meetings_are(tmp_path: Path) -> None:
    opened: list[Path] = []
    api, db = _api(tmp_path, folder_opener=opened.append)
    assert api.open_data_folder() == {"ok": True}
    assert opened == [db.parent]


def test_a_data_folder_that_cannot_open_says_so(tmp_path: Path) -> None:
    def refuse(path: Path) -> None:
        raise OSError("no explorer")

    api, _ = _api(tmp_path, folder_opener=refuse)
    assert api.open_data_folder() == {"ok": False}


def test_set_note_model_refuses_cloud(tmp_path: Path) -> None:
    control = StubControl()
    api, _ = _api(tmp_path, control=control)
    assert api.set_note_model("gemma4:cloud") == {"ok": False}
    assert api.set_note_model("gemma4:31b-cloud") == {"ok": False}
    assert control.calls == []


class StubAsker:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def ask(self, meeting_id: object, question: object) -> dict[str, Any]:
        self.calls.append(("ask", (meeting_id, question)))
        return {"ok": True, "question": {"id": "q"}}

    def prepare(self, meeting_id: object) -> dict[str, Any]:
        self.calls.append(("prepare", (meeting_id,)))
        return {"ok": True}


def test_ask_meeting_passes_through(tmp_path: Path) -> None:
    asker = StubAsker()
    api = _api(tmp_path, asker=asker)[0]
    assert api.ask_meeting("m1", "When?") == {"ok": True, "question": {"id": "q"}}
    assert api.prepare_ask("m1") == {"ok": True}
    assert asker.calls == [("ask", ("m1", "When?")), ("prepare", ("m1",))]


def test_prepare_ask_refuses_non_strings(tmp_path: Path) -> None:
    asker = StubAsker()
    api = _api(tmp_path, asker=asker)[0]
    assert api.prepare_ask(5) == {"ok": False}  # type: ignore[arg-type]
    assert api.ask_meeting(5, "q") == {"ok": False, "reason": "invalid"}  # type: ignore[arg-type]
    assert api.ask_meeting("m", None) == {"ok": False, "reason": "invalid"}  # type: ignore[arg-type]
    assert asker.calls == []
