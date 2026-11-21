"""#281: RunContext on the node execution context.

Covers the SDK half of the run-context contract (epic
betekk/canvastekk-tracker#4320): the request carries an optional versioned
``run_context``, the context exposes it, and the result-file writer prefers
``run_context.workflow_run_id`` over the bare wire ``run_id``. Absent
``run_context`` behaves exactly as before (pre-#1443 engines, local runs).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from canvastekk_workflow_sdk import NodeExecutionContext, NodeExecutionRequest
from canvastekk_workflow_sdk.result_file import read_result_file_header, write_result_file
from canvastekk_workflow_sdk.run_context import RunContext

_V1_SAMPLE = {
    "run_context_version": "1.0.0",
    "workflow_run_id": "3f2b8a2e-1111-4222-8333-444455556666",
    "workflow_definition_id": "def-uuid-1",
    "workflow_definition_slug": "model-checker",
    "workflow_definition_version": "1.4.0",
    "account_id": 42,
    "started_at": "2026-11-21T12:00:00+00:00",
}


class TestRunContextModel:
    def test_parses_v1_sample(self) -> None:
        ctx = RunContext.model_validate(_V1_SAMPLE)
        assert ctx.workflow_run_id == _V1_SAMPLE["workflow_run_id"]
        assert ctx.workflow_definition_slug == "model-checker"
        assert ctx.account_id == 42

    def test_rejects_missing_workflow_run_id(self) -> None:
        with pytest.raises(Exception):
            RunContext.model_validate({"run_context_version": "1.0.0"})

    def test_optional_fields_default_none(self) -> None:
        ctx = RunContext.model_validate(
            {"run_context_version": "1.0.0", "workflow_run_id": "r-1"}
        )
        assert ctx.workflow_definition_id is None
        assert ctx.started_at is None


class TestRequestAndContext:
    def test_request_with_run_context_populates_context(self) -> None:
        request = NodeExecutionRequest.model_validate(
            {"run_id": "r-1", "node_id": "n-1", "run_context": _V1_SAMPLE}
        )
        ctx = NodeExecutionContext(request=request)
        assert ctx.run_context is not None
        assert ctx.run_context.workflow_run_id == _V1_SAMPLE["workflow_run_id"]

    def test_request_without_run_context_leaves_none(self) -> None:
        request = NodeExecutionRequest.model_validate({"run_id": "r-1", "node_id": "n-1"})
        ctx = NodeExecutionContext(request=request)
        assert ctx.run_context is None

    def test_local_context_has_no_run_context(self, tmp_path: Path) -> None:
        ctx = NodeExecutionContext(output_dir=tmp_path / "r-1" / "n-1", run_id="r-1", node_id="n-1")
        assert ctx.run_context is None


class TestResultFileHeaderId:
    @pytest.fixture
    def ctx_with(self, tmp_path: Path):
        def _make(run_context: RunContext | None) -> NodeExecutionContext:
            request = (
                NodeExecutionRequest.model_validate(
                    {"run_id": "wire-run-id", "node_id": "n-1", "run_context": run_context.model_dump()}
                )
                if run_context
                else None
            )
            if request is not None:
                return NodeExecutionContext(request=request)
            return NodeExecutionContext(
                output_dir=tmp_path / "wire-run-id" / "n-1", run_id="wire-run-id", node_id="n-1"
            )

        return _make

    def test_header_prefers_run_context_workflow_run_id(self, ctx_with) -> None:
        ctx = ctx_with(RunContext.model_validate(_V1_SAMPLE))
        out = write_result_file(
            ctx, result_schema="model_check.rule", result_schema_version="0.1.0", body={"ok": True}
        )
        with Path(out["result_file"]).open("rb") as stream:
            header = read_result_file_header(stream)
        assert header["workflow_run_id"] == _V1_SAMPLE["workflow_run_id"]

    def test_header_falls_back_to_run_id_without_run_context(self, ctx_with) -> None:
        ctx = ctx_with(None)
        out = write_result_file(
            ctx, result_schema="model_check.rule", result_schema_version="0.1.0", body={"ok": True}
        )
        with Path(out["result_file"]).open("rb") as stream:
            header = read_result_file_header(stream)
        assert header["workflow_run_id"] == "wire-run-id"
