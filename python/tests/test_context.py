"""Tests for ExecutionContext."""

import logging
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from canvastekk_workflow_sdk import NodeExecutionRequest
from canvastekk_workflow_sdk import context as context_module
from canvastekk_workflow_sdk.context import ExecutionContext


@pytest.fixture
def exec_request() -> NodeExecutionRequest:
    return NodeExecutionRequest(
        run_id="run-123",
        node_id="node-456",
        inputs={"key": "value"},
    )


@pytest.fixture
def context(exec_request: NodeExecutionRequest) -> ExecutionContext:
    return ExecutionContext(exec_request)


class TestExecutionContext:
    def test_run_id(self, context: ExecutionContext) -> None:
        assert context.run_id == "run-123"

    def test_node_id(self, context: ExecutionContext) -> None:
        assert context.node_id == "node-456"

    def test_output_dir_created(self, context: ExecutionContext) -> None:
        assert context.output_dir.exists()
        assert context.output_dir.is_dir()

    def test_output_dir_contains_run_and_node(self, context: ExecutionContext) -> None:
        assert "run-123" in str(context.output_dir)
        assert "node-456" in str(context.output_dir)

    def test_custom_output_dir(self, exec_request: NodeExecutionRequest, tmp_path: Path) -> None:
        custom_dir = tmp_path / "custom_output"
        ctx = ExecutionContext(exec_request, output_dir=custom_dir)
        assert ctx.output_dir == custom_dir
        assert custom_dir.exists()

    def test_logger_is_configured(self, context: ExecutionContext) -> None:
        assert isinstance(context.logger, logging.Logger)
        assert "node-456" in context.logger.name

    def test_output_path(self, context: ExecutionContext) -> None:
        path = context.output_path("result.ply")
        assert path.name == "result.ply"
        assert path.parent == context.output_dir

    def test_report_progress(self, context: ExecutionContext) -> None:
        context.report_progress(0.5, "halfway done")

    def test_report_progress_full(self, context: ExecutionContext) -> None:
        context.report_progress(1.0)


class TestTokenUsage:
    def test_initial_token_usage_empty(self, context: ExecutionContext) -> None:
        assert context.token_usage == {}

    def test_record_token_usage(self, context: ExecutionContext) -> None:
        context.record_token_usage(
            prompt_tokens=100,
            completion_tokens=50,
            total_tokens=150,
        )
        assert context.token_usage == {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
        }

    def test_token_usage_returns_copy(self, context: ExecutionContext) -> None:
        context.record_token_usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        usage = context.token_usage
        usage["prompt_tokens"] = 999
        assert context.token_usage["prompt_tokens"] == 10

    def test_record_token_usage_overwrites(self, context: ExecutionContext) -> None:
        context.record_token_usage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        context.record_token_usage(prompt_tokens=200, completion_tokens=100, total_tokens=300)
        assert context.token_usage["total_tokens"] == 300

    def test_record_token_usage_defaults(self, context: ExecutionContext) -> None:
        context.record_token_usage()
        assert context.token_usage == {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }


class TestOutputDirEnvironmentVariable:
    """Tests for CANVASTEKK_OUTPUT_DIR environment variable (Phase 1)."""

    def test_output_dir_uses_env_var_when_set(
        self, exec_request: NodeExecutionRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that CANVASTEKK_OUTPUT_DIR env var overrides /tmp."""
        monkeypatch.setenv("CANVASTEKK_OUTPUT_DIR", str(tmp_path))
        ctx = ExecutionContext(exec_request)
        assert tmp_path in ctx.output_dir.parents
        assert exec_request.run_id in str(ctx.output_dir)
        assert exec_request.node_id in str(ctx.output_dir)

    def test_output_dir_fallback_to_tmp_when_env_not_set(
        self, exec_request: NodeExecutionRequest, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test that /tmp is used when CANVASTEKK_OUTPUT_DIR is not set."""
        monkeypatch.delenv("CANVASTEKK_OUTPUT_DIR", raising=False)
        ctx = ExecutionContext(exec_request)
        assert Path("/tmp") in ctx.output_dir.parents
        assert exec_request.run_id in str(ctx.output_dir)
        assert exec_request.node_id in str(ctx.output_dir)

    def test_custom_output_dir_overrides_env_var(
        self, exec_request: NodeExecutionRequest, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Test that explicit output_dir parameter overrides env var."""
        monkeypatch.setenv("CANVASTEKK_OUTPUT_DIR", "/tmp/should-not-use")
        custom_dir = tmp_path / "custom"
        ctx = ExecutionContext(exec_request, output_dir=custom_dir)
        assert ctx.output_dir == custom_dir
        assert "/tmp/should-not-use" not in str(ctx.output_dir)


class TestAccountIdProperty:
    """DA-2242: ExecutionContext.account_id surfaces the request value."""

    def test_returns_request_account_id(self) -> None:
        req = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}, account_id=7)
        assert ExecutionContext(req).account_id == 7

    def test_none_when_request_has_none(self, context: ExecutionContext) -> None:
        assert context.account_id is None

    def test_none_without_request(self) -> None:
        assert ExecutionContext(run_id="r1", node_id="n1").account_id is None


class TestProgressPing:
    """DA-3230: fire-and-forget progress ping to {callback_url}/progress."""

    @staticmethod
    def _recorder(calls: list[tuple[str, dict]]) -> Callable[[str, dict], None]:
        def fake_deliver(url: str, payload: dict) -> None:
            calls.append((url, payload))

        return fake_deliver

    def test_execution_id_default_and_explicit(self) -> None:
        assert ExecutionContext(run_id="r", node_id="n").execution_id is None
        req = NodeExecutionRequest(run_id="r", node_id="n", inputs={})
        assert ExecutionContext(req, execution_id="exec-1").execution_id == "exec-1"

    def test_noop_without_callback_url(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(context_module, "_deliver_progress_ping", self._recorder(calls))
        req = NodeExecutionRequest(run_id="r", node_id="n", inputs={})
        ctx = ExecutionContext(req, execution_id="exec-1")
        ctx.report_progress(0.5, "halfway")
        assert calls == []

    def test_noop_without_execution_id(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(context_module, "_deliver_progress_ping", self._recorder(calls))
        req = NodeExecutionRequest(
            run_id="r", node_id="n", inputs={}, callback_url="http://engine/cb"
        )
        ctx = ExecutionContext(req)
        ctx.report_progress(0.5)
        assert calls == []

    def test_happy_path_posts_execution_id_percent_message(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(context_module, "_deliver_progress_ping", self._recorder(calls))
        req = NodeExecutionRequest(
            run_id="r", node_id="n", inputs={}, callback_url="http://engine/cb"
        )
        ctx = ExecutionContext(req, execution_id="exec-42")
        ctx.report_progress(0.5, "halfway")
        assert calls == [
            (
                "http://engine/cb/progress",
                {"execution_id": "exec-42", "percent": 50, "message": "halfway"},
            )
        ]

    def test_message_key_omitted_when_empty(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(context_module, "_deliver_progress_ping", self._recorder(calls))
        req = NodeExecutionRequest(
            run_id="r", node_id="n", inputs={}, callback_url="http://engine/cb"
        )
        ctx = ExecutionContext(req, execution_id="exec-43")
        ctx.report_progress(0.25)
        assert calls == [("http://engine/cb/progress", {"execution_id": "exec-43", "percent": 25})]

    def test_percent_clamped_and_message_truncated(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(context_module, "_deliver_progress_ping", self._recorder(calls))
        req = NodeExecutionRequest(
            run_id="r", node_id="n", inputs={}, callback_url="http://engine/cb"
        )
        ctx = ExecutionContext(req, execution_id="exec-44")
        ctx.report_progress(1.5, "x" * 1500)
        assert len(calls) == 1
        url, payload = calls[0]
        assert url == "http://engine/cb/progress"
        assert payload["percent"] == 100
        assert len(payload["message"]) == 1000

    def test_trailing_slash_normalized(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[tuple[str, dict]] = []
        monkeypatch.setattr(context_module, "_deliver_progress_ping", self._recorder(calls))
        req = NodeExecutionRequest(
            run_id="r", node_id="n", inputs={}, callback_url="http://engine/cb/"
        )
        ctx = ExecutionContext(req, execution_id="exec-46")
        ctx.report_progress(1.0)
        assert calls[0][0] == "http://engine/cb/progress"

    def test_deliver_swallows_httpx_errors(
        self, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
    ) -> None:
        def boom(url: str, **kwargs: object) -> None:
            raise ConnectionError("engine unreachable")

        monkeypatch.setattr(httpx, "post", boom)
        with caplog.at_level(logging.WARNING, logger="canvastekk_workflow_sdk.context"):
            context_module._deliver_progress_ping("http://engine/cb/progress", {"percent": 1})
        assert any("Progress ping failed" in rec.message for rec in caplog.records)
