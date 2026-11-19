"""
Control Flow Handlers

Built-in START and END node handlers for local workflow execution.
These are plain callables, not WorkflowNodeBase subclasses — no schema validation,
no middleware, no HTTP wrapping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from canvastekk_workflow_sdk.node_execution_context import NodeExecutionContext


def start_handler(inputs: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
    """Identity passthrough: return all inputs as outputs.

    Matches engine's ``start_node.start_handler`` behavior.
    """
    return dict(inputs)


def end_handler(inputs: dict[str, Any], context: NodeExecutionContext) -> dict[str, Any]:
    """Identity passthrough: collect wired inputs as workflow result.

    Matches engine's ``end_node.end_handler`` behavior.
    """
    return dict(inputs)


CONTROL_FLOW_HANDLERS: dict[str, Any] = {
    "__start__": start_handler,
    "__end__": end_handler,
}
