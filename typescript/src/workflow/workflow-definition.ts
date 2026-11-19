/**
 * Edge type for workflow connections.
 *
 * - `"default"` — Standard data flow edge
 * - `"success"` — Traversed only on upstream success
 * - `"failure"` — Traversed only on upstream failure
 * - `"conditional"` — Traversed based on a condition expression
 */
export type EdgeType = "default" | "success" | "failure" | "conditional";

/**
 * Edge connecting two workflow nodes.
 *
 * Uses engine-compatible field names (from_node, to_node) matching the
 * Python SDK and CanvasTEKK Workflow Engine's SaveWorkflowRequest.spec schema.
 *
 * All fields are readonly.
 *
 * @property id - Unique edge identifier
 * @property from_node - Source node ID (non-empty)
 * @property to_node - Target node ID (non-empty)
 * @property from_output - Output field name on the source node
 * @property to_input - Input field name on the target node
 * @property edge_type - Edge type for conditional routing
 * @property condition - Optional condition expression for conditional edges
 */
export interface WorkflowEdgeDefinition {
  readonly id: string;
  readonly from_node: string;
  readonly to_node: string;
  readonly from_output: string;
  readonly to_input: string;
  readonly edge_type: EdgeType;
  readonly condition?: string | null;
}

/**
 * Node instance within a workflow definition.
 *
 * All fields are readonly.
 *
 * @property id - Unique node identifier within the workflow (non-empty)
 * @property workflow_node_id - Optional reference to a registered node
 * @property slug - Node type slug (e.g., "segmentation-v1.0.0")
 * @property version - Optional version override
 * @property name - Human-readable display name
 * @property x - Optional X position for visual layout
 * @property y - Optional Y position for visual layout
 * @property inputs - Static input values for this node instance
 * @property config_schema - Optional node configuration schema
 */
export interface WorkflowDefinitionNode {
  readonly id: string;
  readonly workflow_node_id?: string | null;
  readonly slug?: string | null;
  readonly version?: string | null;
  readonly name?: string | null;
  readonly x?: number | null;
  readonly y?: number | null;
  readonly inputs: Record<string, unknown>;
  readonly config_schema?: Record<string, unknown> | null;
}

/**
 * Complete workflow specification (DAG of nodes and edges).
 *
 * All fields are readonly.
 *
 * @property nodes - Ordered list of workflow nodes
 * @property edges - List of connections between nodes
 * @property metadata - Arbitrary metadata for the workflow
 */
export interface WorkflowDefinitionSpec {
  readonly nodes: WorkflowDefinitionNode[];
  readonly edges: WorkflowEdgeDefinition[];
  readonly metadata: Record<string, unknown>;
}
