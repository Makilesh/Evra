"""Structured JSON logs in rotating files, with meeting content redacted (BUILD.md §9.1)."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import structlog
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


def redact_content(_logger: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Replace meeting content with a marker unless this is a DEBUG call."""
    if method_name == "debug":
        return event_dict
    for key in CONTENT_KEYS.intersection(event_dict):
        event_dict[key] = REDACTED
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
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
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
