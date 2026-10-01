"""
Structured Logging Configuration

Provides a JSON log formatter and environment-variable-driven configuration
so that node authors get production-ready logging out of the box in any
deployment environment (AWS Lambda, EC2, ECS, local dev).

Environment Variables:

    CANVASTEKK_LOG_LEVEL
        Log level for all SDK loggers.  Defaults to ``INFO``.
        Accepted values: ``DEBUG``, ``INFO``, ``WARNING``, ``ERROR``, ``CRITICAL``.

    CANVASTEKK_LOG_FORMAT
        Output format.  ``json`` (default) emits one JSON object per line —
        ideal for CloudWatch Logs, Datadog, ELK.  ``text`` emits human-
        readable lines for local development.

Usage:

    The SDK calls :func:`configure_logging` automatically at app startup.
    Node authors can also call it explicitly in tests or scripts::

        from canvastekk_workflow_sdk.logging import configure_logging

        configure_logging()  # reads CANVASTEKK_LOG_LEVEL / CANVASTEKK_LOG_FORMAT

    Inside ``execute()``::

        def execute(self, inputs, context):
            context.logger.info("processing started", extra={"file_count": 3})
            # → {"message":"processing started","level":"INFO","run_id":"...","node_id":"...","file_count":3}
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime
from typing import Any

_SDK_LOGGER_PREFIX = "canvastekk_workflow_sdk"
_NODE_LOGGER_PREFIX = "node."


def _get_env_log_level() -> int:
    raw = os.environ.get("CANVASTEKK_LOG_LEVEL", "INFO").upper()
    return getattr(logging, raw, logging.INFO)


def _get_env_log_format() -> str:
    """DA-3359: human/console output by default; ``json`` opts into one-line JSON.

    Accepts ``console`` (or the legacy ``text`` alias) and ``json``.
    """
    raw = os.environ.get("CANVASTEKK_LOG_FORMAT", "console").lower()
    return "json" if raw == "json" else "console"


class StructuredJsonFormatter(logging.Formatter):
    """Emit one JSON object per log line.

    Every log record is serialized as a JSON object with at least:

    - ``timestamp`` — ISO 8601 UTC
    - ``level`` — ``INFO``, ``ERROR``, etc.
    - ``logger`` — logger name (e.g. ``node.ff-1``)
    - ``message`` — the log message

    Any ``extra`` dict passed to the logger call is merged into the object.
    If the record has ``run_id`` / ``node_id`` attributes (set by the SDK
    middleware) they are included as top-level keys for correlation.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as a JSON object.

        Args:
            record: Log record to format.

        Returns:
            JSON string with timestamp, level, logger, message, and context.
        """
        entry: dict[str, Any] = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        if hasattr(record, "run_id"):
            entry["run_id"] = record.run_id
        if hasattr(record, "node_id"):
            entry["node_id"] = record.node_id

        # Merge extra={...} fields: stdlib logging sets them directly as
        # attributes on the record — copy any non-standard ones. Also honor
        # records constructed with an explicit `_extra` dict (legacy path).
        _standard = {
            "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
            "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "created", "msecs", "relativeCreated", "thread", "threadName",
            "processName", "process", "taskName", "message", "asctime",
        }
        for key, value in record.__dict__.items():
            if key == "_extra" and isinstance(value, dict):
                entry.update(value)
            elif key not in _standard and not key.startswith("_"):
                entry[key] = value

        if record.exc_info and record.exc_info[1] is not None:
            entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(entry, default=str)


class HumanReadableFormatter(logging.Formatter):
    """Plain-text formatter for local development.

    Includes ``run_id`` when present for correlation without JSON noise.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format a log record as human-readable text.

        Args:
            record: Log record to format.

        Returns:
            Formatted string with timestamp, level, logger, message.
        """
        ts = datetime.now(tz=UTC).strftime("%Y-%m-%d %H:%M:%S")
        base = f"{ts} [{record.levelname:>7}] {record.name}: {record.getMessage()}"

        run_id = getattr(record, "run_id", None)
        if run_id:
            base = f"[{run_id[:8]}] {base}"

        if record.exc_info and record.exc_info[1] is not None:
            base += "\n" + self.formatException(record.exc_info)

        return base


def _make_handler() -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    if _get_env_log_format() == "json":
        handler.setFormatter(StructuredJsonFormatter())
    else:
        handler.setFormatter(HumanReadableFormatter())
    return handler


def configure_logging(
    *,
    level: int | None = None,
    fmt: str | None = None,
) -> None:
    """Configure all SDK and node loggers.

    Reads ``CANVASTEKK_LOG_LEVEL`` and ``CANVASTEKK_LOG_FORMAT`` from the
    environment unless overridden by the explicit parameters.

    This is called automatically by :func:`create_node_app` at startup.
    Call it manually in tests or scripts if you need SDK logging outside
    the HTTP server.

    Args:
        level: Override log level (e.g. ``logging.DEBUG``).
            Defaults to ``CANVASTEKK_LOG_LEVEL`` env var or ``INFO``.
        fmt: Override format (``"json"`` or ``"console"``/``"text"``).
            Defaults to ``CANVASTEKK_LOG_FORMAT`` env var or ``"console"``.
    """
    actual_level = level if level is not None else _get_env_log_level()
    if fmt is not None:
        os.environ["CANVASTEKK_LOG_FORMAT"] = fmt

    handler = _make_handler()

    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) and getattr(h, "_sdk_configured", False) for h in root.handlers):
        handler._sdk_configured = True
        root.addHandler(handler)
        root.setLevel(actual_level)

    sdk_logger = logging.getLogger(_SDK_LOGGER_PREFIX)
    sdk_logger.setLevel(actual_level)

    node_logger = logging.getLogger(_NODE_LOGGER_PREFIX)
    node_logger.setLevel(actual_level)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def get_node_logger(node_id: str, run_id: str | None = None) -> logging.Logger:
    """Get a pre-configured logger for a node execution.

    Args:
        node_id: Node instance identifier.
        run_id: Workflow run identifier (included in structured logs).

    Returns:
        A ``logging.Logger`` named ``node.<node_id>``.
    """
    safe_id = node_id.replace(".", "_").replace(" ", "_")
    return logging.getLogger(f"{_NODE_LOGGER_PREFIX}{safe_id}")
