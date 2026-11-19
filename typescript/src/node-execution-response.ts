import { z } from "zod";
import { NodeInputValidationError } from "./exceptions.js";
import { NODE_CALL_PROTOCOL_2_OUTCOMES } from "./node-call-protocol.js";

/**
 * S.5 (SDK#161): the node-execution status vocabulary (lowercase wire).
 *
 * Extends the response's `pass`/`fail` with the engine-synthesized `skipped`
 * (D.6 skip-on-upstream-failure) and `timeout` — nodes keep answering
 * `pass`/`fail`; the engine synthesizes the other two.
 */
export const WorkflowNodeCallOutcomeSchema = z.enum([
  "pass",
  "fail",
  "skipped",
  "timeout",
]);

export type WorkflowNodeCallOutcome = z.infer<typeof WorkflowNodeCallOutcomeSchema>;

/**
 * Parse a node-execution status strictly (S.5, SDK#161).
 *
 * STRICT BY DEFAULT and ARMED: missing, non-string, or unknown values raise
 * a validation-class error — never a silent default. The ENGINE's flip from
 * lenient to strict happens when it bumps its SDK pin to this release
 * (CWE#852, gated on the F.4 floor confirmation).
 *
 * @param value - Wire value (pass | fail | skipped | timeout)
 * @returns The matching status literal
 * @throws {NodeInputValidationError} On missing/unknown values (validation category)
 */
export function parseWorkflowNodeCallOutcome(value: unknown): WorkflowNodeCallOutcome {
  // Node protocol 2 (engine#1300): the exact words SUCCEEDED / FAILED read as
  // pass / fail. Still strict: no case folding, ACCEPTED is not a result.
  const legacy = typeof value === "string" ? NODE_CALL_PROTOCOL_2_OUTCOMES[value] : undefined;
  const parsed = WorkflowNodeCallOutcomeSchema.safeParse(
    legacy === "pass" || legacy === "fail" ? legacy : value,
  );
  if (!parsed.success) {
    throw new NodeInputValidationError(
      `Unknown node execution status ${JSON.stringify(value)}; expected one of ["pass","fail","skipped","timeout"]`,
      { details: { received: JSON.stringify(value) } },
    );
  }
  return parsed.data;
}

export const NodeExecutionResponseSchema = z.object({
  execution_id: z.string(),
  // Node code produces pass / fail; /execute answers SUCCEEDED / FAILED when
  // the engine asks for node protocol 2 (X-Node-Protocol, engine#1300).
  status: z.union([z.literal("pass"), z.literal("fail"), z.literal("SUCCEEDED"), z.literal("FAILED")]),
  outputs: z.record(z.string(), z.unknown()).nullable().default(null),
  token_usage: z.number().min(0.0).default(0.0),
  duration_ms: z.number().int().min(0).default(0),
  error: z.string().nullable().default(null),
  error_type: z.string().nullable().default(null),
  error_code: z.string().nullable().default(null),
  dry_run: z.boolean().default(false),
});

/**
 * Node execution response returned to the workflow engine.
 *
 * Fields use snake_case for wire-format compatibility with the Python engine.
 *
 * @property execution_id - Unique identifier for this execution
 * @property status - Execution result: `"pass"` or `"fail"` (`"SUCCEEDED"` / `"FAILED"` on the wire under node protocol 2)
 * @property outputs - Output values on success, `null` on failure
 * @property duration_ms - Execution duration in milliseconds
 * @property token_usage - Token consumption (0.0 if not applicable)
 * @property error - Error message on failure, `null` on success
 * @property error_type - Error class name (e.g., `"NodeValidationError"`)
 * @property error_code - Machine-readable error code (e.g., `"VALIDATION_ERROR"`)
 */
export type NodeExecutionResponse = z.infer<typeof NodeExecutionResponseSchema>;

/**
 * Creates a success response from node execution.
 *
 * @param executionId - Unique execution identifier
 * @param outputs - Node output values
 * @param durationMs - Execution duration in milliseconds
 * @param tokenUsage - Token consumption count
 * @returns NodeExecutionResponse with status "pass"
 */
function createSuccessResponse(
  executionId: string,
  outputs: Record<string, unknown>,
  durationMs = 0,
  tokenUsage = 0.0,
  dryRun = false,
): NodeExecutionResponse {
  return {
    execution_id: executionId,
    status: "pass",
    outputs,
    duration_ms: durationMs,
    token_usage: tokenUsage,
    error: null,
    error_type: null,
    error_code: null,
    dry_run: dryRun,
  };
}

/**
 * Creates a failure response from node execution.
 *
 * @param executionId - Unique execution identifier
 * @param error - Human-readable error message
 * @param errorType - Error class name
 * @param durationMs - Execution duration in milliseconds
 * @param errorCode - Machine-readable error code
 * @returns NodeExecutionResponse with status "fail"
 */
function createFailureResponse(
  executionId: string,
  error: string,
  errorType: string | null = null,
  durationMs = 0,
  errorCode: string | null = null,
  dryRun = false,
): NodeExecutionResponse {
  return {
    execution_id: executionId,
    status: "fail",
    outputs: null,
    error,
    error_type: errorType,
    duration_ms: durationMs,
    error_code: errorCode,
    dry_run: dryRun,
    token_usage: 0.0,
  };
}

export const NodeExecutionResponseFactory = {
  success: createSuccessResponse,
  failure: createFailureResponse,
};

export const WorkflowNodeHealthResponseSchema = z.object({
  status: z.union([
    z.literal("healthy"),
    z.literal("unhealthy"),
    z.literal("degraded"),
  ]),
  node_id: z.string(),
  version: z.string(),
  checks: z.record(z.string(), z.boolean()).default({}),
});

/** Node health check response. */
export type WorkflowNodeHealthResponse = z.infer<typeof WorkflowNodeHealthResponseSchema>;
