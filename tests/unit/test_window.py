from pathlib import Path

import pytest
from webview.util import is_local_url

from evra.ui.window import DEV_SERVER_URL, UiNotBuiltError, resolve_ui_url


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

    fake = _patch_webview(monkeypatch)
    bus = EventBus()
    storage = tmp_path / "data" / "webview"
    open_main_window(
        url="file:///x/index.html",
        api=BridgeApi(app_name="Evra", version="0", bus=bus),
        bus=bus,
        debug=False,
        storage_dir=storage,
    )
    assert fake.started is not None
    assert fake.started["storage_path"] == str(storage)
    assert fake.started["private_mode"] is True
    assert not fake.started.get("http_server")
    assert storage.is_dir()


def test_open_main_window_refuses_local_path_urls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evra.bridge.api import BridgeApi
    from evra.bridge.events import EventBus
    from evra.ui.window import open_main_window

    fake = _patch_webview(monkeypatch)
    bus = EventBus()
    with pytest.raises(RuntimeError, match="HTTP server"):
        open_main_window(
            url="web/index.html",
            api=BridgeApi(app_name="Evra", version="0", bus=bus),
            bus=bus,
            debug=False,
            storage_dir=tmp_path / "webview",
        )
    assert fake.created is None and fake.started is None
