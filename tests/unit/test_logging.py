"""Unit tests for structured logging."""

import json
import logging

from spotify_pulse.utils.logging import JSONFormatter, get_logger, setup_logging


def test_get_logger_returns_named_logger() -> None:
    """Test that get_logger returns a Logger with correct name."""
    logger = get_logger("spotify_pulse.test")
    assert isinstance(logger, logging.Logger)
    assert logger.name == "spotify_pulse.test"


def test_json_formatter_serializes_log_record() -> None:
    """Test that JSONFormatter outputs a valid JSON string with required keys."""
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="Test message %s",
        args=("formatted",),
        exc_info=None,
    )
    record.custom_field = "extra_value"

    output = formatter.format(record)
    parsed = json.loads(output)

    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "test_logger"
    assert parsed["message"] == "Test message formatted"
    assert parsed["line"] == 42
    assert parsed["custom_field"] == "extra_value"
    assert "timestamp" in parsed


def test_setup_logging_configures_logger() -> None:
    """Test setup_logging configures log level and stream handler."""
    logger_name = "test_custom_setup"
    setup_logging(log_level="DEBUG", json_format=True, logger_name=logger_name)
    logger = logging.getLogger(logger_name)

    assert logger.level == logging.DEBUG
    assert len(logger.handlers) == 1
    assert isinstance(logger.handlers[0].formatter, JSONFormatter)
