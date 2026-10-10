"""
Node Authentication

Provides layered, optional authentication for workflow node endpoints.

Layers (pick one, or none):
    Layer 0: No auth (default) — nodes work out of the box
    Layer 1: API key — shared secret via X-API-Key header
    Layer 2: JWT (HMAC) — engine-signed HS256 tokens
    Layer 3: Keycloak — RS256 JWT with JWKS (enterprise)

All layers support a dev-mode bypass via the ``CANVASTEKK_DEV_MODE``
environment variable.

Example::

    from fastapi import Depends
    from canvastekk_workflow_sdk.auth import NodeAuth

    auth = NodeAuth.api_key()
    app = create_node_app(node, dependencies=[Depends(auth)])

    # Or JWT:
    auth = NodeAuth.jwt()
    app = create_node_app(node, dependencies=[Depends(auth)])
"""

from __future__ import annotations

import hmac
import logging
import os
import time as _time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover - import-time only
    from fastapi import HTTPException, Request




logger = logging.getLogger(__name__)


def _is_dev_mode() -> bool:
    return os.environ.get("CANVASTEKK_DEV_MODE", "").lower() in ("true", "1", "yes")


class _AuthBackend(ABC):
    """Base class for authentication backends."""

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
        from fastapi import Depends, Request  # lazy: core installs without fastapi (#104)

        # `authenticate(request: Request)` is a string annotation (PEP 563);
        # fastapi resolves hints against this module's globals at wiring time.
        globals().setdefault("Request", Request)
        return Depends(self.authenticate)

    def __call__(self, request: Request) -> dict[str, Any]:
        return self.authenticate(request)


class _ApiKeyAuth(_AuthBackend):
    """Validate requests using a shared ``X-API-Key`` header.

    The expected key is read from the environment variable specified by
    ``key_env_var`` (defaults to ``CANVASTEKK_API_KEY``). During a rotation
    window, ``<key_env_var>_NEXT`` (defaults to ``CANVASTEKK_API_KEY_NEXT``)
    is accepted alongside the current key; empty values are ignored.
    """

    def __init__(self, key_env_var: str = "CANVASTEKK_API_KEY") -> None:
        """Initialize the backend, remembering the env var holding the expected key."""
        self._key_env_var = key_env_var

    def _expected_keys(self) -> list[str]:
        """Return the non-empty configured keys (current + optional rotation next)."""
        keys = (
            os.environ.get(self._key_env_var, ""),
            os.environ.get(f"{self._key_env_var}_NEXT", ""),
        )
        return [key for key in keys if key]

    def authenticate(self, request: Request) -> dict[str, Any]:
        """Validate the ``X-API-Key`` header against the configured env var."""
        from fastapi import HTTPException  # lazy: core installs without fastapi (#104)
        if _is_dev_mode():
            logger.debug("Dev mode: skipping API key authentication")
            return {"auth_mode": "dev_bypass"}

        expected_keys = self._expected_keys()
        if not expected_keys:
            logger.warning("Auth env var %s is not set — rejecting all requests", self._key_env_var)
            raise HTTPException(status_code=401, detail="Authentication not configured")

        provided_key = request.headers.get("X-API-Key", "")
        if not any(
            hmac.compare_digest(provided_key.encode(), expected.encode())
            for expected in expected_keys
        ):
            raise HTTPException(status_code=401, detail="Invalid API key")

        return {"auth_mode": "api_key"}


class _JwtAuth(_AuthBackend):
    """Validate requests using HMAC-SHA256 JWT tokens.

    Requires the ``PyJWT`` package (optional dependency).

    The signing secret is read from ``secret_env_var``
    (defaults to ``CANVASTEKK_JWT_SECRET``).
    """

    def __init__(
        self,
        secret_env_var: str = "CANVASTEKK_JWT_SECRET",
        algorithm: str = "HS256",
        audience: str | None = None,
    ) -> None:
        """Initialize the backend with the secret env var, algorithm, and audience."""
        self._secret_env_var = secret_env_var
        self._algorithm = algorithm
        self._audience = audience
        self._jwt_module: Any = None

    def _get_jwt(self) -> Any:
        if self._jwt_module is None:
            try:
                import jwt as pyjwt

                self._jwt_module = pyjwt
            except ImportError:
                raise ImportError(
                    "PyJWT is required for JWT authentication. Install with: pip install canvastekk-workflow-sdk[jwt]"
                )
        return self._jwt_module

    def authenticate(self, request: Request) -> dict[str, Any]:
        """Validate the ``Authorization: Bearer`` JWT token."""
        from fastapi import HTTPException  # lazy: core installs without fastapi (#104)
        if _is_dev_mode():
            logger.debug("Dev mode: skipping JWT authentication")
            return {"auth_mode": "dev_bypass"}

        secret = os.environ.get(self._secret_env_var, "")
        if not secret:
            raise HTTPException(status_code=401, detail="JWT authentication not configured")

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")

        token = auth_header[7:]
        jwt = self._get_jwt()

        try:
            decode_opts: dict[str, Any] = {"algorithms": [self._algorithm]}
            if self._audience:
                decode_opts["audience"] = self._audience
            payload = jwt.decode(token, secret, **decode_opts)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

        return {"auth_mode": "jwt", "payload": payload}


class _KeycloakAuth(_AuthBackend):
    """Validate requests using Keycloak-issued RS256 JWT tokens.

    Requires ``PyJWT`` and ``cryptography`` (optional dependencies).

    Fetches the public key from Keycloak's JWKS endpoint and validates
    the ``Bearer`` token's signature, expiration, and audience.
    """

    def __init__(
        self,
        server_url: str | None = None,
        realm: str | None = None,
        audience: str | None = None,
        algorithm: str = "RS256",
    ) -> None:
        """Initialize Keycloak authentication backend.

        Args:
            server_url: Keycloak base URL (or set CANVASTEKK_KEYCLOAK_SERVER_URL).
            realm: Keycloak realm (or set CANVASTEKK_KEYCLOAK_REALM).
            audience: Expected aud claim (or set CANVASTEKK_KEYCLOAK_AUDIENCE).
            algorithm: JWT algorithm (default: RS256).

        The instance maintains JWKS caching with refresh-on-miss behavior and
        cooldown to prevent excessive retries during key rotation.
        """
        self._server_url = server_url or os.environ.get("CANVASTEKK_KEYCLOAK_SERVER_URL", "")
        self._realm = realm or os.environ.get("CANVASTEKK_KEYCLOAK_REALM", "")
        self._audience = audience or os.environ.get("CANVASTEKK_KEYCLOAK_AUDIENCE")
        self._algorithm = algorithm
        self._jwt_module: Any = None
        self._jwks_cache: Any = None
        self._jwks_fetched_at: float = 0.0
        self._jwks_ttl: float = 300.0
        self._last_refresh_attempt: float = 0.0
        self._refresh_cooldown: float = 10.0

    def _get_jwt(self) -> Any:
        if self._jwt_module is None:
            try:
                import jwt as pyjwt

                self._jwt_module = pyjwt
            except ImportError:
                raise ImportError(
                    "PyJWT and cryptography are required for Keycloak authentication. "
                    "Install with: pip install canvastekk-workflow-sdk[keycloak]"
                )
        return self._jwt_module

    def _fetch_jwks(self) -> Any:
        now = _time.monotonic()
        if self._jwks_cache is not None and (now - self._jwks_fetched_at) < self._jwks_ttl:
            return self._jwks_cache

        import json
        import urllib.request

        if not self._server_url or not self._realm:
            raise HTTPException(status_code=401, detail="Keycloak server URL and realm must be configured")

        jwks_url = f"{self._server_url.rstrip('/')}/realms/{self._realm}/protocol/openid-connect/certs"
        try:
            req = urllib.request.Request(jwks_url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                jwks_data = json.loads(resp.read())
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Failed to fetch JWKS from Keycloak: {e}")

        jwt = self._get_jwt()
        jwks = jwt.PyJWKSet.from_dict(jwks_data)
        self._jwks_cache = jwks
        self._jwks_fetched_at = _time.monotonic()
        return jwks

    def authenticate(self, request: Request) -> dict[str, Any]:
        """Authenticate a request using Keycloak-issued JWT tokens.

        Implements refresh-on-miss with cooldown: if a token's kid is not found
        in the cached JWKS, a refresh is attempted unless one occurred within
        the last 10 seconds (preventing excessive retries during key rotation).

        Args:
            request: FastAPI request object

        Returns:
            Dict with auth_mode='keycloak' and decoded payload

        Raises:
            HTTPException: 401 if authentication fails, 503 if JWKS fetch fails
        """
        from fastapi import HTTPException  # lazy: core installs without fastapi (#104)
        if _is_dev_mode():
            logger.debug("Dev mode: skipping Keycloak authentication")
            return {"auth_mode": "dev_bypass"}

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Missing Bearer token")

        token = auth_header[7:]
        jwt = self._get_jwt()

        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="Invalid token header")

        kid = unverified_header.get("kid")
        if not kid:
            raise HTTPException(
                status_code=401,
                detail="Token header missing required 'kid' field",
            )
        jwks = self._fetch_jwks()

        signing_key = None
        for key in jwks.keys:
            if key.key_id == kid:
                signing_key = key.key
                break

        if not signing_key:
            now_mono = _time.monotonic()
            if (now_mono - self._last_refresh_attempt) < self._refresh_cooldown:
                logger.warning(
                    "kid '%s' not found in JWKS — refresh skipped (cooldown %.1fs remaining)",
                    kid,
                    self._refresh_cooldown - (now_mono - self._last_refresh_attempt),
                )
                raise HTTPException(
                    status_code=401,
                    detail=f"Token signing key (kid='{kid}') not found in JWKS",
                )
            logger.info(
                "kid '%s' not found in cached JWKS — forcing refresh (available: %s)",
                kid,
                [k.key_id for k in jwks.keys],
            )
            self._last_refresh_attempt = now_mono
            self._jwks_cache = None
            self._jwks_fetched_at = 0.0
            try:
                jwks = self._fetch_jwks()
            except HTTPException:
                raise
            for key in jwks.keys:
                if key.key_id == kid:
                    signing_key = key.key
                    break

        if not signing_key:
            raise HTTPException(
                status_code=401,
                detail=f"Token signing key (kid='{kid}') not found in JWKS",
            )

        try:
            decode_opts: dict[str, Any] = {"algorithms": [self._algorithm]}
            if self._audience:
                decode_opts["audience"] = self._audience
            payload = jwt.decode(token, signing_key, **decode_opts)
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.InvalidTokenError as e:
            raise HTTPException(status_code=401, detail=f"Invalid token: {e}")

        return {"auth_mode": "keycloak", "payload": payload}


class NodeAuth:
    """Factory for node authentication backends.

    Provides class methods that return FastAPI-compatible dependency callables.
    Use with ``create_node_app(dependencies=[Depends(auth)])``.

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
        from fastapi import Request  # lazy: core installs without fastapi (#104)
        globals().setdefault("Request", Request)
        """Create an API key authentication backend.

        Args:
            key_env_var: Environment variable name holding the expected API key.

        Returns:
            An ``_ApiKeyAuth`` instance usable as a FastAPI dependency.
        """
        return _ApiKeyAuth(key_env_var=key_env_var)

    @staticmethod
    def jwt(
        secret_env_var: str = "CANVASTEKK_JWT_SECRET",
        algorithm: str = "HS256",
        audience: str | None = None,
    ) -> _JwtAuth:
        from fastapi import Request  # lazy: core installs without fastapi (#104)
        globals().setdefault("Request", Request)
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
        from fastapi import Request  # lazy: core installs without fastapi (#104)
        globals().setdefault("Request", Request)
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
