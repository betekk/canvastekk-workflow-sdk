import type { WorkflowDefinitionSpec } from "./models.js";

/**
 * Error thrown when workflow input/output resolution fails.
 *
 * Includes an error code and optional node ID for debugging.
 */
export class ResolverError extends Error {
  /** Error code categorizing the failure type. */
  readonly code: "NODE_NOT_FOUND" | "KEY_NOT_FOUND" | "INVALID_PATH" | "TRAVERSAL_ERROR" | "FORBIDDEN_KEY";
  /** Optional node ID where the error occurred (for debugging). */
  readonly nodeId?: string;

  /**
   * Creates a new ResolverError.
   *
   * @param message - Human-readable error message
   * @param code - Error type code
   * @param nodeId - Optional node ID where the error occurred
   */
  constructor(
    message: string,
    code: "NODE_NOT_FOUND" | "KEY_NOT_FOUND" | "INVALID_PATH" | "TRAVERSAL_ERROR" | "FORBIDDEN_KEY",
    nodeId?: string,
  ) {
    super(message);
    this.name = "ResolverError";
    this.code = code;
    this.nodeId = nodeId;
  }
}

/**
 * Type guard to check if a value is a plain object (Record).
 *
 * @param value - Value to check
 * @returns True if the value is a non-null object and not an array
 */
function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * Resolves a node's inputs from static params + incoming edge outputs.
 *
 * @param nodeId - Target node ID
 * @param spec - Workflow definition spec
 * @param nodeOutputs - Map of node ID → outputs from prior executions
 * @returns Resolved inputs for the target node
 * @throws {ResolverError} When node not found or output key resolution fails
 */
/** Keys that must never be assigned/merged onto resolved-input objects —
 * assignment via these would poison the object's prototype chain. */
const DANGEROUS_KEYS = new Set(["__proto__", "constructor", "prototype"]);

/** Defines a plain own data property (never touches the prototype chain). */
function defineOwn(target: Record<string, unknown>, key: string, value: unknown): void {
  Object.defineProperty(target, key, {
    value,
    writable: true,
    enumerable: true,
    configurable: true,
  });
}

export function resolveInputs(
  nodeId: string,
  spec: WorkflowDefinitionSpec,
  nodeOutputs: Record<string, Record<string, unknown>>,
): Record<string, unknown> {
  const node = spec.nodes.find((n) => n.id === nodeId);
  if (!node) throw new ResolverError(`Node not found: ${nodeId}`, "NODE_NOT_FOUND", nodeId);

  const resolved: Record<string, unknown> = { ...node.inputs };

  const incoming = spec.edges.filter((e) => e.to_node === nodeId);
  for (const edge of incoming) {
    const sourceOutputs = nodeOutputs[edge.from_node] ?? {};
    const value = resolveOutput(sourceOutputs, edge.from_output, edge.from_node);
    if (edge.to_input) {
      if (DANGEROUS_KEYS.has(edge.to_input)) {
        throw new ResolverError(
          `Forbidden to_input key '${edge.to_input}' (prototype pollution)`,
          "FORBIDDEN_KEY",
          edge.from_node,
        );
      }
      defineOwn(resolved, edge.to_input, value);
    } else if (typeof value === "object" && value !== null && !Array.isArray(value)) {
      for (const [k, v] of Object.entries(value)) {
        if (!DANGEROUS_KEYS.has(k)) defineOwn(resolved, k, v);
      }
    }
  }

  return resolved;
}

/**
 * Resolves a single output value from source node outputs.
 *
 * Supports dot-notation traversal for nested objects.
 *
 * @param sourceOutputs - Source node's output object
 * @param fromOutput - Output key path (empty string returns all outputs)
 * @param fromNode - Optional source node ID for error messages
 * @returns Resolved output value
 * @throws {ResolverError} When output key not found or path is invalid
 */
function resolveOutput(
  sourceOutputs: Record<string, unknown>,
  fromOutput: string,
  fromNode?: string,
): unknown {
  if (!fromOutput) return sourceOutputs;

  if (Object.hasOwn(sourceOutputs, fromOutput)) return sourceOutputs[fromOutput];

  if (fromOutput.includes(".")) return walkDotPath(sourceOutputs, fromOutput, fromNode);

  const nodeCtx = fromNode ? ` from node '${fromNode}'` : "";
  throw new ResolverError(
    `Cannot resolve from_output '${fromOutput}'${nodeCtx}; available keys: ${sortedKeys(sourceOutputs)}`,
    "KEY_NOT_FOUND",
    fromNode,
  );
}

/**
 * Walks a dot-notation path through a nested object.
 *
 * @param data - Object to traverse
 * @param path - Dot-separated path (e.g., "output.nested.value")
 * @param fromNode - Optional source node ID for error messages
 * @returns Value at the path endpoint
 * @throws {ResolverError} When path is invalid, hits a non-object, or key not found
 */
function walkDotPath(data: Record<string, unknown>, path: string, fromNode?: string): unknown {
  let current: unknown = data;
  for (const segment of path.split(".")) {
    if (!segment) throw new ResolverError(`Invalid dot-path '${path}' (empty segment)`, "INVALID_PATH", fromNode);
    if (!isRecord(current)) {
      throw new ResolverError(
        `Cannot walk dot-path '${path}': segment '${segment}' hits non-dict`,
        "TRAVERSAL_ERROR",
        fromNode,
      );
    }
    if (!Object.hasOwn(current, segment)) {
      const nodeCtx = fromNode ? ` from node '${fromNode}'` : "";
      throw new ResolverError(
        `Dot-path '${path}': segment '${segment}' not found${nodeCtx}`,
        "KEY_NOT_FOUND",
        fromNode,
      );
    }
    current = current[segment];
  }
  return current;
}

/**
 * Returns a sorted list of an object's keys as a string for error messages.
 *
 * @param obj - Object to extract keys from
 * @returns Sorted keys as a bracketed string
 */
function sortedKeys(obj: Record<string, unknown>): string {
  return `[${Object.keys(obj).sort().join(", ")}]`;
}
