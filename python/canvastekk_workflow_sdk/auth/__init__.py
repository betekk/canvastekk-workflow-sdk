"""
Node Authentication

Provides layered, optional authentication for workflow node endpoints.

The framework-free standard lives in :mod:`canvastekk_workflow_sdk.auth.core`
(``Tekk*`` classes — importable with no web framework installed); the
FastAPI adapter (:mod:`canvastekk_workflow_sdk.auth.fastapi`, gated behind
the ``[fastapi]`` extra) exposes the classic ``NodeAuth`` factory and
FastAPI-compatible backends.

Layers (pick one, or none):
    Layer 0: No auth (default) — nodes work out of the box
    Layer 1: API key — shared secret via X-API-Key header
    Layer 2: JWT (HMAC) — engine-signed HS256 tokens
    Layer 3: Keycloak — RS256 JWT with JWKS (enterprise)

All layers support a dev-mode bypass via the ``CANVASTEKK_DEV_MODE``
environment variable.

Example (FastAPI — unchanged since v0.60.0)::

    from fastapi import Depends
    from canvastekk_workflow_sdk.auth import NodeAuth

    auth = NodeAuth.api_key()
    app = create_node_app(node, dependencies=[Depends(auth)])

Example (framework-free)::

    from canvastekk_workflow_sdk.auth.core import TekkNodeAuth

    auth = TekkNodeAuth.api_key()
    context = auth.verify(provided_api_key)
"""

from __future__ import annotations

from canvastekk_workflow_sdk.auth.core import (  # noqa: F401
    TekkApiKeyAuth,
    TekkAuthBackend,
    TekkAuthError,
    TekkAuthInvalidCredential,
    TekkAuthMissingCredential,
    TekkAuthNotConfigured,
    TekkAuthTokenExpired,
    TekkAuthUnavailable,
    TekkCentralAuth,
    TekkJwtAuth,
    TekkKeycloakAuth,
    TekkNodeAuth,
    _is_dev_mode,
    _VerifyUnavailableError,
)

# FastAPI-adapter names served lazily (module __getattr__, PEP 562) so this
# package — and canvastekk_workflow_sdk.auth.core — import cleanly without
# fastapi installed. Mirrors the root-package gate for the same symbols.
_FASTAPI_EXPORTS = frozenset(
    {
        "NodeAuth",
        "_AuthBackend",
        "_ApiKeyAuth",
        "_CentralAuth",
        "_JwtAuth",
        "_KeycloakAuth",
    }
)


def __getattr__(name: str):
    if name in _FASTAPI_EXPORTS:
        try:
            import fastapi  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                f"{name!r} requires the fastapi-backed auth adapter; "
                "install the extra: pip install canvastekk-workflow-sdk[fastapi]"
            ) from exc
        from canvastekk_workflow_sdk.auth import fastapi as _fastapi

        value = getattr(_fastapi, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
