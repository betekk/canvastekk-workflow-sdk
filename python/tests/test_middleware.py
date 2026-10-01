"""Tests for middleware system."""

from typing import Any

from canvastekk_workflow_sdk import (
    BaseNode,
    ExecutionContext,
    NodeExecutionRequest,
    WorkflowNodeManifest,
    __version__,
)
from canvastekk_workflow_sdk.middleware import LoggingMiddleware, TimingMiddleware


class EchoNode(BaseNode):
    definition = WorkflowNodeManifest(
        slug="echo",
        version="1.0.0",
        name="Echo",
        description="Returns input unchanged",
        input_schema={"type": "object", "properties": {"message": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"message": {"type": "string"}}},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"message": inputs.get("message", "")}


class FailingNode(BaseNode):
    definition = WorkflowNodeManifest(
        slug="failing",
        version="1.0.0",
        name="Failing",
        description="Always fails",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise ValueError("intentional")


class TrackingMiddleware:
    """Test middleware that tracks calls."""

    def __init__(self) -> None:
        self.before_calls: list[dict] = []
        self.after_calls: list[dict] = []
        self.error_calls: list[dict] = []

    def on_before_execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        self.before_calls.append({"inputs": inputs, "run_id": context.run_id})
        return inputs

    def on_after_execute(
        self,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        self.after_calls.append({"outputs": outputs, "duration_ms": duration_ms})

    def on_error(
        self,
        inputs: dict[str, Any],
        error: Exception,
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        self.error_calls.append({"error": str(error), "duration_ms": duration_ms})


class InputModifyingMiddleware:
    """Middleware that modifies inputs before execution."""

    def on_before_execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        inputs["injected"] = True
        return inputs

    def on_after_execute(
        self, inputs: dict[str, Any], outputs: dict[str, Any], context: ExecutionContext, duration_ms: int
    ) -> None:
        pass

    def on_error(self, inputs: dict[str, Any], error: Exception, context: ExecutionContext, duration_ms: int) -> None:
        pass


class TestMiddleware:
    def test_before_and_after_called_on_success(self) -> None:
        tracker = TrackingMiddleware()
        node = EchoNode()
        node.add_middleware(tracker)

        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"message": "hello"},
            )
        )

        assert response.status == "pass"
        assert len(tracker.before_calls) == 1
        assert len(tracker.after_calls) == 1
        assert len(tracker.error_calls) == 0
        assert tracker.before_calls[0]["run_id"] == "r1"

    def test_error_called_on_failure(self) -> None:
        tracker = TrackingMiddleware()
        node = FailingNode()
        node.add_middleware(tracker)

        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={},
            )
        )

        assert response.status == "fail"
        assert len(tracker.before_calls) == 1
        assert len(tracker.after_calls) == 0
        assert len(tracker.error_calls) == 1
        assert "intentional" in tracker.error_calls[0]["error"]

    def test_input_modifying_middleware(self) -> None:
        node = EchoNode()
        node.add_middleware(InputModifyingMiddleware())

        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"message": "hello"},
            )
        )

        assert response.status == "pass"

    def test_add_middleware_returns_self(self) -> None:
        node = EchoNode()
        result = node.add_middleware(TrackingMiddleware())
        assert result is node

    def test_logging_middleware_is_default(self) -> None:
        node = EchoNode()
        assert len(node._middleware) == 1
        assert isinstance(node._middleware[0], LoggingMiddleware)


class TestTimingMiddleware:
    def test_records_successful_timing(self) -> None:
        timer = TimingMiddleware()
        node = EchoNode()
        node.add_middleware(timer)

        node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"message": "hi"},
            )
        )

        assert len(timer.timings) == 1
        assert timer.timings[0]["status"] == "pass"
        assert timer.timings[0]["duration_ms"] >= 0

    def test_records_failed_timing(self) -> None:
        timer = TimingMiddleware()
        node = FailingNode()
        node.add_middleware(timer)

        node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={},
            )
        )

        assert len(timer.timings) == 1
        assert timer.timings[0]["status"] == "fail"
        assert timer.timings[0]["error_type"] == "ValueError"

    def test_accumulates_across_runs(self) -> None:
        timer = TimingMiddleware()
        node = EchoNode()
        node.add_middleware(timer)

        for i in range(5):
            node.run(
                NodeExecutionRequest(
                    run_id=f"r{i}",
                    node_id="n1",
                    inputs={"message": "hi"},
                )
            )

        assert len(timer.timings) == 5


class TestSDKVersionMiddleware:
    def test_adds_header(self) -> None:
        from starlette.testclient import TestClient

        from canvastekk_workflow_sdk.app import create_node_app

        client = TestClient(create_node_app(EchoNode()))
        response = client.get("/health")
        assert response.headers["x-sdk-version"] == __version__


class TestNodeSlugHeader:
    """DA-3359: X-Canvastekk-Node-Slug beside the version header."""

    def test_slug_present_on_single_node_app(self) -> None:
        from starlette.testclient import TestClient

        from canvastekk_workflow_sdk.app import create_node_app

        client = TestClient(create_node_app(EchoNode()))
        response = client.get("/health")
        assert response.headers["x-canvastekk-node-slug"] == EchoNode().definition.slug

    def test_exactly_one_version_header(self) -> None:
        from starlette.testclient import TestClient

        from canvastekk_workflow_sdk.app import create_node_app

        client = TestClient(create_node_app(EchoNode()))
        response = client.get("/health")
        assert response.headers["x-sdk-version"] == __version__

    def test_middleware_accepts_absent_slug(self) -> None:
        from starlette.applications import Starlette
        from starlette.responses import PlainTextResponse
        from starlette.testclient import TestClient

        from canvastekk_workflow_sdk.middleware import SDKVersionMiddleware

        app = Starlette()
        app.add_middleware(SDKVersionMiddleware)  # multi-node: no slug to stamp

        async def _home(request):  # type: ignore[no-untyped-def]
            return PlainTextResponse("ok")

        app.add_route("/", _home, methods=["GET"])
        client = TestClient(app)
        response = client.get("/")
        assert response.headers["x-sdk-version"] == __version__
        assert "x-canvastekk-node-slug" not in response.headers
