"""Tests for the DA-3009 post-execution heap trim."""

import sys
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest, create_node_app
from canvastekk_workflow_sdk import app as app_module


class EchoNode(BaseNode):
    """Minimal echo node (mirrors test_app.py)."""

    definition = WorkflowNodeManifest(
        slug="echo-trim",
        version="1.0.0",
        name="EchoTrim",
        description="Returns message unchanged",
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
    """Node whose execute always raises."""

    definition = WorkflowNodeManifest(
        slug="fail-trim",
        version="1.0.0",
        name="FailTrim",
        description="Always raises",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
        raise RuntimeError("boom")


def _reset_libc_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Force the module-level libc resolver to re-run for each test."""
    monkeypatch.setattr(app_module, "_LIBC_HANDLE", None)
    monkeypatch.setattr(app_module, "_LIBC_RESOLVED", False)


class _FakeLibc:
    """Stands in for ctypes.CDLL — records malloc_trim calls."""

    def __init__(self, with_symbol: bool = True) -> None:
        self.calls = 0
        if with_symbol:
            self.malloc_trim = self._trim

    def _trim(self, _arg: int) -> int:
        self.calls += 1
        return 1


class TestReleaseFreedHeap:
    """Branch coverage for _release_freed_heap."""

    def test_opt_out_env_skips_trim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_SDK_MEMORY_TRIM", "0")
        _reset_libc_cache(monkeypatch)
        with (
            patch.object(app_module.gc, "collect") as gc_collect,
            patch("ctypes.CDLL") as fake_cdll,
        ):
            app_module._release_freed_heap()
        gc_collect.assert_not_called()
        fake_cdll.assert_not_called()

    def test_non_linux_platform_skips_trim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CANVASTEKK_SDK_MEMORY_TRIM", raising=False)
        monkeypatch.setattr(app_module.sys, "platform", "darwin")
        _reset_libc_cache(monkeypatch)
        with patch("ctypes.CDLL") as fake_cdll:
            app_module._release_freed_heap()
        fake_cdll.assert_not_called()

    def test_glibc_path_trims_once_after_gc(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CANVASTEKK_SDK_MEMORY_TRIM", raising=False)
        _reset_libc_cache(monkeypatch)
        fake = _FakeLibc()
        with (
            patch("ctypes.util.find_library", return_value="libc.so.6"),
            patch("ctypes.CDLL", return_value=fake) as fake_cdll,
            patch.object(app_module.gc, "collect") as gc_collect,
        ):
            app_module._release_freed_heap()
            app_module._release_freed_heap()
        gc_collect.assert_called()
        fake_cdll.assert_called_once()
        assert fake.calls == 2

    def test_missing_malloc_trim_symbol_disables_trim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CANVASTEKK_SDK_MEMORY_TRIM", raising=False)
        _reset_libc_cache(monkeypatch)
        fake = _FakeLibc(with_symbol=False)
        with (
            patch("ctypes.util.find_library", return_value="libc.so.6"),
            patch("ctypes.CDLL", return_value=fake),
            patch.object(app_module.gc, "collect") as gc_collect,
        ):
            app_module._release_freed_heap()
            app_module._release_freed_heap()
        gc_collect.assert_not_called()
        assert app_module._LIBC_HANDLE is None

    def test_cdll_failure_is_swallowed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CANVASTEKK_SDK_MEMORY_TRIM", raising=False)
        _reset_libc_cache(monkeypatch)
        with patch("ctypes.CDLL", side_effect=OSError("no libc")):
            app_module._release_freed_heap()
        assert app_module._LIBC_HANDLE is None

    def test_find_library_fallback_uses_libc_so_6(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When find_library returns None the loader falls back to 'libc.so.6'."""
        monkeypatch.delenv("CANVASTEKK_SDK_MEMORY_TRIM", raising=False)
        _reset_libc_cache(monkeypatch)
        fake = _FakeLibc()
        with (
            patch("ctypes.util.find_library", return_value=None),
            patch("ctypes.CDLL", return_value=fake) as fake_cdll,
        ):
            app_module._release_freed_heap()
        fake_cdll.assert_called_once_with("libc.so.6")
        assert fake.calls == 1


class TestExecuteTrimsExactlyOnce:
    """The finally wiring around the /execute execution section."""

    def _client(self) -> TestClient:
        return TestClient(create_node_app(EchoNode()))

    def test_success_path_trims_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []
        monkeypatch.setattr(app_module, "_release_freed_heap", lambda: calls.append(1))
        client = self._client()
        response = client.post(
            "/execute",
            json={"run_id": "test-run", "node_id": "test-node", "inputs": {"message": "hi"}},
        )
        assert response.status_code == 200
        assert calls == [1]

    def test_error_path_trims_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        calls: list[int] = []
        monkeypatch.setattr(app_module, "_release_freed_heap", lambda: calls.append(1))
        client = TestClient(create_node_app(FailingNode()), raise_server_exceptions=False)
        response = client.post(
            "/execute",
            json={"run_id": "test-run", "node_id": "test-node", "inputs": {}},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "fail"
        assert calls == [1]

    def test_timeout_path_trims_once(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """NodeTimeoutError propagates through the finally — the production
        poisoning scenario (heavy invocation outlives its budget)."""
        calls: list[int] = []
        monkeypatch.setattr(app_module, "_release_freed_heap", lambda: calls.append(1))

        class SlowNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="slow-trim",
                version="1.0.0",
                name="SlowTrim",
                description="Sleeps past its budget",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
                timeout_seconds=1,
            )

            def execute(self, inputs: dict[str, Any], context: ExecutionContext) -> dict[str, Any]:
                import time

                time.sleep(2.0)
                return {}

        client = TestClient(create_node_app(SlowNode()), raise_server_exceptions=False)
        response = client.post(
            "/execute",
            json={"run_id": "test-run", "node_id": "test-node", "inputs": {}},
        )
        assert response.status_code >= 400
        assert calls == [1]

    def test_validation_short_circuit_does_not_trim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Early 400/422 returns happen before the execution section — no trim."""
        calls: list[int] = []
        monkeypatch.setattr(app_module, "_release_freed_heap", lambda: calls.append(1))
        client = self._client()
        response = client.post("/execute", content=b"not-json", headers={"Content-Type": "application/json"})
        assert response.status_code == 400
        assert calls == []


def test_real_glibc_trim_returns_memory_when_available() -> None:
    """On glibc Linux the real helper runs end-to-end without error."""
    if sys.platform != "linux":
        pytest.skip("linux-only")
    blob = bytearray(50 * 1024 * 1024)
    del blob
    app_module._release_freed_heap()
