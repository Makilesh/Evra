"""The pywebview main window (BUILD.md §4.3). Never start pywebview's HTTP server (D6)."""

from __future__ import annotations

from pathlib import Path

from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus
from evra.constants import APP_NAME

DEV_SERVER_URL = "http://127.0.0.1:5173"
WEB_DIR = Path(__file__).parent / "web"
PAPER = "#FAF9F6"


class UiNotBuiltError(RuntimeError):
    pass


def resolve_ui_url(*, dev: bool, web_dir: Path = WEB_DIR) -> str:
    if dev:
        return DEV_SERVER_URL
    index = web_dir / "index.html"
    if not index.is_file():
        raise UiNotBuiltError(
            f"The UI is not built ({index} is missing). Run: npm --prefix frontend run build"
        )
    return index.resolve().as_uri()


def open_main_window(*, url: str, api: BridgeApi, bus: EventBus, debug: bool) -> None:
    import webview  # imported here: loads pythonnet/WebView2 only when a window is needed
    from webview.util import is_local_url

    if is_local_url(url):
        raise RuntimeError(f"refusing {url!r}: it would start pywebview's HTTP server")
    window = webview.create_window(
        APP_NAME,
        url=url,
        js_api=api,
        width=1100,
        height=720,
        min_size=(720, 480),
        background_color=PAPER,
    )
    if window is None:
        raise RuntimeError("pywebview did not create a window")
    bus.attach(window)
    webview.start(debug=debug, private_mode=True)
