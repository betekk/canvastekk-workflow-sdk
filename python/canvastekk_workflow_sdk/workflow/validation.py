"""
Graph Validation

Validates workflow DAGs for structural correctness: unique IDs, edge references,
START/END constraints, cycle detection, and graph connectivity (orphan/dead-end).
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from canvastekk_workflow_sdk.workflow.models import (
        WorkflowDefinitionNode,
        WorkflowDefinitionSpec,
        WorkflowEdgeDefinition,
    )


@dataclass
class ValidationResult:
    """Result of workflow graph validation."""

    is_valid: bool = True
    errors: list[str] = field(default_factory=list)
    orphans: list[str] = field(default_factory=list)
    dead_ends: list[str] = field(default_factory=list)


def validate(spec: WorkflowDefinitionSpec) -> ValidationResult:
    """Validate a workflow spec for structural correctness.

    Checks:
    1. Node ID uniqueness
    2. Edge reference validity
    3. START/END constraints (exactly 1 start, >= 1 end, degree rules)
    4. Cycle detection (Kahn's algorithm)
    5. Forward BFS connectivity (orphans)
    6. Reverse BFS connectivity (dead-ends)

    Args:
        spec: The workflow spec to validate.

    Returns:
        ValidationResult with is_valid=True if no errors found.

    Raises:
        WorkflowValidationError: If validation fails and caller doesn't check result.
    """
    result = ValidationResult()
    nodes = spec.nodes
    edges = spec.edges
    node_ids = {n.id for n in nodes}
    node_map = {n.id: n for n in nodes}

    _check_node_ids(nodes, result)
    _check_edge_references(edges, node_ids, result)
    _check_start_end(nodes, edges, node_map, result)

    if not result.is_valid:
        return result

    _check_cycles(nodes, edges, result)

    if not result.is_valid:
        return result

    _check_connectivity(nodes, edges, node_map, result)

    return result


def _check_node_ids(nodes: list[WorkflowDefinitionNode], result: ValidationResult) -> None:
    """Validate that all nodes have unique, non-empty string IDs.

    Args:
        nodes: List of workflow nodes.
        result: ValidationResult to accumulate errors.
    """
    seen: set[str] = set()
    for node in nodes:
        if not node.id or not isinstance(node.id, str):
            result.errors.append("All nodes must have a non-empty string 'id'")
            result.is_valid = False
            return
        if node.id in seen:
            result.errors.append(f"Duplicate node ID: '{node.id}'")
            result.is_valid = False
            return
        seen.add(node.id)


def _check_edge_references(
    edges: list[WorkflowEdgeDefinition],
    node_ids: set[str],
    result: ValidationResult,
) -> None:
    """Validate that all edges reference existing nodes and have unique IDs.

    Args:
        edges: List of workflow edges.
        node_ids: Set of valid node IDs.
        result: ValidationResult to accumulate errors.
    """
    edge_ids: set[str] = set()
    for edge in edges:
        if edge.id and edge.id in edge_ids:
            result.errors.append(f"Duplicate edge ID: '{edge.id}'")
            result.is_valid = False
            return
        edge_ids.add(edge.id)

        if edge.from_node not in node_ids:
            result.errors.append(f"Edge references non-existent from_node: '{edge.from_node}'")
            result.is_valid = False
        if edge.to_node not in node_ids:
            result.errors.append(f"Edge references non-existent to_node: '{edge.to_node}'")
            result.is_valid = False


def _check_start_end(
    nodes: list[WorkflowDefinitionNode],
    edges: list[WorkflowEdgeDefinition],
    node_map: dict[str, WorkflowDefinitionNode],
    result: ValidationResult,
) -> None:
    """Validate START/END constraints.

    Requires exactly 1 __start__ node and >= 1 __end__ node.
    Start nodes must have in_degree=0, end nodes must have out_degree=0.

    Args:
        nodes: List of workflow nodes.
        edges: List of workflow edges.
        node_map: Mapping of node ID to node.
        result: ValidationResult to accumulate errors.
    """
    start_nodes = [n for n in nodes if n.slug == "__start__"]
    end_nodes = [n for n in nodes if n.slug == "__end__"]

    if not start_nodes:
        result.errors.append("Workflow must have a __start__ node")
        result.is_valid = False
        return

    if len(start_nodes) != 1:
        result.errors.append(f"Workflow must have exactly 1 __start__ node, found {len(start_nodes)}")
        result.is_valid = False
        return

    if not end_nodes:
        result.errors.append("Workflow must have at least 1 __end__ node")
        result.is_valid = False
        return

    start_id = start_nodes[0].id
    end_ids = {n.id for n in end_nodes}

    in_degree: dict[str, int] = {n.id: 0 for n in nodes}
    out_degree: dict[str, int] = {n.id: 0 for n in nodes}

    for edge in edges:
        if edge.to_node in in_degree:
            in_degree[edge.to_node] += 1
        if edge.from_node in out_degree:
            out_degree[edge.from_node] += 1

    if in_degree.get(start_id, 0) != 0:
        result.errors.append("__start__ node must have no incoming edges (in_degree must be 0)")
        result.is_valid = False

    for eid in end_ids:
        if out_degree.get(eid, 0) != 0:
            result.errors.append(f"__end__ node '{eid}' must have no outgoing edges (out_degree must be 0)")
            result.is_valid = False


def _check_cycles(
    nodes: list[WorkflowDefinitionNode],
    edges: list[WorkflowEdgeDefinition],
    result: ValidationResult,
) -> None:
    """Detect cycles using Kahn's algorithm (topological sort).

    If not all nodes are processed, the remaining nodes form a cycle.

    Args:
        nodes: List of workflow nodes.
        edges: List of workflow edges.
        result: ValidationResult to accumulate errors.
    """
    node_ids = {n.id for n in nodes}
    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

    for edge in edges:
        adj[edge.from_node].append(edge.to_node)
        in_degree[edge.to_node] += 1

    queue = deque(nid for nid, deg in in_degree.items() if deg == 0)
    processed = 0

    while queue:
        current = queue.popleft()
        processed += 1
        for neighbor in adj[current]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    if processed < len(nodes):
        remaining = [nid for nid, deg in in_degree.items() if deg > 0]
        result.errors.append(f"Workflow contains a cycle involving node(s): {', '.join(sorted(remaining))}")
        result.is_valid = False


def _check_connectivity(
    nodes: list[WorkflowDefinitionNode],
    edges: list[WorkflowEdgeDefinition],
    node_map: dict[str, WorkflowDefinitionNode],
    result: ValidationResult,
) -> None:
    """Check graph connectivity using BFS.

    Identifies orphan nodes (unreachable from __start__) and dead-end
    nodes (no path to any __end__ node).

    Args:
        nodes: List of workflow nodes.
        edges: List of workflow edges.
        node_map: Mapping of node ID to node.
        result: ValidationResult to accumulate errors.
    """
    start_nodes = [n for n in nodes if n.slug == "__start__"]
    if not start_nodes:
        return

    start_id = start_nodes[0].id
    end_ids = {n.id for n in nodes if n.slug == "__end__"}

    adj: dict[str, list[str]] = defaultdict(list)
    rev_adj: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adj[edge.from_node].append(edge.to_node)
        rev_adj[edge.to_node].append(edge.from_node)

    all_ids = {n.id for n in nodes}

    reachable = _bfs(start_id, adj)
    orphans = sorted(all_ids - reachable)
    if orphans:
        result.orphans = orphans
        result.errors.append(f"Orphan node(s) unreachable from __start__: {', '.join(orphans)}")
        result.is_valid = False

    can_reach_end = _bfs_multi(end_ids, rev_adj)
    dead_ends = sorted(all_ids - can_reach_end)
    if dead_ends:
        result.dead_ends = dead_ends
        result.errors.append(f"Dead-end node(s) with no path to __end__: {', '.join(dead_ends)}")
        result.is_valid = False


def _bfs(start: str, adj: dict[str, list[str]]) -> set[str]:
    """Breadth-first search from a single start node.

    Args:
        start: Start node ID.
        adj: Adjacency list mapping node ID to neighbor IDs.

    Returns:
        Set of reachable node IDs.
    """
    visited: set[str] = set()
    queue = deque([start])
    visited.add(start)
    while queue:
        current = queue.popleft()
        for neighbor in adj[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return visited


def _bfs_multi(starts: set[str], adj: dict[str, list[str]]) -> set[str]:
    """Breadth-first search from multiple start nodes.

    Args:
        starts: Set of start node IDs.
        adj: Adjacency list mapping node ID to neighbor IDs.

    Returns:
        Set of reachable node IDs.
    """
    visited: set[str] = set()
    queue = deque(starts)
    visited.update(starts)
    while queue:
        current = queue.popleft()
        for neighbor in adj[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return visited
