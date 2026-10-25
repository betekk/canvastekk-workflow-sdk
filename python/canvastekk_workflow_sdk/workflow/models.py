"""
Workflow Models

Engine-compatible Pydantic models matching the CanvasTEKK Workflow Engine's
``SaveWorkflowRequest.spec`` schema. ``WorkflowDefinitionSpec.model_dump(mode="json")``
produces JSON directly POSTable to ``/api/workflows/definitions``.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class EdgeType(StrEnum):
    """When an edge fires relative to source node execution outcome.

    Matches engine's ``EdgeType`` for routing semantics.
    """

    DEFAULT = "default"
    SUCCESS = "success"
    FAILURE = "failure"
    CONDITIONAL = "conditional"


class WorkflowEdgeDefinition(BaseModel):
    """
    An edge connecting two nodes in a workflow graph.

    Uses engine-compatible field names (``from_node``, ``to_node``).

    Constraints:
        from_node: Must be non-empty (min_length=1)
        to_node: Must be non-empty (min_length=1)
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    from_node: str = Field(min_length=1, description="Source node instance ID")
    to_node: str = Field(min_length=1, description="Target node instance ID")
    from_output: str = Field(default="", description="Output field from source (supports dot-notation)")
    to_input: str = Field(default="", description="Input field name on target node")
    edge_type: EdgeType = Field(default=EdgeType.DEFAULT, description="Routing type")
    condition: str | None = Field(default=None, description="CEL expression for conditional edges")


class WorkflowDefinitionNode(BaseModel):
    """
    A node instance placed into a workflow definition.

    Uses engine-compatible field names. Outputs are NOT stored here —
    they flow through edges at runtime.

    Constraints:
        id: Must be non-empty (min_length=1)
    """

    id: str = Field(min_length=1, description="Unique node instance ID within the workflow")
    workflow_node_id: str | None = Field(default=None, description="Registry node type ID reference")
    slug: str | None = Field(
        default=None, description="Node type slug from registry (e.g. '__start__', 'segmentation-v1.0.0')"
    )
    version: str | None = Field(default=None, description="Pinned node version")
    name: str | None = Field(default=None, description="Display label")
    x: float | None = Field(default=None, description="Canvas X coordinate")
    y: float | None = Field(default=None, description="Canvas Y coordinate")
    inputs: dict[str, Any] = Field(default_factory=dict, description="Static input values")
    config_schema: dict[str, Any] | None = Field(default=None, description="Node configuration schema")


class WorkflowDefinitionSpec(BaseModel):
    """Complete workflow specification as a directed acyclic graph.

    ``model_dump(mode="json")`` produces JSON compatible with the engine's
    ``SaveWorkflowRequest.spec`` schema.
    """

    nodes: list[WorkflowDefinitionNode] = Field(description="All nodes in the workflow")
    edges: list[WorkflowEdgeDefinition] = Field(description="All edges connecting nodes")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Workflow metadata (e.g. {'version': '1.0.0'})",
    )
