"""Tests for workflow builder."""

import pytest

from canvastekk_workflow_sdk.workflow.builder import WorkflowBuilder
from canvastekk_workflow_sdk.workflow.models import EdgeType


class TestWorkflowBuilder:
    def test_basic_workflow_creation(self) -> None:
        spec = (
            WorkflowBuilder()
            .add_start("start", outputs=["message"])
            .add_node("echo", slug="echo-v1.0.0")
            .add_end("end")
            .connect("start", "echo", from_output="message", to_input="message")
            .connect("echo", "end", from_output="message", to_input="result")
            .build()
        )

        assert len(spec.nodes) == 3
        assert len(spec.edges) == 2

    def test_add_start_creates_start_slug(self) -> None:
        builder = WorkflowBuilder()
        builder.add_start("start_node")
        spec = builder.build(validate=False)

        start_node = next(n for n in spec.nodes if n.id == "start_node")
        assert start_node.slug == "__start__"

    def test_add_end_creates_end_slug(self) -> None:
        builder = WorkflowBuilder()
        builder.add_end("end_node")
        spec = builder.build(validate=False)

        end_node = next(n for n in spec.nodes if n.id == "end_node")
        assert end_node.slug == "__end__"

    def test_add_start_with_outputs_list(self) -> None:
        builder = WorkflowBuilder()
        builder.add_start("start", outputs=["file1", "file2"])
        spec = builder.build(validate=False)

        start_node = next(n for n in spec.nodes if n.id == "start")
        assert start_node.slug == "__start__"
        assert start_node.name == "START"
        assert start_node.inputs == {}

    def test_add_start_with_outputs_dict(self) -> None:
        builder = WorkflowBuilder()
        builder.add_start("start", outputs={"file": {"type": "string"}, "count": {"type": "integer"}})
        spec = builder.build(validate=False)

        start_node = next(n for n in spec.nodes if n.id == "start")
        assert start_node.slug == "__start__"
        assert start_node.inputs == {}

    def test_add_start_rejects_second_start(self) -> None:
        builder = WorkflowBuilder()
        builder.add_start("start1")

        with pytest.raises(ValueError, match="already has a START node"):
            builder.add_start("start2")

    def test_add_node_rejects_reserved_slugs(self) -> None:
        builder = WorkflowBuilder()

        with pytest.raises(ValueError, match="reserved slug '__start__'"):
            builder.add_node("node", slug="__start__")

        with pytest.raises(ValueError, match="reserved slug '__end__'"):
            builder.add_node("node", slug="__end__")

    def test_build_triggers_validation_by_default(self) -> None:
        builder = WorkflowBuilder()
        builder.add_start("start")
        builder.add_end("end")

        from canvastekk_workflow_sdk.workflow.validation import validate

        spec = builder.build(validate=False)
        result = validate(spec)

        assert result.is_valid is False
        assert any("no path to __end__" in error.lower() for error in result.errors)

    def test_build_skip_validation(self) -> None:
        spec = WorkflowBuilder().add_start("start").add_end("end").build(validate=False)

        assert len(spec.nodes) == 2

    def test_duplicate_node_id_detection(self) -> None:
        builder = WorkflowBuilder()
        builder.add_start("duplicate")

        with pytest.raises(ValueError, match="Duplicate node ID: 'duplicate'"):
            builder.add_node("duplicate", slug="echo-v1.0.0")

    def test_method_chaining(self) -> None:
        result = (
            WorkflowBuilder()
            .add_start("start")
            .add_node("node1", slug="echo-v1.0.0")
            .add_end("end")
            .connect("start", "node1")
            .connect("node1", "end")
        )

        assert isinstance(result, WorkflowBuilder)

    def test_connect_validates_node_ids_exist(self) -> None:
        builder = WorkflowBuilder()
        builder.add_start("start")
        builder.add_end("end")

        with pytest.raises(ValueError, match="Unknown source node: 'unknown'"):
            builder.connect("unknown", "start")

        with pytest.raises(ValueError, match="Unknown target node: 'unknown'"):
            builder.connect("start", "unknown")

    def test_connect_with_edge_type_parameter(self) -> None:
        spec = (
            WorkflowBuilder()
            .add_start("start")
            .add_node("node", slug="echo-v1.0.0")
            .add_end("end")
            .connect("start", "node", edge_type=EdgeType.SUCCESS)
            .build(validate=False)
        )

        edge = next(e for e in spec.edges if e.from_node == "start" and e.to_node == "node")
        assert edge.edge_type == EdgeType.SUCCESS

    def test_connect_with_condition(self) -> None:
        spec = (
            WorkflowBuilder()
            .add_start("start")
            .add_node("node", slug="echo-v1.0.0")
            .add_end("end")
            .connect("start", "node", condition="value > 10")
            .build(validate=False)
        )

        edge = next(e for e in spec.edges if e.from_node == "start" and e.to_node == "node")
        assert edge.condition == "value > 10"

    def test_add_node_with_all_parameters(self) -> None:
        spec = (
            WorkflowBuilder()
            .add_node("node1", slug="echo-v1.0.0", name="My Echo", version="1.0.0", inputs={"message": "hello"})
            .add_end("end")
            .build(validate=False)
        )

        node = next(n for n in spec.nodes if n.id == "node1")
        assert node.slug == "echo-v1.0.0"
        assert node.name == "My Echo"
        assert node.version == "1.0.0"
        assert node.inputs == {"message": "hello"}

    def test_add_start_with_config_schema(self) -> None:
        builder = WorkflowBuilder()
        builder.add_start("start", config_schema={"type": "object", "properties": {"value": {"type": "integer"}}})
        spec = builder.build(validate=False)

        start_node = next(n for n in spec.nodes if n.id == "start")
        assert start_node.slug == "__start__"
        assert start_node.inputs == {}

    def test_multiple_edges_between_same_nodes(self) -> None:
        spec = (
            WorkflowBuilder()
            .add_start("start")
            .add_node("node", slug="echo-v1.0.0")
            .add_end("end")
            .connect("start", "node", edge_type=EdgeType.SUCCESS)
            .connect("start", "node", edge_type=EdgeType.FAILURE)
            .build(validate=False)
        )

        edges = [e for e in spec.edges if e.from_node == "start" and e.to_node == "node"]
        assert len(edges) == 2
        assert edges[0].edge_type != edges[1].edge_type

    def test_add_start_with_workflow_node_id(self) -> None:
        builder = WorkflowBuilder()
        builder.add_start("start", workflow_node_id="wn-start-1")
        spec = builder.build(validate=False)

        start_node = next(n for n in spec.nodes if n.id == "start")
        assert start_node.workflow_node_id == "wn-start-1"

    def test_add_end_with_workflow_node_id(self) -> None:
        builder = WorkflowBuilder()
        builder.add_end("end", workflow_node_id="wn-end-1")
        spec = builder.build(validate=False)

        end_node = next(n for n in spec.nodes if n.id == "end")
        assert end_node.workflow_node_id == "wn-end-1"

    def test_add_node_with_workflow_node_id_and_config_schema(self) -> None:
        spec = (
            WorkflowBuilder()
            .add_node(
                "node1",
                slug="echo-v1.0.0",
                workflow_node_id="wn-123",
                config_schema={"type": "object", "properties": {"param": {"type": "string"}}},
            )
            .add_end("end")
            .build(validate=False)
        )

        node = next(n for n in spec.nodes if n.id == "node1")
        assert node.workflow_node_id == "wn-123"
        assert node.config_schema == {"type": "object", "properties": {"param": {"type": "string"}}}

    def test_add_node_with_optional_slug(self) -> None:
        spec = WorkflowBuilder().add_node("node1").add_end("end").build(validate=False)

        node = next(n for n in spec.nodes if n.id == "node1")
        assert node.slug is None
