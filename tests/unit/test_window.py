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
