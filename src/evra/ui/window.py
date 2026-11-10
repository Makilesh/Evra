"""The pywebview main window (BUILD.md §4.3). Never start pywebview's HTTP server (D6)."""

from __future__ import annotations

import sys
from pathlib import Path

from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus
from evra.constants import APP_NAME

DEV_SERVER_URL = "http://127.0.0.1:5173"
WEB_DIR = Path(__file__).parent / "web"
# The pad (`--pad` in frontend/src/index.css). WebView2 shows this colour until the page paints
# and while the window resizes, so it follows the theme the page is about to pick.
PAD_LIGHT = "#E7EFDB"
PAD_DARK = "#131A15"
_PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"


def apps_use_light_theme() -> int | None:
    """Windows' app theme (0 = dark), the setting WebView2 reports as `prefers-color-scheme`.
    None when it cannot be read."""
    if sys.platform != "win32":
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PERSONALIZE_KEY) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
    except OSError:
        return None
    return value if isinstance(value, int) else None


def window_background(light_theme: int | None) -> str:
    return PAD_DARK if light_theme == 0 else PAD_LIGHT


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


def open_main_window(
    *, url: str, api: BridgeApi, bus: EventBus, debug: bool, storage_dir: Path
) -> None:
    """Open the window. `storage_dir` holds the WebView2 profile (D23: never %TEMP%);
    private mode still wipes it on close."""
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
        background_color=window_background(apps_use_light_theme()),
    )
    if window is None:
        raise RuntimeError("pywebview did not create a window")
    bus.attach(window)
    storage_dir.mkdir(parents=True, exist_ok=True)
    webview.start(debug=debug, private_mode=True, storage_path=str(storage_dir))
