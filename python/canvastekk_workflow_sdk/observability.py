"""
Metrics & Observability

Opt-in observability support for node execution.
Provides structured metrics collection without hard dependencies on
any specific observability backend.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class NodeExecutionMetric:
    """A single execution metric record."""

    run_id: str
    node_id: str
    node_name: str
    status: str
    duration_ms: int
    error_type: str | None = None
    error_code: str | None = None
    token_usage: float = 0.0
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the metric to a JSON-friendly dictionary."""
        return {
            "run_id": self.run_id,
            "node_id": self.node_id,
            "node_name": self.node_name,
            "status": self.status,
            "duration_ms": self.duration_ms,
            "error_type": self.error_type,
            "error_code": self.error_code,
            "token_usage": self.token_usage,
            "timestamp": self.timestamp,
        }


class NodeExecutionMetricsCollector:
    """Collects execution metrics in-process.

    Usage:
        collector = NodeExecutionMetricsCollector()
        collector.record(metric)
        summary = collector.get_summary()
    """

    def __init__(self, max_records: int = 10000) -> None:
        """Initialize metrics collector.

        Args:
            max_records: Maximum number of metrics to keep (evicts oldest).
        """
        self._metrics: list[NodeExecutionMetric] = []
        self._max_records = max_records
        self._lock = threading.Lock()

    def record(self, metric: NodeExecutionMetric) -> None:
        """Append a metric, evicting the oldest entry when capacity is reached."""
        with self._lock:
            self._metrics.append(metric)
            if len(self._metrics) > self._max_records:
                self._metrics = self._metrics[-self._max_records :]

    def get_summary(self, last_n: int | None = None) -> dict[str, Any]:
        """Return aggregated statistics over the collected metrics.

        Args:
            last_n: If set, only consider the most recent *last_n* records.

        Returns:
            A dict with keys ``total_executions``, ``pass_count``,
            ``fail_count``, ``success_rate``, ``avg_duration_ms``,
            ``min_duration_ms``, ``max_duration_ms``, and
            ``total_token_usage``.  Returns ``{"total_executions": 0}``
            when no metrics have been recorded.
        """
        with self._lock:
            metrics = list(self._metrics[-last_n:]) if last_n else list(self._metrics)
        if not metrics:
            return {"total_executions": 0}

        pass_count = sum(1 for m in metrics if m.status == "pass")
        fail_count = sum(1 for m in metrics if m.status == "fail")
        durations = [m.duration_ms for m in metrics]

        return {
            "total_executions": len(metrics),
            "pass_count": pass_count,
            "fail_count": fail_count,
            "success_rate": pass_count / len(metrics) if metrics else 0.0,
            "avg_duration_ms": sum(durations) / len(durations),
            "min_duration_ms": min(durations),
            "max_duration_ms": max(durations),
            "total_token_usage": sum(m.token_usage for m in metrics),
        }

    def clear(self) -> None:
        """Remove all collected metrics."""
        with self._lock:
            self._metrics.clear()
