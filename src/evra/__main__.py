"""Command-line entry point: `evra` / `python -m evra`."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from evra import __version__
from evra.constants import APP_ID, APP_NAME


def _positive_seconds(value: str) -> float:
    seconds = float(value)
    if seconds <= 0:
        raise argparse.ArgumentTypeError("seconds must be > 0")
    return seconds


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
    test = commands.add_parser("capture-test", help="record both channels, write WAVs + health")
    test.add_argument("seconds", type=_positive_seconds, help="how long to record")
    test.add_argument("--mic", default=None, help="microphone index or name (default: system)")
    test.add_argument("--out", default=None, help="output folder (default: <data>/capture-test)")
    test.add_argument("--fake-mic", default=None, help="replay this WAV as the microphone")
    test.add_argument("--fake-system", default=None, help="replay this WAV as system audio")
    test.add_argument("--list-devices", action="store_true", help="list microphones and exit")
    test.add_argument("--data-dir", type=Path, default=None, help="keep all app data here")
    models = commands.add_parser("models", help="list (and download) the speech models")
    models.add_argument("--download", action="store_true", help="download missing models")
    models.add_argument("--data-dir", type=Path, default=None, help="keep all app data here")
    transcribe = commands.add_parser("transcribe", help="transcribe a WAV file")
    transcribe.add_argument("wav", help="16-bit PCM WAV file")
    transcribe.add_argument("--data-dir", type=Path, default=None, help="keep all app data here")
    record = commands.add_parser("record", help="record a 1:1 call and transcribe it live")
    record.add_argument("seconds", type=_positive_seconds, help="how long to record")
    record.add_argument(
        "--situation",
        default="call_headphones",
        choices=["call_headphones", "call_speakers", "in_person", "hybrid"],
    )
    record.add_argument("--mic", default=None, help="microphone index or name")
    record.add_argument("--data-dir", type=Path, default=None, help="keep all app data here")
    note = commands.add_parser("note", help="write a cited note for a recorded meeting")
    note.add_argument("meeting_id", nargs="?", default=None, help="meeting id (default: latest)")
    note.add_argument("--model", default=None, help="Ollama model (default: settings llm.model)")
    note.add_argument("--template", default=None, help="note template (default: the meeting's)")
    note.add_argument(
        "--think",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="let a thinking model think first (default: settings llm.think)",
    )
    note.add_argument("--data-dir", type=Path, default=None, help="keep all app data here")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        from evra.app import run_app  # keeps `evra --version` fast
        from evra.paths import resolve_paths

        return run_app(dev=args.dev, debug=args.debug, paths=resolve_paths(args.data_dir))
    if args.command == "capture-test":
        from evra.capture.capture_test import capture_test_command
        from evra.paths import resolve_paths

        return capture_test_command(args, resolve_paths(args.data_dir))
    if args.command == "record":
        from evra.paths import resolve_paths
        from evra.transcribe.record import record_command

        return record_command(args, resolve_paths(args.data_dir))
    if args.command in ("models", "transcribe"):
        from evra.paths import resolve_paths
        from evra.transcribe.cli import models_command, transcribe_command

        command = models_command if args.command == "models" else transcribe_command
        return command(args, resolve_paths(args.data_dir))
    if args.command == "note":
        from evra.notes.cli import note_command
        from evra.paths import resolve_paths

        return note_command(args, resolve_paths(args.data_dir))
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
