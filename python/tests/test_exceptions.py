"""Tests for structured exception hierarchy."""

import pytest

from canvastekk_workflow_sdk.exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    NodeIOError,
    NodeTimeoutError,
    NodeValidationError,
    get_http_status_for_error,
)


class TestNodeExecutionError:
    def test_base_error(self) -> None:
        err = NodeExecutionError("something broke")
        assert str(err) == "something broke"
        assert err.message == "something broke"
        assert err.error_code == "EXECUTION_ERROR"
        assert err.details == {}

    def test_with_details(self) -> None:
        err = NodeExecutionError("fail", error_code="CUSTOM", details={"key": "val"})
        assert err.error_code == "CUSTOM"
        assert err.details == {"key": "val"}

    def test_to_dict(self) -> None:
        err = NodeExecutionError("msg", error_code="TEST", details={"a": 1})
        d = err.to_dict()
        assert d == {"error_code": "TEST", "message": "msg", "details": {"a": 1}}

    def test_is_exception(self) -> None:
        with pytest.raises(NodeExecutionError):
            raise NodeExecutionError("boom")


class TestNodeTimeoutError:
    def test_timeout_message(self) -> None:
        err = NodeTimeoutError(30)
        assert "30s" in str(err)
        assert err.timeout_seconds == 30
        assert err.error_code == "TIMEOUT"
        assert err.details == {"timeout_seconds": 30}

    def test_is_node_execution_error(self) -> None:
        err = NodeTimeoutError(60)
        assert isinstance(err, NodeExecutionError)

    def test_canonical_watchdog_details_contract(self) -> None:
        """#3499: the canonical details dict the CISA job_runner watchdog
        (#3500) POSTs on budget enforcement. Freezing the shape here makes
        the cross-repo contract explicit; raise-site canonical wiring lands
        with #3498 (execution_id source)."""
        details = {
            "slug": "ifc-cubicle-ledge",
            "execution_id": "ecs-0f2c6a1e-0000-4000-8000-000000000000",
            "run_id": "run-123",
            "declared_budget_s": 1800,
            "hard_ceiling_s": 1800,
            "enforced_at_s": 1710,
            "host": "ecs-job",
        }
        err = NodeTimeoutError(1710, details=details)
        assert err.error_code == "TIMEOUT"
        assert err.timeout_seconds == 1710
        assert err.details == details
        assert err.to_dict() == {
            "error_code": "TIMEOUT",
            "message": "Node execution timed out after 1710s",
            "details": details,
        }


class TestNodeValidationError:
    def test_validation_error_with_errors(self) -> None:
        errors = [{"path": ["field"], "message": "required"}]
        err = NodeValidationError("Validation failed", errors=errors)
        assert err.error_code == "VALIDATION_ERROR"
        assert err.errors == errors

    def test_to_dict_includes_errors(self) -> None:
        errors = [{"path": ["x"], "message": "bad"}]
        err = NodeValidationError("fail", errors=errors)
        d = err.to_dict()
        assert "errors" in d
        assert d["errors"] == errors

    def test_is_node_execution_error(self) -> None:
        assert isinstance(NodeValidationError("x"), NodeExecutionError)


class TestNodeIOError:
    def test_io_error_with_path(self) -> None:
        err = NodeIOError("file not found", path="/tmp/x.ply")
        assert err.error_code == "IO_ERROR"
        assert err.path == "/tmp/x.ply"
        assert err.details == {"path": "/tmp/x.ply"}

    def test_io_error_without_path(self) -> None:
        err = NodeIOError("io fail")
        assert err.path is None
        assert err.details == {}

    def test_is_node_execution_error(self) -> None:
        assert isinstance(NodeIOError("x"), NodeExecutionError)


class TestNodeConfigurationError:
    def test_config_error(self) -> None:
        err = NodeConfigurationError("bad config")
        assert err.error_code == "CONFIGURATION_ERROR"
        assert isinstance(err, NodeExecutionError)


class TestGetHttpStatusCode:
    def test_timeout_maps_to_408(self) -> None:
        assert get_http_status_for_error(NodeTimeoutError(10)) == 408

    def test_validation_maps_to_422(self) -> None:
        assert get_http_status_for_error(NodeValidationError("x")) == 422

    def test_io_maps_to_500(self) -> None:
        assert get_http_status_for_error(NodeIOError("x")) == 500

    def test_config_maps_to_500(self) -> None:
        assert get_http_status_for_error(NodeConfigurationError("x")) == 500

    def test_unknown_defaults_to_500(self) -> None:
        assert get_http_status_for_error(NodeExecutionError("x")) == 500
