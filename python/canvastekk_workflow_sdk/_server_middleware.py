"""Starlette-backed middleware — only loaded when fastapi is installed.

Gated behind the `[fastapi]` extra: this module imports starlette at module
level and is therefore resolved lazily via the package `__getattr__`
(#104). Import as ``canvastekk_workflow_sdk.SDKVersionMiddleware`` or from
``canvastekk_workflow_sdk._server_middleware`` directly.
"""

from __future__ import annotations

from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

__all__ = ["SDKVersionMiddleware"]


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
