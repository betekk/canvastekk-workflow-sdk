"""Tests for the node-token contract module (#3825)."""

import pytest

from canvastekk_workflow_sdk.node_token import (
    NODE_TOKEN_PREFIX,
    NodeTokenClaims,
    is_node_token,
    mint_node_token,
    verify_node_token,
)

KEY = "unit-signing-key-0123456789abcdef0123456789abcdef"
OTHER_KEY = "another-signing-key-fedcba9876543210fedcba9876543210"


class TestMintNodeToken:
    """Tests for mint_node_token."""

    def test_round_trip_preserves_claims(self) -> None:
        token = mint_node_token("run-1", "node-a", KEY, ttl_seconds=300, now=1_000_000)
        claims = verify_node_token(token, KEY, now=1_000_100)
        assert claims == NodeTokenClaims(run_id="run-1", node_id="node-a", iat=1_000_000, exp=1_000_300)

    def test_token_has_scheme_prefix(self) -> None:
        token = mint_node_token("run-1", "node-a", KEY, ttl_seconds=60, now=0)
        assert token.startswith(NODE_TOKEN_PREFIX)
        assert token[len(NODE_TOKEN_PREFIX) :].count(".") == 1

    def test_deterministic_for_same_inputs(self) -> None:
        first = mint_node_token("run-1", "node-a", KEY, ttl_seconds=60, now=5)
        second = mint_node_token("run-1", "node-a", KEY, ttl_seconds=60, now=5)
        assert first == second

    @pytest.mark.parametrize(
        ("run_id", "node_id", "key", "ttl"),
        [
            ("", "node-a", KEY, 60),
            ("run-1", "", KEY, 60),
            ("run-1", "node-a", "", 60),
            ("run-1", "node-a", KEY, 0),
            ("run-1", "node-a", KEY, -10),
        ],
    )
    def test_invalid_arguments_raise(self, run_id: str, node_id: str, key: str, ttl: int) -> None:
        with pytest.raises(ValueError):
            mint_node_token(run_id, node_id, key, ttl_seconds=ttl, now=0)


class TestVerifyNodeToken:
    """Tests for verify_node_token."""

    def test_valid_token_before_expiry(self) -> None:
        token = mint_node_token("run-9", "node-z", KEY, ttl_seconds=100, now=1_000)
        claims = verify_node_token(token, KEY, now=1_099)
        assert claims is not None
        assert claims.run_id == "run-9"
        assert claims.node_id == "node-z"

    def test_expired_token_returns_none(self) -> None:
        token = mint_node_token("run-9", "node-z", KEY, ttl_seconds=100, now=1_000)
        assert verify_node_token(token, KEY, now=1_100) is None

    def test_wrong_key_returns_none(self) -> None:
        token = mint_node_token("run-9", "node-z", KEY, ttl_seconds=100, now=1_000)
        assert verify_node_token(token, OTHER_KEY, now=1_050) is None

    def test_tampered_payload_returns_none(self) -> None:
        token = mint_node_token("run-9", "node-z", KEY, ttl_seconds=100, now=1_000)
        payload_segment, signature_segment = token[len(NODE_TOKEN_PREFIX) :].split(".")
        import base64
        import json

        padded = payload_segment + "=" * (-len(payload_segment) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
        claims["run_id"] = "run-evil"
        mutated = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        tampered = f"{NODE_TOKEN_PREFIX}{mutated}.{signature_segment}"
        assert verify_node_token(tampered, KEY, now=1_050) is None

    def test_tampered_signature_returns_none(self) -> None:
        token = mint_node_token("run-9", "node-z", KEY, ttl_seconds=100, now=1_000)
        payload_segment, signature_segment = token[len(NODE_TOKEN_PREFIX) :].split(".")
        flipped = "A" if not signature_segment.startswith("A") else "B"
        tampered = f"{NODE_TOKEN_PREFIX}{payload_segment}.{flipped}{signature_segment[1:]}"
        assert verify_node_token(tampered, KEY, now=1_050) is None

    def test_non_token_string_returns_none(self) -> None:
        assert verify_node_token("totally-not-a-token", KEY) is None
        assert verify_node_token("", KEY) is None

    def test_garbage_base64_returns_none(self) -> None:
        assert verify_node_token(f"{NODE_TOKEN_PREFIX}!!!.???", KEY) is None
        assert verify_node_token(f"{NODE_TOKEN_PREFIX}only-one-part", KEY) is None

    def test_valid_json_but_wrong_shape_returns_none(self) -> None:
        import base64
        import json

        claims = {"run_id": "run-1", "iat": 0, "exp": 9_999_999_999}
        payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
        import hashlib
        import hmac as hmac_mod

        signature = (
            base64.urlsafe_b64encode(
                hmac_mod.new(
                    KEY.encode(),
                    (NODE_TOKEN_PREFIX + payload).encode(),
                    hashlib.sha256,
                ).digest()
            )
            .rstrip(b"=")
            .decode()
        )
        token = f"{NODE_TOKEN_PREFIX}{payload}.{signature}"
        assert verify_node_token(token, KEY, now=1) is None


class TestIsNodeToken:
    """Tests for is_node_token shape check."""

    def test_true_for_minted_token(self) -> None:
        token = mint_node_token("run-1", "node-a", KEY, ttl_seconds=60, now=0)
        assert is_node_token(token) is True

    def test_false_for_plain_key(self) -> None:
        assert is_node_token("legacy-static-key-123") is False

    def test_false_for_empty_and_none_like(self) -> None:
        assert is_node_token("") is False

    def test_false_for_prefix_only(self) -> None:
        assert is_node_token(NODE_TOKEN_PREFIX) is False
        assert is_node_token(f"{NODE_TOKEN_PREFIX}.sig") is False

    def test_false_for_extra_segments(self) -> None:
        assert is_node_token(f"{NODE_TOKEN_PREFIX}a.b.c") is False

    def test_false_for_non_base64_segments(self) -> None:
        assert is_node_token(f"{NODE_TOKEN_PREFIX}!!!.???") is False
