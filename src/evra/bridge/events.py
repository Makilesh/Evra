"""Python -> React events: window.__evraEmit(name, payload) (see frontend/src/bridge.ts)."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any, Protocol

_EVENT_NAME = re.compile(r"^[a-z][a-z0-9_.:-]{0,63}$")


class JsRunner(Protocol):
    def run_js(self, script: str) -> Any: ...


def build_emit_script(name: str, payload: Mapping[str, Any]) -> str:
    """Serialise to ASCII-only JSON, which is also a valid JS expression."""
    if not _EVENT_NAME.match(name):
        raise ValueError(f"invalid event name: {name!r}")
    body = json.dumps(dict(payload), ensure_ascii=True, separators=(",", ":"))
    body = body.replace("</", r"<\/")
    return f"window.__evraEmit && window.__evraEmit({json.dumps(name)}, {body});"


class EventBus:
    def __init__(self) -> None:
        self._runner: JsRunner | None = None

    def attach(self, runner: JsRunner) -> None:
        self._runner = runner

    def emit(self, name: str, payload: Mapping[str, Any]) -> bool:
        """Push an event to the UI. Returns False if no window is attached yet."""
        script = build_emit_script(name, payload)
        if self._runner is None:
            return False
        self._runner.run_js(script)
        return True
