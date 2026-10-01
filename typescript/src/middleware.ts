import type { ExecutionContext } from "./context.js";

/**
 * Interface for node execution middleware hooks.
 */
export interface NodeMiddleware {
  /**
   * Called before node execution begins.
   * @param inputs - Node input data
   * @param context - Execution context
   * @returns Possibly modified inputs
   */
  onBeforeExecute(
    inputs: Record<string, unknown>,
    context: ExecutionContext,
  ): Record<string, unknown>;

  /**
   * Called after successful node execution.
   * @param inputs - Node input data
   * @param outputs - Node output data
   * @param context - Execution context
   * @param durationMs - Execution duration in milliseconds
   */
  onAfterExecute(
    inputs: Record<string, unknown>,
    outputs: Record<string, unknown>,
    context: ExecutionContext,
    durationMs: number,
  ): void;

  /**
   * Called when node execution fails.
   * @param inputs - Node input data
   * @param error - Error that occurred
   * @param context - Execution context
   * @param durationMs - Execution duration in milliseconds
   */
  onError(
    inputs: Record<string, unknown>,
    error: Error,
    context: ExecutionContext,
    durationMs: number,
  ): void;
}

/**
 * Middleware that logs node execution events.
 */
export class LoggingMiddleware implements NodeMiddleware {
  onBeforeExecute(
    inputs: Record<string, unknown>,
    context: ExecutionContext,
  ): Record<string, unknown> {
    context.logger.info(
      `[${context.runId}] Executing node with ${Object.keys(inputs).length} input(s)`,
      { run_id: context.runId, node_id: context.nodeId },
    );
    return inputs;
  }

  onAfterExecute(
    inputs: Record<string, unknown>,
    outputs: Record<string, unknown>,
    context: ExecutionContext,
    durationMs: number,
  ): void {
    context.logger.info(
      `[${context.runId}] Completed in ${durationMs}ms with ${Object.keys(outputs).length} output(s)`,
      { run_id: context.runId, node_id: context.nodeId, duration_ms: durationMs },
    );
  }

  onError(
    inputs: Record<string, unknown>,
    error: Error,
    context: ExecutionContext,
    durationMs: number,
  ): void {
    context.logger.error(
      `[${context.runId}] Failed after ${durationMs}ms: ${error}`,
      {
        run_id: context.runId,
        node_id: context.nodeId,
        duration_ms: durationMs,
        error_type: error.constructor.name,
      },
    );
  }
}

/**
 * Middleware that collects execution timing metrics.
 */
export class TimingMiddleware implements NodeMiddleware {
  private _timings: Array<Record<string, unknown>> = [];

  /** Array of timing records. */
  get timings(): Array<Record<string, unknown>> {
    return this._timings;
  }

  onBeforeExecute(
    inputs: Record<string, unknown>,
    _context: ExecutionContext,
  ): Record<string, unknown> {
    return inputs;
  }

  onAfterExecute(
    _inputs: Record<string, unknown>,
    _outputs: Record<string, unknown>,
    context: ExecutionContext,
    durationMs: number,
  ): void {
    this._timings.push({
      run_id: context.runId,
      node_id: context.nodeId,
      duration_ms: durationMs,
      status: "pass",
    });
  }

  onError(
    _inputs: Record<string, unknown>,
    error: Error,
    context: ExecutionContext,
    durationMs: number,
  ): void {
    this._timings.push({
      run_id: context.runId,
      node_id: context.nodeId,
      duration_ms: durationMs,
      status: "fail",
      error_type: error.constructor.name,
    });
  }
}

/**
 * Express middleware that adds SDK version to response headers.
 */
export class SDKVersionMiddleware {
  private _version: string;
  private _nodeSlug: string | null;

  /**
   * Creates a new SDK version middleware.
   * @param version - SDK version string
   * @param nodeSlug - optional node slug for X-Canvastekk-Node-Slug (DA-3359)
   */
  constructor(version: string, nodeSlug: string | null = null) {
    this._version = version;
    this._nodeSlug = nodeSlug;
  }

  /**
   * Returns an Express middleware function.
   * @returns Express middleware function
   */
  handler(): (req: unknown, res: { setHeader: (k: string, v: string) => void }, next: () => void) => void {
    return (_req: unknown, res: { setHeader: (k: string, v: string) => void }, next: () => void) => {
      res.setHeader("X-SDK-Version", this._version);
      if (this._nodeSlug) {
        res.setHeader("X-Canvastekk-Node-Slug", this._nodeSlug);
      }
      next();
    };
  }
}
