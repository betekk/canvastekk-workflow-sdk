"""
FastAPI App Factory

Creates a FastAPI application with standard node endpoints:
- POST /execute - Run the node
- GET /health - Health check
- GET /manifest - Node self-description
- POST /hook - Webhook/callback handler (stub, 501 by default)
"""

from __future__ import annotations

import asyncio
import gc
import hashlib
import inspect
import logging
import os
import re
import shutil
import sys
import threading
from collections.abc import Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from canvastekk_workflow_sdk._url import is_dev_mode as _is_dev_mode
from canvastekk_workflow_sdk.auth import NodeAuth, _AuthBackend
from canvastekk_workflow_sdk.exceptions import NodeExecutionError, NodeTimeoutError, get_http_status_for_error
from canvastekk_workflow_sdk.logging import configure_logging
from canvastekk_workflow_sdk.middleware import SDKVersionMiddleware
from canvastekk_workflow_sdk.request import NodeExecutionRequest
from canvastekk_workflow_sdk.response import HealthResponse, NodeExecutionResponse
from canvastekk_workflow_sdk.uploads import UploadTarget, get_default_uploader

# Registry of cancel events for in-flight timed executions (cooperative
# cancellation — see BaseNode._set_cancel_event / context.cancel_event).
_ACTIVE_CANCELS: dict[str, threading.Event] = {}

# DA-2242: canonical X-Account-Id values (the engine sends str(int)).
# ASCII-only: canonical str(int) never contains non-ASCII digits.
_ACCOUNT_ID_RE = re.compile(r"^[0-9]+$")

# 2**63 - 1 is 19 digits — longer strings are provably out of range and are
# rejected before int() so absurdly long headers can't trip CPython's
# CVE-2020-10735 digit-conversion limit (ValueError → unhandled 500).
_ACCOUNT_ID_MAX_DIGITS = 19

# Default request body limit — parity with the TypeScript SDK's 50 MB
# express.json limit. Override with CANVASTEKK_MAX_BODY_BYTES.
DEFAULT_MAX_BODY_BYTES = 50 * 1024 * 1024

# DA-3009: memoized glibc handle for the post-execution heap trim. None is
# cached after the first resolve on platforms without malloc_trim (musl,
# non-linux) so the lookup cost is paid at most once per process.
_LIBC_HANDLE: Any = None
_LIBC_RESOLVED = False


def _release_freed_heap() -> None:
    """Return freed glibc heap to the OS after each execution (DA-3009).

    Python frees objects but glibc keeps the heap mapped, so a warm Lambda
    sandbox's RSS stays at the high-water mark of its heaviest invocation.
    Subsequent invocations in that sandbox then run under kernel reclaim
    pressure (observed in dev: ~100x slower I/O, ~15x slower compute, and a
    900s activity timeout on work that takes ~40s on a healthy sandbox).
    ``gc.collect()`` + ``malloc_trim(0)`` returns the freed heap once per
    execution. Silent no-op off glibc;
    ``CANVASTEKK_SDK_MEMORY_TRIM=0`` opts out.

    The unlocked module-global memoization below is deliberately race-tolerant:
    worst case under concurrent first executions is one redundant dlopen or
    one invocation skipping its trim — both self-heal on the next call.
    """
    global _LIBC_HANDLE, _LIBC_RESOLVED
    if os.environ.get("CANVASTEKK_SDK_MEMORY_TRIM", "1").strip().lower() in {"0", "false", "no"}:
        return
    if sys.platform != "linux":
        return
    if not _LIBC_RESOLVED:
        _LIBC_RESOLVED = True
        try:
            import ctypes
            import ctypes.util

            name = ctypes.util.find_library("c") or "libc.so.6"
            handle: Any = ctypes.CDLL(name)
            if not hasattr(handle, "malloc_trim"):
                handle = None
        except Exception:  # defensive — exotic platforms must never 500
            handle = None
        _LIBC_HANDLE = handle
    if _LIBC_HANDLE is None:
        return
    try:
        gc.collect()
        _LIBC_HANDLE.malloc_trim(0)
    except Exception:
        logging.getLogger(__name__).debug("Post-execution heap trim skipped", exc_info=True)


class _BodySizeLimitMiddleware:  # ASGI middleware (Starlette style)
    """Reject request bodies larger than CANVASTEKK_MAX_BODY_BYTES (413).

    Applies to every JSON endpoint (``/execute``, ``/hook``) — mirrors the
    TS SDK's global ``express.json({ limit: "50mb" })`` behavior.
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        try:
            max_bytes = int(os.environ.get("CANVASTEKK_MAX_BODY_BYTES", DEFAULT_MAX_BODY_BYTES))
        except ValueError:
            max_bytes = DEFAULT_MAX_BODY_BYTES

        from starlette.responses import JSONResponse as JsonResponseBody

        content_length = 0
        for header_name, header_value in scope.get("headers", []):
            if header_name == b"content-length":
                try:
                    content_length = int(header_value)
                except ValueError:
                    content_length = 0
                break

        if content_length > max_bytes:
            response = JsonResponseBody(
                status_code=413,
                content={"detail": f"Request body exceeds limit ({max_bytes} bytes)"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


if TYPE_CHECKING:
    from canvastekk_workflow_sdk.base import BaseNode

logger = logging.getLogger(__name__)


def _upload_outputs_to_s3(
    response: NodeExecutionResponse,
    upload_urls: dict[str, UploadTarget],
    file_output_fields: list[str],
) -> None:
    """Upload file outputs via engine upload targets (DA-2886).

    Delegates to the default ``S3PresignedUploader`` instance.

    Args:
        response: The node execution response containing output values.
        upload_urls: Mapping of output field name to upload target
            (multipart session descriptor; a legacy string target
            raises :class:`NodeIOError`).
        file_output_fields: Output field names that produce files.
    """
    get_default_uploader().upload_outputs(response, upload_urls, file_output_fields)


_NODE_OPENAPI_TAGS: list[dict[str, str]] = [
    {"name": "Execution", "description": "Run a node with given inputs and receive structured output."},
    {"name": "Health", "description": "Check node health and readiness."},
    {"name": "Discovery", "description": "Retrieve node metadata, schemas, and self-description."},
    {"name": "Callbacks", "description": "Webhook and async callback endpoints."},
    {"name": "Observability", "description": "Execution metrics and telemetry."},
]


def create_node_app(
    node: BaseNode,
    *,
    dependencies: Sequence[Any] | None = None,
    extra_routes: list[APIRouter] | None = None,
    auth: _AuthBackend | Literal["api-key"] | None = None,
    **fastapi_kwargs: Any,
) -> FastAPI:
    """
    Create a FastAPI application with standard node endpoints.

    DA-3359: raises once the SDK's support horizon has passed (break-glass:
    ``CANVASTEKK_SDK_ALLOW_UNSUPPORTED=1``).

    This function creates an HTTP server that implements the node contract:
    - POST /execute - Execute the node with given inputs
    - GET /health - Return node health status
    - GET /manifest - Return node's self-description (WorkflowNodeManifest)
    - POST /hook - Webhook/callback handler

    Args:
        node: The BaseNode instance to wrap
        dependencies: Optional FastAPI dependencies applied to all endpoints
            (e.g., ``[Depends(custom_dep)]`` for custom request-scoped logic).
        extra_routes: Optional list of FastAPI APIRouter instances to mount
            on the application.
        auth: Optional authentication for all endpoints (DA-1890 adoption):
            ``"api-key"`` constructs ``NodeAuth.api_key()`` (reads
            ``CANVASTEKK_API_KEY``); any backend built by the
            :class:`NodeAuth` factories (e.g. ``NodeAuth.api_key()``,
            ``NodeAuth.jwt(...)``) is used directly; ``None`` (default)
            leaves authentication unconfigured.
            When ``dependencies`` already contains an auth backend, the
            ``auth`` argument is skipped with a warning.
        **fastapi_kwargs: Additional arguments passed to FastAPI constructor
            (e.g., title, version, docs_url)

    Returns:
        FastAPI application instance

    Example:
        node = EchoNode()
        app = create_node_app(node, auth="api-key")

        # Or with a fully configured backend:
        # app = create_node_app(node, auth=NodeAuth.jwt(secret="..."))

        # Run with: uvicorn handler:app --port 8001
    """
    # DA-3359: entrypoint horizon gate (import stays log-only).
    from canvastekk_workflow_sdk._horizon import enforce_support_horizon

    enforce_support_horizon()

    resolved_auth: _AuthBackend | None
    if auth is None or isinstance(auth, _AuthBackend):
        resolved_auth = auth
    elif auth == "api-key":
        resolved_auth = NodeAuth.api_key()
    else:
        raise ValueError(f"Unknown auth shorthand {auth!r}. Use 'api-key', a NodeAuth backend, or None.")

    router_dependencies = list(dependencies) if dependencies else []
    has_auth_dependency = any(isinstance(getattr(dep, "dependency", dep), _AuthBackend) for dep in router_dependencies)
    if resolved_auth is not None:
        if has_auth_dependency:
            logging.getLogger(__name__).warning(
                "create_node_app: 'dependencies' already contains an auth backend; "
                "ignoring the 'auth' argument to avoid double authentication."
            )
        else:
            router_dependencies.append(Depends(resolved_auth))
            has_auth_dependency = True

    default_kwargs: dict[str, Any] = {
        "title": node.definition.name,
        "version": node.definition.version,
        "description": node.definition.description,
        "openapi_tags": _NODE_OPENAPI_TAGS,
    }
    default_kwargs.update(fastapi_kwargs)

    # Merge node lifespan hooks with any user-provided lifespan
    base_lifespan = default_kwargs.pop("lifespan", None)

    @asynccontextmanager
    async def _node_lifespan(app: Any) -> Any:
        configure_logging()
        # Loud auth-posture warnings (DA-1711 3.3): surface misconfiguration
        # at startup instead of failing silently in production.
        if _is_dev_mode():
            logging.getLogger(__name__).warning(
                "CANVASTEKK_DEV_MODE is active: ALL authentication is bypassed "
                "and URL policy restrictions are lifted. Never enable in production."
            )
        elif not has_auth_dependency:
            logging.getLogger(__name__).warning(
                "Node server starting with NO authentication configured. "
                "Every endpoint (incl. /execute, /metrics) is unauthenticated. "
                "Pass auth='api-key' (or a NodeAuth via create_node_app(auth=...)) "
                "or ensure the node is network-isolated."
            )
        async with node._lifespan():
            if base_lifespan:
                async with base_lifespan(app):
                    yield
            else:
                yield

    app = FastAPI(lifespan=_node_lifespan, **default_kwargs)
    app.add_middleware(SDKVersionMiddleware, node_slug=getattr(getattr(node, "definition", None), "slug", None))
    app.add_middleware(_BodySizeLimitMiddleware)

    # DA-2603: code digest computed once at startup — sha256 over the source
    # bytes of the module defining the node class. ponytail: single-module
    # digest; walk the package if nodes grow multi-file.
    handler_module = inspect.getmodule(type(node))
    handler_source = inspect.getsourcefile(handler_module) if handler_module is not None else None
    try:
        with open(handler_source, "rb") as f:  # type: ignore[arg-type]
            code_digest = hashlib.sha256(f.read()).hexdigest()
    except (OSError, TypeError):
        code_digest = None
        logging.getLogger(__name__).warning(
            "Could not resolve handler source for code_digest (%r); /manifest will serve without it",
            handler_source,
        )

    router = APIRouter(dependencies=router_dependencies)

    @router.post(
        "/execute",
        response_model=NodeExecutionResponse,
        summary="Execute node",
        description="Execute the node with given inputs via JSON body.",
        tags=["Execution"],
        responses={
            200: {"description": "Node executed successfully"},
            400: {
                "description": "Bad request — invalid or missing inputs, or malformed X-Account-Id header",
                "content": {"application/json": {"example": {"detail": "Missing required input: file_path"}}},
            },
            422: {
                "description": "Validation error — request body does not match schema",
                "content": {
                    "application/json": {"example": {"detail": [{"loc": ["body", "run_id"], "msg": "field required"}]}}
                },
            },
            500: {
                "description": "Internal server error — unexpected failure during execution",
                "content": {
                    "application/json": {"example": {"detail": "Unexpected error", "error_type": "RuntimeError"}}
                },
            },
        },
    )
    async def execute(request: Request) -> NodeExecutionResponse:
        """
        Execute the node with given inputs via JSON body.

        The engine sends presigned GET URLs for file input fields.
        Outputs are uploaded via multipart upload-session descriptors
        after successful execution (a legacy presigned-PUT string target
        fails the execution with NodeIOError — DA-3340).
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid JSON body"},
            )
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=422,
                content={"detail": "Request body must be a JSON object"},
            )

        # DA-2242: account_id is engine-controlled — the X-Account-Id header
        # is the EXCLUSIVE source. Body-supplied values are stripped so no
        # caller can forge account identity. Absent/empty → None (local runs).
        body.pop("account_id", None)
        account_id: int | None = None
        account_header = request.headers.get("x-account-id")
        if account_header is not None and account_header.strip():
            candidate = account_header.strip()
            if not _ACCOUNT_ID_RE.match(candidate):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "Malformed X-Account-Id header"},
                )
            if len(candidate) > _ACCOUNT_ID_MAX_DIGITS:
                return JSONResponse(
                    status_code=400,
                    content={"detail": "X-Account-Id header out of range"},
                )
            parsed = int(candidate)
            if not (1 <= parsed <= 2**63 - 1):
                return JSONResponse(
                    status_code=400,
                    content={"detail": "X-Account-Id header out of range"},
                )
            account_id = parsed

        try:
            exec_request = NodeExecutionRequest(**body, account_id=account_id)
        except ValidationError:
            return JSONResponse(
                status_code=422,
                content={"detail": "Request body failed validation"},
            )

        try:
            timeout = node.definition.effective_runtime_seconds
            if timeout and timeout > 0:
                cancel_event = threading.Event()
                cancel_key = id(exec_request)

                def _run_with_cancel() -> Any:
                    # Publish the cancel event on a module-level registry so the
                    # BaseNode run() inside the worker thread can pick it up.
                    _ACTIVE_CANCELS[cancel_key] = cancel_event
                    try:
                        node._set_cancel_event(cancel_event)
                        return node.run(exec_request)
                    finally:
                        _ACTIVE_CANCELS.pop(cancel_key, None)
                        node._set_cancel_event(None)

                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(_run_with_cancel),
                        timeout=timeout,
                    )
                except TimeoutError:
                    cancel_event.set()
                    raise NodeTimeoutError(
                        timeout,
                        details={
                            "slug": node.definition.slug,
                            "execution_id": exec_request.execution_id,
                            "run_id": exec_request.run_id,
                            "node_id": exec_request.node_id,
                            "declared_budget_s": node.definition.timeout_seconds,
                            "hard_ceiling_s": node.definition.hard_max_runtime_seconds,
                            "enforced_at_s": timeout,
                            "host": "inline-lambda",
                        },
                    )
                finally:
                    _ACTIVE_CANCELS.pop(cancel_key, None)
            else:
                response = await asyncio.to_thread(node.run, exec_request)

            if exec_request.output_upload_url and response.status == "pass":
                file_output_fields = node.definition.file_output_fields
                if file_output_fields:
                    try:
                        await asyncio.to_thread(
                            _upload_outputs_to_s3,
                            response,
                            exec_request.output_upload_url,
                            file_output_fields,
                        )
                    except Exception as exc:
                        # A declared file output that could not be uploaded means
                        # the engine would receive a local path it cannot fetch —
                        # fail the execution instead of silently passing (4.1).
                        logging.getLogger(__name__).error("Output upload failed: %s", exc)
                        response = response.model_copy(
                            update={
                                "status": "fail",
                                "error": f"Output upload failed: {exc}",
                                "error_code": "UPLOAD_FAILED",
                            }
                        )

            # Clean up the per-execution temp dir AFTER uploads have completed —
            # long-running node servers otherwise accumulate downloads/outputs
            # in /tmp until disk exhaustion (DA-1711 4.4).
            try:
                output_dir = Path("/tmp") / exec_request.run_id / exec_request.node_id
                if output_dir.is_dir() and output_dir.exists():
                    shutil.rmtree(output_dir, ignore_errors=True)
            except Exception:
                logging.getLogger(__name__).debug("Post-execution temp cleanup skipped", exc_info=True)

            return response

        finally:
            # DA-3009: return freed glibc heap to the OS — both success and
            # exception paths trim exactly once, after the response is built.
            _release_freed_heap()

    @router.get(
        "/health",
        response_model=HealthResponse,
        summary="Health check",
        description="Returns healthy/unhealthy/degraded status along with individual check results.",
        tags=["Health"],
    )
    async def health() -> HealthResponse:
        """
        Check node health.

        Returns healthy/unhealthy/degraded status along with
        individual check results.
        """
        checks = node.health_check()

        # Determine overall status from checks
        if not checks:
            status: Literal["healthy", "unhealthy", "degraded"] = "healthy"
        elif all(checks.values()):
            status = "healthy"
        elif any(checks.values()):
            status = "degraded"
        else:
            status = "unhealthy"

        return HealthResponse(
            status=status,
            node_id=node.definition.id,
            version=node.definition.version,
            checks=checks,
        )

    @router.get(
        "/manifest",
        summary="Node manifest",
        description="Returns the full WorkflowNodeManifest including identity, schemas, cost, retry policy, and metadata. "
        "Used by the registry for auto-discovery.",
        tags=["Discovery"],
    )
    async def manifest() -> JSONResponse:
        """
        Get node's self-description (manifest).

        Returns the WorkflowNodeManifest which includes:
        - Identity (id, slug, name, version, description)
        - Schema (input_schema, output_schema)
        - Cost (token_cost)
        - Retry defaults
        - Metadata (category, timeout, role)
        - SDK version (sdk_version — auto-injected)
        - Node environment (mode — "dev" or "production", from CANVASTEKK_NODE_ENV)
        - Code digest (code_digest — sha256 of the handler module source,
          computed at startup, auto-injected; never author-settable)

        Used by registry for auto-discovery and manifest cross-checking.
        The engine reads ``mode`` to decide routing and test behaviour.
        """
        import canvastekk_workflow_sdk

        content = node.definition.to_dict()
        content["sdk_version"] = canvastekk_workflow_sdk.__version__
        if code_digest is not None:
            content["code_digest"] = code_digest
        raw_env = os.environ.get("CANVASTEKK_NODE_ENV", "dev").lower()
        if raw_env in ("dev", "development", "test"):
            mode = "dev"
        elif raw_env in ("uat", "staging"):
            mode = "uat"
        else:
            mode = "production"
        content["mode"] = mode
        return JSONResponse(content=content)

    @router.post(
        "/hook",
        summary="Webhook callback",
        description="Receives external triggers, progress updates, or async completion notifications. "
        "Returns 501 if the node has not overridden hook().",
        tags=["Callbacks"],
    )
    async def hook(request: Request) -> JSONResponse:
        """
        Webhook/callback endpoint for async operations.

        Receives external triggers, progress updates, or async completion
        notifications. Subclasses can override BaseNode.hook() to handle
        these payloads.

        Returns 501 Not Implemented if the node has not overridden hook().
        """
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(
                status_code=400,
                content={"detail": "Invalid JSON body"},
            )
        if not isinstance(body, dict):
            return JSONResponse(
                status_code=422,
                content={"detail": "Request body must be a JSON object"},
            )
        result = node.hook(body)
        if result is None:
            return JSONResponse(
                status_code=501,
                content={"detail": "Hook not implemented for this node"},
            )
        return JSONResponse(content=result)

    @router.get(
        "/metrics",
        summary="Execution metrics",
        description="Aggregated execution statistics including success rate, average duration, and token usage.",
        tags=["Observability"],
    )
    async def metrics() -> JSONResponse:
        """
        Get node execution metrics.

        Returns aggregated execution statistics including success rate,
        average duration, and token usage.
        """
        return JSONResponse(content=node._metrics_collector.get_summary())

    @router.get(
        "/live",
        summary="Liveness probe",
        description="Returns 200 if the process is alive. Used by Kubernetes to decide whether to restart the pod.",
        tags=["Health"],
    )
    async def liveness() -> JSONResponse:
        """Liveness probe — always returns 200 if the process is running."""
        return JSONResponse(content={"status": "alive"})

    @router.get(
        "/ready",
        summary="Readiness probe",
        description="Returns 200 when the node is ready to accept traffic. "
        "Calls node.health_check(); returns 503 if any check fails.",
        tags=["Health"],
    )
    async def readiness() -> JSONResponse:
        """Readiness probe — returns 200 when the node can accept traffic."""
        checks = node.health_check()
        if not checks or all(checks.values()):
            return JSONResponse(content={"status": "ready", "node_id": node.definition.id, "checks": checks})
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "node_id": node.definition.id, "checks": checks},
        )

    app.include_router(router)

    if extra_routes:
        for extra_router in extra_routes:
            app.include_router(extra_router)

    @app.exception_handler(NodeExecutionError)
    async def node_error_handler(request: object, exc: NodeExecutionError) -> JSONResponse:
        """Handle structured node execution errors."""
        status_code = get_http_status_for_error(exc)
        return JSONResponse(
            status_code=status_code,
            content={
                "detail": exc.message,
                "error_type": type(exc).__name__,
                "error_code": exc.error_code,
                **exc.details,
            },
        )

    @app.exception_handler(Exception)
    async def exception_handler(request: object, exc: Exception) -> JSONResponse:
        """Handle unexpected exceptions.

        The exception detail is logged server-side; the client receives a
        generic message (no internals/paths/URLs leak to callers).
        """
        logging.getLogger(__name__).exception("Unhandled exception on %s", request)
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "error_type": type(exc).__name__,
            },
        )

    return app
