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
from evra.logging_setup import configure_logging
from evra.paths import AppPaths, resolve_paths
from evra.store.db import connect
from evra.store.migrate import migrate
from evra.ui.window import WEB_DIR, UiNotBuiltError, open_main_window, resolve_ui_url

log = structlog.get_logger(__name__)


class WindowOpener(Protocol):
    def __call__(self, *, url: str, api: BridgeApi, bus: EventBus, debug: bool) -> None: ...


@dataclass
class App:
    paths: AppPaths
    settings: Settings
    bus: EventBus
    api: BridgeApi
    debug: bool


def build_app(paths: AppPaths, *, debug: bool) -> App:
    paths.ensure()
    configure_logging(paths.log_dir, debug=debug)
    settings = load_settings(paths.settings_file)
    conn = connect(paths.db_path)
    try:
        schema = migrate(conn)
    finally:
        conn.close()
    bus = EventBus()
    api = BridgeApi(app_name=APP_NAME, version=__version__, bus=bus)
    log.info("app_started", version=__version__, schema_version=schema)
    return App(paths=paths, settings=settings, bus=bus, api=api, debug=debug)


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
    app = build_app(paths or resolve_paths(), debug=debug or debug_enabled())
    opener(url=url, api=app.api, bus=app.bus, debug=app.debug)
    return 0
