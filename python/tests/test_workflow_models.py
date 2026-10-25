"""Tests for workflow models."""

from canvastekk_workflow_sdk.workflow.models import (
    EdgeType,
    WorkflowDefinitionNode,
    WorkflowDefinitionSpec,
    WorkflowEdgeDefinition,
)


class TestWorkflowSpec:
    def test_serialization_to_json(self) -> None:
        spec = WorkflowDefinitionSpec(
            nodes=[
                WorkflowDefinitionNode(id="node1", slug="echo-v1.0.0"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="node1", to_node="node2"),
            ],
        )
        data = spec.model_dump(mode="json")
        assert isinstance(data, dict)
        assert len(data["nodes"]) == 1
        assert len(data["edges"]) == 1

    def test_round_trip_serialization(self) -> None:
        original = WorkflowDefinitionSpec(
            metadata={"version": "1.0.0"},
            nodes=[
                WorkflowDefinitionNode(id="n1", slug="start-v1.0.0", inputs={"value": 42}),
                WorkflowDefinitionNode(id="n2", slug="echo-v1.0.0", version="1.0.0"),
            ],
            edges=[
                WorkflowEdgeDefinition(from_node="n1", to_node="n2", from_output="value", to_input="input"),
            ],
        )

        data = original.model_dump(mode="json")
        restored = WorkflowDefinitionSpec(**data)
        second_data = restored.model_dump(mode="json")

        assert data == second_data
        assert original.metadata == restored.metadata
        assert len(original.nodes) == len(restored.nodes)
        assert len(original.edges) == len(restored.edges)

    def test_metadata_defaults_to_empty_dict(self) -> None:
        spec = WorkflowDefinitionSpec(nodes=[], edges=[])
        assert spec.metadata == {}


class TestEdgeType:
    def test_enum_values(self) -> None:
        assert EdgeType.DEFAULT == "default"
        assert EdgeType.SUCCESS == "success"
        assert EdgeType.FAILURE == "failure"
        assert EdgeType.CONDITIONAL == "conditional"

    def test_edge_type_count(self) -> None:
        assert len(EdgeType) == 4


class TestWorkflowEdge:
    def test_default_values(self) -> None:
        edge = WorkflowEdgeDefinition(from_node="n1", to_node="n2")
        assert edge.id is not None
        assert isinstance(edge.id, str)
        assert edge.edge_type == EdgeType.DEFAULT
        assert edge.from_output == ""
        assert edge.to_input == ""
        assert edge.condition is None

    def test_auto_generated_id_unique(self) -> None:
        edge1 = WorkflowEdgeDefinition(from_node="n1", to_node="n2")
        edge2 = WorkflowEdgeDefinition(from_node="n2", to_node="n3")
        assert edge1.id != edge2.id

    def test_all_fields_settable(self) -> None:
        edge = WorkflowEdgeDefinition(
            id="custom-id",
            from_node="n1",
            to_node="n2",
            from_output="result",
            to_input="input",
            edge_type=EdgeType.SUCCESS,
            condition="true",
        )
        assert edge.id == "custom-id"
        assert edge.from_node == "n1"
        assert edge.to_node == "n2"
        assert edge.from_output == "result"
        assert edge.to_input == "input"
        assert edge.edge_type == EdgeType.SUCCESS
        assert edge.condition == "true"

    def test_condition_defaults_to_none(self) -> None:
        edge = WorkflowEdgeDefinition(from_node="n1", to_node="n2")
        assert edge.condition is None


class TestWorkflowNode:
    def test_minimal_node(self) -> None:
        node = WorkflowDefinitionNode(id="n1", slug="echo-v1.0.0")
        assert node.id == "n1"
        assert node.slug == "echo-v1.0.0"
        assert node.version is None
        assert node.name is None
        assert node.x is None
        assert node.y is None
        assert node.inputs == {}
        assert node.workflow_node_id is None
        assert node.config_schema is None

    def test_all_fields_settable(self) -> None:
        node = WorkflowDefinitionNode(
            id="n1",
            slug="segmentation-v1.0.0",
            version="1.0.0",
            name="My Segmentation",
            x=100.5,
            y=200.0,
            inputs={"threshold": 0.5},
            workflow_node_id="wn-123",
            config_schema={"type": "object"},
        )
        assert node.id == "n1"
        assert node.slug == "segmentation-v1.0.0"
        assert node.version == "1.0.0"
        assert node.name == "My Segmentation"
        assert node.x == 100.5
        assert node.y == 200.0
        assert node.inputs == {"threshold": 0.5}
        assert node.workflow_node_id == "wn-123"
        assert node.config_schema == {"type": "object"}

    def test_no_outputs_field(self) -> None:
        node = WorkflowDefinitionNode(id="n1", slug="echo-v1.0.0")
        assert not hasattr(node, "outputs")

    def test_inputs_default_to_empty_dict(self) -> None:
        node = WorkflowDefinitionNode(id="n1", slug="echo-v1.0.0")
        assert node.inputs == {}

    def test_positional_coordinates_optional(self) -> None:
        node = WorkflowDefinitionNode(id="n1", slug="echo-v1.0.0", x=50.0)
        assert node.x == 50.0
        assert node.y is None

        node2 = WorkflowDefinitionNode(id="n2", slug="echo-v1.0.0", y=100.0)
        assert node2.x is None
        assert node2.y == 100.0

    def test_slug_optional(self) -> None:
        node = WorkflowDefinitionNode(id="n1")
        assert node.slug is None


class TestWorkflowSpecComplete:
    def test_complete_workflow_spec(self) -> None:
        spec = WorkflowDefinitionSpec(
            metadata={"author": "test", "version": "1.0.0"},
            nodes=[
                WorkflowDefinitionNode(id="start", slug="__start__"),
                WorkflowDefinitionNode(
                    id="segment",
                    slug="segmentation-v1.0.0",
                    version="1.0.0",
                    name="Segmentation",
                    inputs={"method": "dbscan"},
                ),
                WorkflowDefinitionNode(id="end", slug="__end__"),
            ],
            edges=[
                WorkflowEdgeDefinition(
                    from_node="start",
                    to_node="segment",
                    from_output="point_cloud",
                    to_input="input_file",
                ),
                WorkflowEdgeDefinition(
                    from_node="segment",
                    to_node="end",
                    from_output="instances",
                    to_input="result",
                ),
            ],
        )
        assert len(spec.nodes) == 3
        assert len(spec.edges) == 2
        assert spec.metadata == {"author": "test", "version": "1.0.0"}
