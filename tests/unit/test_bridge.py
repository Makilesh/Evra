import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest

from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus, build_emit_script
from evra.capture.devices import MicList
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate


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
        "get_meeting",
        "list_meetings",
        "list_mics",
        "ping",
        "recording_state",
        "rename_meeting",
        "request_hello",
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
