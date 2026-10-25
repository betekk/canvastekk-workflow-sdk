"""Run-scoped node tokens — the engine→node credential contract (#3825).

A node token is a self-contained, HMAC-signed credential minted by the
workflow engine at dispatch time and presented to nodes in the
``X-API-Key`` header slot (wire-compatible with the legacy static key;
only the semantics change). Nodes never hold the signing key — they
shape-check the token and delegate verification to the engine's verify
endpoint (``NodeAuth.central()``); the engine verifies locally with
``verify_node_token`` (see ``docs/NODE-TOKEN-CONTRACT.md``).

Format::

    cwnt_v1.<b64url(payload_json)>.<b64url(hmac_sha256)>

The HMAC is computed over the prefixed payload segment
(``cwnt_v1.<payload_b64>``) so the signature is domain-separated from
any other b64 payload scheme. Stdlib only — importable without fastapi
or httpx (#104), by the engine and nodes alike.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time as _time
from dataclasses import dataclass

__all__ = [
    "NODE_TOKEN_PREFIX",
    "NodeTokenClaims",
    "is_node_token",
    "mint_node_token",
    "verify_node_token",
]

NODE_TOKEN_PREFIX = "cwnt_v1."


@dataclass(frozen=True)
class NodeTokenClaims:
    """Verified claims carried by a node token.

    Attributes:
        run_id: Temporal run the token authorizes.
        node_id: Node the token was minted for.
        iat: Issued-at (epoch seconds).
        exp: Expiry (epoch seconds) — run deadline plus grace; retries
            mint a fresh token rather than extending this one.
    """

    run_id: str
    node_id: str
    iat: int
    exp: int


def _b64url_encode(data: bytes) -> str:
    """Encode bytes as unpadded url-safe base64."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    """Decode unpadded url-safe base64, re-adding the stripped padding.

    Raises:
        ValueError: On non-base64 input (padded or illegal characters).
    """
    padded = segment + "=" * (-len(segment) % 4)
    standard = padded.translate(str.maketrans("-_", "+/"))
    return base64.b64decode(standard, validate=True)


def mint_node_token(
    run_id: str,
    node_id: str,
    signing_key: str,
    ttl_seconds: int,
    now: float | None = None,
) -> str:
    """Mint a run-scoped node token (engine-side).

    Args:
        run_id: Temporal run identifier (non-empty).
        node_id: Target node identifier (non-empty).
        signing_key: HMAC-SHA256 signing secret (non-empty; ≥32 bytes
            recommended — enforced at the infra layer, not here).
        ttl_seconds: Token lifetime; expiry = now + ttl (run deadline plus
            grace). Must be positive.
        now: Issuance time override (epoch seconds) for tests.

    Returns:
        The serialized token ``cwnt_v1.<payload>.<sig>``.

    Raises:
        ValueError: If any argument is empty/malformed or ttl is not positive.
    """
    if not run_id or not isinstance(run_id, str):
        raise ValueError("run_id must be a non-empty string")
    if not node_id or not isinstance(node_id, str):
        raise ValueError("node_id must be a non-empty string")
    if not signing_key:
        raise ValueError("signing_key must be non-empty")
    if ttl_seconds <= 0:
        raise ValueError("ttl_seconds must be positive")

    issued_at = int(now if now is not None else _time.time())
    claims = {
        "run_id": run_id,
        "node_id": node_id,
        "iat": issued_at,
        "exp": issued_at + int(ttl_seconds),
    }
    payload_segment = _b64url_encode(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
    signature = hmac.new(
        signing_key.encode("utf-8"),
        (NODE_TOKEN_PREFIX + payload_segment).encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{NODE_TOKEN_PREFIX}{payload_segment}.{_b64url_encode(signature)}"


def verify_node_token(
    token: str,
    signing_key: str,
    now: float | None = None,
) -> NodeTokenClaims | None:
    """Verify a node token locally (engine-side, constant-time compare).

    Args:
        token: The serialized token as presented on the wire.
        signing_key: The HMAC-SHA256 signing secret.
        now: Clock override (epoch seconds) for tests.

    Returns:
        The claims when the signature is valid and the token is unexpired;
        ``None`` for any malformed, tampered, wrongly-signed, or expired
        token (callers treat ``None`` as a definitive reject).
    """
    if not isinstance(token, str) or not token.startswith(NODE_TOKEN_PREFIX):
        return None
    parts = token[len(NODE_TOKEN_PREFIX) :].split(".")
    if len(parts) != 2:
        return None
    payload_segment, signature_segment = parts
    try:
        payload_bytes = _b64url_decode(payload_segment)
        signature = _b64url_decode(signature_segment)
    except (ValueError, binascii.Error):
        return None

    expected = hmac.new(
        signing_key.encode("utf-8"),
        (NODE_TOKEN_PREFIX + payload_segment).encode("ascii"),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(signature, expected):
        return None

    try:
        claims = json.loads(payload_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(claims, dict):
        return None
    run_id = claims.get("run_id")
    node_id = claims.get("node_id")
    iat = claims.get("iat")
    exp = claims.get("exp")
    if not isinstance(run_id, str) or not run_id:
        return None
    if not isinstance(node_id, str) or not node_id:
        return None
    if not isinstance(iat, int) or not isinstance(exp, int):
        return None

    current = int(now if now is not None else _time.time())
    if current >= exp:
        return None
    return NodeTokenClaims(run_id=run_id, node_id=node_id, iat=iat, exp=exp)


def is_node_token(value: str) -> bool:
    """Shape-check a presented credential without cryptography (node-side).

    Args:
        value: The presented ``X-API-Key`` value.

    Returns:
        True when the value has the node-token shape (prefix + two
        well-formed segments); this routes the dual-accept decision only —
        it proves nothing about validity.
    """
    if not isinstance(value, str) or not value.startswith(NODE_TOKEN_PREFIX):
        return False
    remainder = value[len(NODE_TOKEN_PREFIX) :]
    if remainder.count(".") != 1:
        return False
    payload_segment, signature_segment = remainder.split(".")
    if not payload_segment or not signature_segment:
        return False
    try:
        _b64url_decode(payload_segment)
        _b64url_decode(signature_segment)
    except (ValueError, binascii.Error):
        return False
    return True
