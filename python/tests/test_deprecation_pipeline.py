"""Deprecation pipeline tests (DA-2305).

Covers the three SDK-side halves of the deprecation pipeline:
registry payload emission (wire shape), ``DeprecationInfo`` model
validation, and ``BaseNode`` runtime sunset/refusal semantics.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from canvastekk_workflow_sdk import (
    BaseNode,
    ExecutionContext,
    NodeConfigurationError,
    NodeExecutionRequest,
    WorkflowNodeManifest,
)
from canvastekk_workflow_sdk.definition import DeprecationInfo
from canvastekk_workflow_sdk.registry import build_registry_payload


def _manifest(deprecation: DeprecationInfo | None) -> WorkflowNodeManifest:
    return WorkflowNodeManifest(
        name="legacy-echo",
        version="1.0.0",
        title="Legacy Echo",
        description="Echo node used for deprecation pipeline tests",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        deprecation=deprecation,
    )


def _make_node(deprecation: DeprecationInfo | None) -> BaseNode:
    """Build an instantiated echo node whose definition carries the given deprecation."""

    class _DeprecationEchoNode(BaseNode):
        definition = _manifest(deprecation)

        def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
            return {"echo": inputs.get("message", "")}

    return _DeprecationEchoNode()


class TestRegistryPayloadEmission:
    """build_registry_payload emits SDK-shaped deprecation (DA-2305)."""

    def test_deprecation_emitted_with_wire_shape(self) -> None:
        dep = DeprecationInfo(
            deprecated_at=date(2026, 9, 3),
            sunset_date=date(2027, 1, 1),
            replacement_slug="cds-file",
            migration_url="https://docs.example.test/cds-file",
            notice="Replaced by the flat file controller.",
        )
        payload = build_registry_payload(_manifest(dep))
        assert "deprecation" in payload
        emitted = payload["deprecation"]
        assert set(emitted.keys()) == {
            "deprecated_at",
            "sunset_date",
            "replacement_slug",
            "migration_url",
            "notice",
        }
        assert emitted["deprecated_at"] == "2026-09-03"
        assert emitted["sunset_date"] == "2027-01-01"
        assert emitted["replacement_slug"] == "cds-file"
        assert emitted["notice"] == "Replaced by the flat file controller."

    def test_deprecation_absent_when_unset(self) -> None:
        payload = build_registry_payload(_manifest(None))
        assert "deprecation" not in payload


class TestDeprecationInfoValidation:
    """DeprecationInfo enforces sunset >= deprecated ordering."""

    def test_sunset_before_deprecated_rejected(self) -> None:
        with pytest.raises(ValidationError, match="sunset"):
            DeprecationInfo(
                deprecated_at=date(2026, 9, 3),
                sunset_date=date(2026, 1, 1),
                notice="Bad ordering.",
            )

    def test_sunset_equal_deprecated_allowed(self) -> None:
        dep = DeprecationInfo(
            deprecated_at=date(2026, 9, 3),
            sunset_date=date(2026, 9, 3),
            notice="Same-day sunset.",
        )
        assert dep.sunset_date == dep.deprecated_at

    def test_either_date_none_allowed(self) -> None:
        dep = DeprecationInfo(deprecated_at=date(2026, 9, 3), notice="No firm sunset.")
        assert dep.sunset_date is None
        dep2 = DeprecationInfo(sunset_date=date(2027, 1, 1), notice="Unknown start.")
        assert dep2.deprecated_at is None


class TestRuntimeSunsetLifecycle:
    """BaseNode.run enforces deprecation lifecycle (DA-2305)."""

    def _request(self) -> NodeExecutionRequest:
        return NodeExecutionRequest(run_id="r1", node_id="n1", inputs={})

    def test_sunseted_node_refuses_to_run(self) -> None:
        node = _make_node(
            DeprecationInfo(
                deprecated_at=date(2025, 1, 1),
                sunset_date=datetime.now(UTC).date() - timedelta(days=1),
                replacement_slug="cds-file",
                notice="Sunset yesterday.",
            )
        )
        response = node.run(self._request())
        assert response.status == "fail"
        error_text = str(response.error)
        assert "was sunset" in error_text
        assert "cds-file" in error_text

    def test_sunset_refusal_is_structured_sdk161(self) -> None:
        """S.2: sunset refusal carries NODE_SUNSET + machine-readable details."""
        sunset_date = datetime.now(UTC).date() - timedelta(days=1)
        node = _make_node(
            DeprecationInfo(
                deprecated_at=date(2025, 1, 1),
                sunset_date=sunset_date,
                replacement_slug="cds-file",
                notice="Sunset yesterday.",
            )
        )
        try:
            node._check_deprecation_lifecycle()
            raise AssertionError("sunset must refuse")
        except NodeConfigurationError as exc:
            assert exc.error_code == "NODE_SUNSET"
            assert exc.category == "lifecycle"
            assert exc.details["sunset_date"] == sunset_date.isoformat()
            assert exc.details["replacement_slug"] == "cds-file"

    def test_sunset_day_is_inclusive_node_still_runs(self) -> None:
        """The sunset date itself is the last day of service (RFC 8594 reading)."""
        node = _make_node(
            DeprecationInfo(
                deprecated_at=datetime.now(UTC).date() - timedelta(days=30),
                sunset_date=datetime.now(UTC).date(),
                replacement_slug="cds-file",
                notice="Final day of service.",
            )
        )
        response = node.run(self._request())
        assert response.status == "pass"

    def test_deprecated_not_sunset_warns_and_passes(self, caplog: pytest.LogCaptureFixture) -> None:
        node = _make_node(
            DeprecationInfo(
                deprecated_at=datetime.now(UTC).date() - timedelta(days=30),
                sunset_date=datetime.now(UTC).date() + timedelta(days=365),
                replacement_slug="cds-file",
                notice="Deprecation window open.",
            )
        )
        with caplog.at_level(logging.WARNING, logger="canvastekk_workflow_sdk.base"):
            response = node.run(self._request())
        assert response.status == "pass"
        assert any("deprecated" in record.message and "cds-file" in record.message for record in caplog.records)

    def test_clean_node_no_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        node = _make_node(None)
        with caplog.at_level(logging.WARNING, logger="canvastekk_workflow_sdk.base"):
            response = node.run(self._request())
        assert response.status == "pass"
        assert not any("deprecated" in record.message for record in caplog.records)
