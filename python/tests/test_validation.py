"""Tests for input validation against JSON Schema."""

from typing import Any

from canvastekk_workflow_sdk import NodeExecutionContext, NodeExecutionRequest, WorkflowNodeBase, WorkflowNodeManifest


class StrictNode(WorkflowNodeBase):
    manifest = WorkflowNodeManifest(
        name="strict",
        version="1.0.0",
        title="Strict",
        description="Requires specific inputs",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "count": {"type": "integer", "minimum": 0},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["name"],
        },
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
        return {"echo": inputs.get("name")}


class LooseNode(WorkflowNodeBase):
    manifest = WorkflowNodeManifest(
        name="loose",
        version="1.0.0",
        title="Loose",
        description="Accepts anything",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )

    def execute(self, inputs: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
        return inputs


class TestInputValidation:
    def test_valid_inputs_pass(self) -> None:
        node = StrictNode()
        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"name": "test", "count": 5},
            )
        )
        assert response.status == "pass"
        assert response.outputs == {"echo": "test"}

    def test_missing_required_field_fails(self) -> None:
        node = StrictNode()
        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"count": 5},
            )
        )
        assert response.status == "fail"
        assert response.error_code == "VALIDATION_ERROR"
        assert "name" in response.error

    def test_wrong_type_fails(self) -> None:
        node = StrictNode()
        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"name": "test", "count": "not_a_number"},
            )
        )
        assert response.status == "fail"
        assert response.error_code == "VALIDATION_ERROR"

    def test_constraint_violation_fails(self) -> None:
        node = StrictNode()
        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"name": "test", "count": -5},
            )
        )
        assert response.status == "fail"
        assert response.error_code == "VALIDATION_ERROR"

    def test_wrong_array_item_type_fails(self) -> None:
        node = StrictNode()
        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"name": "test", "tags": [1, 2, 3]},
            )
        )
        assert response.status == "fail"
        assert response.error_code == "VALIDATION_ERROR"

    def test_loose_schema_always_passes(self) -> None:
        node = LooseNode()
        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"anything": "goes", "num": 42},
            )
        )
        assert response.status == "pass"

    def test_loose_schema_empty_inputs(self) -> None:
        node = LooseNode()
        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={},
            )
        )
        assert response.status == "pass"

    def test_multiple_errors_reports_first(self) -> None:
        node = StrictNode()
        response = node.run(
            NodeExecutionRequest(
                run_id="r1",
                node_id="n1",
                inputs={"count": "bad", "tags": "not_array"},
            )
        )
        assert response.status == "fail"
        assert response.error_code == "VALIDATION_ERROR"
