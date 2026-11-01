"""
FastAPI adapter for node authentication.

Adapter-only module (behind the ``[fastapi]`` extra): extracts the
credential from a FastAPI ``Request``, delegates to the framework-free
core (:mod:`canvastekk_workflow_sdk.auth.core`), and maps the
``TekkAuthError`` taxonomy to ``HTTPException`` with byte-identical
status + detail as v0.60.0.

Example::

    from fastapi import Depends
    from canvastekk_workflow_sdk.auth import NodeAuth

    auth = NodeAuth.api_key()
    app = create_node_app(node, dependencies=[Depends(auth)])
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from fastapi import HTTPException, Request

from canvastekk_workflow_sdk.auth.core import (
    TekkApiKeyAuth,
    TekkAuthError,
    TekkCentralAuth,
    TekkJwtAuth,
    TekkKeycloakAuth,
)


def _to_http(exc: TekkAuthError) -> HTTPException:
    """Map a TekkAuthError to the v0.60.0-identical HTTPException."""
    return HTTPException(status_code=exc.status, detail=str(exc))


class _AuthBackend(ABC):
    """Base class for FastAPI-backed authentication adapters."""

    @abstractmethod
    def authenticate(self, request: Request) -> dict[str, Any]:
        """Authenticate the incoming request.

        Args:
            request: FastAPI request object.

        Returns:
            Dict with authentication context (e.g., auth_mode).
        """
        ...

    def as_dependency(self) -> Any:
        """Return a FastAPI ``Depends()`` callable for this backend."""
        from fastapi import Depends

        return Depends(self.authenticate)

    def __call__(self, request: Request) -> dict[str, Any]:
        return self.authenticate(request)


class _ApiKeyAuth(TekkApiKeyAuth, _AuthBackend):
    """FastAPI face of ``TekkApiKeyAuth`` — reads ``X-API-Key``."""

    def authenticate(self, request: Request) -> dict[str, Any]:
        """Validate the ``X-API-Key`` header against the configured env var."""
        try:
            return self.verify(request.headers.get("X-API-Key", ""))
        except TekkAuthError as exc:
            raise _to_http(exc) from exc


class _CentralAuth(TekkCentralAuth, _AuthBackend):
    """FastAPI face of ``TekkCentralAuth`` — reads ``X-API-Key``."""

    def authenticate(self, request: Request) -> dict[str, Any]:
        """Validate the ``X-API-Key`` token (or legacy key) centrally."""
        try:
            return self.verify(request.headers.get("X-API-Key", ""))
        except TekkAuthError as exc:
            raise _to_http(exc) from exc


class _JwtAuth(TekkJwtAuth, _AuthBackend):
    """FastAPI face of ``TekkJwtAuth`` — reads ``Authorization``."""

    def authenticate(self, request: Request) -> dict[str, Any]:
        """Validate the ``Authorization: Bearer`` JWT token."""
        try:
            return self.verify(request.headers.get("Authorization", ""))
        except TekkAuthError as exc:
            raise _to_http(exc) from exc


class _KeycloakAuth(TekkKeycloakAuth, _AuthBackend):
    """FastAPI face of ``TekkKeycloakAuth`` — reads ``Authorization``."""

    def authenticate(self, request: Request) -> dict[str, Any]:
        """Authenticate a request using Keycloak-issued JWT tokens.

        Raises:
            HTTPException: 401 if authentication fails, 503 if JWKS fetch fails
        """
        try:
            return self.verify(request.headers.get("Authorization", ""))
        except TekkAuthError as exc:
            raise _to_http(exc) from exc


class NodeAuth:
    """Factory for FastAPI-compatible node authentication backends.

    Provides class methods that return FastAPI dependency callables.
    Use with ``create_node_app(dependencies=[Depends(auth)])``.

    The framework-free equivalent is ``TekkNodeAuth``
    (``canvastekk_workflow_sdk.auth.core``) — same layers, no framework.

    Example::

        # Layer 1: API key (simplest)
        auth = NodeAuth.api_key()
        app = create_node_app(node, dependencies=[Depends(auth)])

        # Layer 2: JWT (HMAC)
        auth = NodeAuth.jwt()
        app = create_node_app(node, dependencies=[Depends(auth)])

        # Layer 3: Keycloak (enterprise)
        auth = NodeAuth.keycloak()
        app = create_node_app(node, dependencies=[Depends(auth)])
    """

    @staticmethod
    def api_key(key_env_var: str = "CANVASTEKK_API_KEY") -> _ApiKeyAuth:
        """Create an API key authentication backend.

        Args:
            key_env_var: Environment variable name holding the expected API key.

        Returns:
            An ``_ApiKeyAuth`` instance usable as a FastAPI dependency.
        """
        return _ApiKeyAuth(key_env_var=key_env_var)

    @staticmethod
    def central(
        verify_base_url_env_var: str = "CWE_API_BASE_URL",
        verify_path: str = "/api/nodes/verify-token",
        cache_ttl: float = 60.0,
        timeout: float = 5.0,
        legacy_key_env_var: str | None = "CANVASTEKK_API_KEY",
    ) -> _CentralAuth:
        """Create a central-validation auth backend (engine-issued tokens).

        Production mode for org nodes (#3825): the ``X-API-Key`` header
        carries a run-scoped token minted by the engine; verdicts come from
        the engine's verify endpoint (cached, fail-closed per DA-1949).

        Args:
            verify_base_url_env_var: Env var holding the engine base URL.
            verify_path: Path of the verify endpoint on the engine.
            cache_ttl: Verdict cache lifetime in seconds.
            timeout: Verify-endpoint call timeout in seconds.
            legacy_key_env_var: Env var holding the legacy static key —
                dual-accept transition; set ``None`` for central-only (the
                legacy leg is inert whenever the env var is unset).

        Returns:
            A ``_CentralAuth`` instance usable as a FastAPI dependency.
        """
        return _CentralAuth(
            verify_base_url_env_var=verify_base_url_env_var,
            verify_path=verify_path,
            cache_ttl=cache_ttl,
            timeout=timeout,
            legacy_key_env_var=legacy_key_env_var,
        )

    @staticmethod
    def jwt(
        secret_env_var: str = "CANVASTEKK_JWT_SECRET",
        algorithm: str = "HS256",
        audience: str | None = None,
    ) -> _JwtAuth:
        """Create a JWT (HMAC-SHA256) authentication backend.

        Requires the ``PyJWT`` package.

        Args:
            secret_env_var: Environment variable name holding the signing secret.
            algorithm: JWT algorithm (default: HS256).
            audience: Expected ``aud`` claim in the token.

        Returns:
            A ``_JwtAuth`` instance usable as a FastAPI dependency.
        """
        return _JwtAuth(secret_env_var=secret_env_var, algorithm=algorithm, audience=audience)

    @staticmethod
    def keycloak(
        server_url: str | None = None,
        realm: str | None = None,
        audience: str | None = None,
        algorithm: str = "RS256",
    ) -> _KeycloakAuth:
        """Create a Keycloak RS256 JWT authentication backend.

        Requires the ``PyJWT`` and ``cryptography`` packages.

        Args:
            server_url: Keycloak base URL (or set ``CANVASTEKK_KEYCLOAK_SERVER_URL``).
            realm: Keycloak realm (or set ``CANVASTEKK_KEYCLOAK_REALM``).
            audience: Expected ``aud`` claim (or set ``CANVASTEKK_KEYCLOAK_AUDIENCE``).
            algorithm: JWT algorithm (default: RS256).

        Returns:
            A ``_KeycloakAuth`` instance usable as a FastAPI dependency.
        """
        return _KeycloakAuth(server_url=server_url, realm=realm, audience=audience, algorithm=algorithm)
