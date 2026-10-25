"""
Level Computation

BFS topological sort that groups nodes into execution levels.
Nodes within the same level have no dependencies on each other
and can execute in parallel.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from canvastekk_workflow_sdk.workflow.models import WorkflowDefinitionSpec


def compute_levels(spec: WorkflowDefinitionSpec) -> list[list[str]]:
    """Compute execution levels via BFS topological sort (Kahn's algorithm).

    Args:
        spec: The workflow spec.

    Returns:
        List of levels, where each level is a list of node IDs that
        can execute in parallel.

    Raises:
        ValueError: If the graph contains a cycle.
    """
    node_ids = [n.id for n in spec.nodes]
    if not node_ids:
        return []

    adj: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = {nid: 0 for nid in node_ids}

    for edge in spec.edges:
        adj[edge.from_node].append(edge.to_node)
        in_degree[edge.to_node] += 1

    queue = deque(sorted(nid for nid in node_ids if in_degree[nid] == 0))
    levels: list[list[str]] = []
    processed = 0

    while queue:
        level_size = len(queue)
        level: list[str] = []
        for _ in range(level_size):
            current = queue.popleft()
            level.append(current)
            processed += 1
            for neighbor in sorted(adj[current]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        levels.append(level)

    if processed != len(node_ids):
        remaining = [nid for nid in node_ids if in_degree[nid] > 0]
        raise ValueError(f"Workflow contains a cycle involving node(s): {', '.join(sorted(remaining))}")

    return levels
