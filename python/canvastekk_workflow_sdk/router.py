"""
Multi-Node Router

Creates a single FastAPI application that hosts multiple nodes,
each under its own URL prefix. Useful for consolidating several
nodes behind one server.

Example::

    from canvastekk_workflow_sdk.router import create_multi_node_app

    app = create_multi_node_app({
        "segment": SegmentNode(),
        "measure": MeasureNode(),
    })

Each node gets its own set of 6 endpoints:
    POST /segment/execute
    GET  /segment/health
    GET  /segment/manifest
    ...
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from canvastekk_workflow_sdk.app import create_node_app

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from fastapi import FastAPI



if TYPE_CHECKING:
    from canvastekk_workflow_sdk.base import BaseNode


def create_multi_node_app(
    nodes: dict[str, BaseNode],
    *,
    global_dependencies: list[Any] | None = None,
    **fastapi_kwargs: Any,
) -> FastAPI:
    """Create a FastAPI app hosting multiple nodes under URL prefixes.

    Each key in ``nodes`` becomes a URL prefix. For example,
    ``{"segment": SegmentNode()}`` creates endpoints like
    ``POST /segment/execute``.

    Args:
        nodes: Mapping of URL prefix to BaseNode instance.
            Prefixes should be URL-safe (no slashes).
        global_dependencies: FastAPI dependencies applied to all
            node endpoints across all mounted nodes.
        **fastapi_kwargs: Additional arguments passed to the root
            FastAPI constructor.

    Returns:
        A FastAPI application with all node endpoints mounted.

    Example::

        app = create_multi_node_app({
            "segment": SegmentNode(),
            "measure": MeasureNode(),
        })

        # Endpoints:
        # POST /segment/execute, GET /segment/health, ...
        # POST /measure/execute, GET /measure/health, ...
    """
    from fastapi import FastAPI  # lazy: core installs without fastapi (#104)

    app = FastAPI(**fastapi_kwargs)

    node_apps: list[tuple[str, Any]] = []
    try:
        for prefix, node in nodes.items():
            node_app = create_node_app(
                node,
                dependencies=global_dependencies,
            )
            node_apps.append((prefix, node_app))
    except Exception:
        for prefix, node_app in node_apps:
            try:
                app.unmount(f"/{prefix}")
            except Exception:
                pass
        raise

    for prefix, node_app in node_apps:
        app.mount(f"/{prefix}", node_app)

    @app.get("/health")
    async def root_health() -> dict[str, Any]:
        """Root health endpoint for the multi-node application.

        Returns:
            Dict with ``status`` and list of mounted node prefixes.
        """
        return {"status": "healthy", "nodes": list(nodes.keys())}

    return app
