"""Tests for multi-node router."""

from typing import Any

from fastapi.testclient import TestClient

from canvastekk_workflow_sdk import NodeExecutionContext, WorkflowNodeBase, WorkflowNodeManifest
from canvastekk_workflow_sdk.multi_node_router import create_multi_workflow_node_app


class EchoNode(WorkflowNodeBase):
    manifest = WorkflowNodeManifest(
        slug="echo",
        version="1.0.0",
        name="Echo",
        description="Returns input unchanged",
        input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"message": {"type": "string"}}},
    )

    def execute(self, inputs: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
        return {"message": inputs.get("message", "")}


class ReverseNode(WorkflowNodeBase):
    manifest = WorkflowNodeManifest(
        slug="reverse",
        version="1.0.0",
        name="Reverse",
        description="Reverses input string",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
    )

    def execute(self, inputs: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
        return {"result": inputs.get("text", "")[::-1]}


class UpperNode(WorkflowNodeBase):
    manifest = WorkflowNodeManifest(
        slug="upper",
        version="1.0.0",
        name="Upper",
        description="Converts to uppercase",
        input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"result": {"type": "string"}}},
    )

    def execute(self, inputs: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
        return {"result": inputs.get("text", "").upper()}


class TestMultiNodeRouter:
    """Tests for create_multi_workflow_node_app function."""

    def test_two_nodes_on_same_app_both_respond_independently(self) -> None:
        """Test that two nodes on same app both respond independently."""
        app = create_multi_workflow_node_app(
            {
                "echo": EchoNode(),
                "reverse": ReverseNode(),
            }
        )
        client = TestClient(app)

        response1 = client.post(
            "/echo/execute",
            json={"run_id": "r1", "node_id": "n1", "inputs": {"message": "hello"}},
        )
        assert response1.status_code == 200
        assert response1.json()["outputs"]["message"] == "hello"

        response2 = client.post(
            "/reverse/execute",
            json={"run_id": "r2", "node_id": "n2", "inputs": {"text": "hello"}},
        )
        assert response2.status_code == 200
        assert response2.json()["outputs"]["result"] == "olleh"

    def test_root_health_endpoint_returns_healthy_with_node_list(self) -> None:
        """Test that root health endpoint returns healthy with node list."""
        app = create_multi_workflow_node_app(
            {
                "echo": EchoNode(),
                "reverse": ReverseNode(),
                "upper": UpperNode(),
            }
        )
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert set(data["nodes"]) == {"echo", "reverse", "upper"}

    def test_each_nodes_health_endpoint_works_under_prefix(self) -> None:
        """Test that each node's /health endpoint works under prefix."""
        app = create_multi_workflow_node_app(
            {
                "echo": EchoNode(),
                "reverse": ReverseNode(),
            }
        )
        client = TestClient(app)

        response1 = client.get("/echo/health")
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["status"] == "healthy"
        assert data1["node_id"] == "echo-v1.0.0"

        response2 = client.get("/reverse/health")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["status"] == "healthy"
        assert data2["node_id"] == "reverse-v1.0.0"

    def test_each_nodes_manifest_endpoint_works_under_prefix(self) -> None:
        """Test that each node's /manifest endpoint works under prefix."""
        app = create_multi_workflow_node_app(
            {
                "echo": EchoNode(),
                "reverse": ReverseNode(),
            }
        )
        client = TestClient(app)

        response1 = client.get("/echo/manifest")
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["id"] == "echo-v1.0.0"
        assert data1["slug"] == "echo"

        response2 = client.get("/reverse/manifest")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["id"] == "reverse-v1.0.0"
        assert data2["slug"] == "reverse"

    def test_each_nodes_execute_endpoint_works_under_prefix(self) -> None:
        """Test that each node's /execute endpoint works under prefix."""
        app = create_multi_workflow_node_app(
            {
                "echo": EchoNode(),
                "reverse": ReverseNode(),
            }
        )
        client = TestClient(app)

        response1 = client.post(
            "/echo/execute",
            json={"run_id": "r1", "node_id": "n1", "inputs": {"message": "test"}},
        )
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["status"] == "pass"
        assert data1["outputs"]["message"] == "test"

        response2 = client.post(
            "/reverse/execute",
            json={"run_id": "r2", "node_id": "n2", "inputs": {"text": "test"}},
        )
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["status"] == "pass"
        assert data2["outputs"]["result"] == "tset"

    def test_works_with_single_node(self) -> None:
        """Test that router works with a single node."""
        app = create_multi_workflow_node_app({"echo": EchoNode()})
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["nodes"] == ["echo"]

        response = client.post(
            "/echo/execute",
            json={"run_id": "r1", "node_id": "n1", "inputs": {"message": "hello"}},
        )
        assert response.status_code == 200
        assert response.json()["outputs"]["message"] == "hello"

    def test_three_nodes_on_same_app_all_respond_independently(self) -> None:
        """Test that three nodes on same app all respond independently."""
        app = create_multi_workflow_node_app(
            {
                "echo": EchoNode(),
                "reverse": ReverseNode(),
                "upper": UpperNode(),
            }
        )
        client = TestClient(app)

        response1 = client.post(
            "/echo/execute",
            json={"run_id": "r1", "node_id": "n1", "inputs": {"message": "hello"}},
        )
        assert response1.status_code == 200
        assert response1.json()["outputs"]["message"] == "hello"

        response2 = client.post(
            "/reverse/execute",
            json={"run_id": "r2", "node_id": "n2", "inputs": {"text": "hello"}},
        )
        assert response2.status_code == 200
        assert response2.json()["outputs"]["result"] == "olleh"

        response3 = client.post(
            "/upper/execute",
            json={"run_id": "r3", "node_id": "n3", "inputs": {"text": "hello"}},
        )
        assert response3.status_code == 200
        assert response3.json()["outputs"]["result"] == "HELLO"

    def test_nodes_metrics_endpoint_works_under_prefix(self) -> None:
        """Test that each node's /metrics endpoint works under prefix."""
        app = create_multi_workflow_node_app(
            {
                "echo": EchoNode(),
                "reverse": ReverseNode(),
            }
        )
        client = TestClient(app)

        client.post("/echo/execute", json={"run_id": "r1", "node_id": "n1", "inputs": {"message": "test"}})
        client.post("/reverse/execute", json={"run_id": "r2", "node_id": "n2", "inputs": {"text": "test"}})

        response1 = client.get("/echo/metrics")
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["total_executions"] == 1

        response2 = client.get("/reverse/metrics")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["total_executions"] == 1

    def test_nodes_manifest_endpoint_works_under_prefix(self) -> None:
        """Test that each node's /manifest endpoint works under prefix."""
        app = create_multi_workflow_node_app(
            {
                "echo": EchoNode(),
                "reverse": ReverseNode(),
            }
        )
        client = TestClient(app)

        response1 = client.get("/echo/manifest")
        assert response1.status_code == 200
        data1 = response1.json()
        assert data1["id"] == "echo-v1.0.0"
        assert data1["slug"] == "echo"

        response2 = client.get("/reverse/manifest")
        assert response2.status_code == 200
        data2 = response2.json()
        assert data2["id"] == "reverse-v1.0.0"
        assert data2["slug"] == "reverse"

    def test_global_dependencies_applied_to_all_nodes(self) -> None:
        """Test that global dependencies are applied to all nodes."""
        from fastapi import Depends, Request

        dependency_invocations: list[str] = []

        def custom_dependency(request: Request) -> None:
            dependency_invocations.append(request.url.path)

        app = create_multi_workflow_node_app(
            {"echo": EchoNode(), "reverse": ReverseNode()},
            global_dependencies=[Depends(custom_dependency)],
        )
        client = TestClient(app)

        client.get("/echo/health")
        client.get("/reverse/health")

        assert "/echo/health" in dependency_invocations
        assert "/reverse/health" in dependency_invocations

    def test_fastapi_kwargs_passed_to_root_app(self) -> None:
        """Test that FastAPI kwargs are passed to root app."""
        app = create_multi_workflow_node_app(
            {"echo": EchoNode()},
            title="Multi Node App",
            version="1.0.0",
        )
        assert app.title == "Multi Node App"
        assert app.version == "1.0.0"

    def test_empty_nodes_dict_creates_app_with_root_health_only(self) -> None:
        """Test that empty nodes dict creates app with only root health endpoint."""
        app = create_multi_workflow_node_app({})
        client = TestClient(app)

        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["nodes"] == []

    def test_prefixes_without_leading_slash(self) -> None:
        """Test that prefixes work without leading slash."""
        app = create_multi_workflow_node_app(
            {
                "echo": EchoNode(),
                "reverse": ReverseNode(),
            }
        )
        client = TestClient(app)

        response1 = client.post(
            "/echo/execute",
            json={"run_id": "r1", "node_id": "n1", "inputs": {"message": "test"}},
        )
        assert response1.status_code == 200

        response2 = client.post(
            "/reverse/execute",
            json={"run_id": "r2", "node_id": "n2", "inputs": {"text": "test"}},
        )
        assert response2.status_code == 200
