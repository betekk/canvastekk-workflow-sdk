"""
Input Resolver

Resolves a node's inputs from static params + incoming edge outputs.
Supports dot-notation traversal for nested output extraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from canvastekk_workflow_sdk.workflow.models import WorkflowDefinitionSpec


def resolve_inputs(
    node_id: str,
    spec: WorkflowDefinitionSpec,
    node_outputs: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Resolves a node's inputs from static params + incoming edge outputs.

    Merges static inputs with values from connected upstream nodes.
    Supports dot-notation traversal for nested output extraction.

    Args:
        node_id: Target node ID
        spec: Workflow definition spec
        node_outputs: Map of node ID -> outputs from prior executions

    Returns:
        Dict of resolved input values for the target node

    Raises:
        KeyError: If node not found in spec or output key resolution fails
    """
    try:
        node = next(n for n in spec.nodes if n.id == node_id)
    except StopIteration:
        raise KeyError(f"Node '{node_id}' not found in spec") from None
    resolved: dict[str, Any] = dict(node.inputs)

    incoming = [e for e in spec.edges if e.to_node == node_id]
    for edge in incoming:
        source_outputs = node_outputs.get(edge.from_node, {})
        value = _resolve_output(source_outputs, edge.from_output, edge.from_node)
        if edge.to_input:
            resolved[edge.to_input] = value
        elif isinstance(value, dict):
            resolved.update(value)

    return resolved


def _resolve_output(
    source_outputs: dict[str, Any],
    from_output: str,
    from_node: str = "",
) -> Any:
    """Resolves a single output value from source node outputs.

    Supports dot-notation traversal for nested objects.

    Args:
        source_outputs: Source node's output object
        from_output: Output key path (empty string returns all outputs)
        from_node: Optional source node ID for error messages

    Returns:
        Resolved output value

    Raises:
        KeyError: If output key not found or path is invalid
    """
    if not from_output:
        return source_outputs

    if from_output in source_outputs:
        return source_outputs[from_output]
    if "." in from_output:
        return _walk_dot_path(source_outputs, from_output, from_node)
    node_ctx = f" from node '{from_node}'" if from_node else ""
    raise KeyError(
        f"Cannot resolve from_output '{from_output}'{node_ctx}; available keys: {sorted(source_outputs.keys())}"
    )


def _walk_dot_path(data: dict[str, Any], path: str, from_node: str = "") -> Any:
    """Walks a dot-notation path through a nested object.

    Args:
        data: Object to traverse
        path: Dot-separated path (e.g., "output.nested.value")
        from_node: Optional source node ID for error messages

    Returns:
        Value at the path endpoint

    Raises:
        KeyError: If path is invalid, hits a non-object, or key not found
    """
    current: Any = data
    for segment in path.split("."):
        if not segment:
            raise KeyError(f"Invalid dot-path '{path}' (empty segment)")
        if not isinstance(current, dict):
            raise KeyError(f"Cannot walk dot-path '{path}': segment '{segment}' hits non-dict")
        if segment not in current:
            node_ctx = f" from node '{from_node}'" if from_node else ""
            raise KeyError(f"Dot-path '{path}': segment '{segment}' not found{node_ctx}")
        current = current[segment]
    return current
