"""
Framework-free node authentication core.

The verify standard (credential contract, verdict caching, fail-closed,
dual-accept, JWKS rotation) lives here with **zero framework imports** —
no fastapi, no starlette. Hosts extract the credential from their own
request object and call ``verify(<header value>)``; the FastAPI adapter
(:mod:`canvastekk_workflow_sdk.auth.fastapi`, behind the ``[fastapi]``
extra) maps the :class:`TekkAuthError` taxonomy to HTTP responses.

Layers (pick one, or none):
    Layer 0: No auth (default) — nodes work out of the box
    Layer 1: API key — shared secret via X-API-Key header
    Layer 2: JWT (HMAC) — engine-signed HS256 tokens
    Layer 3: Keycloak — RS256 JWT with JWKS (enterprise)

All layers support a dev-mode bypass via the ``CANVASTEKK_DEV_MODE``
environment variable.

Example (framework-free)::

    from canvastekk_workflow_sdk.auth.core import TekkNodeAuth

    auth = TekkNodeAuth.api_key()
    context = auth.verify(provided_api_key)  # raises TekkAuthError on reject

The FastAPI face remains ``NodeAuth`` (see ``canvastekk_workflow_sdk.auth``).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time as _time
from abc import ABC, abstractmethod
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Error taxonomy — the SDK-defined auth failure contract.
#
# Every authentication rejection raises one of these (never a bare string
# HTTPException). Each carries:
#   * ``status`` — the intended HTTP status for framework adapters
#     (401 reject, 503 fail-closed unavailable)
#   * ``code`` — a stable machine-readable identifier (never rename;
#     consumers may branch on it)
#   * ``str(exc)`` — the human-facing detail, byte-identical to the
#     v0.60.0 HTTP responses so adapters emit unchanged bodies
# ---------------------------------------------------------------------------


class TekkAuthError(Exception):
    """Base class for all SDK authentication failures.

    Cause: an authentication attempt did not succeed.
    Remediation: catch the specific subclass (or this base) instead of
    string-matching HTTP error bodies; ``.status`` and ``.code`` are
    stable contracts.
    """

    status: int = 401
    code: str = "auth_error"
    default_detail: str = "Authentication failed"

    def __init__(self, detail: str | None = None) -> None:
        self.detail = detail or self.default_detail
        super().__init__(self.detail)


class TekkAuthNotConfigured(TekkAuthError):
    """Authentication is required but no credential source is configured (401).

    Cause: the env var holding the expected secret/base URL is unset.
    Remediation: set the documented env var (e.g. ``CANVASTEKK_API_KEY``,
    ``CWE_API_BASE_URL``, ``CANVASTEKK_JWT_SECRET``) or disable auth.
    """

    status = 401
    code = "auth_not_configured"
    default_detail = "Authentication not configured"


class TekkAuthMissingCredential(TekkAuthError):
    """The request presented no credential where one is required (401).

    Cause: the expected header was absent or empty.
    Remediation: send the credential (``X-API-Key`` or
    ``Authorization: Bearer <token>``).
    """

    status = 401
    code = "auth_missing_credential"
    default_detail = "Missing credential"


class TekkAuthInvalidCredential(TekkAuthError):
    """The presented credential was rejected (401).

    Cause: wrong key, invalid/expired-format token, unknown signing key,
    or a definitive ``valid: false`` verdict from the engine.
    Remediation: present a current credential; check rotation env vars
    (``<key_env_var>_NEXT``) during key rotation.
    """

    status = 401
    code = "auth_invalid_credential"
    default_detail = "Invalid credential"


class TekkAuthTokenExpired(TekkAuthError):
    """The presented token's expiry has passed (401).

    Cause: ``exp`` claim is in the past (signature was otherwise valid).
    Remediation: obtain a fresh token from the issuer.
    """

    status = 401
    code = "auth_token_expired"
    default_detail = "Token has expired"


class TekkAuthUnavailable(TekkAuthError):
    """The credential validator could not deliver a verdict (503, fail-closed).

    Cause: validator (engine verify endpoint / Keycloak JWKS) unreachable,
    timed out, or returned a malformed response — never cached.
    Remediation: retry; check validator health and connectivity. The
    backend intentionally fails closed rather than accepting on doubt
    (DA-1949).
    """

    status = 503
    code = "auth_unavailable"
    default_detail = "Authentication service unavailable"


class _VerifyUnavailableError(Exception):
    """The engine verify endpoint could not deliver a verdict (fail-closed)."""


def _is_dev_mode() -> bool:
    return os.environ.get("CANVASTEKK_DEV_MODE", "").lower() in ("true", "1", "yes")


class TekkAuthBackend(ABC):
    """Framework-free base for authentication backends."""

    @abstractmethod
    def verify(self, credential: str) -> dict[str, Any]:
        """Verify a raw credential value.

        Args:
            credential: The header value the host extracted (``X-API-Key``
                value, or the full ``Authorization`` header value for
                Bearer schemes).

        Returns:
            Dict with authentication context (e.g., auth_mode).

        Raises:
            TekkAuthError: subclasses carry the rejection reason, the
                intended status, and a stable code.
        """
        ...


class TekkApiKeyAuth(TekkAuthBackend):
    """Validate a shared ``X-API-Key`` secret (framework-free).

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

    def verify(self, credential: str) -> dict[str, Any]:
        """Validate the ``X-API-Key`` value against the configured env var."""
        if _is_dev_mode():
            logger.debug("Dev mode: skipping API key authentication")
            return {"auth_mode": "dev_bypass"}

        expected_keys = self._expected_keys()
        if not expected_keys:
            logger.warning("Auth env var %s is not set — rejecting all requests", self._key_env_var)
            raise TekkAuthNotConfigured("Authentication not configured")

        if not any(hmac.compare_digest(credential.encode(), expected.encode()) for expected in expected_keys):
            raise TekkAuthInvalidCredential("Invalid API key")

        return {"auth_mode": "api_key"}


class TekkCentralAuth(TekkAuthBackend):
    """Validate engine-issued run tokens via the workflow engine (#3825).

    Production auth mode for org nodes ("secretless nodes"): the presented
    ``X-API-Key`` value carries a run-scoped token minted by the engine at
    dispatch; this backend delegates verification to the engine's verify
    endpoint and caches verdicts by token hash.

    Dual-accept transition: when ``legacy_key_env_var`` names a set env var,
    a constant-time static-key match is accepted first (``auth_mode`` =
    ``legacy_api_key``); the legacy leg is inert when the env var is unset —
    retirement happens by env removal, not code change (#3838).

    Fail-closed law (DA-1949): a definitive ``valid: false`` verdict is a
    401 (:class:`TekkAuthInvalidCredential`); any transport failure
    (unreachable engine, timeout, malformed response) is a 503
    (:class:`TekkAuthUnavailable`) — the backend never fails open.
    Transport errors are never cached. Token values are never logged.
    """

    _CACHE_MAX_ENTRIES = 1024

    def __init__(
        self,
        verify_base_url_env_var: str = "CWE_API_BASE_URL",
        verify_path: str = "/api/nodes/verify-token",
        cache_ttl: float = 60.0,
        timeout: float = 5.0,
        legacy_key_env_var: str | None = "CANVASTEKK_API_KEY",
    ) -> None:
        """Initialize the backend with verify-endpoint and cache settings.

        Args:
            verify_base_url_env_var: Env var holding the engine base URL.
            verify_path: Path of the verify endpoint on the engine.
            cache_ttl: Verdict cache lifetime in seconds (also bounds valid
                verdicts by the token's own expiry).
            timeout: Verify-endpoint call timeout in seconds.
            legacy_key_env_var: Env var holding the legacy static key
                (dual-accept transition); ``None`` disables the legacy leg.
        """
        self._verify_base_url_env_var = verify_base_url_env_var
        self._verify_path = verify_path
        self._cache_ttl = cache_ttl
        self._timeout = timeout
        self._legacy_key_env_var = legacy_key_env_var
        self._verdict_cache: dict[str, tuple[bool, dict[str, Any] | None, float]] = {}

    def _legacy_matches(self, provided: str) -> bool:
        """Return True when the credential matches the configured legacy key."""
        if not self._legacy_key_env_var:
            return False
        keys = (
            os.environ.get(self._legacy_key_env_var, ""),
            os.environ.get(f"{self._legacy_key_env_var}_NEXT", ""),
        )
        expected = [key for key in keys if key]
        return any(hmac.compare_digest(provided.encode(), key.encode()) for key in expected)

    def _cache_expiry(self, valid: bool, claims: dict[str, Any] | None) -> float:
        """Return the monotonic instant a cached verdict expires."""
        now = _time.monotonic()
        if not valid or not isinstance(claims.get("exp"), (int, float)):
            return now + self._cache_ttl
        wall_remaining = float(claims["exp"]) - _time.time()
        return now + max(0.0, min(self._cache_ttl, wall_remaining))

    def _remote_verify(self, token: str, base_url: str) -> tuple[bool, dict[str, Any] | None]:
        """Call the engine verify endpoint; return the parsed verdict.

        Raises:
            _VerifyUnavailableError: On any transport or protocol failure — the
                caller must fail closed (503), never cache.
        """
        import http.client
        import json
        import urllib.error
        import urllib.request

        url = f"{base_url}{self._verify_path}"
        body = json.dumps({"token": token}).encode("utf-8")
        request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                payload = json.loads(response.read())
        except (
            urllib.error.URLError,
            http.client.HTTPException,
            TimeoutError,
            OSError,
            ValueError,
        ) as error:
            raise _VerifyUnavailableError(str(error)) from error
        if not isinstance(payload, dict) or not isinstance(payload.get("valid"), bool):
            raise _VerifyUnavailableError("Malformed verify response")
        if payload["valid"]:
            run_id = payload.get("run_id")
            node_id = payload.get("node_id")
            exp = payload.get("exp")
            if not isinstance(run_id, str) or not isinstance(node_id, str) or not isinstance(exp, (int, float)):
                raise _VerifyUnavailableError("Malformed verify response")
            claims = {"run_id": run_id, "node_id": node_id, "exp": exp}
            return True, claims
        return False, None

    def _validated_claims(self, token: str) -> dict[str, Any] | None:
        """Return claims for a valid token, honoring the verdict cache.

        Raises:
            TekkAuthNotConfigured: When the engine base URL is unset.
            _VerifyUnavailableError: When the engine cannot be reached and no
                cached verdict covers the token.
        """
        digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
        cached = self._verdict_cache.get(digest)
        if cached is not None and cached[2] > _time.monotonic():
            valid, claims, _ = cached
            return claims if valid else None

        base_url = os.environ.get(self._verify_base_url_env_var, "").rstrip("/")
        if not base_url:
            raise TekkAuthNotConfigured("Authentication not configured")

        valid, claims = self._remote_verify(token, base_url)
        if len(self._verdict_cache) >= self._CACHE_MAX_ENTRIES:
            self._verdict_cache.clear()
        self._verdict_cache[digest] = (valid, claims, self._cache_expiry(valid, claims))
        return claims if valid else None

    def verify(self, credential: str) -> dict[str, Any]:
        """Validate the ``X-API-Key`` token (or legacy key) centrally."""
        if _is_dev_mode():
            logger.debug("Dev mode: skipping central token authentication")
            return {"auth_mode": "dev_bypass"}

        if not credential:
            raise TekkAuthMissingCredential("Missing API key")

        if self._legacy_matches(credential):
            return {"auth_mode": "legacy_api_key"}

        try:
            claims = self._validated_claims(credential)
        except _VerifyUnavailableError as error:
            raise TekkAuthUnavailable("Token validator unavailable") from error
        if claims is None:
            raise TekkAuthInvalidCredential("Invalid node token")
        return {
            "auth_mode": "central",
            "run_id": claims.get("run_id"),
            "node_id": claims.get("node_id"),
        }


class TekkJwtAuth(TekkAuthBackend):
    """Validate HMAC-SHA256 JWT Bearer tokens (framework-free).

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

    def verify(self, credential: str) -> dict[str, Any]:
        """Validate the ``Authorization: Bearer`` JWT token."""
        if _is_dev_mode():
            logger.debug("Dev mode: skipping JWT authentication")
            return {"auth_mode": "dev_bypass"}

        secret = os.environ.get(self._secret_env_var, "")
        if not secret:
            raise TekkAuthNotConfigured("JWT authentication not configured")

        if not credential.startswith("Bearer "):
            raise TekkAuthMissingCredential("Missing Bearer token")

        token = credential[7:]
        jwt = self._get_jwt()

        try:
            decode_opts: dict[str, Any] = {"algorithms": [self._algorithm]}
            if self._audience:
                decode_opts["audience"] = self._audience
            payload = jwt.decode(token, secret, **decode_opts)
        except jwt.ExpiredSignatureError:
            raise TekkAuthTokenExpired("Token has expired")
        except jwt.InvalidTokenError as e:
            raise TekkAuthInvalidCredential(f"Invalid token: {e}") from e

        return {"auth_mode": "jwt", "payload": payload}


class TekkKeycloakAuth(TekkAuthBackend):
    """Validate Keycloak-issued RS256 JWT Bearer tokens (framework-free).

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
            raise TekkAuthNotConfigured("Keycloak server URL and realm must be configured")

        jwks_url = f"{self._server_url.rstrip('/')}/realms/{self._realm}/protocol/openid-connect/certs"
        try:
            req = urllib.request.Request(jwks_url)
            with urllib.request.urlopen(req, timeout=10) as resp:
                jwks_data = json.loads(resp.read())
        except Exception as e:
            raise TekkAuthUnavailable(f"Failed to fetch JWKS from Keycloak: {e}") from e

        jwt = self._get_jwt()
        jwks = jwt.PyJWKSet.from_dict(jwks_data)
        self._jwks_cache = jwks
        self._jwks_fetched_at = _time.monotonic()
        return jwks

    def verify(self, credential: str) -> dict[str, Any]:
        """Authenticate using Keycloak-issued JWT tokens.

        Implements refresh-on-miss with cooldown: if a token's kid is not found
        in the cached JWKS, a refresh is attempted unless one occurred within
        the last 10 seconds (preventing excessive retries during key rotation).

        Args:
            credential: The full ``Authorization`` header value.

        Returns:
            Dict with auth_mode='keycloak' and decoded payload

        Raises:
            TekkAuthError: 401 subclasses if authentication fails,
                TekkAuthUnavailable (503) if the JWKS fetch fails
        """
        if _is_dev_mode():
            logger.debug("Dev mode: skipping Keycloak authentication")
            return {"auth_mode": "dev_bypass"}

        if not credential.startswith("Bearer "):
            raise TekkAuthMissingCredential("Missing Bearer token")

        token = credential[7:]
        jwt = self._get_jwt()

        try:
            unverified_header = jwt.get_unverified_header(token)
        except jwt.InvalidTokenError:
            raise TekkAuthInvalidCredential("Invalid token header")

        kid = unverified_header.get("kid")
        if not kid:
            raise TekkAuthInvalidCredential("Token header missing required 'kid' field")
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
                raise TekkAuthInvalidCredential(f"Token signing key (kid='{kid}') not found in JWKS")
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
            except TekkAuthError:
                raise
            for key in jwks.keys:
                if key.key_id == kid:
                    signing_key = key.key
                    break

        if not signing_key:
            raise TekkAuthInvalidCredential(f"Token signing key (kid='{kid}') not found in JWKS")

        try:
            decode_opts: dict[str, Any] = {"algorithms": [self._algorithm]}
            if self._audience:
                decode_opts["audience"] = self._audience
            payload = jwt.decode(token, signing_key, **decode_opts)
        except jwt.ExpiredSignatureError:
            raise TekkAuthTokenExpired("Token has expired")
        except jwt.InvalidTokenError as e:
            raise TekkAuthInvalidCredential(f"Invalid token: {e}") from e

        return {"auth_mode": "keycloak", "payload": payload}


class TekkNodeAuth:
    """Factory for framework-free node authentication backends.

    Provides class methods that return :class:`TekkAuthBackend` instances
    whose ``verify(<header value>)`` is pure of any web framework. Hosts
    on FastAPI should use ``NodeAuth`` (the adapter) instead — same
    layers, ``Depends``-compatible.

    Example::

        from canvastekk_workflow_sdk.auth.core import TekkNodeAuth

        auth = TekkNodeAuth.api_key()
        context = auth.verify(provided_api_key)
    """

    @staticmethod
    def api_key(key_env_var: str = "CANVASTEKK_API_KEY") -> TekkApiKeyAuth:
        """Create an API key authentication backend.

        Args:
            key_env_var: Environment variable name holding the expected API key.

        Returns:
            A ``TekkApiKeyAuth`` instance whose ``verify`` takes the
            ``X-API-Key`` header value.
        """
        return TekkApiKeyAuth(key_env_var=key_env_var)

    @staticmethod
    def central(
        verify_base_url_env_var: str = "CWE_API_BASE_URL",
        verify_path: str = "/api/nodes/verify-token",
        cache_ttl: float = 60.0,
        timeout: float = 5.0,
        legacy_key_env_var: str | None = "CANVASTEKK_API_KEY",
    ) -> TekkCentralAuth:
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
            A ``TekkCentralAuth`` instance whose ``verify`` takes the
            ``X-API-Key`` header value.
        """
        return TekkCentralAuth(
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
    ) -> TekkJwtAuth:
        """Create a JWT (HMAC-SHA256) authentication backend.

        Requires the ``PyJWT`` package.

        Args:
            secret_env_var: Environment variable name holding the signing secret.
            algorithm: JWT algorithm (default: HS256).
            audience: Expected ``aud`` claim in the token.

        Returns:
            A ``TekkJwtAuth`` instance whose ``verify`` takes the full
            ``Authorization`` header value.
        """
        return TekkJwtAuth(secret_env_var=secret_env_var, algorithm=algorithm, audience=audience)

    @staticmethod
    def keycloak(
        server_url: str | None = None,
        realm: str | None = None,
        audience: str | None = None,
        algorithm: str = "RS256",
    ) -> TekkKeycloakAuth:
        """Create a Keycloak RS256 JWT authentication backend.

        Requires the ``PyJWT`` and ``cryptography`` packages.

        Args:
            server_url: Keycloak base URL (or set ``CANVASTEKK_KEYCLOAK_SERVER_URL``).
            realm: Keycloak realm (or set ``CANVASTEKK_KEYCLOAK_REALM``).
            audience: Expected ``aud`` claim (or set ``CANVASTEKK_KEYCLOAK_AUDIENCE``).
            algorithm: JWT algorithm (default: RS256).

        Returns:
            A ``TekkKeycloakAuth`` instance whose ``verify`` takes the full
            ``Authorization`` header value.
        """
        return TekkKeycloakAuth(server_url=server_url, realm=realm, audience=audience, algorithm=algorithm)
