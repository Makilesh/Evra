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


def _built_ui(tmp_path: Path) -> Path:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<html></html>", encoding="utf-8")
    return web


def test_window_failure_is_logged_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    def broken_opener(
        *, url: str, api: BridgeApi, bus: EventBus, debug: bool, storage_dir: Path
    ) -> None:
        raise RuntimeError("webview2 missing")

    paths = AppPaths.under(tmp_path / "home")
    code = run_app(
        dev=False, debug=False, paths=paths, web_dir=_built_ui(tmp_path), opener=broken_opener
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "RuntimeError" in err and str(paths.log_dir / "evra.log") in err
    assert "Traceback" not in err
    log_text = (paths.log_dir / "evra.log").read_text(encoding="utf-8")
    assert '"exc_type": "RuntimeError"' in log_text
    assert "app_failed" in log_text


def test_startup_failure_in_database_is_logged_and_exits_1(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = AppPaths.under(tmp_path / "home")
    paths.db_path.mkdir(parents=True)  # a folder where the database file should be
    code = run_app(dev=False, debug=False, paths=paths, web_dir=_built_ui(tmp_path))
    assert code == 1
    assert "could not start" in capsys.readouterr().err
    assert "app_failed" in (paths.log_dir / "evra.log").read_text(encoding="utf-8")


def test_build_app_recovers_meetings_left_mid_way(tmp_path: Path) -> None:
    from evra.store.meetings import MeetingStore
    from evra.store.migrate import migrate

    paths = AppPaths.under(tmp_path)
    paths.ensure()
    conn = connect(paths.db_path)
    migrate(conn)
    mid = MeetingStore(conn).create_meeting(
        title="t", mode="one_on_one", situation="call_headphones", template="one_on_one"
    )
    conn.close()
    build_app(paths, debug=False)
    conn = connect(paths.db_path)
    try:
        assert MeetingStore(conn).get_meeting(mid)["state"] == "failed"
    finally:
        conn.close()


def test_closing_the_window_shuts_the_meeting_service_down(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evra.services.meetings import MeetingService

    closed: list[bool] = []
    monkeypatch.setattr(MeetingService, "shutdown", lambda self: closed.append(True))

    def fake_opener(
        *, url: str, api: BridgeApi, bus: EventBus, debug: bool, storage_dir: Path
    ) -> None:
        return None

    paths = AppPaths.under(tmp_path / "home")
    assert (
        run_app(
            dev=False, debug=False, paths=paths, web_dir=_built_ui(tmp_path), opener=fake_opener
        )
        == 0
    )
    assert closed == [True]
