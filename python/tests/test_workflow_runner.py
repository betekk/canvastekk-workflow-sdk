"""Tests for workflow runner, executor, resolver, and level computation."""

import tempfile
from pathlib import Path

import pytest

from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest
from canvastekk_workflow_sdk.workflow.executor import InProcessExecutor
from canvastekk_workflow_sdk.workflow.level import compute_levels
from canvastekk_workflow_sdk.workflow.models import (
    WorkflowDefinitionNode,
    WorkflowDefinitionSpec,
    WorkflowEdgeDefinition,
)
from canvastekk_workflow_sdk.workflow.resolver import _resolve_output, _walk_dot_path, resolve_inputs
from canvastekk_workflow_sdk.workflow.runner import ErrorPolicy, WorkflowRunner, WorkflowRunResult


class TestResolverOutput:
    def test_flat_key_resolution(self) -> None:
        source_outputs = {"message": "hello", "count": 5}
        result = _resolve_output(source_outputs, "message")
        assert result == "hello"

    def test_flat_key_not_found_raises(self) -> None:
        source_outputs = {"message": "hello"}
        with pytest.raises(KeyError):
            _resolve_output(source_outputs, "missing")

    def test_dot_notation_resolution(self) -> None:
        source_outputs = {"data": {"nested": {"value": 42}}}
        result = _resolve_output(source_outputs, "data.nested.value")
        assert result == 42

    def test_dot_path_partial_nesting(self) -> None:
        source_outputs = {"user": {"name": "Alice", "age": 30}}
        result = _resolve_output(source_outputs, "user.name")
        assert result == "Alice"

    def test_dot_path_not_found_raises(self) -> None:
        source_outputs = {"data": {"nested": {"value": 42}}}
        with pytest.raises(KeyError):
            _resolve_output(source_outputs, "data.missing.field")

    def test_empty_from_output_returns_full_outputs(self) -> None:
        source_outputs = {"file": "data.ply", "count": 5}
        result = _resolve_output(source_outputs, "")
        assert result == source_outputs

    def test_key_not_in_outputs_with_dot_raises(self) -> None:
        source_outputs = {"message": "hello"}
        with pytest.raises(KeyError):
            _resolve_output(source_outputs, "missing")


class TestResolveInputs:
    def test_static_inputs_used(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="node1", slug="echo-v1.0.0", inputs={"threshold": 0.5}),
            ],
            edges=[],
        )
        node_outputs = {}

        result = resolve_inputs("node1", spec, node_outputs)
        assert result == {"threshold": 0.5}

    def test_static_inputs_merged_with_edge_inputs(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="node1", slug="echo-v1.0.0", inputs={"threshold": 0.5}),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="node1", from_output="file", to_input="input_file"),
            ],
        )
        node_outputs = {"start": {"file": "/data/input.ply"}}

        result = resolve_inputs("node1", spec, node_outputs)
        assert result == {"threshold": 0.5, "input_file": "/data/input.ply"}

    def test_edge_overwrites_static_input(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="node1", slug="echo-v1.0.0", inputs={"file": "/static.txt"}),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="node1", from_output="file", to_input="file"),
            ],
        )
        node_outputs = {"start": {"file": "/dynamic.ply"}}

        result = resolve_inputs("node1", spec, node_outputs)
        assert result == {"file": "/dynamic.ply"}

    def test_multiple_incoming_edges_merged(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="node1", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="node2", slug="echo-v1.0.0"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="node1", from_output="file1", to_input="input1"),
                WorkflowEdgeDefinition(from_node="start", to_node="node1", from_output="file2", to_input="input2"),
            ],
        )
        node_outputs = {"start": {"file1": "a.ply", "file2": "b.ply"}}

        result = resolve_inputs("node1", spec, node_outputs)
        assert result == {"input1": "a.ply", "input2": "b.ply"}

    def test_empty_from_output_returns_full_outputs(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="node1", slug="echo-v1.0.0"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="node1", from_output="", to_input=""),
            ],
        )
        node_outputs = {"start": {"file": "data.ply", "count": 5}}

        result = resolve_inputs("node1", spec, node_outputs)
        assert result == {"file": "data.ply", "count": 5}


class TestWalkDotPath:
    def test_walk_simple_path(self) -> None:
        data = {"user": {"name": "Alice"}}
        result = _walk_dot_path(data, "user.name")
        assert result == "Alice"

    def test_walk_deep_path(self) -> None:
        data = {"a": {"b": {"c": {"d": 42}}}}
        result = _walk_dot_path(data, "a.b.c.d")
        assert result == 42

    def test_walk_empty_segment_raises(self) -> None:
        data = {"a": {"b": 1}}
        with pytest.raises(KeyError, match="empty segment"):
            _walk_dot_path(data, "a..b")

    def test_walk_non_dict_raises(self) -> None:
        data = {"a": 42}
        with pytest.raises(KeyError, match="non-dict"):
            _walk_dot_path(data, "a.b")

    def test_walk_missing_key_raises(self) -> None:
        data = {"a": {"b": 1}}
        with pytest.raises(KeyError, match="not found"):
            _walk_dot_path(data, "a.missing")


class TestLevelComputation:
    def test_single_node(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[WorkflowDefinitionNode(id="node1", slug="echo-v1.0.0")],
            edges=[],
        )
        levels = compute_levels(spec)
        assert levels == [["node1"]]

    def test_linear_chain(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="A", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="B", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="C", slug="echo-v1.0.0"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="A", to_node="B"),
                WorkflowEdgeDefinition(from_node="B", to_node="C"),
            ],
        )
        levels = compute_levels(spec)
        assert levels == [["A"], ["B"], ["C"]]

    def test_diamond_dag(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="A", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="B", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="C", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="D", slug="echo-v1.0.0"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="A", to_node="B"),
                WorkflowEdgeDefinition(from_node="A", to_node="C"),
                WorkflowEdgeDefinition(from_node="B", to_node="D"),
                WorkflowEdgeDefinition(from_node="C", to_node="D"),
            ],
        )
        levels = compute_levels(spec)
        assert levels == [["A"], ["B", "C"], ["D"]]

    def test_empty_spec(self) -> None:
        spec = WorkflowDefinitionSpec(nodes=[], edges=[])
        levels = compute_levels(spec)
        assert levels == []

    def test_cycle_raises(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="A", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="B", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="C", slug="echo-v1.0.0"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="A", to_node="B"),
                WorkflowEdgeDefinition(from_node="B", to_node="C"),
                WorkflowEdgeDefinition(from_node="C", to_node="A"),
            ],
        )
        with pytest.raises(ValueError, match="cycle"):
            compute_levels(spec)


class TestInProcessExecutor:
    def test_executor_registration(self) -> None:
        executor = InProcessExecutor()
        node = EchoNode()
        result = executor.register("echo-v1.0.0", node)
        assert result is executor
        assert executor.has("echo-v1.0.0")

    def test_executor_has_checks_registry(self) -> None:
        executor = InProcessExecutor()
        assert executor.has("missing") is False

        executor.register("echo-v1.0.0", EchoNode())
        assert executor.has("echo-v1.0.0") is True


class TestWorkflowRunner:
    def test_linear_workflow_execution(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="echo", slug="echo-v1.0.0", inputs={"message": "hello"}),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="echo"),
                WorkflowEdgeDefinition(from_node="echo", to_node="end", from_output="message", to_input="result"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("echo-v1.0.0", EchoNode())
        runner = WorkflowRunner(executor)

        result = runner.run(spec)

        assert result.status == "completed"
        assert result.final_outputs == {"result": "hello"}
        assert len(result.node_results) == 3
        assert result.duration_ms >= 0

    def test_workflow_run_result_structure(self) -> None:
        result = WorkflowRunResult(
            status="completed",
            final_outputs={"value": 42},
            node_results=[],
            duration_ms=100,
        )
        assert result.status == "completed"
        assert result.final_outputs == {"value": 42}
        assert result.node_results == []
        assert result.duration_ms == 100

    def test_node_results_structure(self) -> None:
        from canvastekk_workflow_sdk.workflow.runner import NodeResult

        node_result = NodeResult(
            node_id="n1",
            slug="echo-v1.0.0",
            status="completed",
            outputs={"message": "hello"},
            duration_ms=50,
        )
        assert node_result.node_id == "n1"
        assert node_result.slug == "echo-v1.0.0"
        assert node_result.status == "completed"
        assert node_result.outputs == {"message": "hello"}
        assert node_result.duration_ms == 50

    def test_error_handling_failing_node(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="fail", slug="failing-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="fail"),
                WorkflowEdgeDefinition(from_node="fail", to_node="end"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("failing-v1.0.0", FailingNode())
        runner = WorkflowRunner(executor)

        result = runner.run(spec, inputs={})

        assert result.status == "failed"
        failed_result = next(r for r in result.node_results if r.node_id == "fail")
        assert failed_result.status == "failed"
        assert failed_result.error is not None

    def test_error_policy_fail_fast(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="fail", slug="failing-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="fail"),
                WorkflowEdgeDefinition(from_node="fail", to_node="end"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("failing-v1.0.0", FailingNode())
        runner = WorkflowRunner(executor, error_policy=ErrorPolicy.FAIL_FAST)

        result = runner.run(spec, inputs={})

        assert result.status == "failed"
        fail_result = next((r for r in result.node_results if r.node_id == "fail"), None)
        assert fail_result is not None
        assert fail_result.status == "failed"

    def test_error_policy_continue(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="fail", slug="failing-v1.0.0"),
                WorkflowDefinitionNode(id="skip", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="fail"),
                WorkflowEdgeDefinition(from_node="start", to_node="skip"),
                WorkflowEdgeDefinition(from_node="fail", to_node="end"),
                WorkflowEdgeDefinition(from_node="skip", to_node="end"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("failing-v1.0.0", FailingNode())
        executor.register("echo-v1.0.0", EchoNode())
        runner = WorkflowRunner(executor, error_policy=ErrorPolicy.CONTINUE)

        result = runner.run(spec, inputs={})

        assert result.status == "failed"
        skip_result = next(r for r in result.node_results if r.node_id == "skip")
        assert skip_result.status == "completed"

    def test_missing_executor_fails_node(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="missing", slug="unknown-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="missing"),
                WorkflowEdgeDefinition(from_node="missing", to_node="end"),
            ],
        )

        executor = InProcessExecutor()
        runner = WorkflowRunner(executor)

        result = runner.run(spec, inputs={})

        assert result.status == "failed"
        missing_result = next(r for r in result.node_results if r.node_id == "missing")
        assert missing_result.status == "failed"
        assert "No executor registered" in missing_result.error

    def test_upstream_failure_skips_dependent_nodes(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="fail", slug="failing-v1.0.0"),
                WorkflowDefinitionNode(id="dependent", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="fail"),
                WorkflowEdgeDefinition(from_node="fail", to_node="dependent"),
                WorkflowEdgeDefinition(from_node="dependent", to_node="end"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("failing-v1.0.0", FailingNode())
        executor.register("echo-v1.0.0", EchoNode())
        runner = WorkflowRunner(executor, error_policy=ErrorPolicy.CONTINUE)

        result = runner.run(spec, inputs={})

        dependent_result = next(r for r in result.node_results if r.node_id == "dependent")
        assert dependent_result.status == "skipped"
        assert dependent_result.skipped_reason == "upstream_failed"


class EchoNode(BaseNode):
    definition = WorkflowNodeManifest(
        slug="echo",
        version="1.0.0",
        name="Echo",
        description="Returns input message",
        input_schema={"type": "object"},
        output_schema={"type": "object", "properties": {"message": {"type": "string"}}},
    )

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
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

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        raise ValueError("Intentional failure")


class FileWriterNode(BaseNode):
    definition = WorkflowNodeManifest(
        slug="file-writer",
        version="1.0.0",
        name="File Writer",
        description="Writes a file to output_dir",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
        },
    )

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        path = context.output_path("data.txt")
        path.write_text("hello from A")
        return {"file_path": str(path)}


class FileReaderNode(BaseNode):
    definition = WorkflowNodeManifest(
        slug="file-reader",
        version="1.0.0",
        name="File Reader",
        description="Reads a file from file_path input",
        input_schema={
            "type": "object",
            "properties": {"file_path": {"type": "string"}},
        },
        output_schema={
            "type": "object",
            "properties": {"content": {"type": "string"}},
        },
    )

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        content = Path(inputs["file_path"]).read_text()
        return {"content": content}


class OutputDirCaptureNode(BaseNode):
    definition = WorkflowNodeManifest(
        slug="dir-capture",
        version="1.0.0",
        name="Dir Capture",
        description="Captures output_dir path in outputs",
        input_schema={"type": "object"},
        output_schema={
            "type": "object",
            "properties": {"captured_dir": {"type": "string"}},
        },
    )

    def __init__(self, capture_list: list[str] | None = None) -> None:
        super().__init__()
        self._capture_list = capture_list

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        dir_str = str(context.output_dir)
        if self._capture_list is not None:
            self._capture_list.append(dir_str)
        return {"captured_dir": dir_str}


class TestWorkflowRunnerOutputDir:
    def test_file_passing_between_nodes(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="writer", slug="file-writer-v1.0.0"),
                WorkflowDefinitionNode(id="reader", slug="file-reader-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="writer"),
                WorkflowEdgeDefinition(
                    from_node="writer",
                    to_node="reader",
                    from_output="file_path",
                    to_input="file_path",
                ),
                WorkflowEdgeDefinition(
                    from_node="reader",
                    to_node="end",
                    from_output="content",
                    to_input="result",
                ),
            ],
        )

        executor = InProcessExecutor()
        executor.register("file-writer-v1.0.0", FileWriterNode())
        executor.register("file-reader-v1.0.0", FileReaderNode())
        runner = WorkflowRunner(executor)

        result = runner.run(spec, inputs={})

        assert result.status == "completed"
        assert result.final_outputs["result"] == "hello from A"

    def test_user_supplied_output_dir_not_cleaned_up(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "my_outputs"

            spec = WorkflowDefinitionSpec(
                nodes=[
                    WorkflowDefinitionNode(id="start", slug="__start__"),
                    WorkflowDefinitionNode(id="echo", slug="echo-v1.0.0", inputs={"message": "hi"}),
                    WorkflowDefinitionNode(id="end", slug="__end__"),
                ],
                edges=[
                    WorkflowEdgeDefinition(from_node="start", to_node="echo"),
                    WorkflowEdgeDefinition(
                        from_node="echo",
                        to_node="end",
                        from_output="message",
                        to_input="result",
                    ),
                ],
            )

            executor = InProcessExecutor()
            executor.register("echo-v1.0.0", EchoNode())
            runner = WorkflowRunner(executor, output_dir=output_dir)

            result = runner.run(spec, inputs={})

            assert result.status == "completed"
            assert output_dir.exists()
            assert result.output_dir == output_dir

    def test_auto_created_temp_dir_cleaned_up(self) -> None:
        captured_dir: list[str] = []

        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="cap", slug="dir-capture-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="cap"),
                WorkflowEdgeDefinition(from_node="cap", to_node="end"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("dir-capture-v1.0.0", OutputDirCaptureNode(captured_dir))
        runner = WorkflowRunner(executor)

        result = runner.run(spec, inputs={})

        assert result.status == "completed"
        assert captured_dir
        assert not Path(captured_dir[0]).exists()
        assert result.output_dir is None

    def test_cleanup_false_preserves_temp_dir(self) -> None:
        captured_dir: list[str] = []

        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="cap", slug="dir-capture-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="cap"),
                WorkflowEdgeDefinition(from_node="cap", to_node="end"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("dir-capture-v1.0.0", OutputDirCaptureNode(captured_dir))
        runner = WorkflowRunner(executor, cleanup=False)

        result = runner.run(spec, inputs={})

        assert result.status == "completed"
        assert captured_dir
        assert Path(captured_dir[0]).exists()
        assert Path(captured_dir[0]) == result.output_dir / "cap"

    def test_auto_temp_dir_cleaned_up_on_exception(self) -> None:
        captured_dir: list[str] = []

        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="cap", slug="dir-capture-v1.0.0"),
                WorkflowDefinitionNode(id="fail", slug="failing-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="cap"),
                WorkflowEdgeDefinition(from_node="cap", to_node="fail"),
                WorkflowEdgeDefinition(from_node="fail", to_node="end"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("dir-capture-v1.0.0", OutputDirCaptureNode(captured_dir))
        executor.register("failing-v1.0.0", FailingNode())
        runner = WorkflowRunner(executor)

        result = runner.run(spec, inputs={})

        assert result.status == "failed"
        assert captured_dir
        assert not Path(captured_dir[0]).exists()

    def test_result_exposes_output_dir_when_not_cleaned(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp) / "outputs"

            spec = WorkflowDefinitionSpec(
                nodes=[
                    WorkflowDefinitionNode(id="start", slug="__start__"),
                    WorkflowDefinitionNode(id="echo", slug="echo-v1.0.0", inputs={"message": "x"}),
                    WorkflowDefinitionNode(id="end", slug="__end__"),
                ],
                edges=[
                    WorkflowEdgeDefinition(from_node="start", to_node="echo"),
                    WorkflowEdgeDefinition(
                        from_node="echo",
                        to_node="end",
                        from_output="message",
                        to_input="result",
                    ),
                ],
            )

            executor = InProcessExecutor()
            executor.register("echo-v1.0.0", EchoNode())
            runner = WorkflowRunner(executor, output_dir=output_dir)

            result = runner.run(spec, inputs={})

            assert result.output_dir == output_dir

    def test_result_output_dir_none_when_auto_cleaned(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="echo", slug="echo-v1.0.0", inputs={"message": "x"}),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="echo"),
                WorkflowEdgeDefinition(
                    from_node="echo",
                    to_node="end",
                    from_output="message",
                    to_input="result",
                ),
            ],
        )

        executor = InProcessExecutor()
        executor.register("echo-v1.0.0", EchoNode())
        runner = WorkflowRunner(executor)

        result = runner.run(spec, inputs={})

        assert result.output_dir is None


class TestStartInputSeeding:
    """Regression tests for run(spec, inputs={...}) — seeded START outputs
    must reach downstream nodes (previously clobbered by the re-run start
    handler, crashing the whole run)."""

    def test_nonempty_run_inputs_reach_downstream(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="echo", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(
                    from_node="start", to_node="echo", from_output="point_cloud", to_input="message"
                ),
                WorkflowEdgeDefinition(from_node="echo", to_node="end", from_output="message", to_input="result"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("echo-v1.0.0", EchoNode())
        runner = WorkflowRunner(executor)

        result = runner.run(spec, inputs={"point_cloud": "/tmp/scan.ply"})

        assert result.status == "completed"
        assert result.final_outputs == {"result": "/tmp/scan.ply"}

    def test_seeded_inputs_merge_with_static_start_inputs(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__", inputs={"static_key": "static"}),
                WorkflowDefinitionNode(id="echo", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="echo", from_output="static_key", to_input="message"),
                WorkflowEdgeDefinition(from_node="echo", to_node="end", from_output="message", to_input="result"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("echo-v1.0.0", EchoNode())
        runner = WorkflowRunner(executor)

        result = runner.run(spec, inputs={"seeded_key": "seeded"})

        assert result.status == "completed"
        assert result.final_outputs == {"result": "static"}
        start_result = next(r for r in result.node_results if r.node_id == "start")
        assert start_result.status == "completed"
        assert start_result.outputs == {"static_key": "static", "seeded_key": "seeded"}


class TestResolverErrorIsolation:
    """A mis-wired edge must fail ONE node, not crash run()."""

    def test_user_node_bad_from_output_is_failed_node_result(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="echo", slug="echo-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(
                    from_node="start", to_node="echo", from_output="missing_key", to_input="message"
                ),
                WorkflowEdgeDefinition(from_node="echo", to_node="end", from_output="message", to_input="result"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("echo-v1.0.0", EchoNode())
        runner = WorkflowRunner(executor)

        result = runner.run(spec, inputs={"other": "x"})

        assert result.status == "failed"
        echo_result = next(r for r in result.node_results if r.node_id == "echo")
        assert echo_result.status == "failed"
        assert "Input resolution failed" in echo_result.error


class TestPerNodeOutputSubdirs:
    """Per-node output subdirs prevent same-filename collisions between
    parallel nodes (DA-1711 step 2.3)."""

    def test_parallel_nodes_same_filename_no_collision(self) -> None:
        captured: list[str] = []

        class CollisionNode(BaseNode):
            definition = WorkflowNodeManifest(
                slug="collision",
                version="1.0.0",
                name="Collision",
                description="Writes result.txt",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            def execute(self, inputs, context):
                p = context.output_path("result.txt")
                p.write_text(context.node_id)
                captured.append(str(p))
                return {"file": str(p)}

        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(id="a", slug="collision-v1.0.0"),
                WorkflowDefinitionNode(id="b", slug="collision-v1.0.0"),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="start", to_node="a"),
                WorkflowEdgeDefinition(from_node="start", to_node="b"),
                WorkflowEdgeDefinition(from_node="a", to_node="end"),
                WorkflowEdgeDefinition(from_node="b", to_node="end"),
            ],
        )

        executor = InProcessExecutor()
        executor.register("collision-v1.0.0", CollisionNode())
        runner = WorkflowRunner(executor, cleanup=False)

        result = runner.run(spec, inputs={})

        assert result.status == "completed"
        assert len(captured) == 2
        assert captured[0] != captured[1]
        contents = {Path(p).parent.name: Path(p).read_text() for p in captured}
        assert contents == {"a": "a", "b": "b"}
        import shutil

        shutil.rmtree(result.output_dir, ignore_errors=True)
