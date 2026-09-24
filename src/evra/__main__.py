"""Command-line entry point: `evra` / `python -m evra`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from evra import __version__
from evra.constants import APP_ID, APP_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME} desktop app")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    commands = parser.add_subparsers(dest="command")
    run = commands.add_parser("run", help="open the Evra window")
    run.add_argument("--dev", action="store_true", help="load the Vite dev server (development)")
    run.add_argument("--debug", action="store_true", help="DEBUG logs and WebView devtools")
    run.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="keep all app data here (default: <repo>/.data from source, else per-user dirs)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        from evra.app import run_app  # keeps `evra --version` fast
        from evra.paths import resolve_paths

        return run_app(dev=args.dev, debug=args.debug, paths=resolve_paths(args.data_dir))
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
