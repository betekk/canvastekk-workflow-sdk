"""Tests for the pre-flight registry diff helpers (issue #233).

Covers ``fetch_published_definition`` (engine GET by-name) and
``diff_against_published`` (engine immutability-diff mirror). The probe
wiring tests live with the CLI tests; these exercise the registry layer
contract directly.
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from canvastekk_workflow_sdk.registry import (
    diff_against_published,
    fetch_published_definition,
)

#: Well-formed registry credential (DA-1948 shape: ctk_ + 43).
CTK = "ctk_" + "x" * 43

NAME = "cds-file-lambda"


class _Resp:
    """Minimal httpx.Response stub for the patched GET."""

    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("boom", request=None, response=None)  # type: ignore[arg-type]

    def json(self) -> dict:
        return self._payload


class TestFetchPublishedDefinition:
    def test_200_returns_parsed_definition_with_bearer_auth(self) -> None:
        captured: dict = {}

        def fake_get(url: str, headers: dict | None = None, timeout: float = 0.0, **_: object) -> _Resp:
            captured["url"] = url
            captured["headers"] = headers or {}
            return _Resp(200, {"name": NAME, "version": "1.9.1", "timeout_seconds": 7200})

        with patch("canvastekk_workflow_sdk.registry.httpx.get", side_effect=fake_get):
            node = fetch_published_definition("https://cwe.example.com", NAME, token=CTK)

        assert node == {"name": NAME, "version": "1.9.1", "timeout_seconds": 7200}
        assert captured["url"] == f"https://cwe.example.com/api/workflows/nodes/by-name/{NAME}"
        assert captured["headers"]["Authorization"] == f"Bearer {CTK}"

    def test_404_returns_none_for_new_node(self) -> None:
        with patch("canvastekk_workflow_sdk.registry.httpx.get", return_value=_Resp(404)):
            assert fetch_published_definition("https://cwe.example.com", "never-published") is None

    def test_non_ctk_token_raises_rotation_error(self) -> None:
        """#239: legacy tokens fail locally (rotation message) — never a
        header the engine retired (#3760)."""
        with pytest.raises(ValueError, match="ask ops to rotate"):
            fetch_published_definition("https://cwe.example.com", NAME, token="legacy-token")

    def test_transport_error_propagates_for_caller_degradation(self) -> None:
        with patch(
            "canvastekk_workflow_sdk.registry.httpx.get",
            side_effect=httpx.ConnectError("engine unreachable"),
        ):
            with pytest.raises(httpx.ConnectError):
                fetch_published_definition("https://cwe.example.com", NAME)

    def test_trailing_slash_base_url_is_tolerated(self) -> None:
        captured: dict = {}

        def fake_get(url: str, **_: object) -> _Resp:
            captured["url"] = url
            return _Resp(200, {"name": NAME})

        with patch("canvastekk_workflow_sdk.registry.httpx.get", side_effect=fake_get):
            fetch_published_definition("https://cwe.example.com/", NAME)
        assert captured["url"] == f"https://cwe.example.com/api/workflows/nodes/by-name/{NAME}"

    def test_register_style_full_endpoint_url_is_normalized(self) -> None:
        captured: dict = {}

        def fake_get(url: str, **_: object) -> _Resp:
            captured["url"] = url
            return _Resp(200, {"name": NAME})

        with patch("canvastekk_workflow_sdk.registry.httpx.get", side_effect=fake_get):
            fetch_published_definition("https://cwe.example.com/api/workflows/nodes/", NAME)
        assert captured["url"] == f"https://cwe.example.com/api/workflows/nodes/by-name/{NAME}"


class TestDiffAgainstPublished:
    LOCAL = {
        "name": NAME,
        "version": "1.9.1",
        "timeout_seconds": 7200,
        "description": "Global file operations",
        "input_schema": {"type": "object"},
    }

    def test_changed_field_is_reported(self) -> None:
        published = dict(self.LOCAL, timeout_seconds=3600)
        assert diff_against_published(self.LOCAL, published) == ["timeout_seconds"]

    def test_identical_payload_is_unchanged(self) -> None:
        assert diff_against_published(self.LOCAL, dict(self.LOCAL)) == []

    def test_engine_assigned_fields_are_ignored(self) -> None:
        published = dict(self.LOCAL, id="new-uuid", owner="someone-else", source="foreign", node_status="inactive")
        assert diff_against_published(self.LOCAL, published) == []

    def test_local_only_keys_are_skipped(self) -> None:
        local = dict(self.LOCAL, future_sdk_field="value")
        assert diff_against_published(local, dict(self.LOCAL)) == []

    def test_version_drift_is_reported_as_a_field(self) -> None:
        published = dict(self.LOCAL, version="1.9.0")
        assert "version" in diff_against_published(self.LOCAL, published)
