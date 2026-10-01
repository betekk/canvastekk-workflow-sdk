"""
Middleware System

Provides a plugin architecture for pre/post execute hooks.
Node authors can register middleware to add cross-cutting concerns
(logging, metrics, auth, etc.) without modifying core execution logic.

Also provides ``SDKVersionMiddleware`` which injects the ``X-SDK-Version``
response header on all HTTP responses.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

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


class SDKVersionMiddleware(BaseHTTPMiddleware):
    """Inject ``X-SDK-Version`` and ``X-Canvastekk-Node-Slug`` into responses.

    Industry-standard pattern (Stripe, AWS SDKs, Twilio) that enables
    engine-side version-aware routing and debugging without parsing
    the response body. DA-3359 adds the node slug beside the version
    header (still exactly one version header); the slug is present when
    the app factory knows its node (single-node apps).
    """

    def __init__(self, app: Any, node_slug: str | None = None) -> None:
        super().__init__(app)
        self._node_slug = node_slug

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Inject X-SDK-Version (and the node slug) into the response.

        Args:
            request: FastAPI request object.
            call_next: Next middleware/endpoint in chain.

        Returns:
            Response with X-SDK-Version header added.
        """
        response = await call_next(request)
        import canvastekk_workflow_sdk

        response.headers["X-SDK-Version"] = canvastekk_workflow_sdk.__version__
        if self._node_slug:
            response.headers["X-Canvastekk-Node-Slug"] = self._node_slug
        return response
