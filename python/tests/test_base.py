"""Tests for BaseNode class."""

import threading
from typing import Any

import pytest

from canvastekk_workflow_sdk import BaseNode, ExecutionContext, NodeExecutionRequest, WorkflowNodeManifest
from canvastekk_workflow_sdk import context as context_module
from canvastekk_workflow_sdk.context import execution_context_var
from canvastekk_workflow_sdk.exceptions import (
    NodeIOError,
    NodeOutputValidationError,
    NodeTimeoutError,
)
from canvastekk_workflow_sdk.middleware import TimingMiddleware
from canvastekk_workflow_sdk.observability import MetricsCollector


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
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"message": inputs.get("message", "")}


class FailingNode(BaseNode):
    """Node that always fails for testing."""

    definition = WorkflowNodeManifest(
        slug="failing",
        version="1.0.0",
        name="Failing",
        description="Always fails",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise ValueError("Intentional failure for testing")


class HealthyNode(BaseNode):
    """Node with custom health checks."""

    definition = WorkflowNodeManifest(
        slug="healthy",
        version="1.0.0",
        name="Healthy",
        description="Has custom health checks",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {}

    def health_check(self) -> dict[str, Any]:
        return {
            "model_loaded": True,
            "storage_accessible": True,
        }


class NodeIOErrorNode(BaseNode):
    """Node that raises NodeIOError."""

    definition = WorkflowNodeManifest(
        slug="io-err",
        version="1.0.0",
        name="IO Error",
        description="Raises IO error",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise NodeIOError("File not found", path="/tmp/missing.ply")


class NodeTimeoutErrorNode(BaseNode):
    """Node that raises NodeTimeoutError."""

    definition = WorkflowNodeManifest(
        slug="timeout-err",
        version="1.0.0",
        name="Timeout Error",
        description="Raises timeout",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise NodeTimeoutError(30)


class TokenReportingNode(BaseNode):
    """Node that reports token usage via context."""

    definition = WorkflowNodeManifest(
        slug="token",
        version="1.0.0",
        name="Token",
        description="Reports token usage",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        token_cost=1.0,
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        context.record_token_usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
        return {"done": True}


class ValidatedNode(BaseNode):
    """Node with required input fields for validation testing."""

    definition = WorkflowNodeManifest(
        slug="validated",
        version="1.0.0",
        name="Validated",
        description="Has required inputs",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["name", "count"],
        },
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"name": inputs["name"], "count": inputs["count"]}


class TestBaseNode:
    """Tests for BaseNode class."""

    def test_definition_required(self) -> None:
        """Test that subclasses must define a definition."""
        with pytest.raises(TypeError, match="must define a 'definition'"):

            class InvalidNode(BaseNode):
                def execute(self, inputs: dict, context: ExecutionContext) -> dict:
                    return {}

    def test_execute_success(self) -> None:
        """Test successful node execution."""
        node = EchoNode()
        request = NodeExecutionRequest(
            run_id="test-run",
            node_id="test-node",
            inputs={"message": "Hello, World!"},
        )
        response = node.run(request)

        assert response.status == "pass"
        assert response.outputs == {"message": "Hello, World!"}
        assert response.error is None
        assert response.error_type is None
        assert response.duration_ms >= 0
        assert response.execution_id is not None

    def test_execute_failure(self) -> None:
        """Test node execution failure."""
        node = FailingNode()
        request = NodeExecutionRequest(
            run_id="test-run",
            node_id="test-node",
            inputs={},
        )
        response = node.run(request)

        assert response.status == "fail"
        assert response.outputs is None
        assert response.error == "Intentional failure for testing"
        assert response.error_type == "ValueError"
        assert response.duration_ms >= 0

    def test_default_health_check(self) -> None:
        """Test default health check returns empty dict."""
        node = EchoNode()
        checks = node.health_check()
        assert checks == {}

    def test_custom_health_check(self) -> None:
        """Test custom health check."""
        node = HealthyNode()
        checks = node.health_check()
        assert checks == {
            "model_loaded": True,
            "storage_accessible": True,
        }

    def test_create_app(self) -> None:
        """Test that create_app returns a FastAPI instance."""
        node = EchoNode()
        app = node.create_app()
        assert app is not None
        # Check that routes exist. fastapi >=0.143 nests the router under an
        # _IncludedRouter in app.routes, so introspect via the public
        # openapi paths instead of iterating app.routes.
        paths = set(app.openapi()["paths"])
        assert "/execute" in paths
        assert "/health" in paths
        assert "/manifest" in paths


class TestBaseNodeTypedExceptions:
    def test_io_error_response(self) -> None:
        node = NodeIOErrorNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))
        assert response.status == "fail"
        assert response.error == "File not found"
        assert response.error_type == "NodeIOError"
        assert response.error_code == "IO_ERROR"

    def test_timeout_error_response(self) -> None:
        node = NodeTimeoutErrorNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))
        assert response.status == "fail"
        assert "timed out" in response.error
        assert response.error_type == "NodeTimeoutError"
        assert response.error_code == "TIMEOUT"

    def test_generic_exception_no_error_code(self) -> None:
        node = FailingNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))
        assert response.status == "fail"
        assert response.error_code is None

    def test_validation_error_on_missing_required(self) -> None:
        node = ValidatedNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))
        assert response.status == "fail"
        assert response.error_type == "NodeValidationError"
        assert response.error_code == "VALIDATION_ERROR"

    def test_validation_passes_with_valid_inputs(self) -> None:
        node = ValidatedNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={"name": "test", "count": 5}))
        assert response.status == "pass"
        assert response.outputs == {"name": "test", "count": 5}


class TestBaseNodeDynamicTokenUsage:
    def test_dynamic_token_usage_reported(self) -> None:
        node = TokenReportingNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))
        assert response.status == "pass"
        assert response.token_usage == 150.0

    def test_static_token_cost_as_fallback(self) -> None:
        node = EchoNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={"message": "hi"}))
        assert response.status == "pass"
        assert response.token_usage == 0.0


class TestBaseNodeMetricsIntegration:
    def test_successful_execution_records_metric(self) -> None:
        collector = MetricsCollector()
        node = EchoNode()
        node.set_metrics_collector(collector)

        node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={"message": "hi"}))

        summary = collector.get_summary()
        assert summary["total_executions"] == 1
        assert summary["pass_count"] == 1
        assert summary["fail_count"] == 0

    def test_failed_execution_records_metric(self) -> None:
        collector = MetricsCollector()
        node = FailingNode()
        node.set_metrics_collector(collector)

        node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))

        summary = collector.get_summary()
        assert summary["total_executions"] == 1
        assert summary["fail_count"] == 1

    def test_dynamic_token_usage_in_metrics(self) -> None:
        collector = MetricsCollector()
        node = TokenReportingNode()
        node.set_metrics_collector(collector)

        node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))

        summary = collector.get_summary()
        assert summary["total_token_usage"] == 150.0


class TestBaseNodeMiddlewareIntegration:
    def test_add_middleware_chaining(self) -> None:
        node = EchoNode()
        timing = TimingMiddleware()
        result = node.add_middleware(timing)
        assert result is node

    def test_timing_middleware_records(self) -> None:
        timing = TimingMiddleware()
        node = EchoNode()
        node.add_middleware(timing)

        node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={"message": "hi"}))

        assert len(timing.timings) == 1
        assert timing.timings[0]["status"] == "pass"

    def test_timing_middleware_on_error(self) -> None:
        timing = TimingMiddleware()
        node = FailingNode()
        node.add_middleware(timing)

        node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))

        assert len(timing.timings) == 1
        assert timing.timings[0]["status"] == "fail"
        assert timing.timings[0]["error_type"] == "ValueError"

    def test_hook_default_returns_none(self) -> None:
        node = EchoNode()
        assert node.hook({}) is None


class TestBaseNodeInitSubclass:
    def test_abstract_subclass_skips_validation(self) -> None:
        from abc import ABC

        class MiddleNode(BaseNode, ABC):
            pass

        assert not hasattr(MiddleNode, "definition") or MiddleNode.definition is None


class OutputValidationNode(BaseNode):
    """Node with strict output schema for validation testing."""

    definition = WorkflowNodeManifest(
        slug="output-val",
        version="1.0.0",
        name="Output Validation",
        description="Has strict output schema",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "integer"}},
        },
        output_schema={
            "type": "object",
            "properties": {
                "result": {"type": "integer"},
                "message": {"type": "string"},
            },
            "required": ["result", "message"],
        },
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        val = inputs.get("value", 0)
        return {"result": val * 2, "message": f"Doubled: {val * 2}"}


class OutputValidationErrorNode(BaseNode):
    """Node that returns invalid output type."""

    definition = WorkflowNodeManifest(
        slug="output-err",
        version="1.0.0",
        name="Output Error",
        description="Returns invalid output",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"count": {"type": "integer"}},
        },
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"count": "not an integer"}


class OutputMissingRequiredNode(BaseNode):
    """Node that returns missing required field."""

    definition = WorkflowNodeManifest(
        slug="output-missing",
        version="1.0.0",
        name="Output Missing",
        description="Returns missing required field",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}, "age": {"type": "integer"}},
            "required": ["name", "age"],
        },
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"name": "John"}


class TrivialOutputSchemaNode(BaseNode):
    """Node with trivial output schema."""

    definition = WorkflowNodeManifest(
        slug="trivial",
        version="1.0.0",
        name="Trivial",
        description="Has trivial output schema",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        return {"anything": "goes"}


class TestBaseNodeOutputValidation:
    """Tests for output schema validation (Phase 1)."""

    def test_valid_output_passes_validation(self) -> None:
        """Test that valid output passes schema validation."""
        node = OutputValidationNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={"value": 5}))
        assert response.status == "pass"
        assert response.outputs == {"result": 10, "message": "Doubled: 10"}
        assert response.error is None

    def test_invalid_output_wrong_type_raises_error(self) -> None:
        """Test that invalid output type raises NodeOutputValidationError."""
        node = OutputValidationErrorNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))
        assert response.status == "fail"
        assert response.error_type == "NodeOutputValidationError"
        assert response.error_code == "OUTPUT_VALIDATION_ERROR"
        assert "output validation failed" in response.error.lower()

    def test_missing_required_output_field_raises_error(self) -> None:
        """Test that missing required output field raises NodeOutputValidationError."""
        node = OutputMissingRequiredNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))
        assert response.status == "fail"
        assert response.error_type == "NodeOutputValidationError"
        assert response.error_code == "OUTPUT_VALIDATION_ERROR"
        assert "output validation failed" in response.error.lower()

    def test_trivial_output_schema_always_passes(self) -> None:
        """Test that trivial output schema {'type': 'object'} always passes."""
        node = TrivialOutputSchemaNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))
        assert response.status == "pass"
        assert response.outputs == {"anything": "goes"}

    def test_output_validation_error_code(self) -> None:
        """Test that NodeOutputValidationError has correct error_code."""
        try:
            raise NodeOutputValidationError("test error")
        except NodeOutputValidationError as e:
            assert e.error_code == "OUTPUT_VALIDATION_ERROR"

    def test_output_validation_error_in_response(self) -> None:
        """Test that error_type is correctly set in response."""
        node = OutputValidationErrorNode()
        response = node.run(NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}))
        assert response.status == "fail"
        assert response.error_type == "NodeOutputValidationError"
        assert response.error is not None


class TestLifecycleHooks:
    """Tests for lifecycle hooks (Phase 2)."""

    def test_on_startup_hook_fires_on_app_start(self) -> None:
        """Test that on_startup is called when the app starts."""

        class LifecycleNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="lifecycle",
                version="1.0.0",
                name="Lifecycle",
                description="Tests lifecycle hooks",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            startup_called = False
            shutdown_called = False

            def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
                return {"startup": self.startup_called, "shutdown": self.shutdown_called}

            async def on_startup(self) -> None:
                self.startup_called = True

            async def on_shutdown(self) -> None:
                self.shutdown_called = True

        from fastapi.testclient import TestClient

        node = LifecycleNode()
        app = node.create_app()

        assert node.startup_called is False
        assert node.shutdown_called is False

        with TestClient(app) as client:
            assert node.startup_called is True
            assert node.shutdown_called is False

            response = client.get("/health")
            assert response.status_code == 200

        assert node.shutdown_called is True

    def test_on_shutdown_hook_fires_on_app_stop(self) -> None:
        """Test that on_shutdown is called when the app stops."""

        class ShutdownNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="shutdown",
                version="1.0.0",
                name="Shutdown",
                description="Tests shutdown hook",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            shutdown_called = False

            def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
                return {}

            async def on_shutdown(self) -> None:
                self.shutdown_called = True

        from fastapi.testclient import TestClient

        node = ShutdownNode()
        app = node.create_app()

        assert node.shutdown_called is False

        with TestClient(app):
            pass

        assert node.shutdown_called is True

    def test_default_hooks_are_no_ops(self) -> None:
        """Test that default on_startup and on_shutdown are no-ops."""
        node = EchoNode()

        from fastapi.testclient import TestClient

        app = node.create_app()

        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200

    def test_lifespan_context_manager_calls_both_hooks(self) -> None:
        """Test that _lifespan context manager calls on_startup and on_shutdown."""
        hook_order: list[str] = []

        class OrderedLifecycleNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="ordered",
                version="1.0.0",
                name="Ordered",
                description="Tests hook order",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
                return {}

            async def on_startup(self) -> None:
                hook_order.append("startup")

            async def on_shutdown(self) -> None:
                hook_order.append("shutdown")

        node = OrderedLifecycleNode()

        async def test_lifespan() -> None:
            async with node._lifespan():
                pass

        import asyncio

        asyncio.run(test_lifespan())

        assert hook_order == ["startup", "shutdown"]

    def test_on_startup_exception_propagates(self) -> None:
        """Test that exceptions in on_startup propagate correctly."""

        class FailingStartupNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="failing-startup",
                version="1.0.0",
                name="Failing Startup",
                description="Tests startup exception",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
                return {}

            async def on_startup(self) -> None:
                raise RuntimeError("Startup failed")

        node = FailingStartupNode()

        async def test_startup_failure() -> None:
            with pytest.raises(RuntimeError, match="Startup failed"):
                async with node._lifespan():
                    pass

        import asyncio

        asyncio.run(test_startup_failure())

    def test_on_shutdown_exception_propagates(self) -> None:
        """Test that exceptions in on_shutdown propagate correctly."""

        class FailingShutdownNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="failing-shutdown",
                version="1.0.0",
                name="Failing Shutdown",
                description="Tests shutdown exception",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
                return {}

            async def on_shutdown(self) -> None:
                raise RuntimeError("Shutdown failed")

        node = FailingShutdownNode()

        async def test_shutdown_failure() -> None:
            with pytest.raises(RuntimeError, match="Shutdown failed"):
                async with node._lifespan():
                    pass

        import asyncio

        asyncio.run(test_shutdown_failure())

    def test_lifespan_works_with_create_node_app(self) -> None:
        """Test that lifespan hooks work with create_node_app function."""

        class LifecycleTestNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="lifespan-test",
                version="1.0.0",
                name="Lifespan Test",
                description="Tests lifespan with create_node_app",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            startup_called = False
            shutdown_called = False

            def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
                return {}

            async def on_startup(self) -> None:
                self.startup_called = True

            async def on_shutdown(self) -> None:
                self.shutdown_called = True

        from fastapi.testclient import TestClient

        from canvastekk_workflow_sdk.app import create_node_app

        node = LifecycleTestNode()
        app = create_node_app(node)

        assert node.startup_called is False
        assert node.shutdown_called is False

        with TestClient(app):
            assert node.startup_called is True
            assert node.shutdown_called is False

        assert node.shutdown_called is True

    def test_multiple_contexts_invoke_hooks_multiple_times(self) -> None:
        """Test that multiple TestClient contexts invoke hooks multiple times."""

        class MultiLifecycleNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="multi-lifecycle",
                version="1.0.0",
                name="Multi Lifecycle",
                description="Tests multiple contexts",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            startup_count = 0
            shutdown_count = 0

            def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
                return {}

            async def on_startup(self) -> None:
                self.startup_count += 1

            async def on_shutdown(self) -> None:
                self.shutdown_count += 1

        from fastapi.testclient import TestClient

        node = MultiLifecycleNode()
        app = node.create_app()

        assert node.startup_count == 0
        assert node.shutdown_count == 0

        with TestClient(app):
            assert node.startup_count == 1
            assert node.shutdown_count == 0

        assert node.shutdown_count == 1

        with TestClient(app):
            assert node.startup_count == 2
            assert node.shutdown_count == 1

        assert node.shutdown_count == 2


class ProgressNode(BaseNode):
    """Node that reports progress mid-run (DA-3230)."""

    definition = WorkflowNodeManifest(
        slug="progress-node",
        version="1.0.0",
        name="Progress",
        description="Reports progress mid-run",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"done": {"type": "boolean"}},
        },
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        self.report_progress(50, "still calculating")
        return {"done": True}


class SlowProgressNode(ProgressNode):
    """Progress node whose execute sleeps briefly so runs can overlap."""

    definition = WorkflowNodeManifest(
        slug="slow-progress-node",
        version="1.0.0",
        name="SlowProgress",
        description="Reports progress after a short delay",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"done": {"type": "boolean"}},
        },
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        import time

        time.sleep(0.02)
        self.report_progress(75, "nearly there")
        return {"done": True}


class TestBaseNodeReportProgress:
    """DA-3230: BaseNode.report_progress ambient-context behavior."""

    def test_noop_outside_run(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(context_module, "_deliver_progress_ping", lambda u, p: calls.append((u, p)))
        node = ProgressNode()
        node.report_progress(50, "orphan")  # must not raise or send
        assert calls == []

    def test_sends_run_execution_id_inside_execute(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(context_module, "_deliver_progress_ping", lambda u, p: calls.append((u, p)))
        node = ProgressNode()
        resp = node.run(
            NodeExecutionRequest(
                run_id="r-prog",
                node_id="n-prog",
                inputs={},
                callback_url="http://engine/callbacks/r-prog/n-prog",
            )
        )
        assert resp.status == "pass"
        assert calls == [
            (
                "http://engine/callbacks/r-prog/n-prog/progress",
                {"execution_id": resp.execution_id, "percent": 50, "message": "still calculating"},
            )
        ]

    def test_interleaved_runs_ping_own_execution_ids(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(context_module, "_deliver_progress_ping", lambda u, p: calls.append((u, p)))
        node = SlowProgressNode()
        results: dict[str, Any] = {}

        def _run_a() -> None:
            results["a"] = node.run(
                NodeExecutionRequest(
                    run_id="ra", node_id="na", inputs={}, callback_url="http://engine/cb/ra"
                )
            )

        def _run_b() -> None:
            results["b"] = node.run(
                NodeExecutionRequest(
                    run_id="rb", node_id="nb", inputs={}, callback_url="http://engine/cb/rb"
                )
            )

        ta = threading.Thread(target=_run_a)
        tb = threading.Thread(target=_run_b)
        ta.start()
        tb.start()
        ta.join()
        tb.join()

        by_url = {url: payload for url, payload in calls}
        assert by_url["http://engine/cb/ra/progress"]["execution_id"] == results["a"].execution_id
        assert by_url["http://engine/cb/rb/progress"]["execution_id"] == results["b"].execution_id
        assert results["a"].execution_id != results["b"].execution_id

    def test_error_path_resets_context_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(context_module, "_deliver_progress_ping", lambda u, p: None)
        node = FailingNode()
        resp = node.run(
            NodeExecutionRequest(
                run_id="r-err", node_id="n-err", inputs={}, callback_url="http://engine/cb"
            )
        )
        assert resp.status == "fail"
        assert execution_context_var.get() is None

    def test_provided_execution_id_flows_to_pings(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#3498: a dispatcher-provided execution_id is adopted verbatim —
        context, response, and every progress ping carry it."""
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(context_module, "_deliver_progress_ping", lambda u, p: calls.append((u, p)))
        node = ProgressNode()
        resp = node.run(
            NodeExecutionRequest(
                run_id="r-prog",
                node_id="n-prog",
                inputs={},
                callback_url="http://engine/callbacks/r-prog/n-prog",
                execution_id="ecs-1234",
            )
        )
        assert resp.status == "pass"
        assert resp.execution_id == "ecs-1234"
        assert calls == [
            (
                "http://engine/callbacks/r-prog/n-prog/progress",
                {"execution_id": "ecs-1234", "percent": 50, "message": "still calculating"},
            )
        ]

    def test_fallback_invents_distinct_ids_per_run(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """#3498 back-compat: absent execution_id → uuid4 fallback (inline
        behavior unchanged); two runs never share an id."""
        monkeypatch.setattr(context_module, "_deliver_progress_ping", lambda u, p: None)
        node = ProgressNode()
        req = NodeExecutionRequest(
            run_id="r-fb", node_id="n-fb", inputs={},
            callback_url="http://engine/callbacks/r-fb/n-fb",
        )
        a = node.run(req.model_copy())
        b = node.run(req.model_copy())
        assert a.execution_id != b.execution_id
        assert len(a.execution_id) == 36  # uuid4 shape
