"""Tests for structured logging configuration."""

import json
import logging

import pytest

from canvastekk_workflow_sdk.logging import (
    HumanReadableFormatter,
    StructuredJsonFormatter,
    configure_logging,
    get_node_logger,
)


class TestStructuredJsonFormatter:
    def test_basic_log_entry(self) -> None:
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="node.ff-1",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="processing started",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        entry = json.loads(output)
        assert entry["message"] == "processing started"
        assert entry["level"] == "INFO"
        assert entry["logger"] == "node.ff-1"
        assert "timestamp" in entry

    def test_includes_correlation_ids(self) -> None:
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="node.ff-1",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=None,
            exc_info=None,
        )
        record.run_id = "run-abc123"
        record.node_id = "ff-1"
        output = formatter.format(record)
        entry = json.loads(output)
        assert entry["run_id"] == "run-abc123"
        assert entry["node_id"] == "ff-1"

    def test_exception_included(self) -> None:
        formatter = StructuredJsonFormatter()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys

            exc_info = sys.exc_info()

        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="failed",
            args=None,
            exc_info=exc_info,
        )
        output = formatter.format(record)
        entry = json.loads(output)
        assert "exception" in entry
        assert "ValueError: boom" in entry["exception"]

    def test_non_serializable_handled(self) -> None:
        formatter = StructuredJsonFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="test",
            args=None,
            exc_info=None,
        )
        record._extra = {"data": b"bytes"}
        output = formatter.format(record)
        entry = json.loads(output)
        assert "data" in entry


class TestHumanReadableFormatter:
    def test_plain_text_output(self) -> None:
        formatter = HumanReadableFormatter()
        record = logging.LogRecord(
            name="node.ff-1",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="hello",
            args=None,
            exc_info=None,
        )
        output = formatter.format(record)
        assert "hello" in output
        assert "INFO" in output

    def test_run_id_included(self) -> None:
        formatter = HumanReadableFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="msg",
            args=None,
            exc_info=None,
        )
        record.run_id = "run-abc123def"
        output = formatter.format(record)
        assert "[run-abc1]" in output


class TestConfigureLogging:
    def test_default_is_info_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CANVASTEKK_LOG_LEVEL", raising=False)
        from canvastekk_workflow_sdk import logging as logging_mod

        assert logging_mod._get_env_log_level() == logging.INFO

    def test_env_overrides_level(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_LOG_LEVEL", "DEBUG")
        from canvastekk_workflow_sdk import logging as logging_mod

        assert logging_mod._get_env_log_level() == logging.DEBUG

    def test_env_format_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_LOG_FORMAT", "json")
        from canvastekk_workflow_sdk import logging as logging_mod

        assert logging_mod._get_env_log_format() == "json"

    def test_env_format_text(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_LOG_FORMAT", "text")
        from canvastekk_workflow_sdk import logging as logging_mod

        assert logging_mod._get_env_log_format() == "console"  # text is the console alias

    def test_env_format_default_is_console(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """DA-3359: console output is the default; json is opt-in."""
        monkeypatch.delenv("CANVASTEKK_LOG_FORMAT", raising=False)
        from canvastekk_workflow_sdk import logging as logging_mod

        assert logging_mod._get_env_log_format() == "console"
        monkeypatch.setenv("CANVASTEKK_LOG_FORMAT", "json")
        assert logging_mod._get_env_log_format() == "json"

    def test_configure_sets_handler(self) -> None:
        configure_logging(level=logging.DEBUG, fmt="text")
        logger = logging.getLogger("canvastekk_workflow_sdk")
        assert logger.level == logging.DEBUG


class TestGetNodeLogger:
    def test_returns_named_logger(self) -> None:
        logger = get_node_logger("ff-1")
        assert logger.name == "node.ff-1"

    def test_different_node_ids(self) -> None:
        a = get_node_logger("node-a")
        b = get_node_logger("node-b")
        assert a.name != b.name
