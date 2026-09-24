from pathlib import Path

import pytest

from evra.app import build_app, run_app
from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus
from evra.paths import AppPaths
from evra.store.db import connect
from evra.store.migrate import current_version


def test_build_app_creates_dirs_logs_and_migrated_db(tmp_path: Path) -> None:
    paths = AppPaths.under(tmp_path)
    app = build_app(paths, debug=False)
    assert paths.db_path.exists()
    conn = connect(paths.db_path)
    assert current_version(conn) == 1
    conn.close()
    assert (paths.log_dir / "evra.log").exists()
    assert app.api.app_info()["name"] == "Evra"


def test_run_app_without_built_ui_exits_2_with_hint(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code = run_app(
        dev=False, debug=False, paths=AppPaths.under(tmp_path), web_dir=tmp_path / "missing"
    )
    assert code == 2
    assert "npm --prefix frontend run build" in capsys.readouterr().err


def test_run_app_opens_window_with_file_url(tmp_path: Path) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html></html>", encoding="utf-8")
    calls: list[tuple[str, Path]] = []

    def fake_opener(
        *, url: str, api: BridgeApi, bus: EventBus, debug: bool, storage_dir: Path
    ) -> None:
        calls.append((url, storage_dir))

    paths = AppPaths.under(tmp_path / "home")
    code = run_app(dev=False, debug=False, paths=paths, web_dir=web, opener=fake_opener)
    assert code == 0
    [(url, storage_dir)] = calls
    assert url.startswith("file:///")
    assert storage_dir == paths.data_dir / "webview"
