"""Tests for the canonical node-service bootstrap (sdk#220).

create_authed_app / mount_node / create_lambda_handler — see
docs/NODE-SERVICE-LAYOUT.md for the standard these pin.
"""

from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from canvastekk_workflow_sdk import (
    BaseNode,
    ExecutionContext,
    WorkflowNodeManifest,
    create_authed_app,
    create_lambda_handler,
    mount_node,
)


class EchoNode(BaseNode):
    """Simple echo node for testing."""

    definition = WorkflowNodeManifest(
        slug="echo",
        version="1.0.0",
        name="Echo",
        description="Returns input unchanged",
        input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        token_cost=0.0,
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"message": inputs.get("message", "")}


class StartupFlagNode(EchoNode):
    """Node whose on_startup hook records it ran (lifespan-chaining proof)."""

    definition = WorkflowNodeManifest(
        slug="startup-flag",
        version="1.0.0",
        name="StartupFlag",
        description="Echo that records on_startup invocation",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        token_cost=0.0,
    )

    startup_ran: bool = False

    async def on_startup(self) -> None:
        type(self).startup_ran = True


def _execute_body() -> dict[str, Any]:
    return {"run_id": "r1", "node_id": "n1", "inputs": {"message": "hi"}}


class TestCreateAuthedApp:
    def test_central_only_default_fail_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """No verify base URL + no legacy window: every request fails closed."""
        monkeypatch.delenv("CWE_API_BASE_URL", raising=False)
        monkeypatch.setenv("CANVASTEKK_API_KEY", "legacy-value")
        app = create_authed_app(EchoNode())
        client = TestClient(app)
        # Even a matching legacy key is INERT: legacy_key_env_var=None by default.
        resp = client.post("/execute", json=_execute_body(), headers={"X-API-Key": "legacy-value"})
        assert resp.status_code == 401

    def test_legacy_window_passthrough(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """legacy_key_env_var keeps the static-key leg live during dual-accept."""
        monkeypatch.delenv("CWE_API_BASE_URL", raising=False)
        monkeypatch.setenv("BOOTSTRAP_TEST_KEY", "static-key-1")
        app = create_authed_app(EchoNode(), legacy_key_env_var="BOOTSTRAP_TEST_KEY")
        client = TestClient(app)
        ok = client.post("/execute", json=_execute_body(), headers={"X-API-Key": "static-key-1"})
        assert ok.status_code == 200
        assert ok.json()["outputs"]["message"] == "hi"

    def test_extra_routes_rejected(self) -> None:
        """extra_routes bypass the auth dependency in create_node_app — refused."""
        from fastapi import APIRouter

        with pytest.raises(ValueError, match="extra_routes"):
            create_authed_app(EchoNode(), extra_routes=[APIRouter()])


class TestMountNode:
    def test_dual_purpose_auth_boundary(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Root routes stay open; node sub-app routes carry central auth."""
        monkeypatch.delenv("CWE_API_BASE_URL", raising=False)
        monkeypatch.setenv("BOOTSTRAP_TEST_KEY", "static-key-1")
        root = FastAPI()

        @root.get("/ping")
        async def ping() -> dict[str, str]:
            return {"ping": "pong"}

        mount_node(root, EchoNode(), legacy_key_env_var="BOOTSTRAP_TEST_KEY")
        client = TestClient(root)

        assert client.get("/ping").status_code == 200  # root face: no node auth
        assert client.get("/node/manifest").status_code == 401  # node face: auth required
        ok = client.post(
            "/node/execute", json=_execute_body(), headers={"X-API-Key": "static-key-1"}
        )
        assert ok.status_code == 200  # node face: authed succeeds
        denied = client.post("/node/execute", json=_execute_body())
        assert denied.status_code == 401  # node face: anonymous denied

    def test_node_routes_fail_closed_without_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CWE_API_BASE_URL", raising=False)
        monkeypatch.setenv("CANVASTEKK_API_KEY", "legacy-inert-by-default")
        root = FastAPI()
        mount_node(root, EchoNode())
        client = TestClient(root)

        denied = client.post("/node/execute", json=_execute_body(), headers={"X-API-Key": "legacy-inert-by-default"})
        assert denied.status_code == 401

    def test_mounted_node_lifespan_runs(self) -> None:
        """Starlette skips mounted sub-app lifespans — mount_node chains them."""
        StartupFlagNode.startup_ran = False
        root = FastAPI()
        mount_node(root, StartupFlagNode())
        with TestClient(root):
            pass  # entering the client runs the root lifespan
        assert StartupFlagNode.startup_ran is True

    def test_custom_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BOOTSTRAP_TEST_KEY", "static-key-1")
        monkeypatch.delenv("CWE_API_BASE_URL", raising=False)
        root = FastAPI()
        mount_node(root, EchoNode(), prefix="/cw", legacy_key_env_var="BOOTSTRAP_TEST_KEY")
        client = TestClient(root)
        ok = client.post("/cw/execute", json=_execute_body(), headers={"X-API-Key": "static-key-1"})
        assert ok.status_code == 200
        missing = client.post("/node/execute", json=_execute_body())
        assert missing.status_code == 404


class TestCreateLambdaHandler:
    def test_plain_event_dispatch(self) -> None:
        """Non-HTTP events route to the caller's dispatcher."""

        def plain(event: dict[str, Any], context: Any) -> dict[str, Any]:
            return {"ok": True, "echo": event["prompt"]}

        handler = create_lambda_handler(FastAPI(), plain_event=plain)
        assert handler({"prompt": "run-it"}, None) == {"ok": True, "echo": "run-it"}

    def test_http_event_dispatch(self) -> None:
        """API-Gateway-v2-shaped events dispatch through Mangum onto the app."""
        mangum = pytest.importorskip("mangum")  # [lambda] extra
        root = FastAPI()

        @root.get("/ping")
        async def ping() -> dict[str, str]:
            return {"ping": "pong"}

        handler = create_lambda_handler(root, plain_event=lambda e, c: {"ok": False})
        event = {
            "version": "2.0",
            "routeKey": "$default",
            "rawPath": "/ping",
            "rawQueryString": "",
            "headers": {"host": "lambda.amazonaws.com"},
            "requestContext": {
                "http": {"method": "GET", "path": "/ping", "protocol": "HTTP/1.1", "sourceIp": "127.0.0.1", "userAgent": "pytest"},
                "routeKey": "$default",
                "requestId": "test",
                "stage": "$default",
            },
            "isBase64Encoded": False,
        }
        result = handler(event, None)
        assert result["statusCode"] == 200
        assert mangum is not None  # silence linters on the importerskip alias
