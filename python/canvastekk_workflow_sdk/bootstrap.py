"""Canonical node-service bootstrap (sdk#220).

The blessed composition of node serving surfaces — promoted from the
canvastekk-workflow-nodes repo-local factory plus the hand-rolled
dual-purpose/lambda faces (see ``docs/NODE-SERVICE-LAYOUT.md``):

- :func:`create_authed_app` — ``create_node_app`` + ``NodeAuth.central()``
  (central-only by default; ``legacy_key_env_var`` keeps a dual-accept
  window alive for existing fleets).
- :func:`mount_node` — dual-purpose services: the service's own routes stay
  on the root app; the authed node sub-app mounts under a prefix.
- :func:`create_lambda_handler` — serverless dual dispatch:
  structurally-HTTP events run through Mangum onto the ASGI app; plain
  events route to the caller's dispatcher. Python-only (no TS parity —
  Mangum/Lambda Runtime API are python-runtime concerns).

Normative contract: ``docs/NODE-TOKEN-CONTRACT.md``.
"""

from __future__ import annotations

from collections.abc import Callable
from contextlib import asynccontextmanager
from typing import Any

from canvastekk_workflow_sdk.base import BaseNode

__all__ = ["create_authed_app", "mount_node", "create_lambda_handler"]


def create_authed_app(
    node: BaseNode,
    *,
    legacy_key_env_var: str | None = None,
    **kwargs: Any,
) -> Any:
    """Create a node app with central token auth on all node endpoints.

    Central-only by default: the ``X-API-Key`` slot carries engine-minted
    run-scoped tokens verified centrally by the engine (fail-closed when the
    engine cannot answer). Existing fleets mid-transition pass
    ``legacy_key_env_var="CANVASTEKK_API_KEY"`` to keep the static-key leg
    live — it is INERT whenever the env vars are unset, so retirement is env
    removal, not code change.

    Args:
        node: The workflow node instance.
        legacy_key_env_var: Env var holding the legacy static key during a
            dual-accept window. ``None`` (default) = central-only.
        **kwargs: Forwarded to ``create_node_app``.

    Returns:
        The node's FastAPI app with the auth dependency wired.

    Raises:
        ValueError: If ``extra_routes`` is passed — ``create_node_app``
            mounts extra routes without the auth dependency, so auth would
            not cover them (verified still true: app.py ``include_router``
            call carries no router dependencies).
    """
    if kwargs.get("extra_routes"):
        raise ValueError(
            "create_authed_app does not support extra_routes — SDK mounts them without the auth dependency"
        )
    from canvastekk_workflow_sdk.app import create_node_app
    from canvastekk_workflow_sdk.auth import NodeAuth

    return create_node_app(
        node,
        auth=NodeAuth.central(legacy_key_env_var=legacy_key_env_var),
        **kwargs,
    )


def mount_node(
    root_app: Any,
    node: BaseNode,
    *,
    prefix: str = "/node",
    legacy_key_env_var: str | None = None,
    **kwargs: Any,
) -> Any:
    """Mount an authed node sub-app onto an existing (dual-purpose) service.

    The service keeps its own routes on ``root_app``; the node contract
    (``/execute``, ``/health``, ``/manifest``, …) serves under ``prefix``
    with the central-auth boundary intact — root-app routes are NOT behind
    node auth.

    Starlette does not run mounted sub-app lifespans, so the node's lifespan
    (``on_startup``/``on_shutdown`` wiring) is chained into the root app's
    lifespan context here.

    Args:
        root_app: The service's FastAPI app (its own routes already on it).
        node: The workflow node instance.
        prefix: Mount path for the node sub-app (default ``/node``).
        legacy_key_env_var: Passed to :func:`create_authed_app`.
        **kwargs: Forwarded to :func:`create_node_app`.

    Returns:
        ``root_app`` (for chaining/uvicorn ``app = mount_node(...)``).
    """

    sub_app = create_authed_app(node, legacy_key_env_var=legacy_key_env_var, **kwargs)
    root_app.mount(prefix, sub_app)

    root_lifespan = root_app.router.lifespan_context
    sub_lifespan = sub_app.router.lifespan_context

    @asynccontextmanager
    async def _combined_lifespan(app: Any) -> Any:
        async with root_lifespan(app) as root_state:
            async with sub_lifespan(app) as sub_state:
                yield {**(root_state or {}), **(sub_state or {})}

    root_app.router.lifespan_context = _combined_lifespan
    return root_app


def _is_structurally_http(event: Any) -> bool:
    """Return True when the Lambda event shape is an HTTP invoke.

    Covers API Gateway REST (``httpMethod``), HTTP API (``requestContext.http``),
    and ALB (``httpMethod``) payloads. Anything else is a plain service event.
    """
    if not isinstance(event, dict):
        return False
    if "httpMethod" in event:
        return True
    request_context = event.get("requestContext")
    return isinstance(request_context, dict) and isinstance(request_context.get("http"), dict)


def create_lambda_handler(
    app: Any,
    *,
    plain_event: Callable[[dict[str, Any], Any], dict[str, Any]],
) -> Callable[[dict[str, Any], Any], dict[str, Any]]:
    """Create a dual-dispatch AWS Lambda handler for a composite service.

    Structurally-HTTP events (Function URL / API Gateway / ALB) dispatch
    through Mangum onto ``app`` (``lifespan="off"`` — the composite manages
    its own setup; matches the proven CLS lane posture). Any other event
    routes to ``plain_event(payload, context)`` — the service's own run
    path.

    Python-only helper — documented as the parity exception in
    ``docs/NODE-SERVICE-LAYOUT.md``.

    Args:
        app: The composite ASGI app (service routes + mounted node).
        plain_event: Dispatcher for non-HTTP events: receives the raw event
            payload and the Lambda context; returns the invocation result.

    Returns:
        A Lambda handler callable ``(event, context) -> result``.

    Raises:
        ImportError: At call time for HTTP events when ``mangum`` is not
            installed (it is an optional dependency — install the
            ``[lambda]`` extra or ``pip install mangum``).
    """
    mangum_asgi: Any = None

    def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
        nonlocal mangum_asgi
        if _is_structurally_http(event):
            if mangum_asgi is None:
                try:
                    from mangum import Mangum
                except ImportError as error:  # pragma: no cover - env-dependent
                    raise ImportError(
                        "create_lambda_handler needs mangum for HTTP events — "
                        "install canvastekk-workflow-sdk[lambda] or mangum"
                    ) from error
                mangum_asgi = Mangum(app, lifespan="off")
            return mangum_asgi(event, context)
        return plain_event(event, context)

    return handler
