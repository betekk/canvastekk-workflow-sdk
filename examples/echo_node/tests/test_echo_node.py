"""
Tests for Echo Node example.

Demonstrates unit and integration testing patterns for nodes with file I/O.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient
from handler import EchoNode, app, manifest

from canvastekk_workflow_sdk import NodeExecutionRequest


class _MockStreamResponse:
    """Minimal httpx.StreamResponse stand-in for example tests."""

    status_code = 200
    headers: dict = {}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_bytes(self, chunk_size):
        yield _MOCK_INPUT_CONTENT


_MOCK_INPUT_CONTENT = b"hello world"


class TestEchoNodeUnit:
    def test_manifest_file_fields(self):
        assert manifest.file_input_fields == ["input_file"]
        assert manifest.file_output_fields == ["output_file"]

    def test_manifest_format(self):
        props = manifest.input_schema["properties"]["input_file"]
        assert props["format"] == "file"
        assert props["type"] == "string"

    def test_definition_extensions(self):
        props = manifest.input_schema["properties"]["input_file"]
        assert props["x-accept"] == [".txt", ".csv", ".json"]
        assert props["x-maxSizeBytes"] == 10485760

    @patch("canvastekk_workflow_sdk.workflow_node_base.httpx.stream")
    def test_execute_returns_output_path(self, mock_stream, tmp_path):
        mock_stream.return_value = _MockStreamResponse()

        node = EchoNode()
        request = NodeExecutionRequest(
            run_id="test-run",
            node_id="echo-1",
            inputs={"input_file": "https://example.com/test.txt"},
        )
        response = node.run(request)

        assert response.status == "pass"
        assert response.outputs is not None
        assert "output_file" in response.outputs


class TestEchoNodeAPI:
    client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["node_id"] == "echo-v1.0.0"

    def test_manifest(self):
        resp = self.client.get("/manifest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Echo"
        input_file = data["input_schema"]["properties"]["input_file"]
        assert input_file["format"] == "file"
        assert input_file["x-accept"] == [".txt", ".csv", ".json"]

    @patch("canvastekk_workflow_sdk.workflow_node_base.httpx.stream")
    def test_execute_json(self, mock_stream):
        mock_stream.return_value = _MockStreamResponse()

        resp = self.client.post(
            "/execute",
            json={
                "run_id": "run-1",
                "node_id": "echo-1",
                "inputs": {"input_file": "https://example.com/test.txt"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pass"
        assert "output_file" in data["outputs"]
