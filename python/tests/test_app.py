"""Tests for FastAPI app factory."""

import os
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi import APIRouter, Depends, Request
from fastapi.testclient import TestClient

from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest, __version__, create_node_app


class EchoNode(BaseNode):
    """Simple echo node for testing."""

    definition = WorkflowNodeManifest(
        slug="echo",
        version="1.0.0",
        name="Echo",
        description="Returns input unchanged",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
        },
        token_cost=0.0,
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"message": inputs.get("message", "")}


class FileProcessingNode(BaseNode):
    """Node that accepts file uploads and scalar inputs."""

    definition = WorkflowNodeManifest(
        slug="file-proc",
        version="1.0.0",
        name="File Processor",
        description="Processes uploaded files",
        input_schema={
            "type": "object",
            "properties": {
                "point_cloud": {"type": "string", "format": "file", "description": "Point cloud file"},
                "threshold": {"type": "number", "default": 0.5},
                "iterations": {"type": "integer", "default": 10},
                "verbose": {"type": "boolean", "default": False},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "result_path": {"type": "string", "format": "file"},
            },
        },
        token_cost=0.0,
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        result: dict[str, Any] = {}
        if "point_cloud" in inputs:
            # Read the file content to verify it was saved correctly
            file_path = Path(inputs["point_cloud"])
            result["file_content"] = file_path.read_text() if file_path.exists() else ""
            result["file_name"] = file_path.name
        if "threshold" in inputs:
            result["threshold_used"] = inputs["threshold"]
        if "iterations" in inputs:
            result["iterations_used"] = inputs["iterations"]
        if "verbose" in inputs:
            result["verbose_used"] = inputs["verbose"]
        return result


class FailingNode(BaseNode):
    """Node that always fails."""

    definition = WorkflowNodeManifest(
        slug="failing",
        version="1.0.0",
        name="Failing",
        description="Always fails",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise ValueError("Intentional failure")


class DegradedNode(BaseNode):
    """Node with mixed health checks."""

    definition = WorkflowNodeManifest(
        slug="degraded",
        version="1.0.0",
        name="Degraded",
        description="Has degraded health",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {}

    def health_check(self) -> dict[str, Any]:
        return {
            "primary": True,
            "secondary": False,
        }


@pytest.fixture
def echo_client() -> TestClient:
    """Create test client for echo node."""
    node = EchoNode()
    app = create_node_app(node)
    return TestClient(app)


@pytest.fixture
def failing_client() -> TestClient:
    """Create test client for failing node."""
    node = FailingNode()
    app = create_node_app(node)
    return TestClient(app)


@pytest.fixture
def degraded_client() -> TestClient:
    """Create test client for degraded node."""
    node = DegradedNode()
    app = create_node_app(node)
    return TestClient(app)


class TestExecuteEndpoint:
    """Tests for POST /execute endpoint."""

    def test_execute_success(self, echo_client: TestClient) -> None:
        """Test successful execution."""
        response = echo_client.post(
            "/execute",
            json={
                "run_id": "test-run",
                "node_id": "test-node",
                "inputs": {"message": "Hello!"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pass"
        assert data["outputs"] == {"message": "Hello!"}
        assert data["error"] is None
        assert data["execution_id"] is not None
        assert data["duration_ms"] >= 0

    def test_execute_empty_inputs(self, echo_client: TestClient) -> None:
        """Test execution with empty inputs."""
        response = echo_client.post(
            "/execute",
            json={
                "run_id": "test-run",
                "node_id": "test-node",
                "inputs": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pass"
        assert data["outputs"] == {"message": ""}

    def test_execute_failure(self, failing_client: TestClient) -> None:
        """Test execution failure."""
        response = failing_client.post(
            "/execute",
            json={
                "run_id": "test-run",
                "node_id": "test-node",
                "inputs": {},
            },
        )
        assert response.status_code == 200  # Error is in response body, not HTTP status
        data = response.json()
        assert data["status"] == "fail"
        assert data["outputs"] is None
        assert data["error"] == "Intentional failure"
        assert data["error_type"] == "ValueError"

    def test_execute_with_presigned_url_input(self) -> None:
        """Test execution with presigned URL for file input field."""
        node = FileProcessingNode()
        client = TestClient(create_node_app(node))

        with tempfile.NamedTemporaryFile(suffix=".ply", delete=False, mode="w") as f:
            f.write("fake point cloud data")
            local_path = f.name

        try:
            response = client.post(
                "/execute",
                json={
                    "run_id": "run-1",
                    "node_id": "node-1",
                    "inputs": {
                        "point_cloud": local_path,
                    },
                },
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pass"
            assert "file_content" in data["outputs"]
        finally:
            os.unlink(local_path)


class TestHealthEndpoint:
    """Tests for GET /health endpoint."""

    def test_health_healthy(self, echo_client: TestClient) -> None:
        """Test health check for healthy node."""
        response = echo_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["node_id"] == "echo-v1.0.0"
        assert data["version"] == "1.0.0"

    def test_health_degraded(self, degraded_client: TestClient) -> None:
        """Test health check for degraded node."""
        response = degraded_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["checks"]["primary"] is True
        assert data["checks"]["secondary"] is False


class TestManifestBasic:
    """Basic tests for GET /manifest endpoint."""

    def test_manifest(self, echo_client: TestClient) -> None:
        """Test getting node manifest."""
        response = echo_client.get("/manifest")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "echo-v1.0.0"
        assert data["slug"] == "echo"
        assert data["version"] == "1.0.0"
        assert data["name"] == "Echo"
        assert data["description"] == "Returns input unchanged"
        assert data["token_cost"] == 0.0
        assert "input_schema" in data
        assert "output_schema" in data
        assert "default_retry" in data


class FileOutputNode(BaseNode):
    """Node that produces file outputs for S3 upload testing."""

    definition = WorkflowNodeManifest(
        slug="file-output",
        version="1.0.0",
        name="File Output",
        description="Produces a file output",
        input_schema={
            "type": "object",
            "properties": {"input_data": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "properties": {
                "result_path": {"type": "string", "format": "file"},
                "summary": {"type": "string"},
            },
        },
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        # Create a real temp file to simulate binary output
        fd, path = tempfile.mkstemp(suffix=".ply")
        os.close(fd)
        Path(path).write_bytes(b"fake binary output data")
        return {"result_path": path, "summary": "done"}


class FailingOutputNode(BaseNode):
    """Node that always fails — for testing S3 upload skip on failure."""

    definition = WorkflowNodeManifest(
        slug="fail-output",
        version="1.0.0",
        name="Fail Output",
        description="Always fails",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {
                "result_path": {"type": "string", "format": "file"},
            },
        },
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise RuntimeError("Node execution failed")


class BogusPathOutputNode(BaseNode):
    """Node whose file output points at a missing path (DA-2337)."""

    definition = WorkflowNodeManifest(
        slug="bogus-path-output",
        version="1.0.0",
        name="Bogus Path Output",
        description="Returns a file output that does not exist on disk",
        input_schema={"type": "object", "properties": {}},
        output_schema={
            "type": "object",
            "properties": {
                "result_path": {"type": "string", "format": "file"},
            },
        },
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"result_path": "/nonexistent/does-not-exist.ply"}


@pytest.fixture
def file_output_client() -> TestClient:
    """Create test client for file output node."""
    node = FileOutputNode()
    app = create_node_app(node)
    return TestClient(app)


@pytest.fixture
def failing_output_client() -> TestClient:
    """Create test client for failing output node."""
    node = FailingOutputNode()
    app = create_node_app(node)
    return TestClient(app)


@pytest.fixture
def bogus_path_output_client() -> TestClient:
    """Create test client for bogus-path output node (DA-2337)."""
    node = BogusPathOutputNode()
    app = create_node_app(node)
    return TestClient(app)


class TestOutputUploadToS3:
    """Tests for S3 output upload via pre-signed URLs."""

    def test_output_upload_url_triggers_s3_upload(self, file_output_client: TestClient) -> None:
        """When output_upload_url is provided and status=pass, upload_file is called."""
        with patch("canvastekk_workflow_sdk.uploads.S3PresignedUploader.upload_file") as mock_upload:
            response = file_output_client.post(
                "/execute",
                json={
                    "run_id": "run-1",
                    "node_id": "node-1",
                    "inputs": {"input_data": "test"},
                    "output_upload_url": {
                        "result_path": "https://s3.amazonaws.com/presigned-put",
                    },
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pass"

            mock_upload.assert_called_once()
            call_args = mock_upload.call_args
            assert call_args[0][1] == "https://s3.amazonaws.com/presigned-put"
            uploaded_file = call_args[0][0]
            assert uploaded_file == data["outputs"]["result_path"]

    def test_output_upload_url_skipped_on_failure(self, failing_output_client: TestClient) -> None:
        """When node returns status=fail, upload_file should NOT be called."""
        with patch("canvastekk_workflow_sdk.uploads.S3PresignedUploader.upload_file") as mock_upload:
            response = failing_output_client.post(
                "/execute",
                json={
                    "run_id": "run-1",
                    "node_id": "node-1",
                    "inputs": {},
                    "output_upload_url": {
                        "result_path": "https://s3.amazonaws.com/presigned-put",
                    },
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "fail"

            # Upload should NOT have been called
            mock_upload.assert_not_called()

    def test_missing_file_output_fails_with_upload_failed(self, bogus_path_output_client: TestClient) -> None:
        """A passing node whose file output is not a local file fails (DA-2337).

        Pins the app.py seam: the uploader's NodeIOError converts to
        fail/UPLOAD_FAILED instead of a silent pass (or a raw 500 if the
        broad except is ever narrowed).
        """
        response = bogus_path_output_client.post(
            "/execute",
            json={
                "run_id": "run-1",
                "node_id": "node-1",
                "inputs": {},
                "output_upload_url": {
                    "result_path": "https://s3.amazonaws.com/presigned-put",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fail"
        assert data["error_code"] == "UPLOAD_FAILED"
        assert "result_path" in data["error"]

    def test_output_upload_url_skipped_when_not_provided(self, file_output_client: TestClient) -> None:
        """When output_upload_url is None, no upload is attempted."""
        with patch("canvastekk_workflow_sdk.uploads.S3PresignedUploader.upload_file") as mock_upload:
            response = file_output_client.post(
                "/execute",
                json={
                    "run_id": "run-1",
                    "node_id": "node-1",
                    "inputs": {"input_data": "test"},
                },
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pass"

            # No upload should happen
            mock_upload.assert_not_called()

    def test_legacy_string_target_fails_with_upload_failed(self, file_output_client: TestClient) -> None:
        """A legacy presigned-PUT string target fails the execution (DA-3340).

        No mocking: the real upload_file sees the string and raises
        NodeIOError, which the app seam converts to fail/UPLOAD_FAILED.
        """
        response = file_output_client.post(
            "/execute",
            json={
                "run_id": "run-1",
                "node_id": "node-1",
                "inputs": {"input_data": "test"},
                "output_upload_url": {
                    "result_path": "https://s3.amazonaws.com/presigned-put",
                },
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fail"
        assert data["error_code"] == "UPLOAD_FAILED"
        assert "engine sent deprecated presigned target" in data["error"]


class TestAsyncExecution:
    """Tests for async execution with asyncio.to_thread (Phase 1)."""

    def test_execute_endpoint_works_with_async_wrapper(self, echo_client: TestClient) -> None:
        """Test that POST /execute works correctly with asyncio.to_thread wrapping."""
        response = echo_client.post(
            "/execute",
            json={
                "run_id": "test-run",
                "node_id": "test-node",
                "inputs": {"message": "Async test"},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "pass"
        assert data["outputs"] == {"message": "Async test"}
        assert data["error"] is None
        assert data["execution_id"] is not None

    def test_execute_with_failure_still_works_with_async_wrapper(self, failing_client: TestClient) -> None:
        """Test that execution failures are correctly handled with async wrapper."""
        response = failing_client.post(
            "/execute",
            json={
                "run_id": "test-run",
                "node_id": "test-node",
                "inputs": {},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "fail"
        assert data["outputs"] is None
        assert data["error"] == "Intentional failure"
        assert data["error_type"] == "ValueError"


class TestDependencyInjection:
    """Tests for FastAPI dependency injection (Phase 2)."""

    def test_dependency_applied_to_all_endpoints(self) -> None:
        """Test that a custom dependency is invoked on all endpoints."""
        dependency_invocations: list[str] = []

        def custom_dependency(request: Request) -> None:
            dependency_invocations.append(request.url.path)

        node = EchoNode()
        app = create_node_app(node, dependencies=[Depends(custom_dependency)])
        client = TestClient(app)

        client.get("/health")
        client.get("/manifest")
        client.get("/metrics")
        client.post("/execute", json={"run_id": "r1", "node_id": "n1", "inputs": {"message": "test"}})
        client.post("/hook", json={"event": "test"})

        assert "/health" in dependency_invocations
        assert "/manifest" in dependency_invocations
        assert "/metrics" in dependency_invocations
        assert "/execute" in dependency_invocations
        assert "/hook" in dependency_invocations

    def test_dependency_rejects_invalid_request(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that a dependency can reject requests."""
        monkeypatch.setenv("CANVASTEKK_API_KEY", "correct-key")

        from canvastekk_workflow_sdk.auth import NodeAuth

        auth = NodeAuth.api_key()
        node = EchoNode()
        app = create_node_app(node, dependencies=[Depends(auth)])
        client = TestClient(app)

        response = client.get("/health", headers={})
        assert response.status_code == 401

        response = client.get("/health", headers={"X-API-Key": "correct-key"})
        assert response.status_code == 200

    def test_multiple_dependencies_all_invoked(self) -> None:
        """Test that multiple dependencies are all invoked."""
        dependency_order: list[str] = []

        def dep1(request: Request) -> None:
            dependency_order.append("dep1")

        def dep2(request: Request) -> None:
            dependency_order.append("dep2")

        node = EchoNode()
        app = create_node_app(node, dependencies=[Depends(dep1), Depends(dep2)])
        client = TestClient(app)

        client.get("/health")
        assert dependency_order == ["dep1", "dep2"]

    def test_empty_dependencies_list(self) -> None:
        """Test that empty dependencies list works."""
        node = EchoNode()
        app = create_node_app(node, dependencies=[])
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200


class TestExtraRoutes:
    """Tests for extra routes feature (Phase 2)."""

    def test_extra_route_accessible(self) -> None:
        """Test that a custom route is accessible on the created app."""
        extra_router = APIRouter(prefix="/custom", tags=["Custom"])

        @extra_router.get("/info")
        def custom_info() -> dict[str, str]:
            return {"message": "Custom endpoint"}

        node = EchoNode()
        app = create_node_app(node, extra_routes=[extra_router])
        client = TestClient(app)

        response = client.get("/custom/info")
        assert response.status_code == 200
        assert response.json() == {"message": "Custom endpoint"}

    def test_multiple_extra_routes_accessible(self) -> None:
        """Test that multiple extra routers are all accessible."""
        router1 = APIRouter(prefix="/api/v1", tags=["V1"])

        @router1.get("/data")
        def get_v1_data() -> dict[str, str]:
            return {"version": "v1"}

        router2 = APIRouter(prefix="/api/v2", tags=["V2"])

        @router2.get("/data")
        def get_v2_data() -> dict[str, str]:
            return {"version": "v2"}

        node = EchoNode()
        app = create_node_app(node, extra_routes=[router1, router2])
        client = TestClient(app)

        response1 = client.get("/api/v1/data")
        assert response1.status_code == 200
        assert response1.json() == {"version": "v1"}

        response2 = client.get("/api/v2/data")
        assert response2.status_code == 200
        assert response2.json() == {"version": "v2"}

    def test_standard_routes_still_work_with_extra_routes(self) -> None:
        """Test that standard routes still work when extra routes are added."""
        extra_router = APIRouter(prefix="/extra")

        @extra_router.get("/test")
        def extra_test() -> dict[str, str]:
            return {"extra": "route"}

        node = EchoNode()
        app = create_node_app(node, extra_routes=[extra_router])
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200

        response = client.get("/manifest")
        assert response.status_code == 200

        response = client.get("/metrics")
        assert response.status_code == 200

    def test_extra_routes_with_dependencies(self) -> None:
        """Test that extra routes work alongside app dependencies."""
        dependency_invoked: list[bool] = []

        def custom_dependency(request: Request) -> None:
            dependency_invoked.append(True)

        extra_router = APIRouter(prefix="/custom")

        @extra_router.get("/test")
        def custom_test() -> dict[str, str]:
            return {"test": "data"}

        node = EchoNode()
        app = create_node_app(node, dependencies=[Depends(custom_dependency)], extra_routes=[extra_router])
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        assert len(dependency_invoked) == 1

        response = client.get("/custom/test")
        assert response.status_code == 200
        assert len(dependency_invoked) == 1

    def test_empty_extra_routes_list(self) -> None:
        """Test that empty extra routes list works."""
        node = EchoNode()
        app = create_node_app(node, extra_routes=[])
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200


class TestApiKeyAuthIntegration:
    """Tests for API Key authentication integration with FastAPI endpoints (Phase 2)."""

    def test_api_key_auth_allows_valid_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that valid API key allows access to all endpoints."""
        from canvastekk_workflow_sdk.auth import NodeAuth

        monkeypatch.setenv("CANVASTEKK_API_KEY", "test-secret-key")

        auth = NodeAuth.api_key()
        node = EchoNode()
        app = create_node_app(node, dependencies=[Depends(auth)])
        client = TestClient(app)

        headers = {"X-API-Key": "test-secret-key"}

        response = client.get("/health", headers=headers)
        assert response.status_code == 200

        response = client.get("/manifest", headers=headers)
        assert response.status_code == 200

        response = client.get("/metrics", headers=headers)
        assert response.status_code == 200

        response = client.post(
            "/execute", json={"run_id": "r1", "node_id": "n1", "inputs": {"message": "test"}}, headers=headers
        )
        assert response.status_code == 200

        response = client.post("/hook", json={"event": "test"}, headers=headers)
        assert response.status_code == 501

    def test_api_key_auth_rejects_invalid_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that invalid API key is rejected."""
        from canvastekk_workflow_sdk.auth import NodeAuth

        monkeypatch.setenv("CANVASTEKK_API_KEY", "correct-key")

        auth = NodeAuth.api_key()
        node = EchoNode()
        app = create_node_app(node, dependencies=[Depends(auth)])
        client = TestClient(app)

        headers = {"X-API-Key": "wrong-key"}

        response = client.get("/health", headers=headers)
        assert response.status_code == 401

        response = client.post(
            "/execute", json={"run_id": "r1", "node_id": "n1", "inputs": {"message": "test"}}, headers=headers
        )
        assert response.status_code == 401

    def test_api_key_auth_rejects_missing_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that missing API key is rejected."""
        from canvastekk_workflow_sdk.auth import NodeAuth

        monkeypatch.setenv("CANVASTEKK_API_KEY", "test-key")

        auth = NodeAuth.api_key()
        node = EchoNode()
        app = create_node_app(node, dependencies=[Depends(auth)])
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 401

    def test_api_key_auth_rejects_when_env_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that auth is rejected when env var is not set."""
        from canvastekk_workflow_sdk.auth import NodeAuth

        monkeypatch.delenv("CANVASTEKK_API_KEY", raising=False)

        auth = NodeAuth.api_key()
        node = EchoNode()
        app = create_node_app(node, dependencies=[Depends(auth)])
        client = TestClient(app)

        headers = {"X-API-Key": "any-key"}

        response = client.get("/health", headers=headers)
        assert response.status_code == 401

    def test_api_key_auth_bypass_in_dev_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test that dev mode bypasses API key authentication."""
        from canvastekk_workflow_sdk.auth import NodeAuth

        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "true")
        monkeypatch.delenv("CANVASTEKK_API_KEY", raising=False)

        auth = NodeAuth.api_key()
        node = EchoNode()
        app = create_node_app(node, dependencies=[Depends(auth)])
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200

    def test_api_key_auth_custom_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test API key auth with custom env var name."""
        from canvastekk_workflow_sdk.auth import NodeAuth

        monkeypatch.setenv("MY_CUSTOM_API_KEY", "custom-secret")

        auth = NodeAuth.api_key(key_env_var="MY_CUSTOM_API_KEY")
        node = EchoNode()
        app = create_node_app(node, dependencies=[Depends(auth)])
        client = TestClient(app)

        headers = {"X-API-Key": "custom-secret"}

        response = client.get("/health", headers=headers)
        assert response.status_code == 200


class TestIntegrationLifecycle:
    """Full integration test: auth + execute + S3 upload + lifecycle hooks."""

    def test_full_lifecycle_with_api_key_auth_and_s3_upload(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from canvastekk_workflow_sdk.auth import NodeAuth

        monkeypatch.setenv("CANVASTEKK_API_KEY", "test-integration-key")

        auth = NodeAuth.api_key()
        node = FileOutputNode()
        startup_called: list[bool] = []
        shutdown_called: list[bool] = []

        original_startup = node.on_startup
        original_shutdown = node.on_shutdown

        async def custom_startup() -> None:
            startup_called.append(True)
            await original_startup()

        async def custom_shutdown() -> None:
            shutdown_called.append(True)
            await original_shutdown()

        node.on_startup = custom_startup
        node.on_shutdown = custom_shutdown

        app = create_node_app(node, dependencies=[Depends(auth)])
        headers = {"X-API-Key": "test-integration-key"}

        with TestClient(app) as client:
            assert startup_called

            response = client.get("/health", headers=headers)
            assert response.status_code == 200
            assert response.json()["status"] == "healthy"

            response = client.get("/manifest", headers=headers)
            assert response.status_code == 200
            assert response.json()["slug"] == "file-output"

            with patch("canvastekk_workflow_sdk.uploads.S3PresignedUploader.upload_file") as mock_upload:
                response = client.post(
                    "/execute",
                    json={
                        "run_id": "integration-run",
                        "node_id": "integration-node",
                        "inputs": {"input_data": "integration test"},
                        "output_upload_url": {
                            "result_path": "https://s3.amazonaws.com/presigned-put",
                        },
                    },
                    headers=headers,
                )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "pass"
            assert data["outputs"]["summary"] == "done"
            mock_upload.assert_called_once()

            response = client.get(
                "/execute",
                headers=headers,
            )
            assert response.status_code == 405

            no_auth_response = client.post(
                "/execute",
                json={
                    "run_id": "integration-run",
                    "node_id": "integration-node",
                    "inputs": {"input_data": "should fail"},
                },
            )
            assert no_auth_response.status_code == 401

        assert shutdown_called


class TestManifestEndpoint:
    def test_manifest_includes_sdk_version(self, echo_client: TestClient) -> None:
        response = echo_client.get("/manifest")
        assert response.status_code == 200
        data = response.json()
        assert "sdk_version" in data
        assert data["sdk_version"] == __version__

    def test_manifest_includes_node_fields(self, echo_client: TestClient) -> None:
        response = echo_client.get("/manifest")
        data = response.json()
        assert data["slug"] == "echo"
        assert data["version"] == "1.0.0"
        assert data["id"] == "echo-v1.0.0"
        assert "input_schema" in data
        assert "output_schema" in data

    def test_manifest_defaults_to_dev_mode(self, echo_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CANVASTEKK_NODE_ENV", raising=False)
        response = echo_client.get("/manifest")
        assert response.json()["mode"] == "dev"

    def test_manifest_dev_mode(self, echo_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_NODE_ENV", "dev")
        response = echo_client.get("/manifest")
        assert response.json()["mode"] == "dev"

    def test_manifest_development_mode(self, echo_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_NODE_ENV", "development")
        response = echo_client.get("/manifest")
        assert response.json()["mode"] == "dev"

    def test_manifest_staging_mode(self, echo_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_NODE_ENV", "staging")
        response = echo_client.get("/manifest")
        assert response.json()["mode"] == "uat"

    def test_manifest_uat_mode(self, echo_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_NODE_ENV", "uat")
        response = echo_client.get("/manifest")
        assert response.json()["mode"] == "uat"

    def test_manifest_production_mode(self, echo_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_NODE_ENV", "production")
        response = echo_client.get("/manifest")
        assert response.json()["mode"] == "production"

    def test_manifest_unknown_env_maps_to_production(
        self, echo_client: TestClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CANVASTEKK_NODE_ENV", "qa")
        response = echo_client.get("/manifest")
        assert response.json()["mode"] == "production"


class TestSDKVersionHeader:
    def test_sdk_version_header_on_execute(self, echo_client: TestClient) -> None:
        response = echo_client.post(
            "/execute",
            json={"run_id": "r1", "node_id": "n1", "inputs": {"message": "hi"}},
        )
        assert response.headers.get("x-sdk-version") == __version__

    def test_sdk_version_header_on_manifest(self, echo_client: TestClient) -> None:
        response = echo_client.get("/manifest")
        assert response.headers.get("x-sdk-version") == __version__

    def test_sdk_version_header_on_health(self, echo_client: TestClient) -> None:
        response = echo_client.get("/health")
        assert response.headers.get("x-sdk-version") == __version__


class TestLivenessProbe:
    def test_liveness_returns_200(self, echo_client: TestClient) -> None:
        response = echo_client.get("/live")
        assert response.status_code == 200
        assert response.json() == {"status": "alive"}


class TestReadinessProbe:
    def test_readiness_returns_200_when_no_checks(self, echo_client: TestClient) -> None:
        response = echo_client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert data["checks"] == {}

    def test_readiness_returns_200_when_all_checks_pass(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class HealthyNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="healthy",
                version="1.0.0",
                name="Healthy",
                description="Always healthy",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            def health_check(self) -> dict[str, Any]:
                return {"db": True, "cache": True}

            def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
                return {}

        client = TestClient(create_node_app(HealthyNode()))
        response = client.get("/ready")
        assert response.status_code == 200
        assert response.json()["status"] == "ready"

    def test_readiness_returns_503_when_check_fails(self) -> None:
        class UnhealthyNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="unhealthy",
                version="1.0.0",
                name="Unhealthy",
                description="Always unhealthy",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            def health_check(self) -> dict[str, Any]:
                return {"db": True, "model": False}

            def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
                return {}

        client = TestClient(create_node_app(UnhealthyNode()))
        response = client.get("/ready")
        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"


class TestBodyLimitAndRedaction:
    """DA-1711 3.2/3.3: body-limit middleware, 4xx body-parse mapping,
    generic 500s."""

    def test_oversized_body_rejected_413(self, echo_client, monkeypatch):
        import json as jsonlib

        monkeypatch.setenv("CANVASTEKK_MAX_BODY_BYTES", "1000")
        big = "x" * 2000
        resp = echo_client.post(
            "/execute",
            content=jsonlib.dumps({"run_id": "r1", "node_id": "n1", "inputs": {"msg": big}}),
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 413

    def test_list_body_rejected_422(self, echo_client):
        resp = echo_client.post(
            "/execute",
            content="[1,2,3]",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_invalid_fields_rejected_422(self, echo_client):
        resp = echo_client.post(
            "/execute",
            content='{"run_id": "../../etc", "node_id": "n1"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422

    def test_hook_invalid_json_400(self, echo_client):
        resp = echo_client.post("/hook", content="not json", headers={"Content-Type": "application/json"})
        assert resp.status_code == 400

    def test_traversal_run_id_rejected_422(self, echo_client):
        resp = echo_client.post(
            "/execute",
            content='{"run_id": "../../etc", "node_id": "n1", "inputs": {}}',
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422


class TestCreateNodeAppAuthParam:
    """Tests for the auth= shorthand on create_node_app (DA-1955)."""

    def test_api_key_shorthand_requires_key_on_execute(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """auth='api-key' rejects unauthenticated /execute and accepts the key."""

        monkeypatch.setenv("CANVASTEKK_API_KEY", "test-key-123")
        app = create_node_app(EchoNode(), auth="api-key")
        client = TestClient(app)

        unauthenticated = client.post("/execute", json={"run_id": "r1", "node_id": "n1", "inputs": {}})
        assert unauthenticated.status_code == 401

        authenticated = client.post(
            "/execute",
            json={"run_id": "r1", "node_id": "n1", "inputs": {}},
            headers={"X-API-Key": "test-key-123"},
        )
        assert authenticated.status_code == 200

    def test_auth_none_keeps_current_behavior(self) -> None:
        """auth=None leaves every endpoint unauthenticated (default)."""
        app = create_node_app(EchoNode(), auth=None)
        client = TestClient(app)

        resp = client.post("/execute", json={"run_id": "r1", "node_id": "n1", "inputs": {}})
        assert resp.status_code == 200

    def test_node_auth_instance_honored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicit NodeAuth instance is used directly."""
        from canvastekk_workflow_sdk.auth import NodeAuth

        monkeypatch.setenv("CANVASTEKK_API_KEY", "test-key-123")
        app = create_node_app(EchoNode(), auth=NodeAuth.api_key())
        client = TestClient(app)

        with_key = client.post(
            "/execute",
            json={"run_id": "r1", "node_id": "n1", "inputs": {}},
            headers={"X-API-Key": "test-key-123"},
        )
        assert with_key.status_code == 200

    def test_unknown_shorthand_raises(self) -> None:
        """Unknown strings raise ValueError with the valid options."""
        with pytest.raises(ValueError, match="api-key"):
            create_node_app(EchoNode(), auth="oauth")  # type: ignore[arg-type]

    def test_dependencies_and_auth_merge(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Custom dependencies and auth coexist on the same router."""
        from fastapi import Depends

        monkeypatch.setenv("CANVASTEKK_API_KEY", "test-key-123")
        calls: list[str] = []

        def custom_dep() -> None:
            calls.append("custom_dep")

        app = create_node_app(EchoNode(), dependencies=[Depends(custom_dep)], auth="api-key")
        client = TestClient(app)

        resp = client.post(
            "/execute",
            json={"run_id": "r1", "node_id": "n1", "inputs": {}},
            headers={"X-API-Key": "test-key-123"},
        )
        assert resp.status_code == 200
        assert calls == ["custom_dep"]

    def test_auth_skipped_when_dependencies_already_authed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Existing auth backend in dependencies wins; auth= is skipped."""
        from canvastekk_workflow_sdk.auth import NodeAuth

        monkeypatch.setenv("CANVASTEKK_API_KEY", "test-key-123")
        explicit = NodeAuth.api_key()
        app = create_node_app(EchoNode(), dependencies=[Depends(explicit)], auth="api-key")
        client = TestClient(app)

        with_key = client.post(
            "/execute",
            json={"run_id": "r1", "node_id": "n1", "inputs": {}},
            headers={"X-API-Key": "test-key-123"},
        )
        assert with_key.status_code == 200


class AccountEchoNode(BaseNode):
    """Echoes context.account_id into outputs (DA-2242 header-capture tests)."""

    definition = WorkflowNodeManifest(
        slug="account-echo",
        version="1.0.0",
        name="Account Echo",
        description="Returns context.account_id",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"account_id": context.account_id}


@pytest.fixture
def account_client() -> TestClient:
    """TestClient around an AccountEchoNode /execute endpoint."""
    return TestClient(create_node_app(AccountEchoNode()))


class TestAccountIdHeaderPropagation:
    """DA-2242: X-Account-Id header is the EXCLUSIVE account_id source."""

    _BODY = {"run_id": "r1", "node_id": "n1", "inputs": {}}

    def test_valid_header_reaches_context(self, account_client: TestClient) -> None:
        resp = account_client.post("/execute", json=self._BODY, headers={"X-Account-Id": "42"})
        assert resp.status_code == 200
        assert resp.json()["outputs"] == {"account_id": 42}

    def test_lowercase_header_variant(self, account_client: TestClient) -> None:
        resp = account_client.post("/execute", json=self._BODY, headers={"x-account-id": "7"})
        assert resp.status_code == 200
        assert resp.json()["outputs"] == {"account_id": 7}

    def test_absent_header_yields_none(self, account_client: TestClient) -> None:
        resp = account_client.post("/execute", json=self._BODY)
        assert resp.status_code == 200
        assert resp.json()["outputs"] == {"account_id": None}

    def test_empty_header_treated_as_absent(self, account_client: TestClient) -> None:
        resp = account_client.post("/execute", json=self._BODY, headers={"X-Account-Id": "  "})
        assert resp.status_code == 200
        assert resp.json()["outputs"] == {"account_id": None}

    def test_malformed_header_400(self, account_client: TestClient) -> None:
        resp = account_client.post("/execute", json=self._BODY, headers={"X-Account-Id": "abc"})
        assert resp.status_code == 400

    def test_negative_header_400(self, account_client: TestClient) -> None:
        resp = account_client.post("/execute", json=self._BODY, headers={"X-Account-Id": "-1"})
        assert resp.status_code == 400

    def test_zero_header_400(self, account_client: TestClient) -> None:
        resp = account_client.post("/execute", json=self._BODY, headers={"X-Account-Id": "0"})
        assert resp.status_code == 400

    def test_out_of_range_header_400(self, account_client: TestClient) -> None:
        resp = account_client.post("/execute", json=self._BODY, headers={"X-Account-Id": str(2**63)})
        assert resp.status_code == 400

    def test_absurdly_long_header_400_not_500(self, account_client: TestClient) -> None:
        """CVE-2020-10735: >19-digit strings are rejected before int() — no 500."""
        resp = account_client.post("/execute", json=self._BODY, headers={"X-Account-Id": "1" * 5000})
        assert resp.status_code == 400

    def test_upper_boundary_accepted(self, account_client: TestClient) -> None:
        resp = account_client.post("/execute", json=self._BODY, headers={"X-Account-Id": str(2**63 - 1)})
        assert resp.status_code == 200
        assert resp.json()["outputs"] == {"account_id": 2**63 - 1}

    def test_body_account_id_ignored_without_header(self, account_client: TestClient) -> None:
        """Spoof guard: body-supplied account_id is stripped."""
        body = {**self._BODY, "account_id": 999}
        resp = account_client.post("/execute", json=body)
        assert resp.status_code == 200
        assert resp.json()["outputs"] == {"account_id": None}

    def test_header_wins_over_conflicting_body(self, account_client: TestClient) -> None:
        body = {**self._BODY, "account_id": 999}
        resp = account_client.post("/execute", json=body, headers={"X-Account-Id": "42"})
        assert resp.status_code == 200
        assert resp.json()["outputs"] == {"account_id": 42}


class TestManifestCodeDigest:
    """DA-2603: code_digest is auto-injected, stable, and source-sensitive."""

    def test_manifest_serves_code_digest(self, echo_client: TestClient) -> None:
        data = echo_client.get("/manifest").json()
        assert len(data["code_digest"]) == 64
        int(data["code_digest"], 16)  # 64-char hex
        # Stable across calls (computed once at startup)
        assert echo_client.get("/manifest").json()["code_digest"] == data["code_digest"]

    def test_manifest_still_serves_sdk_version_and_mode(self, echo_client: TestClient) -> None:
        data = echo_client.get("/manifest").json()
        assert "sdk_version" in data
        assert data["mode"] in ("dev", "uat", "production")

    def test_digest_changes_when_handler_source_changes(self, tmp_path, monkeypatch) -> None:
        import importlib
        import sys

        from fastapi.testclient import TestClient

        from canvastekk_workflow_sdk.app import create_node_app

        from .test_base import EchoNode  # noqa: F401  (ensure echo import path exists)

        mod_dir = tmp_path / "digestmod"
        mod_dir.mkdir()
        (mod_dir / "__init__.py").write_text("")
        mod_file = mod_dir / "handler.py"

        def _build_app(body: str):
            mod_file.write_text(body)
            monkeypatch.syspath_prepend(str(tmp_path))
            if "digestmod.handler" in sys.modules:
                del sys.modules["digestmod.handler"]
            module = importlib.import_module("digestmod.handler")
            return create_node_app(module.DigestNode())

        base = (
            "from canvastekk_workflow_sdk import BaseNode, WorkflowNodeManifest\n"
            "class DigestNode(BaseNode):\n"
            "    definition = WorkflowNodeManifest(\n"
            "        slug='digest-node', version='1.0.0', name='Digest',\n"
            "        description='digest probe',\n"
            "        input_schema={'type': 'object'},\n"
            "        output_schema={'type': 'object'},\n"
            "    )\n"
        )
        app_a = _build_app(base + "    def execute(self, inputs):\n        return inputs\n")
        app_b = _build_app(base + "    def execute(self, inputs):\n        return inputs  # b\n")
        digest_a = TestClient(app_a).get("/manifest").json()["code_digest"]
        digest_b = TestClient(app_b).get("/manifest").json()["code_digest"]
        assert digest_a != digest_b
        assert len(digest_a) == 64 and len(digest_b) == 64


class HangingNode(BaseNode):
    """Sleeps past its budget — drives the inline wait_for timeout path."""

    definition = WorkflowNodeManifest(
        slug="hang",
        version="1.0.0",
        name="Hang",
        description="Never finishes in time",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        timeout_seconds=1,
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        import time

        time.sleep(5)
        return {}


class TestInlineTimeoutDetails:
    """#3498: the inline raise site emits the #3499 canonical details —
    all 7 keys present, execution_id null when the request carried none."""

    def _client(self) -> TestClient:
        app = create_node_app(HangingNode())
        return TestClient(app, raise_server_exceptions=False)

    def test_timeout_details_canonical_null_execution_id(self) -> None:
        resp = self._client().post("/execute", json={"run_id": "r-hang", "node_id": "n-hang", "inputs": {}})
        assert resp.status_code == 408  # TIMEOUT → 408 (ERROR_CODE_TO_HTTP_STATUS)
        body = resp.json()
        assert body["error_code"] == "TIMEOUT"
        # the handler spreads details flat into the body (app.py node_error_handler)
        assert body["slug"] == "hang"
        assert body["execution_id"] is None  # key present, value null
        assert body["declared_budget_s"] == 1
        assert body["hard_ceiling_s"] == 7200
        assert body["enforced_at_s"] == 1
        assert body["host"] == "inline-lambda"

    def test_timeout_details_carry_provided_execution_id(self) -> None:
        resp = self._client().post(
            "/execute",
            json={"run_id": "r-hang", "node_id": "n-hang", "inputs": {}, "execution_id": "ecs-99"},
        )
        assert resp.json()["execution_id"] == "ecs-99"
