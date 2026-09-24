"""Structured JSON logs in rotating files, with meeting content redacted (BUILD.md §9.1).

Content rules for callers: pass meeting content only as keyword values (never inside the
event string), e.g. ``log.info("utterance_saved", text=utt.text)`` — values under
CONTENT_KEYS are redacted above DEBUG, at any nesting depth. Exception messages are
redacted above DEBUG too (type and frames are kept; local variables are never logged).
"""

from __future__ import annotations

import logging
import logging.handlers
import re
from pathlib import Path
from typing import Any

import structlog
from structlog.tracebacks import ExceptionDictTransformer
from structlog.typing import EventDict, Processor, WrappedLogger

HANDLER_NAME = "evra-file"
LOG_FILE_NAME = "evra.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 10
REDACTED = "[redacted]"
CONTENT_KEYS = frozenset(
    {
        "text",
        "transcript",
        "note",
        "notes",
        "document",
        "audio",
        "pcm",
        "content",
        "question",
        "answer",
        "prompt",
        "response",
    }
)
# Last line of a formatted traceback: "ValueError: message" -> keep only the type.
_TRACEBACK_TAIL = re.compile(r"^(?P<type>[A-Za-z_][\w.]*)(?::.*)?$")


def _is_debug(method_name: str, event_dict: EventDict) -> bool:
    return method_name == "debug" or event_dict.get("level") == "debug"


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: REDACTED if k in CONTENT_KEYS else _redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [_redact(v) for v in value]
    return value


def redact_content(_logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Replace meeting content (at any depth) with a marker unless this is a DEBUG call."""
    if _is_debug(method_name, event_dict):
        return event_dict
    for key, value in list(event_dict.items()):
        if key in CONTENT_KEYS:
            event_dict[key] = REDACTED
        elif key != "event":
            event_dict[key] = _redact(value)
    return event_dict


def redact_exception_messages(
    _logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Exception messages can quote content: keep type and frames, drop the message."""
    if _is_debug(method_name, event_dict):
        return event_dict
    for exc in event_dict.get("exception") or []:
        if isinstance(exc, dict) and "exc_value" in exc:
            exc["exc_value"] = REDACTED
    return event_dict


def scrub_traceback_text(
    _logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Third-party code (pywebview) logs pre-formatted tracebacks as the message itself."""
    event = event_dict.get("event")
    if _is_debug(method_name, event_dict) or not isinstance(event, str):
        return event_dict
    if "Traceback (most recent call last):" not in event:
        return event_dict
    lines = event.rstrip("\n").split("\n")
    match = _TRACEBACK_TAIL.match(lines[-1].strip())
    if match:
        lines[-1] = f"{match.group('type')}: {REDACTED}"
    event_dict["event"] = "\n".join(lines)
    return event_dict


def shutdown_logging() -> None:
    root = logging.getLogger()
    for handler in list(root.handlers):
        if handler.get_name() == HANDLER_NAME:
            root.removeHandler(handler)
            handler.close()


def configure_logging(log_dir: Path, *, debug: bool) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / LOG_FILE_NAME
    shutdown_logging()

    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
    ]
    handler = logging.handlers.RotatingFileHandler(
        log_file, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    handler.set_name(HANDLER_NAME)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            # stdlib / third-party records get the same redaction as our own events
            foreign_pre_chain=[*shared, redact_content, scrub_traceback_text],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.ExceptionRenderer(ExceptionDictTransformer(show_locals=False)),
                redact_exception_messages,
                structlog.processors.JSONRenderer(),
            ],
        )
    )
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            *shared,
            redact_content,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )
    return log_file
