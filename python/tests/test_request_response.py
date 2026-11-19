"""Tests for request and response models."""

from canvastekk_workflow_sdk.node_execution_request import NodeExecutionRequest
from canvastekk_workflow_sdk.node_execution_response import NodeExecutionResponse, WorkflowNodeHealthResponse


class TestNodeExecutionRequest:
    def test_minimal(self) -> None:
        req = NodeExecutionRequest(run_id="r1", node_id="n1")
        assert req.run_id == "r1"
        assert req.node_id == "n1"
        assert req.inputs == {}
        assert req.callback_url is None
        assert req.output_upload_url is None

    def test_with_inputs(self) -> None:
        req = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"message": "hello"},
        )
        assert req.inputs == {"message": "hello"}

    def test_with_callback_url(self) -> None:
        req = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            callback_url="https://example.com/callback",
        )
        assert req.callback_url == "https://example.com/callback"

    def test_with_output_upload_url(self) -> None:
        req = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            output_upload_url={"result": "https://s3.example.com/presigned"},
        )
        assert req.output_upload_url == {"result": "https://s3.example.com/presigned"}

    def test_from_dict(self) -> None:
        data = {
            "run_id": "r1",
            "node_id": "n1",
            "inputs": {"a": 1},
            "callback_url": "https://example.com",
        }
        req = NodeExecutionRequest.model_validate(data)
        assert req.run_id == "r1"
        assert req.inputs == {"a": 1}
        assert req.callback_url == "https://example.com"

    def test_serialization_roundtrip(self) -> None:
        req = NodeExecutionRequest(
            run_id="r1",
            node_id="n1",
            inputs={"key": "val"},
            output_upload_url={"file": "https://s3.example.com/upload"},
        )
        data = req.model_dump()
        restored = NodeExecutionRequest.model_validate(data)
        assert restored == req


class TestNodeExecutionResponse:
    def test_success_response(self) -> None:
        resp = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"result": "ok"},
            duration_ms=100,
            token_usage=5.0,
        )
        assert resp.status == "pass"
        assert resp.outputs == {"result": "ok"}
        assert resp.duration_ms == 100
        assert resp.token_usage == 5.0
        assert resp.error is None
        assert resp.error_type is None
        assert resp.error_code is None

    def test_success_defaults(self) -> None:
        resp = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={},
        )
        assert resp.duration_ms == 0
        assert resp.token_usage == 0.0

    def test_failure_response(self) -> None:
        resp = NodeExecutionResponse.failure(
            execution_id="exec-2",
            error="something broke",
            error_type="ValueError",
            duration_ms=50,
            error_code="EXECUTION_ERROR",
        )
        assert resp.status == "fail"
        assert resp.outputs is None
        assert resp.error == "something broke"
        assert resp.error_type == "ValueError"
        assert resp.error_code == "EXECUTION_ERROR"
        assert resp.token_usage == 0.0

    def test_failure_without_error_code(self) -> None:
        resp = NodeExecutionResponse.failure(
            execution_id="exec-3",
            error="generic error",
            error_type="RuntimeError",
        )
        assert resp.error_code is None

    def test_serialization_roundtrip(self) -> None:
        resp = NodeExecutionResponse.success(
            execution_id="exec-1",
            outputs={"data": [1, 2, 3]},
            duration_ms=200,
            token_usage=10.5,
        )
        data = resp.model_dump()
        restored = NodeExecutionResponse.model_validate(data)
        assert restored.status == "pass"
        assert restored.outputs == {"data": [1, 2, 3]}
        assert restored.token_usage == 10.5

    def test_failure_serialization(self) -> None:
        resp = NodeExecutionResponse.failure(
            execution_id="exec-4",
            error="timeout",
            error_type="NodeTimeoutError",
            error_code="TIMEOUT",
        )
        data = resp.model_dump()
        assert data["status"] == "fail"
        assert data["error_code"] == "TIMEOUT"
        assert data["outputs"] is None


class TestHealthResponse:
    def test_healthy(self) -> None:
        resp = WorkflowNodeHealthResponse(
            status="healthy",
            node_id="test-v1",
            version="1.0.0",
            checks={"api": True, "db": True},
        )
        assert resp.status == "healthy"
        assert resp.node_id == "test-v1"
        assert resp.checks == {"api": True, "db": True}

    def test_degraded(self) -> None:
        resp = WorkflowNodeHealthResponse(
            status="degraded",
            node_id="test-v1",
            version="1.0.0",
            checks={"primary": True, "secondary": False},
        )
        assert resp.status == "degraded"

    def test_default_checks(self) -> None:
        resp = WorkflowNodeHealthResponse(
            status="healthy",
            node_id="test-v1",
            version="1.0.0",
        )
        assert resp.checks == {}
