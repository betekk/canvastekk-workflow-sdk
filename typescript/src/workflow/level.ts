import type { WorkflowDefinitionSpec } from "./workflow-definition.js";

/**
 * Computes topological levels for workflow execution.
 * Groups nodes that can execute in parallel into levels.
 * @param spec - Workflow specification
 * @returns Array of node ID arrays, one per level
 * @throws Error if workflow contains a cycle
 */
export function computeLevels(spec: WorkflowDefinitionSpec): string[][] {
  const nodeIds = spec.nodes.map((n) => n.id);
  if (nodeIds.length === 0) return [];

  const adj: Map<string, string[]> = new Map();
  const inDegree: Map<string, number> = new Map();

  for (const nid of nodeIds) {
    adj.set(nid, []);
    inDegree.set(nid, 0);
  }

  for (const edge of spec.edges) {
    adj.get(edge.from_node)!.push(edge.to_node);
    inDegree.set(edge.to_node, (inDegree.get(edge.to_node) ?? 0) + 1);
  }

  const queue: string[] = nodeIds.filter((nid) => inDegree.get(nid) === 0).sort();
  const levels: string[][] = [];
  let processed = 0;

  while (queue.length > 0) {
    const levelSize = queue.length;
    const level: string[] = [];
    for (let i = 0; i < levelSize; i++) {
      const current = queue.shift()!;
      level.push(current);
      processed++;
      const neighbors = (adj.get(current) ?? []).sort();
      for (const neighbor of neighbors) {
        const deg = inDegree.get(neighbor)! - 1;
        inDegree.set(neighbor, deg);
        if (deg === 0) {
          queue.push(neighbor);
        }
      }
    }
    levels.push(level);
  }

  if (processed !== nodeIds.length) {
    const remaining = nodeIds.filter((nid) => (inDegree.get(nid) ?? 0) > 0);
    throw new Error(`Workflow contains a cycle involving node(s): ${remaining.sort().join(", ")}`);
  }

  return levels;
}
