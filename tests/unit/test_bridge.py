import json
from typing import Any

import pytest

from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus, build_emit_script


class FakeWindow:
    def __init__(self) -> None:
        self.scripts: list[str] = []

    def run_js(self, script: str) -> Any:
        self.scripts.append(script)
        return None


def _payload_from(script: str) -> Any:
    prefix = 'window.__evraEmit && window.__evraEmit("app.hello", '
    assert script.startswith(prefix) and script.endswith(");")
    return json.loads(script[len(prefix) : -2])


def test_api_surface_is_only_the_intended_methods() -> None:
    api = BridgeApi(app_name="Evra", version="0.1.0", bus=EventBus())
    public = sorted(n for n in dir(api) if not n.startswith("_"))
    assert public == ["app_info", "ping", "request_hello"]


def test_ping_and_app_info() -> None:
    api = BridgeApi(app_name="Evra", version="0.1.0", bus=EventBus())
    assert api.ping("hello") == {"reply": "pong: hello"}
    assert api.app_info() == {"name": "Evra", "version": "0.1.0"}


def test_request_hello_pushes_event_to_window() -> None:
    bus = EventBus()
    window = FakeWindow()
    bus.attach(window)
    BridgeApi(app_name="Evra", version="0.1.0", bus=bus).request_hello()
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
