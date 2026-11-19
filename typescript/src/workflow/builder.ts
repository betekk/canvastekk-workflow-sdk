import type { EdgeType, WorkflowEdgeDefinition, WorkflowDefinitionNode, WorkflowDefinitionSpec } from "./workflow-definition.js";
import { validateWorkflowDefinition } from "./validation.js";

/**
 * Builder for creating workflow specifications.
 */
export class WorkflowBuilder {
  private _nodes: WorkflowDefinitionNode[] = [];
  private _edges: WorkflowEdgeDefinition[] = [];
  private _nodeIds: Set<string> = new Set();
  private _hasStart = false;

  /**
   * Creates a new workflow builder.
   */
  constructor() {}

  /**
   * Checks if a node ID is already used.
   * @param nodeId - Node ID to check
   * @throws {Error} If node ID is duplicate
   */
  private checkDuplicate(nodeId: string): void {
    if (this._nodeIds.has(nodeId)) {
      throw new Error(`Duplicate node ID: '${nodeId}'`);
    }
  }

  /**
   * Adds a START node to the workflow.
   * @param nodeId - Node ID (default: "start")
   * @param opts - Start node options
   * @returns This builder instance for chaining
   * @throws {Error} If START node already exists
   */
  addStart(
    nodeId = "start",
    opts?: {
      outputs?: string[] | Record<string, unknown>;
      workflowNodeId?: string;
      configSchema?: Record<string, unknown>;
    },
  ): this {
    if (this._hasStart) {
      throw new Error("Workflow already has a START node. Only one is allowed.");
    }
    this.checkDuplicate(nodeId);

    let configSchema = opts?.configSchema;
    if (configSchema === undefined && opts?.outputs) {
      const outputs = opts.outputs;
      const props = Array.isArray(outputs)
        ? Object.fromEntries(outputs.map((n) => [n, { type: "string" }]))
        : outputs;
      configSchema = { type: "object", properties: props };
    }

    this._nodes.push({
      id: nodeId,
      slug: "__start__",
      name: "START",
      inputs: {},
      workflow_node_id: opts?.workflowNodeId ?? null,
      config_schema: configSchema ?? null,
    });
    this._nodeIds.add(nodeId);
    this._hasStart = true;
    return this;
  }

  /**
   * Adds an END node to the workflow.
   * @param nodeId - Node ID (default: "end")
   * @param opts - End node options
   * @returns This builder instance for chaining
   */
  addEnd(nodeId = "end", opts?: { workflowNodeId?: string }): this {
    this.checkDuplicate(nodeId);
    this._nodes.push({
      id: nodeId,
      slug: "__end__",
      name: "END",
      inputs: {},
      workflow_node_id: opts?.workflowNodeId ?? null,
    });
    this._nodeIds.add(nodeId);
    return this;
  }

  /**
   * Adds a workflow node.
   * @param nodeId - Unique node ID
   * @param opts - Node configuration options
   * @returns This builder instance for chaining
   * @throws {Error} If node ID is duplicate or slug is reserved
   */
  addNode(
    nodeId: string,
    opts: {
      slug?: string;
      name?: string;
      inputs?: Record<string, unknown>;
      version?: string;
      workflowNodeId?: string;
      configSchema?: Record<string, unknown>;
    },
  ): this {
    if (opts.slug === "__start__" || opts.slug === "__end__") {
      throw new Error(
        `Cannot use reserved slug '${opts.slug}'. Use addStart() or addEnd() instead.`,
      );
    }
    this.checkDuplicate(nodeId);
    this._nodes.push({
      id: nodeId,
      slug: opts.slug ?? null,
      name: opts.name ?? null,
      inputs: opts.inputs ?? {},
      version: opts.version ?? null,
      workflow_node_id: opts?.workflowNodeId ?? null,
      config_schema: opts?.configSchema ?? null,
    });
    this._nodeIds.add(nodeId);
    return this;
  }

  /**
   * Connects two nodes with an edge.
   *
   * @param fromNode - Source node ID
   * @param toNode - Target node ID
   * @param opts - Connection options
   * @returns This builder instance for chaining
   * @throws {Error} If source or target node not found, or if connecting a node to itself
   */
  connect(
    fromNode: string,
    toNode: string,
    opts?: {
      fromOutput?: string;
      toInput?: string;
      edgeType?: EdgeType;
      condition?: string;
    },
  ): this {
    if (!this._nodeIds.has(fromNode)) {
      throw new Error(`Unknown source node: '${fromNode}'`);
    }
    if (!this._nodeIds.has(toNode)) {
      throw new Error(`Unknown target node: '${toNode}'`);
    }
    if (fromNode === toNode) {
      throw new Error(`Self-loop detected: cannot connect '${fromNode}' to itself`);
    }
    this._edges.push({
      id: crypto.randomUUID(),
      from_node: fromNode,
      to_node: toNode,
      from_output: opts?.fromOutput ?? "",
      to_input: opts?.toInput ?? "",
      edge_type: opts?.edgeType ?? "default",
      condition: opts?.condition ?? null,
    });
    return this;
  }

  /**
   * Builds the workflow specification.
   * @param opts - Build options
   * @returns Workflow specification
   * @throws {Error} If validation fails
   */
  build(opts?: { validate?: boolean }): WorkflowDefinitionSpec {
    const spec: WorkflowDefinitionSpec = {
      nodes: [...this._nodes],
      edges: [...this._edges],
      metadata: {},
    };

    if (opts?.validate !== false) {
      const result = validateWorkflowDefinition(spec);
      if (!result.isValid) {
        throw new Error(`Workflow validation failed: ${result.errors.join("; ")}`);
      }
    }

    return spec;
  }
}
