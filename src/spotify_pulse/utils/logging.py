"""Structured logging configuration for SpotifyPulse.

Provides JSON formatted output for production and container environments,
and colored/readable console formatting for local development.
"""

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize log record into a structured JSON string."""
        log_data: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception details if present
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        # Include custom extra attributes
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
                "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
                "created", "msecs", "relativeCreated", "thread", "threadName",
                "processName", "process", "message",
            }:
                log_data[key] = value

        return json.dumps(log_data)


def setup_logging(
    log_level: str = "INFO",
    json_format: bool = False,
    logger_name: str | None = None,
) -> None:
    """Initialize root or named logger with standard formatters.

    Args:
        log_level: Logging severity level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        json_format: Whether to format records as structured JSON.
        logger_name: Specific logger name to configure, or root logger if None.
    """
    logger = logging.getLogger(logger_name)
    level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Avoid duplicate handlers on re-initialization
    if logger.handlers:
        logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    if json_format:
        handler.setFormatter(JSONFormatter())
    else:
        standard_fmt = (
            "%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d - %(message)s"
        )
        handler.setFormatter(logging.Formatter(standard_fmt, datefmt="%Y-%m-%d %H:%M:%S"))

    logger.addHandler(handler)
    logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    """Retrieve a configured logger instance with the specified module name."""
    return logging.getLogger(name)
