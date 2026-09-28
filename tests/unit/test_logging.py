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


def _raise_with_secret_local() -> None:
    secret_local = "top secret local"  # noqa: F841 - must never reach the log
    raise ValueError("secret words in exception")


def test_exception_logs_type_and_frames_but_not_message_or_locals(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=False)
    try:
        _raise_with_secret_local()
    except ValueError:
        structlog.get_logger("t").exception("job_failed", job="j1")
    [line] = _lines(log_file)
    [exc] = line["exception"]
    assert exc["exc_type"] == "ValueError"
    assert exc["exc_value"] == "[redacted]"
    assert exc["frames"]
    raw = log_file.read_text(encoding="utf-8")
    assert "secret words" not in raw
    assert "top secret local" not in raw


def test_debug_exception_keeps_message(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=True)
    try:
        raise ValueError("visible at debug")
    except ValueError:
        structlog.get_logger("t").debug("dbg", exc_info=True)
    [line] = _lines(log_file)
    assert line["exception"][0]["exc_value"] == "visible at debug"


def test_nested_content_is_redacted(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=False)
    structlog.get_logger("t").info(
        "saved", payload={"text": "secret one", "n": 1}, items=[{"note": "secret two"}]
    )
    [line] = _lines(log_file)
    assert line["payload"] == {"text": "[redacted]", "n": 1}
    assert line["items"] == [{"note": "[redacted]"}]


def test_stdlib_exception_records_are_redacted(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=False)
    try:
        raise RuntimeError("secret in third-party error")
    except RuntimeError:
        logging.getLogger("thirdparty").exception("call failed")
    [line] = _lines(log_file)
    assert line["exception"][0]["exc_type"] == "RuntimeError"
    assert "secret in third-party error" not in log_file.read_text(encoding="utf-8")


def test_pywebview_traceback_text_is_scrubbed(tmp_path: Path) -> None:
    log_file = configure_logging(tmp_path, debug=False)
    logging.getLogger("pywebview").error(
        'Traceback (most recent call last):\n  File "api.py", line 9, in ping\n'
        "ValueError: transcript secret\n"
    )
    [line] = _lines(log_file)
    assert "transcript secret" not in log_file.read_text(encoding="utf-8")
    assert "ValueError" in line["event"]
    assert 'File "api.py", line 9' in line["event"]
