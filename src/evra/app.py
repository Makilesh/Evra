"""Application container and startup (BUILD.md §4)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import structlog

from evra import __version__
from evra.bridge.api import BridgeApi
from evra.bridge.events import EventBus
from evra.config import Settings, debug_enabled, load_settings
from evra.constants import APP_NAME
from evra.logging_setup import LOG_FILE_NAME, configure_logging
from evra.paths import AppPaths, resolve_paths
from evra.services.meetings import MeetingService
from evra.store.db import connect
from evra.store.meetings import MeetingStore
from evra.store.migrate import migrate
from evra.transcribe.recording import RecordingKit
from evra.ui.window import WEB_DIR, UiNotBuiltError, open_main_window, resolve_ui_url

log = structlog.get_logger(__name__)


class WindowOpener(Protocol):
    def __call__(
        self, *, url: str, api: BridgeApi, bus: EventBus, debug: bool, storage_dir: Path
    ) -> None: ...


@dataclass
class App:
    paths: AppPaths
    settings: Settings
    bus: EventBus
    api: BridgeApi
    debug: bool
    service: MeetingService


def build_app(paths: AppPaths, *, debug: bool) -> App:
    paths.ensure()
    configure_logging(paths.log_dir, debug=debug)
    settings = load_settings(paths.settings_file)
    conn = connect(paths.db_path)
    try:
        schema = migrate(conn)
        recovered = MeetingStore(conn).recover_after_restart()
    finally:
        conn.close()
    bus = EventBus()
    service = MeetingService(paths=paths, settings=settings, emit=bus.emit, kit=RecordingKit(paths))
    api = BridgeApi(
        app_name=APP_NAME, version=__version__, bus=bus, control=service, db_path=paths.db_path
    )
    log.info("app_started", version=__version__, schema_version=schema, recovered=recovered)
    return App(paths=paths, settings=settings, bus=bus, api=api, debug=debug, service=service)


def run_app(
    *,
    dev: bool,
    debug: bool,
    paths: AppPaths | None = None,
    web_dir: Path | None = None,
    opener: WindowOpener = open_main_window,
) -> int:
    try:
        url = resolve_ui_url(dev=dev, web_dir=web_dir or WEB_DIR)
    except UiNotBuiltError as exc:
        print(exc, file=sys.stderr)
        return 2
    paths = paths or resolve_paths()
    try:
        app = build_app(paths, debug=debug or debug_enabled())
        try:
            opener(
                url=url,
                api=app.api,
                bus=app.bus,
                debug=app.debug,
                storage_dir=app.paths.data_dir / "webview",
            )
        finally:  # the window is closed: save a running recording, stop the workers
            app.bus.detach()
            app.service.shutdown()
    except Exception as exc:
        # Log the details (redacted per §9.1) and give the user one readable line.
        log.exception("app_failed")
        log_file = paths.log_dir / LOG_FILE_NAME
        print(
            f"{APP_NAME} could not start ({type(exc).__name__}). Details are in {log_file}",
            file=sys.stderr,
        )
        return 1
    return 0
