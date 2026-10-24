"""
Node Execution Response Model

This is the response returned from a node's /execute endpoint.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class NodeExecutionResponse(BaseModel):
    """
    Response payload from node execution.

    Returned by a node's POST /execute endpoint (sync) or
    POSTed to callback_url (async).
    """

    execution_id: str = Field(description="Unique ID for this execution (for cancellation)")
    status: Literal["pass", "fail"] = Field(description="Execution result status")
    outputs: dict[str, Any] | None = Field(
        default=None,
        description="Output values (if pass)",
    )
    token_usage: float = Field(
        default=0.0,
        ge=0.0,
        description="Actual tokens consumed",
    )
    duration_ms: int = Field(
        default=0,
        ge=0,
        description="Execution time in milliseconds",
    )
    error: str | None = Field(
        default=None,
        description="Error message (if fail)",
    )
    error_type: str | None = Field(
        default=None,
        description="Error class name (if fail)",
    )
    error_code: str | None = Field(
        default=None,
        description="Structured error code (e.g., TIMEOUT, VALIDATION_ERROR)",
    )
    dry_run: bool = Field(
        default=False,
        description=(
            "D10 (#111): true when this response is a validation-only dry "
            "run — inputs were fully validated, nothing executed, "
            "token_usage is 0, and execution_id carries the 'dryrun-' "
            "namespace. Always serialized (explicit semantics marker, not "
            "an optional extra)"
        ),
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "execution_id": "exec-xyz789",
                    "status": "pass",
                    "outputs": {"message": "Hello, World!", "timestamp": "2026-01-15T10:30:00+00:00"},
                    "token_usage": 0.0,
                    "duration_ms": 42,
                    "error": None,
                    "error_type": None,
                    "error_code": None,
                }
            ]
        }
    }

    @classmethod
    def success(
        cls,
        execution_id: str,
        outputs: dict[str, Any],
        duration_ms: int = 0,
        token_usage: float = 0.0,
        dry_run: bool = False,
    ) -> NodeExecutionResponse:
        """Create a successful execution response.

        Args:
            execution_id: Unique identifier for this execution.
            outputs: Output values matching the node's output_schema.
            duration_ms: Execution time in milliseconds.
            token_usage: Tokens consumed during execution.
            dry_run: D10 (#111) — mark this as a validation-only response.

        Returns:
            A :class:`NodeExecutionResponse` with ``status="pass"``.
        """
        return cls(
            execution_id=execution_id,
            status="pass",
            outputs=outputs,
            duration_ms=duration_ms,
            token_usage=token_usage,
            dry_run=dry_run,
        )

    @classmethod
    def failure(
        cls,
        execution_id: str,
        error: str,
        error_type: str | None = None,
        duration_ms: int = 0,
        error_code: str | None = None,
        dry_run: bool = False,
    ) -> NodeExecutionResponse:
        """Create a failed execution response.

        Args:
            execution_id: Unique identifier for this execution.
            error: Human-readable error message.
            error_type: Exception class name (e.g. ``"NodeTimeoutError"``).
            duration_ms: Execution time before failure.
            error_code: Structured error code (e.g. ``"TIMEOUT"``).
            dry_run: D10 (#111) — mark this as a dry-run refusal
                (``"DRY_RUN_NOT_SUPPORTED"``).

        Returns:
            A :class:`NodeExecutionResponse` with ``status="fail"``.
        """
        return cls(
            execution_id=execution_id,
            status="fail",
            outputs=None,
            error=error,
            error_type=error_type,
            duration_ms=duration_ms,
            error_code=error_code,
            dry_run=dry_run,
        )


class MultiNodeHealthResponse(BaseModel):
    """Response from the multi-node application's root /health endpoint."""

    status: Literal["healthy"] = Field(description="Aggregate health status")
    nodes: list[str] = Field(description="URL prefixes of the mounted node sub-applications")


class LivenessResponse(BaseModel):
    """Response from /live."""

    status: Literal["alive"] = Field(description="Liveness marker")


class ReadinessResponse(BaseModel):
    """Response from /ready — 200 and 503 bodies share this shape."""

    status: Literal["ready", "not_ready"] = Field(description="Readiness state")
    node_id: str = Field(description="Node identifier")
    checks: dict[str, bool] = Field(
        default_factory=dict,
        description="Individual health check results",
    )


class MetricsSummaryResponse(BaseModel):
    """Response from /metrics — aggregated execution statistics.

    Only ``total_executions`` is always present; the remaining fields
    appear once at least one execution has been recorded.
    """

    total_executions: int = Field(description="Total executions recorded")
    pass_count: int | None = Field(default=None, description="Successful executions")
    fail_count: int | None = Field(default=None, description="Failed executions")
    success_rate: float | None = Field(default=None, description="Pass fraction 0.0-1.0")
    avg_duration_ms: float | None = Field(default=None, description="Mean execution duration")
    min_duration_ms: float | None = Field(default=None, description="Fastest execution duration")
    max_duration_ms: float | None = Field(default=None, description="Slowest execution duration")
    total_token_usage: dict[str, int] | None = Field(default=None, description="Token usage totals by kind")


class HealthResponse(BaseModel):
    """Response from /health endpoint."""

    status: Literal["healthy", "unhealthy", "degraded"] = Field(
        description="Health status",
    )
    node_id: str = Field(description="Node identifier with version")
    version: str = Field(description="Node version")
    checks: dict[str, bool] = Field(
        default_factory=dict,
        description="Individual health check results",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "status": "healthy",
                    "node_id": "echo-v1.0.0",
                    "version": "1.0.0",
                    "checks": {},
                }
            ]
        }
    }
