import re
from pathlib import Path

import pytest
from webview.util import is_local_url

from evra.paths import REPO_ROOT
from evra.ui.window import (
    DEV_SERVER_URL,
    PAD_DARK,
    PAD_LIGHT,
    UiNotBuiltError,
    resolve_ui_url,
    themed_url,
    window_background,
    windows_prefers_dark,
)


def test_dev_mode_uses_vite_dev_server() -> None:
    assert resolve_ui_url(dev=True) == DEV_SERVER_URL == "http://127.0.0.1:5173"


def test_built_mode_uses_file_url(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    url = resolve_ui_url(dev=False, web_dir=tmp_path)
    assert url.startswith("file:///")
    assert url.endswith("/index.html")


def test_file_url_encodes_spaces_and_unicode(tmp_path: Path) -> None:
    web = tmp_path / "GEN AI" / "Mākil"
    web.mkdir(parents=True)
    (web / "index.html").write_text("<html></html>", encoding="utf-8")
    url = resolve_ui_url(dev=False, web_dir=web)
    assert " " not in url
    assert "GEN%20AI" in url
    assert url.isascii()


def test_missing_build_raises_with_hint(tmp_path: Path) -> None:
    with pytest.raises(UiNotBuiltError, match="npm --prefix frontend run build"):
        resolve_ui_url(dev=False, web_dir=tmp_path)


def test_our_urls_never_start_pywebviews_http_server(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>", encoding="utf-8")
    assert not is_local_url(resolve_ui_url(dev=False, web_dir=tmp_path))
    assert not is_local_url(resolve_ui_url(dev=True))


class _FakeWebview:
    """Stands in for the pywebview module so no real window opens."""

    def __init__(self) -> None:
        self.created: dict[str, object] | None = None
        self.started: dict[str, object] | None = None

    def create_window(self, title: str, **kwargs: object) -> object:
        self.created = {"title": title, **kwargs}
        return object()

    def start(self, **kwargs: object) -> None:
        self.started = kwargs


def _patch_webview(monkeypatch: pytest.MonkeyPatch) -> _FakeWebview:
    import webview

    fake = _FakeWebview()
    monkeypatch.setattr(webview, "create_window", fake.create_window)
    monkeypatch.setattr(webview, "start", fake.start)
    return fake


def test_webview_profile_lives_in_given_dir_not_temp(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evra.bridge.api import BridgeApi
    from evra.bridge.events import EventBus
    from evra.ui.window import open_main_window
    from tests.unit.test_bridge import StubControl

    fake = _patch_webview(monkeypatch)
    bus = EventBus()
    storage = tmp_path / "data" / "webview"
    open_main_window(
        url="file:///x/index.html",
        api=BridgeApi(
            app_name="Evra",
            version="0",
            bus=bus,
            control=StubControl(),
            db_path=tmp_path / "evra.db",
        ),
        bus=bus,
        debug=False,
        storage_dir=storage,
    )
    assert fake.started is not None
    assert fake.started["storage_path"] == str(storage)
    assert fake.started["private_mode"] is True
    assert not fake.started.get("http_server")
    assert storage.is_dir()


def test_window_background_follows_the_chosen_theme() -> None:
    assert window_background("light", windows_dark=lambda: True) == PAD_LIGHT
    assert window_background("dark", windows_dark=lambda: False) == PAD_DARK
    assert window_background("system", windows_dark=lambda: True) == PAD_DARK
    assert window_background("system", windows_dark=lambda: False) == PAD_LIGHT


def test_reading_the_windows_app_mode_never_fails() -> None:
    assert windows_prefers_dark() in (True, False)


def test_window_background_is_the_pages_pad_colour() -> None:
    css = (REPO_ROOT / "frontend" / "src" / "index.css").read_text(encoding="utf-8")
    light, dark = re.findall(r"--pad:\s*(#[0-9a-fA-F]{6})", css)[:2]
    assert (light.upper(), dark.upper()) == (PAD_LIGHT, PAD_DARK)


def test_the_page_learns_a_dark_theme_from_its_url() -> None:
    page = "file:///D:/GEN%20AI/Evra/src/evra/ui/web/index.html"
    assert themed_url(page, "light") == page
    assert themed_url(page, "dark") == page + "#theme=dark"
    assert themed_url(page, "system") == page + "#theme=system"
    assert themed_url(DEV_SERVER_URL, "dark") == DEV_SERVER_URL + "#theme=dark"
    assert not is_local_url(themed_url(page, "dark"))


def test_dotnet_still_opens_the_page_when_the_theme_is_dark() -> None:
    """pywebview loads the URL through System.Uri, which escapes a file URL's "?" into the file
    name (WebView2 then shows an error page); a "#" fragment comes through untouched."""
    pytest.importorskip("pythonnet")
    import clr  # noqa: F401  (starts .NET, as pywebview does)
    from System import Uri  # type: ignore[import-not-found]

    uri = Uri(themed_url("file:///D:/GEN%20AI/Evra/src/evra/ui/web/index.html", "dark"))
    assert uri.AbsolutePath.endswith("/index.html")
    assert uri.Fragment == "#theme=dark"


def _open(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, theme: str) -> dict[str, object]:
    from evra.bridge.api import BridgeApi
    from evra.bridge.events import EventBus
    from evra.ui.window import open_main_window
    from tests.unit.test_bridge import StubControl

    fake = _patch_webview(monkeypatch)
    bus = EventBus()
    open_main_window(
        url="file:///x/index.html",
        api=BridgeApi(
            app_name="Evra",
            version="0",
            bus=bus,
            control=StubControl(),
            db_path=tmp_path / "evra.db",
        ),
        bus=bus,
        debug=False,
        storage_dir=tmp_path / "webview",
        theme=theme,  # type: ignore[arg-type]
    )
    assert fake.created is not None
    return fake.created


def test_a_dark_window_opens_dark_with_no_light_flash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _open(tmp_path, monkeypatch, "dark")
    assert created["background_color"] == PAD_DARK
    assert created["url"] == "file:///x/index.html#theme=dark"


def test_a_window_that_matches_windows_opens_on_its_pad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import evra.ui.window as window

    monkeypatch.setattr(window, "windows_prefers_dark", lambda: True)
    created = _open(tmp_path, monkeypatch, "system")
    assert created["background_color"] == PAD_DARK
    assert created["url"] == "file:///x/index.html#theme=system"


def test_a_light_window_opens_on_the_light_pad(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    created = _open(tmp_path, monkeypatch, "light")
    assert created["background_color"] == PAD_LIGHT
    assert created["url"] == "file:///x/index.html"


def test_open_main_window_refuses_local_path_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evra.bridge.api import BridgeApi
    from evra.bridge.events import EventBus
    from evra.ui.window import open_main_window
    from tests.unit.test_bridge import StubControl

    fake = _patch_webview(monkeypatch)
    bus = EventBus()
    with pytest.raises(RuntimeError, match="HTTP server"):
        open_main_window(
            url="web/index.html",
            api=BridgeApi(
                app_name="Evra",
                version="0",
                bus=bus,
                control=StubControl(),
                db_path=tmp_path / "evra.db",
            ),
            bus=bus,
            debug=False,
            storage_dir=tmp_path / "webview",
        )
    assert fake.created is None and fake.started is None
