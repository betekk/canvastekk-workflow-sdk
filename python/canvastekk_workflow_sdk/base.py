"""
Base Node Class

The abstract base class that all nodes must inherit from.
Provides the interface for node execution.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx
import jsonschema

from canvastekk_workflow_sdk._url import (
    DEFAULT_MAX_DOWNLOAD_BYTES,
    MAX_REDIRECT_HOPS,
    UrlPolicyError,
    validate_external_url,
)
from canvastekk_workflow_sdk.context import ExecutionContext, execution_context_var
from canvastekk_workflow_sdk.definition import WorkflowNodeManifest
from canvastekk_workflow_sdk.exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    NodeIOError,
    NodeOutputValidationError,
    NodeTimeoutError,
    NodeValidationError,
)
from canvastekk_workflow_sdk.middleware import LoggingMiddleware, NodeMiddleware
from canvastekk_workflow_sdk.observability import ExecutionMetric, MetricsCollector
from canvastekk_workflow_sdk.request import NodeExecutionRequest
from canvastekk_workflow_sdk.response import NodeExecutionResponse

logger = logging.getLogger(__name__)

# Per-connect/read/write operation timeout for httpx. The TOTAL download
# deadline (``_download_deadline``) is enforced separately in the chunk loop
# because httpx timeouts are per-operation and never trip on slow-drip streams.
_HTTPX_DOWNLOAD_TIMEOUT = 30.0

# Fraction of the node's timeout_seconds reserved for execute() after all
# file downloads complete; downloads share the remainder of the budget.
_DOWNLOAD_BUDGET_FRACTION = 0.8


def _download_deadline(timeout_seconds: int | None, started: float | None = None) -> float:
    """Return a monotonic-clock deadline for all file-input downloads.

    The deadline is a fraction of the node's ``timeout_seconds`` (never
    below 30 s, matching the pre-existing fixed behavior), measured from
    ``started`` (defaults to now).
    """
    budget = (timeout_seconds or 30) * _DOWNLOAD_BUDGET_FRACTION
    budget = max(budget, 30.0)
    start = started if started is not None else time.monotonic()
    return start + budget


class BaseNode(ABC):
    """
    Abstract base class for all nodes.

    Subclasses must:
    1. Define a `definition` class attribute with WorkflowNodeManifest
    2. Implement the `execute()` method

    Example:
        class EchoNode(BaseNode):
            definition = WorkflowNodeManifest(
                name="echo",
                version="1.0.0",
                title="Echo",
                description="Returns input unchanged",
                input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
                output_schema={"type": "object", "properties": {"message": {"type": "string"}}},
            )

            def execute(self, inputs: dict, context: ExecutionContext) -> dict:
                return {"message": inputs.get("message", "")}
    """

    definition: WorkflowNodeManifest

    def __init__(self) -> None:
        """Initialize the base node with default middleware and metrics collector."""
        self._middleware: list[NodeMiddleware] = [LoggingMiddleware()]
        self._metrics_collector: MetricsCollector = MetricsCollector()

    def add_middleware(self, middleware: NodeMiddleware) -> BaseNode:
        """Register a middleware instance. Returns self for chaining.

        Args:
            middleware: A NodeMiddleware implementation.

        Returns:
            self for fluent chaining.
        """
        self._middleware.append(middleware)
        return self

    def set_metrics_collector(self, collector: MetricsCollector) -> BaseNode:
        """Set a custom metrics collector. Returns self for chaining.

        Args:
            collector: A MetricsCollector instance.

        Returns:
            self for fluent chaining.
        """
        self._metrics_collector = collector
        return self

    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Validate that subclasses define required attributes."""
        super().__init_subclass__(**kwargs)
        # Skip validation for abstract classes
        if ABC in cls.__bases__:
            return
        if not hasattr(cls, "definition") or cls.definition is None:
            raise TypeError(f"{cls.__name__} must define a 'definition' class attribute")

    @abstractmethod
    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        """
        Execute the node's business logic.

        This is the only method node authors need to implement.

        Args:
            inputs: Input values (already validated against input_schema).
                    File inputs (``format: "file"``) are automatically downloaded
                    by the SDK before this method is called. Values are local file
                    paths (str). If the input was already a local path, it passes
                    through unchanged.
            context: Execution context providing run_id, node_id, output_dir,
                     downloads_dir, metadata, logger, etc.

        Returns:
            Output dict matching output_schema. File outputs should be paths
            to files in context.output_dir (SDK will upload them).

        Raises:
            Any exception will be caught by the SDK and returned as a failure response.
        """
        ...

    def _validate_inputs(self, inputs: dict[str, Any]) -> None:
        """Validate inputs against the node's input_schema.

        Args:
            inputs: The inputs dict to validate.

        Raises:
            NodeValidationError: If inputs do not match input_schema.
        """
        schema = self.definition.input_schema
        if not schema or schema == {"type": "object"}:
            return

        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(inputs), key=lambda e: list(e.path))
        if errors:
            error_details = [
                {
                    "path": list(e.path),
                    "message": e.message,
                    "validator": e.validator,
                }
                for e in errors
            ]
            raise NodeValidationError(
                f"Input validation failed: {errors[0].message}",
                errors=error_details,
            )

    def _validate_outputs(self, outputs: dict[str, Any]) -> None:
        """Validate outputs against the node's output_schema.

        Args:
            outputs: The outputs dict to validate.

        Raises:
            NodeOutputValidationError: If outputs do not match output_schema.
        """
        schema = self.definition.output_schema
        if not schema or schema == {"type": "object"}:
            return

        validator = jsonschema.Draft7Validator(schema)
        errors = sorted(validator.iter_errors(outputs), key=lambda e: list(e.path))
        if errors:
            error_details = [
                {
                    "path": list(e.path),
                    "message": e.message,
                    "validator": e.validator,
                }
                for e in errors
            ]
            raise NodeOutputValidationError(
                f"Output validation failed: {errors[0].message}",
                errors=error_details,
            )

    @staticmethod
    def _sanitize_filename(raw_name: str) -> str:
        """Strip directory components and path traversal from a filename."""
        return Path(raw_name).name

    @staticmethod
    def _extract_filename(url: str, content_disposition: str | None = None) -> str:
        """Extract a sanitized filename from Content-Disposition or URL path."""
        if content_disposition:
            for part in content_disposition.split(";"):
                part = part.strip()
                if part.lower().startswith("filename="):
                    raw = part.split("=", 1)[1].strip().strip('"').strip("'")
                    if raw:
                        return BaseNode._sanitize_filename(raw)

        parsed = urlparse(url)
        path = parsed.path
        if path:
            raw = path.rstrip("/").rsplit("/", 1)[-1]
            if raw:
                return BaseNode._sanitize_filename(raw)

        return "download"

    def _max_download_bytes(self, field_name: str) -> int:
        """Return the effective byte cap for a file-input field.

        Prefers the manifest ``x-maxSizeBytes`` extension; falls back to the
        ``CANVASTEKK_MAX_DOWNLOAD_BYTES`` env override, then to the 10 GiB
        default. The cap is enforced mid-stream by ``_download_one``.
        """
        schema = self.definition.input_schema.get("properties", {}).get(field_name, {})
        declared = schema.get("x-maxSizeBytes")
        if isinstance(declared, int) and declared > 0:
            return declared
        env_raw = os.environ.get("CANVASTEKK_MAX_DOWNLOAD_BYTES")
        if env_raw:
            try:
                env_cap = int(env_raw)
                if env_cap > 0:
                    return env_cap
            except ValueError:
                logger.warning("Invalid CANVASTEKK_MAX_DOWNLOAD_BYTES value %r ignored", env_raw)
        return DEFAULT_MAX_DOWNLOAD_BYTES

    def _download_one(
        self,
        field_name: str,
        url: str,
        context: ExecutionContext,
    ) -> Path:
        """Download a single presigned URL to the downloads dir.

        Enforces the SSRF URL policy on every request and redirect hop,
        a mid-stream byte cap, a total download deadline, and cleans up
        partial files on any failure.

        Returns the local path of the completed download.
        """
        max_bytes = self._max_download_bytes(field_name)
        deadline = _download_deadline(self.definition.timeout_seconds)
        cancel_event = getattr(context, "cancel_event", None)

        current_url = validate_external_url(url)
        filename = f"{field_name}_{self._extract_filename(current_url)}"

        hops = 0
        try:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise NodeIOError(f"Download for field '{field_name}' was cancelled")

                try:
                    resp = httpx.get(
                        current_url,
                        timeout=_HTTPX_DOWNLOAD_TIMEOUT,
                        follow_redirects=False,
                    )
                except httpx.TimeoutException as exc:
                    raise NodeIOError(f"Timeout downloading file for field '{field_name}': {exc}") from exc
                except httpx.HTTPError as exc:
                    raise NodeIOError(f"Failed to download file for field '{field_name}': {exc}") from exc

                if resp.status_code in (301, 302, 303, 307, 308):
                    hops += 1
                    if hops > MAX_REDIRECT_HOPS:
                        raise NodeIOError(f"Too many redirects downloading file for field '{field_name}'")
                    next_url = resp.headers.get("location")
                    if not next_url:
                        raise NodeIOError(f"Redirect without Location header downloading file for field '{field_name}'")
                    current_url = validate_external_url(
                        next_url if "://" in next_url else str(urljoin(current_url, next_url))
                    )
                    filename = f"{field_name}_{self._extract_filename(current_url)}"
                    continue

                if resp.status_code >= 400:
                    raise NodeIOError(f"HTTP {resp.status_code} downloading file for field '{field_name}'")

                local_path = context.downloads_dir / filename

                content_disposition = resp.headers.get("content-disposition")
                if content_disposition:
                    filename = f"{field_name}_{self._extract_filename(current_url, content_disposition)}"
                    local_path = context.downloads_dir / filename

                content_length = resp.headers.get("content-length")
                if content_length and content_length.isdigit():
                    if int(content_length) > max_bytes:
                        raise NodeIOError(
                            f"File for field '{field_name}' exceeds size cap ({content_length} > {max_bytes} bytes)"
                        )

                try:
                    with open(local_path, "wb") as f:
                        running = 0
                        for chunk in resp.iter_bytes(chunk_size=65536):
                            if cancel_event is not None and cancel_event.is_set():
                                raise NodeIOError(f"Download for field '{field_name}' was cancelled")
                            running += len(chunk)
                            if running > max_bytes:
                                raise NodeIOError(
                                    f"File for field '{field_name}' exceeds size cap ({running} > {max_bytes} bytes)"
                                )
                            if time.monotonic() > deadline:
                                raise NodeIOError(f"Download deadline exceeded for field '{field_name}'")
                            f.write(chunk)
                except BaseException:
                    local_path.unlink(missing_ok=True)
                    raise
                return local_path
        except UrlPolicyError as exc:
            raise NodeIOError(f"Blocked URL for field '{field_name}': {exc}") from exc

    def _prepare_file_inputs(
        self,
        inputs: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Download presigned URL file inputs and replace with local paths.

        Built-in pipeline step in ``run()`` — not a middleware. Iterates
        ``definition.file_input_fields``, downloads any URL values to
        ``context.downloads_dir``, validates them, and stores metadata
        in ``context.metadata``.

        Args:
            inputs: Copy of request inputs (already validated).
            context: Execution context.

        Returns:
            Modified inputs dict with URLs replaced by local paths.

        Raises:
            NodeIOError: If a download fails.
        """
        downloaded: list[Path] = []

        try:
            for field_name in self.definition.file_input_fields:
                value = inputs.get(field_name)

                if value is None or not isinstance(value, str) or not value.strip():
                    continue

                if not value.startswith(("http://", "https://")):
                    continue

                context.report_progress(0.05, f"Downloading {field_name}")

                local_path = self._download_one(field_name, value, context)
                downloaded.append(local_path)

                self.definition.validate_file_input(field_name, local_path)

                file_size = local_path.stat().st_size

                context.metadata[field_name] = {
                    "original_url": value,
                    "local_path": str(local_path),
                    "size_bytes": file_size,
                }

                inputs[field_name] = str(local_path)
                context.report_progress(0.1, f"Downloaded {field_name} ({file_size} bytes)")

        except Exception:
            for path in downloaded:
                path.unlink(missing_ok=True)
            raise

        return inputs

    def _set_cancel_event(self, event: threading.Event | None) -> None:
        """Set a cooperative cancellation event propagated to the execution context.

        Called by the app server before ``run()`` so that a timed-out
        request can stop in-flight file downloads. ``execute()`` itself
        cannot be interrupted.
        """
        self._cancel_event = event

    def _check_deprecation_lifecycle(self) -> None:
        """Enforce the manifest's deprecation lifecycle (DA-2305).

        Warns on every execution of a deprecated node (naming the
        replacement) and refuses execution once ``sunset_date`` has passed.

        Raises:
            NodeConfigurationError: When the node's ``sunset_date`` is in
                the past — the node has been sunset and must not run.
        """
        dep = self.definition.deprecation
        if dep is None:
            return
        replacement = dep.replacement_slug or "unspecified"
        if dep.sunset_date is not None and datetime.now(UTC).date() > dep.sunset_date:
            raise NodeConfigurationError(
                f"Node '{self.definition.slug}' was sunset on {dep.sunset_date.isoformat()} "
                f"and refuses to run; migrate to '{replacement}' ({dep.notice})"
            )
        logger.warning(
            "Node '%s' is deprecated (since %s): %s — migrate to '%s'",
            self.definition.slug,
            dep.deprecated_at.isoformat() if dep.deprecated_at else "unknown date",
            dep.notice,
            replacement,
        )

    def report_progress(self, percent: float | None = None, message: str = "") -> None:
        """
        Report mid-run progress to the workflow engine (DA-3230).

        Fire-and-forget POST to the engine's progress route
        (``{callback_url}/progress``, engine #495) carrying this run's
        ``execution_id``. Best-effort — transport failures are swallowed
        and logged, never raised into node logic (same philosophy as
        DA-2887 telemetry). Safe no-op outside a workflow run (local dev)
        or when the request carries no callback URL: nothing is sent,
        nothing raises.

        Call from inside ``execute()``::

            self.report_progress(50, "still calculating")

        Node-app shared chokepoints (``load_context``, ``ErrorOutputNode``
        subclasses, ``to_node_output`` callers) reach this through the
        unchanged ``execute(inputs, context)`` seam — no per-node wiring
        needed beyond the SDK bump.

        Args:
            percent: Progress percentage 0–100 (clamped). ``None`` sends a
                liveness-only ping (percent 0).
            message: Optional human-readable status; capped at 1000 chars.
        """
        ctx = execution_context_var.get()
        if ctx is None:
            return
        ctx.report_progress((percent if percent is not None else 0) / 100, message)

    def run(self, request: NodeExecutionRequest) -> NodeExecutionResponse:
        """
        Run the node with full error handling, validation, and timing.

        This is called by the HTTP endpoint handler. It:
        1. Validates inputs against input_schema
        2. Creates execution context
        3. Auto-downloads file inputs (built-in pipeline step)
        4. Runs middleware on_before_execute hooks
        5. Calls execute() with timing and timeout enforcement
        6. Runs middleware on_after_execute / on_error hooks
        7. Records metrics
        8. Returns success or failure response

        Args:
            request: The execution request from orchestrator

        Returns:
            NodeExecutionResponse with pass/fail status
        """
        execution_id = str(uuid.uuid4())
        start_time = time.perf_counter()

        try:
            self._check_deprecation_lifecycle()

            self._validate_inputs(request.inputs)

            context = ExecutionContext(
                request,
                cancel_event=getattr(self, "_cancel_event", None),
                execution_id=execution_id,
            )

            # Ambient context for BaseNode.report_progress() during this run
            # (DA-3230) — visible in this thread and inside asyncio.to_thread
            # workers; the Token reset guarantees no leakage across reused
            # executor threads even when execute() raises.
            token = execution_context_var.set(context)
            try:
                inputs = dict(request.inputs)

                if self.definition.has_file_inputs:
                    inputs = self._prepare_file_inputs(inputs, context)

                for mw in self._middleware:
                    inputs = mw.on_before_execute(inputs, context)

                outputs = self.execute(inputs, context)

                self._validate_outputs(outputs)

                duration_ms = int((time.perf_counter() - start_time) * 1000)

                for mw in self._middleware:
                    mw.on_after_execute(inputs, outputs, context, duration_ms)

                token_usage = context.token_usage.get("total_tokens") or self.definition.token_cost

                self._metrics_collector.record(
                    ExecutionMetric(
                        run_id=context.run_id,
                        node_id=context.node_id,
                        node_name=self.definition.slug,
                        status="pass",
                        duration_ms=duration_ms,
                        token_usage=token_usage,
                    )
                )

                return NodeExecutionResponse.success(
                    execution_id=execution_id,
                    outputs=outputs,
                    duration_ms=duration_ms,
                    token_usage=token_usage,
                )
            finally:
                execution_context_var.reset(token)

        except NodeTimeoutError as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._record_error(request, e, duration_ms)
            return NodeExecutionResponse.failure(
                execution_id=execution_id,
                error=e.message,
                error_type=type(e).__name__,
                duration_ms=duration_ms,
                error_code=e.error_code,
            )

        except NodeValidationError as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._record_error(request, e, duration_ms)
            return NodeExecutionResponse.failure(
                execution_id=execution_id,
                error=e.message,
                error_type=type(e).__name__,
                duration_ms=duration_ms,
                error_code=e.error_code,
            )

        except NodeIOError as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._record_error(request, e, duration_ms)
            return NodeExecutionResponse.failure(
                execution_id=execution_id,
                error=e.message,
                error_type=type(e).__name__,
                duration_ms=duration_ms,
                error_code=e.error_code,
            )

        except NodeOutputValidationError as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._record_error(request, e, duration_ms)
            return NodeExecutionResponse.failure(
                execution_id=execution_id,
                error=e.message,
                error_type=type(e).__name__,
                duration_ms=duration_ms,
                error_code=e.error_code,
            )

        except NodeExecutionError as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._record_error(request, e, duration_ms)
            return NodeExecutionResponse.failure(
                execution_id=execution_id,
                error=e.message,
                error_type=type(e).__name__,
                duration_ms=duration_ms,
                error_code=e.error_code,
            )

        except Exception as e:
            duration_ms = int((time.perf_counter() - start_time) * 1000)
            self._record_error(request, e, duration_ms)
            return NodeExecutionResponse.failure(
                execution_id=execution_id,
                error=str(e),
                error_type=type(e).__name__,
                duration_ms=duration_ms,
            )

    def _record_error(
        self,
        request: NodeExecutionRequest,
        error: Exception,
        duration_ms: int,
    ) -> None:
        context = ExecutionContext(request)
        for mw in self._middleware:
            mw.on_error(request.inputs, error, context, duration_ms)

        error_code = getattr(error, "error_code", None)
        self._metrics_collector.record(
            ExecutionMetric(
                run_id=request.run_id,
                node_id=request.node_id,
                node_name=self.definition.slug,
                status="fail",
                duration_ms=duration_ms,
                error_type=type(error).__name__,
                error_code=error_code,
            )
        )

    def health_check(self) -> dict[str, Any]:
        """
        Perform health check for this node.

        Override this method to add custom health checks (e.g., model loaded,
        storage accessible, GPU available).

        Returns:
            Dict with check names as keys and bool results as values.
        """
        return {}

    def hook(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        """
        Handle webhook/callback payloads.

        Override this method to handle async completion notifications,
        progress updates, or external triggers. The default implementation
        returns None, which the /hook endpoint translates to 501 Not Implemented.

        Args:
            payload: The JSON body from the POST /hook request.

        Returns:
            A dict response to send back, or None if hooks are not supported.
        """
        return None

    async def on_startup(self) -> None:
        """
        Hook called when the FastAPI app starts up.

        Override to perform initialization (e.g., load models, warm caches,
        establish connections). Runs once at server startup.

        Default is a no-op.
        """

    async def on_shutdown(self) -> None:
        """
        Hook called when the FastAPI app shuts down.

        Override to perform cleanup (e.g., close connections, flush buffers,
        release resources). Runs once at server shutdown.

        Default is a no-op.
        """

    @asynccontextmanager
    async def _lifespan(self) -> AsyncIterator[None]:
        """FastAPI lifespan context manager wired to on_startup/on_shutdown."""
        await self.on_startup()
        try:
            yield
        finally:
            await self.on_shutdown()

    def create_app(self, **kwargs: Any) -> Any:
        """
        Create a FastAPI app with all required endpoints.

        This is a convenience method that wraps the node in an HTTP server.
        For more control, use the `create_node_app` function from app.py.

        Args:
            **kwargs: Keyword arguments passed to ``create_node_app()``
                (e.g., ``dependencies``, ``extra_routes``, FastAPI kwargs).

        Returns:
            FastAPI application instance
        """
        from canvastekk_workflow_sdk.app import create_node_app

        return create_node_app(self, **kwargs)
