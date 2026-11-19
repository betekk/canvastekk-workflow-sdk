import type { WorkflowDefinitionSpec } from "./workflow-definition.js";

/**
 * Result of workflow DAG validation.
 *
 * @property isValid - True if no validation errors were found
 * @property errors - List of validation error messages
 * @property orphans - Node IDs unreachable from __start__
 * @property deadEnds - Node IDs with no path to any __end__
 */
export interface WorkflowDefinitionValidationResult {
  isValid: boolean;
  errors: string[];
  orphans: string[];
  deadEnds: string[];
}

/**
 * Validates a workflow specification.
 * Checks for cycles, connectivity, orphan nodes, and dead ends.
 * @param spec - Workflow specification
 * @returns Validation result
 */
export function validateWorkflowDefinition(spec: WorkflowDefinitionSpec): WorkflowDefinitionValidationResult {
  const result: WorkflowDefinitionValidationResult = { isValid: true, errors: [], orphans: [], deadEnds: [] };
  const nodeIds = new Set(spec.nodes.map((n) => n.id));
  const nodeMap = new Map(spec.nodes.map((n) => [n.id, n]));

  checkNodeIds(spec.nodes, result);
  checkEdgeReferences(spec.edges, nodeIds, result);
  checkStartEnd(spec.nodes, spec.edges, nodeMap, result);

  if (!result.isValid) return result;

  checkCycles(spec.nodes, spec.edges, result);
  if (!result.isValid) return result;

  checkConnectivity(spec.nodes, spec.edges, result);
  return result;
}

/**
 * Validates that all nodes have unique, non-empty string IDs.
 * @param nodes - Workflow nodes to validate
 * @param result - Validation result to accumulate errors
 */
function checkNodeIds(nodes: WorkflowDefinitionSpec["nodes"], result: WorkflowDefinitionValidationResult): void {
  const seen = new Set<string>();
  for (const node of nodes) {
    if (!node.id || typeof node.id !== "string") {
      result.errors.push("All nodes must have a non-empty string 'id'");
      result.isValid = false;
      return;
    }
    if (seen.has(node.id)) {
      result.errors.push(`Duplicate node ID: '${node.id}'`);
      result.isValid = false;
      return;
    }
    seen.add(node.id);
  }
}

/**
 * Validates that all edges reference existing nodes and have unique IDs.
 * @param edges - Workflow edges to validate
 * @param nodeIds - Set of valid node IDs
 * @param result - Validation result to accumulate errors
 */
function checkEdgeReferences(edges: WorkflowDefinitionSpec["edges"], nodeIds: Set<string>, result: WorkflowDefinitionValidationResult): void {
  const edgeIds = new Set<string>();
  for (const edge of edges) {
    if (edge.id && edgeIds.has(edge.id)) {
      result.errors.push(`Duplicate edge ID: '${edge.id}'`);
      result.isValid = false;
      return;
    }
    edgeIds.add(edge.id);

    if (!nodeIds.has(edge.from_node)) {
      result.errors.push(`Edge references non-existent from_node: '${edge.from_node}'`);
      result.isValid = false;
    }
    if (!nodeIds.has(edge.to_node)) {
      result.errors.push(`Edge references non-existent to_node: '${edge.to_node}'`);
      result.isValid = false;
    }
  }
}

/**
 * Validates START/END constraints: exactly 1 start, >= 1 end, degree rules.
 *
 * Start nodes must have in_degree=0, end nodes must have out_degree=0.
 *
 * @param nodes - Workflow nodes
 * @param edges - Workflow edges
 * @param nodeMap - Node ID to node mapping
 * @param result - Validation result to accumulate errors
 */
function checkStartEnd(
  nodes: WorkflowDefinitionSpec["nodes"],
  edges: WorkflowDefinitionSpec["edges"],
  nodeMap: Map<string, WorkflowDefinitionSpec["nodes"][0]>,
  result: WorkflowDefinitionValidationResult,
): void {
  const startNodes = nodes.filter((n) => n.slug === "__start__");
  const endNodes = nodes.filter((n) => n.slug === "__end__");

  if (startNodes.length === 0) {
    result.errors.push("Workflow must have a __start__ node");
    result.isValid = false;
    return;
  }

  if (startNodes.length !== 1) {
    result.errors.push(`Workflow must have exactly 1 __start__ node, found ${startNodes.length}`);
    result.isValid = false;
    return;
  }

  if (endNodes.length === 0) {
    result.errors.push("Workflow must have at least 1 __end__ node");
    result.isValid = false;
    return;
  }

  const startId = startNodes[0].id;
  const endIds = new Set(endNodes.map((n) => n.id));

  const inDegree = new Map(nodes.map((n) => [n.id, 0]));
  const outDegree = new Map(nodes.map((n) => [n.id, 0]));

  for (const edge of edges) {
    if (inDegree.has(edge.to_node)) inDegree.set(edge.to_node, inDegree.get(edge.to_node)! + 1);
    if (outDegree.has(edge.from_node)) outDegree.set(edge.from_node, outDegree.get(edge.from_node)! + 1);
  }

  if (inDegree.get(startId) !== 0) {
    result.errors.push("__start__ node must have no incoming edges (in_degree must be 0)");
    result.isValid = false;
  }

  for (const eid of endIds) {
    if (outDegree.get(eid) !== 0) {
      result.errors.push(`__end__ node '${eid}' must have no outgoing edges (out_degree must be 0)`);
      result.isValid = false;
    }
  }
}

/**
 * Detects cycles using Kahn's algorithm (topological sort).
 *
 * If not all nodes are processed, the remaining nodes form a cycle.
 *
 * @param nodes - Workflow nodes
 * @param edges - Workflow edges
 * @param result - Validation result to accumulate errors
 */
function checkCycles(nodes: WorkflowDefinitionSpec["nodes"], edges: WorkflowDefinitionSpec["edges"], result: WorkflowDefinitionValidationResult): void {
  const nodeIds = new Set(nodes.map((n) => n.id));
  const adj = new Map<string, string[]>();
  const inDegree = new Map<string, number>();

  for (const nid of nodeIds) {
    adj.set(nid, []);
    inDegree.set(nid, 0);
  }

  for (const edge of edges) {
    adj.get(edge.from_node)!.push(edge.to_node);
    inDegree.set(edge.to_node, (inDegree.get(edge.to_node) ?? 0) + 1);
  }

  const queue = [...nodeIds].filter((nid) => inDegree.get(nid) === 0);
  let processed = 0;

  while (queue.length > 0) {
    const current = queue.shift()!;
    processed++;
    for (const neighbor of adj.get(current) ?? []) {
      const deg = inDegree.get(neighbor)! - 1;
      inDegree.set(neighbor, deg);
      if (deg === 0) queue.push(neighbor);
    }
  }

  if (processed < nodes.length) {
    const remaining = [...nodeIds].filter((nid) => (inDegree.get(nid) ?? 0) > 0);
    result.errors.push(`Workflow contains a cycle involving node(s): ${remaining.sort().join(", ")}`);
    result.isValid = false;
  }
}

/**
 * Checks graph connectivity using BFS from start and reverse BFS to end.
 *
 * Identifies orphan nodes (unreachable from start) and dead-end nodes
 * (no path to any end node).
 *
 * @param nodes - Workflow nodes
 * @param edges - Workflow edges
 * @param result - Validation result to accumulate errors
 */
function checkConnectivity(nodes: WorkflowDefinitionSpec["nodes"], edges: WorkflowDefinitionSpec["edges"], result: WorkflowDefinitionValidationResult): void {
  const startNodes = nodes.filter((n) => n.slug === "__start__");
  if (startNodes.length === 0) return;

  const startId = startNodes[0].id;
  const endIds = new Set(nodes.filter((n) => n.slug === "__end__").map((n) => n.id));

  const adj = new Map<string, string[]>();
  const revAdj = new Map<string, string[]>();
  for (const n of nodes) {
    adj.set(n.id, []);
    revAdj.set(n.id, []);
  }
  for (const edge of edges) {
    adj.get(edge.from_node)!.push(edge.to_node);
    revAdj.get(edge.to_node)!.push(edge.from_node);
  }

  const allIds = new Set(nodes.map((n) => n.id));

  const reachable = bfs(startId, adj);
  const orphans = [...allIds].filter((id) => !reachable.has(id)).sort();
  if (orphans.length > 0) {
    result.orphans = orphans;
    result.errors.push(`Orphan node(s) unreachable from __start__: ${orphans.join(", ")}`);
    result.isValid = false;
  }

  const canReachEnd = bfsMulti(endIds, revAdj);
  const deadEnds = [...allIds].filter((id) => !canReachEnd.has(id)).sort();
  if (deadEnds.length > 0) {
    result.deadEnds = deadEnds;
    result.errors.push(`Dead-end node(s) with no path to __end__: ${deadEnds.join(", ")}`);
    result.isValid = false;
  }
}

/**
 * Breadth-first search from a single start node.
 * @param start - Start node ID
 * @param adj - Adjacency list (node ID → neighbor IDs)
 * @returns Set of reachable node IDs
 */
function bfs(start: string, adj: Map<string, string[]>): Set<string> {
  const visited = new Set<string>();
  const queue = [start];
  visited.add(start);
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const neighbor of adj.get(current) ?? []) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        queue.push(neighbor);
      }
    }
  }
  return visited;
}

/**
 * Breadth-first search from multiple start nodes.
 * @param starts - Set of start node IDs
 * @param adj - Adjacency list (node ID → neighbor IDs)
 * @returns Set of reachable node IDs
 */
function bfsMulti(starts: Set<string>, adj: Map<string, string[]>): Set<string> {
  const visited = new Set<string>(starts);
  const queue = [...starts];
  while (queue.length > 0) {
    const current = queue.shift()!;
    for (const neighbor of adj.get(current) ?? []) {
      if (!visited.has(neighbor)) {
        visited.add(neighbor);
        queue.push(neighbor);
      }
    }
  }
  return visited;
}
