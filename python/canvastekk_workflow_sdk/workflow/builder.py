"""
Workflow Builder

Fluent API for constructing workflow definitions with built-in START/END nodes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from canvastekk_workflow_sdk.workflow.models import (
    EdgeType,
    WorkflowDefinitionNode,
    WorkflowDefinitionSpec,
    WorkflowEdgeDefinition,
)

if TYPE_CHECKING:
    pass


class WorkflowBuilder:
    """Fluent builder for workflow definitions.

    Example::

        spec = (
            WorkflowBuilder()
            .add_start("start", outputs=["point_cloud"])
            .add_node("segment", slug="segmentation-v1.0.0", inputs={"method": "dbscan"})
            .add_end("end")
            .connect("start", "segment", from_output="point_cloud", to_input="input_file")
            .connect("segment", "end", from_output="instances", to_input="result")
            .build()
        )
    """

    def __init__(self) -> None:
        """Initialize workflow builder."""
        self._nodes: list[WorkflowDefinitionNode] = []
        self._edges: list[WorkflowEdgeDefinition] = []
        self._node_ids: set[str] = set()
        self._has_start = False

    def _check_duplicate(self, node_id: str) -> None:
        if node_id in self._node_ids:
            raise ValueError(f"Duplicate node ID: '{node_id}'")

    def add_start(
        self,
        node_id: str = "start",
        *,
        outputs: list[str] | dict[str, Any] | None = None,
        config_schema: dict[str, Any] | None = None,
        workflow_node_id: str | None = None,
    ) -> WorkflowBuilder:
        """Add a START node to the workflow.

        Args:
            node_id: Unique ID for the node.
            outputs: List of output field names or full schema.
            config_schema: Configuration schema for the node.
            workflow_node_id: Optional workflow node type ID.

        Returns:
            Self for chaining.

        Raises:
            ValueError: If START node already exists or ID is duplicate.
        """
        if self._has_start:
            raise ValueError("Workflow already has a START node. Only one is allowed.")
        self._check_duplicate(node_id)

        cs: dict[str, Any] | None = config_schema
        if cs is None and outputs is not None:
            if isinstance(outputs, list):
                props = {name: {"type": "string"} for name in outputs}
            else:
                props = outputs
            cs = {
                "type": "object",
                "properties": props,
            }

        self._nodes.append(
            WorkflowDefinitionNode(
                id=node_id,
                slug="__start__",
                name="START",
                inputs={},
                config_schema=cs,
                workflow_node_id=workflow_node_id,
            )
        )
        self._node_ids.add(node_id)
        self._has_start = True
        return self

    def add_end(
        self,
        node_id: str = "end",
        *,
        workflow_node_id: str | None = None,
    ) -> WorkflowBuilder:
        """Add an END node to the workflow.

        Args:
            node_id: Unique ID for the node.
            workflow_node_id: Optional workflow node type ID.

        Returns:
            Self for chaining.

        Raises:
            ValueError: If ID is duplicate.
        """
        self._check_duplicate(node_id)
        self._nodes.append(
            WorkflowDefinitionNode(
                id=node_id,
                slug="__end__",
                name="END",
                inputs={},
                workflow_node_id=workflow_node_id,
            )
        )
        self._node_ids.add(node_id)
        return self

    def add_node(
        self,
        node_id: str,
        *,
        slug: str | None = None,
        name: str | None = None,
        inputs: dict[str, Any] | None = None,
        version: str | None = None,
        workflow_node_id: str | None = None,
        config_schema: dict[str, Any] | None = None,
    ) -> WorkflowBuilder:
        """Add a workflow node.

        Args:
            node_id: Unique ID for the node instance.
            slug: Node type slug from registry.
            name: Display name.
            inputs: Static input values.
            version: Pinned node version.
            workflow_node_id: Optional workflow node type ID.
            config_schema: Configuration schema.

        Returns:
            Self for chaining.

        Raises:
            ValueError: If ID is duplicate or reserved slug used.
        """
        if slug in ("__start__", "__end__"):
            raise ValueError(f"Cannot use reserved slug '{slug}'. Use add_start() or add_end() instead.")
        self._check_duplicate(node_id)
        self._nodes.append(
            WorkflowDefinitionNode(
                id=node_id,
                slug=slug,
                name=name,
                inputs=inputs or {},
                version=version,
                workflow_node_id=workflow_node_id,
                config_schema=config_schema,
            )
        )
        self._node_ids.add(node_id)
        return self

    def connect(
        self,
        from_node: str,
        to_node: str,
        *,
        from_output: str = "",
        to_input: str = "",
        edge_type: EdgeType = EdgeType.DEFAULT,
        condition: str | None = None,
    ) -> WorkflowBuilder:
        """Connects two nodes with an edge.

        Args:
            from_node: Source node ID
            to_node: Target node ID
            from_output: Output field name from source node (supports dot-notation)
            to_input: Input field name on target node
            edge_type: Edge type for conditional routing
            condition: Optional CEL expression for conditional edges

        Returns:
            Self for chaining

        Raises:
            ValueError: If source or target node not found, or if connecting a node to itself
        """
        if from_node not in self._node_ids:
            raise ValueError(f"Unknown source node: '{from_node}'")
        if to_node not in self._node_ids:
            raise ValueError(f"Unknown target node: '{to_node}'")
        if from_node == to_node:
            raise ValueError(f"Self-loop detected: cannot connect '{from_node}' to itself")

        self._edges.append(
            WorkflowEdgeDefinition(
                from_node=from_node,
                to_node=to_node,
                from_output=from_output,
                to_input=to_input,
                edge_type=edge_type,
                condition=condition,
            )
        )
        return self

    def build(self, *, validate: bool = True) -> WorkflowDefinitionSpec:
        """Build the workflow specification.

        Args:
            validate: Whether to run graph validation.

        Returns:
            WorkflowDefinitionSpec ready for execution.

        Raises:
            WorkflowValidationError: If validation fails.
        """
        from canvastekk_workflow_sdk.workflow.validation import validate as validate_graph

        spec = WorkflowDefinitionSpec(
            nodes=list(self._nodes),
            edges=list(self._edges),
        )

        if validate:
            result = validate_graph(spec)
            if not result.is_valid:
                from canvastekk_workflow_sdk.exceptions import WorkflowValidationError

                raise WorkflowValidationError(f"Workflow validation failed: {'; '.join(result.errors)}")

        return spec
