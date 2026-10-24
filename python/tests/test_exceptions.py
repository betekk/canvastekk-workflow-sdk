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
        assert d == {
            "error_code": "TEST",
            "category": "domain",
            "message": "msg",
            "details": {"a": 1},
        }

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
            "category": "timeout",
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


class TestErrorTaxonomySdk161:
    """S.2 (SDK#161): every exception classifies into exactly one category."""

    def test_categories_registry_is_the_five_axes(self) -> None:
        from canvastekk_workflow_sdk.exceptions import ERROR_CATEGORIES

        assert ERROR_CATEGORIES == (
            "transport",
            "validation",
            "domain",
            "timeout",
            "lifecycle",
        )

    def test_subclass_category_mapping(self) -> None:
        assert NodeTimeoutError(10).category == "timeout"
        assert NodeValidationError("x").category == "validation"
        assert NodeIOError("x").category == "transport"
        assert NodeConfigurationError("x").category == "lifecycle"

    def test_base_defaults_to_domain(self) -> None:
        assert NodeExecutionError("boom").category == "domain"

    def test_to_dict_carries_category(self) -> None:
        payload = NodeIOError("download failed").to_dict()
        assert payload["category"] == "transport"
        assert payload["error_code"] == "IO_ERROR"

    def test_workflow_exceptions_classified(self) -> None:
        from canvastekk_workflow_sdk.exceptions import (
            NodeOutputValidationError,
            WorkflowValidationError,
        )

        assert NodeOutputValidationError("x").category == "validation"
        assert WorkflowValidationError(["bad"]).category == "validation"


class TestErrorEnvelopeSdk161:
    """S.3 (SDK#161): the one {type, message, code} envelope shape."""

    def test_envelope_keys_constant(self) -> None:
        from canvastekk_workflow_sdk.exceptions import ERROR_ENVELOPE_KEYS

        assert ERROR_ENVELOPE_KEYS == ("type", "message", "code")

    def test_envelope_triple(self) -> None:
        from canvastekk_workflow_sdk import error_envelope

        envelope = error_envelope(NodeIOError("download failed"))
        assert envelope == {
            "type": "transport",
            "message": "download failed",
            "code": "IO_ERROR",
        }

    def test_envelope_on_subcoded_error(self) -> None:
        from canvastekk_workflow_sdk import error_envelope
        from canvastekk_workflow_sdk.exceptions import IO_SUBCODE_DOWNLOAD_FAILED

        err = NodeIOError("download failed", details={"sub_code": IO_SUBCODE_DOWNLOAD_FAILED})
        assert error_envelope(err)["code"] == "IO_ERROR"
        assert err.details["sub_code"] == "IO_DOWNLOAD_FAILED"
