import json
import logging
from pathlib import Path
from typing import Any

import structlog

from evra.logging_setup import configure_logging


def _lines(log_file: Path) -> list[dict[str, Any]]:
    for handler in logging.getLogger().handlers:
        handler.flush()
    text = log_file.read_text(encoding="utf-8").strip()
    return [json.loads(line) for line in text.splitlines()] if text else []


def test_info_redacts_meeting_content(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=False)
    structlog.get_logger("t").info("utterance_saved", text="secret words", meeting_id="m1")
    [line] = _lines(log_file)
    assert line["event"] == "utterance_saved"
    assert line["text"] == "[redacted]"
    assert line["meeting_id"] == "m1"
    assert line["level"] == "info"
    assert "secret words" not in log_file.read_text(encoding="utf-8")


def test_debug_calls_keep_content_when_debug_enabled(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=True)
    structlog.get_logger("t").debug("asr_segment", text="hello there")
    [line] = _lines(log_file)
    assert line["text"] == "hello there"


def test_debug_calls_dropped_when_debug_disabled(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=False)
    structlog.get_logger("t").debug("asr_segment", text="hello there")
    assert _lines(log_file) == []


def test_reconfigure_does_not_duplicate_file_handlers(tmp_path: Path) -> None:
    configure_logging(tmp_path, debug=False)
    configure_logging(tmp_path, debug=False)
    names = [h.get_name() for h in logging.getLogger().handlers]
    assert names.count("evra-file") == 1
