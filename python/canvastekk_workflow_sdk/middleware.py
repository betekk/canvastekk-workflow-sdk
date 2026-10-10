"""
Middleware System

Provides a plugin architecture for pre/post execute hooks.
Node authors can register middleware to add cross-cutting concerns
(logging, metrics, auth, etc.) without modifying core execution logic.

The starlette-backed ``SDKVersionMiddleware`` lives in
``_server_middleware`` (gated behind the ``[fastapi]`` extra).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from canvastekk_workflow_sdk.context import ExecutionContext

logger = logging.getLogger(__name__)


@runtime_checkable
class NodeMiddleware(Protocol):
    """Protocol for node execution middleware.

    Implement this protocol to add pre/post hooks around node execution.
    """

    def on_before_execute(
        self,
        inputs: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Called before execute(). Can modify inputs.

        Args:
            inputs: The validated inputs about to be passed to execute().
            context: The execution context.

        Returns:
            The (possibly modified) inputs dict.
        """
        return inputs

    def on_after_execute(
        self,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        """Called after successful execute().

        Args:
            inputs: The inputs that were passed to execute().
            outputs: The outputs returned by execute().
            context: The execution context.
            duration_ms: Execution time in milliseconds.
        """
        ...

    def on_error(
        self,
        inputs: dict[str, Any],
        error: Exception,
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        """Called when execute() raises an exception.

        Args:
            inputs: The inputs that were passed to execute().
            error: The exception raised by execute().
            context: The execution context.
            duration_ms: Execution time before failure.
        """
        ...


class LoggingMiddleware:
    """Middleware that logs execution lifecycle with correlation IDs."""

    def on_before_execute(
        self,
        inputs: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Log before node execution starts.

        Args:
            inputs: The validated inputs about to be passed to execute().
            context: The execution context.

        Returns:
            The inputs dict unchanged.
        """
        context.logger.info(
            f"[{context.run_id}] Executing node with {len(inputs)} input(s)",
            extra={"run_id": context.run_id, "node_id": context.node_id},
        )
        return inputs

    def on_after_execute(
        self,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        """Log after successful node execution.

        Args:
            inputs: The inputs that were passed to execute().
            outputs: The outputs returned by execute().
            context: The execution context.
            duration_ms: Execution time in milliseconds.
        """
        context.logger.info(
            f"[{context.run_id}] Completed in {duration_ms}ms with {len(outputs)} output(s)",
            extra={
                "run_id": context.run_id,
                "node_id": context.node_id,
                "duration_ms": duration_ms,
            },
        )

    def on_error(
        self,
        inputs: dict[str, Any],
        error: Exception,
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        """Log when execute() raises an exception.

        Args:
            inputs: The inputs that were passed to execute().
            error: The exception raised by execute().
            context: The execution context.
            duration_ms: Execution time before failure.
        """
        context.logger.error(
            f"[{context.run_id}] Failed after {duration_ms}ms: {error}",
            extra={
                "run_id": context.run_id,
                "node_id": context.node_id,
                "duration_ms": duration_ms,
                "error_type": type(error).__name__,
            },
        )


class TimingMiddleware:
    """Middleware that records execution timing as structured metadata."""

    def __init__(self) -> None:
        """Initialize timing middleware with empty timings list."""
        self._timings: list[dict[str, Any]] = []

    @property
    def timings(self) -> list[dict[str, Any]]:
        """Return list of recorded timing entries."""
        return self._timings

    def on_before_execute(
        self,
        inputs: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """No-op before execution.

        Args:
            inputs: The validated inputs about to be passed to execute().
            context: The execution context.

        Returns:
            The inputs dict unchanged.
        """
        return inputs

    def on_after_execute(
        self,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        """Record timing for successful execution.

        Args:
            inputs: The inputs that were passed to execute().
            outputs: The outputs returned by execute().
            context: The execution context.
            duration_ms: Execution time in milliseconds.
        """
        self._timings.append(
            {
                "run_id": context.run_id,
                "node_id": context.node_id,
                "duration_ms": duration_ms,
                "status": "pass",
            }
        )

    def on_error(
        self,
        inputs: dict[str, Any],
        error: Exception,
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        """Record timing for failed execution.

        Args:
            inputs: The inputs that were passed to execute().
            error: The exception raised by execute().
            context: The execution context.
            duration_ms: Execution time before failure.
        """
        self._timings.append(
            {
                "run_id": context.run_id,
                "node_id": context.node_id,
                "duration_ms": duration_ms,
                "status": "fail",
                "error_type": type(error).__name__,
            }
        )
