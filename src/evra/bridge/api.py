"""Methods React can call as window.pywebview.api.<name>(...).

pywebview exposes every public attribute, so keep state in underscore attributes.
"""

from __future__ import annotations

from typing import TypedDict

from evra.bridge.events import EventBus


class PingReply(TypedDict):
    reply: str


class AppInfoDict(TypedDict):
    name: str
    version: str


class BridgeApi:
    def __init__(self, *, app_name: str, version: str, bus: EventBus) -> None:
        self._app_name = app_name
        self._version = version
        self._bus = bus

    def ping(self, message: str) -> PingReply:
        return {"reply": f"pong: {message}"}

    def app_info(self) -> AppInfoDict:
        return {"name": self._app_name, "version": self._version}

    def request_hello(self) -> None:
        """Proves the Python -> React push path."""
        self._bus.emit("app.hello", {"message": "Python is connected"})
