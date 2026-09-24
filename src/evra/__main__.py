"""Command-line entry point: `evra` / `python -m evra`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from evra import __version__
from evra.constants import APP_ID, APP_NAME


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog=APP_ID, description=f"{APP_NAME} desktop app")
    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_subparsers(dest="command")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
