import { randomUUID } from "node:crypto";
import { unlinkSync, statSync } from "node:fs";
import { createWriteStream } from "node:fs";
import { join, basename } from "node:path";
import { once } from "node:events";
import AjvModule from "ajv";
const Ajv = AjvModule.default ?? AjvModule;
import type { ValidateFunction } from "ajv";
import type { WorkflowNodeManifest } from "./definition.js";
import { WorkflowNodeManifestSchema, getFileInputFields, validateFileInput } from "./definition.js";
import {
  DEFAULT_MAX_DOWNLOAD_BYTES,
  MAX_REDIRECT_HOPS,
  UrlPolicyError,
  validateExternalUrl,
} from "./url-policy.js";
import { ExecutionContext, executionContextStorage } from "./context.js";
import type { NodeMiddleware } from "./middleware.js";
import { LoggingMiddleware } from "./middleware.js";
import { MetricsCollector, createExecutionMetric } from "./observability.js";
import type { NodeExecutionRequest } from "./request.js";
import { NodeExecutionResponseFactory, type NodeExecutionResponse } from "./response.js";
import {
  NodeExecutionError,
  NodeValidationError,
  NodeOutputValidationError,
  NodeIOError,
  NodeConfigurationError,
} from "./exceptions.js";
import { createLogger } from "./logging.js";
import { createNodeApp } from "./app.js";
import type { CreateNodeAppOptions } from "./app.js";

const ajv = new Ajv({ strict: false });

const logger = createLogger("base-node");

// Fraction of the node's timeout_seconds reserved for execute() after all
// file downloads complete; downloads share the remainder of the budget.
const DOWNLOAD_BUDGET_FRACTION = 0.8;

/**
 * Computes a wall-clock deadline (Date.now() ms) for all file-input
 * downloads: a fraction of the node's timeout_seconds, never below 30 s
 * (matching the previous fixed behavior).
 */
export function downloadDeadline(timeoutSeconds: number | undefined): number {
  const budget = Math.max((timeoutSeconds ?? 30) * DOWNLOAD_BUDGET_FRACTION, 30);
  return Date.now() + budget * 1000;
}

/**
 * Sanitizes a filename by extracting only the base name, preventing path traversal.
 * @param rawName - Raw filename that may contain directory components
 * @returns Safe basename with no directory separators
 */
function sanitizeFilename(rawName: string): string {
  return basename(rawName);
}

/**
 * Extracts a filename from a URL or Content-Disposition header.
 *
 * Tries Content-Disposition first, falls back to URL pathname,
 * then defaults to "download".
 *
 * @param url - Download URL
 * @param contentDisposition - Optional Content-Disposition header value
 * @returns Extracted filename (sanitized)
 */
function extractFilename(url: string, contentDisposition?: string | null): string {
  if (contentDisposition) {
    for (const part of contentDisposition.split(";")) {
      const trimmed = part.trim();
      if (trimmed.toLowerCase().startsWith("filename=")) {
        const raw = trimmed.split("=").slice(1).join("=").trim().replace(/^["']|["']$/g, "");
        if (raw) return sanitizeFilename(raw);
      }
    }
  }

  try {
    const parsed = new URL(url);
    const path = parsed.pathname;
    if (path) {
      const raw = path.replace(/\/$/, "").split("/").pop();
      if (raw) return sanitizeFilename(raw);
    }
  } catch {
    // ignore URL parse errors
  }

  return "download";
}

/**
 * Compiles a JSON Schema into an Ajv validation function.
 *
 * Returns null for trivial schemas (`{"type":"object"}`) to skip unnecessary validation.
 * Compiled validators are cached by Ajv internally.
 *
 * @param schema - JSON Schema object
 * @returns Validation function, or null for trivial schemas
 */
function compileSchema(schema: Record<string, unknown>): ValidateFunction | null {
  if (!schema || JSON.stringify(schema) === '{"type":"object"}') return null;
  return ajv.compile(schema);
}

/**
 * Formats Ajv validation errors into a structured, sorted array.
 *
 * Errors are sorted by instance path for deterministic output.
 *
 * @param errors - Raw Ajv error objects
 * @returns Array of { path, message, validator } objects
 */
function formatAjvErrors(errors: import("ajv").ErrorObject[]): Record<string, unknown>[] {
  return errors
    .sort((a, b) => {
      const ap = a.instancePath.split("/").filter(Boolean);
      const bp = b.instancePath.split("/").filter(Boolean);
      return ap.join("/").localeCompare(bp.join("/"));
    })
    .map((e) => ({
      path: e.instancePath.split("/").filter(Boolean),
      message: e.message ?? "validation failed",
      validator: e.keyword,
    }));
}

/**
 * Abstract base class for all CanvasTEKK workflow nodes.
 *
 * Subclasses must:
 * 1. Define a `definition` class attribute with a valid WorkflowNodeManifest
 * 2. Implement the `execute()` method
 *
 * The SDK validates the definition at construction time and auto-downloads
 * file inputs before calling `execute()`. Output validation runs after
 * `execute()` returns.
 *
 * @example
 * ```typescript
 * class EchoNode extends BaseNode {
 *   definition = {
 *     slug: "echo",
 *     version: "1.0.0",
 *     name: "Echo Node",
 *     description: "Passes inputs through unchanged",
 *     input_schema: { type: "object", properties: { data: { type: "string" } } },
 *     output_schema: { type: "object", properties: { data: { type: "string" } } },
 *   };
 *
 *   execute(inputs: Record<string, unknown>, context: ExecutionContext) {
 *     return inputs;
 *   }
 * }
 * ```
 */
export abstract class BaseNode {
  abstract definition: WorkflowNodeManifest;

  private _middleware: NodeMiddleware[] = [new LoggingMiddleware()];
  private _metricsCollector: MetricsCollector = new MetricsCollector();
  private _cancelSignal: AbortSignal | null = null;
  private _validatedDefinition: WorkflowNodeManifest | null = null;

  /**
   * Creates a new BaseNode instance.
   * Validates the node definition at construction time.
   */
  constructor() {
    // Constructor-time validation replaces Python's __init_subclass__
  }

  get nodeDefinition(): WorkflowNodeManifest {
    return this.getDefinition();
  }

  get metricsCollector(): MetricsCollector {
    return this._metricsCollector;
  }

  /**
   * Gets the validated node definition.
   * Caches the validated definition after first call.
   * @returns Validated workflow node manifest
   */
  protected getDefinition(): WorkflowNodeManifest {
    if (!this._validatedDefinition) {
      this._validatedDefinition = WorkflowNodeManifestSchema.parse(this.definition);
    }
    return this._validatedDefinition;
  }

  /**
   * Adds middleware to the execution pipeline.
   * @param middleware - Middleware to add
   * @returns This instance for chaining
   */
  addMiddleware(middleware: NodeMiddleware): this {
    this._middleware.push(middleware);
    return this;
  }

  /**
   * Sets the metrics collector for execution tracking.
   * @param collector - Metrics collector instance
   * @returns This instance for chaining
   */
  setMetricsCollector(collector: MetricsCollector): this {
    this._metricsCollector = collector;
    return this;
  }

  abstract execute(
    inputs: Record<string, unknown>,
    context: ExecutionContext,
  ): Record<string, unknown> | Promise<Record<string, unknown>>;

  /**
   * Resolves the effective byte cap for a file-input field.
   *
   * Prefers the manifest `x-maxSizeBytes`; falls back to the
   * `CANVASTEKK_MAX_DOWNLOAD_BYTES` env override, then to the 10 GiB
   * default (point clouds in this domain are multi-GB).
   */
  private maxDownloadBytes(fieldName: string): number {
    const def = this.getDefinition();
    const schema = (def.input_schema as Record<string, unknown>)?.properties as
      | Record<string, Record<string, unknown>>
      | undefined;
    const declared = schema?.[fieldName]?.["x-maxSizeBytes"];
    if (typeof declared === "number" && declared > 0) return declared;
    const envRaw = process.env.CANVASTEKK_MAX_DOWNLOAD_BYTES;
    if (envRaw) {
      const envCap = Number.parseInt(envRaw, 10);
      if (Number.isFinite(envCap) && envCap > 0) return envCap;
    }
    return DEFAULT_MAX_DOWNLOAD_BYTES;
  }

  /**
   * Downloads a single presigned URL to the downloads dir, streaming to
   * disk (never buffering the whole body in memory).
   *
   * Enforces the SSRF URL policy on every request and redirect hop, a
   * mid-stream byte cap, a total download deadline, and cleans up the
   * partial file on any failure.
   */
  private async downloadOne(
    fieldName: string,
    url: string,
    context: ExecutionContext,
  ): Promise<string> {
    const maxBytes = this.maxDownloadBytes(fieldName);
    const deadline = downloadDeadline(this.getDefinition().timeout_seconds);

    try {
      return await this.downloadOneInner(fieldName, url, context, maxBytes, deadline);
    } catch (err) {
      if (err instanceof UrlPolicyError) {
        throw new NodeIOError(`Blocked URL for field '${fieldName}': ${err}`);
      }
      throw err;
    }
  }

  private async downloadOneInner(
    fieldName: string,
    url: string,
    context: ExecutionContext,
    maxBytes: number,
    deadline: number,
  ): Promise<string> {
    const cancelSignal = context.cancelSignal;
    let currentUrl = await validateExternalUrl(url);
    let filename = `${fieldName}_${extractFilename(currentUrl, undefined)}`;

    let hops = 0;
     while (true) {
      if (cancelSignal?.aborted) {
        throw new NodeIOError(`Download for field '${fieldName}' was cancelled`);
      }

      let resp: Response;
      try {
        resp = await fetch(currentUrl, {
          redirect: "manual",
          signal: cancelSignal ?? undefined,
        });
      } catch (err) {
        throw new NodeIOError(
          `Failed to download file for field '${fieldName}': ${err}`,
          { path: currentUrl },
        );
      }

      if ([301, 302, 303, 307, 308].includes(resp.status)) {
        hops += 1;
        if (hops > MAX_REDIRECT_HOPS) {
          throw new NodeIOError(
            `Too many redirects downloading file for field '${fieldName}'`,
          );
        }
        const location = resp.headers.get("location");
        if (!location) {
          throw new NodeIOError(
            `Redirect without Location header downloading file for field '${fieldName}'`,
          );
        }
        currentUrl = await validateExternalUrl(
          location.includes("://") ? location : new URL(location, currentUrl).toString(),
        );
        filename = `${fieldName}_${extractFilename(currentUrl, undefined)}`;
        continue;
      }

      if (resp.status >= 400) {
        throw new NodeIOError(
          `HTTP ${resp.status} downloading file for field '${fieldName}'`,
          { path: currentUrl },
        );
      }

      const contentDisposition = resp.headers.get("content-disposition");
      if (contentDisposition) {
        filename = `${fieldName}_${extractFilename(currentUrl, contentDisposition)}`;
      }
      const localPath = join(context.downloadsDir, filename);

      const contentLength = resp.headers.get("content-length");
      if (contentLength && /^\d+$/.test(contentLength)) {
        if (Number.parseInt(contentLength, 10) > maxBytes) {
          throw new NodeIOError(
            `File for field '${fieldName}' exceeds size cap (${contentLength} > ${maxBytes} bytes)`,
          );
        }
      }

      const body = resp.body;
      if (!body) {
        throw new NodeIOError(`Empty response body for field '${fieldName}'`, { path: currentUrl });
      }

      const reader = body.getReader();
      const file = createWriteStream(localPath, { flags: "w" });
      // Lazy open can error after abort/cleanup (e.g. temp dir removed); a
      // listener here keeps such late errors from crashing the process.
      // Real failures still surface via the once("error") handler below.
      file.on("error", () => {});
      try {
        let running = 0;
        for (;;) {
          if (cancelSignal?.aborted) {
            throw new NodeIOError(`Download for field '${fieldName}' was cancelled`);
          }
          const { done, value: chunk } = await reader.read();
          if (done) break;
          running += chunk.length;
          if (running > maxBytes) {
            throw new NodeIOError(
              `File for field '${fieldName}' exceeds size cap (${running} > ${maxBytes} bytes)`,
            );
          }
          if (Date.now() > deadline) {
            throw new NodeIOError(`Download deadline exceeded for field '${fieldName}'`);
          }
          if (!file.write(chunk)) {
            await once(file, "drain");
          }
        }
        await new Promise<void>((resolve, reject) => {
          file.once("error", reject);
          file.end(() => resolve());
        });
      } catch (err) {
        file.destroy();
        try { unlinkSync(localPath); } catch { /* nothing to clean */ }
        throw err;
      } finally {
        try { reader.releaseLock(); } catch { /* already released */ }
      }

      return localPath;
    }
  }

  /**
   * Enforces the advisory deprecation lifecycle at run time (DA-2312,
   * parity with Python BaseNode._check_deprecation_lifecycle).
   *
   * Deprecation is advisory: a deprecated node still runs, with a warning
   * naming the replacement. Once `sunset_date` passes — day-inclusive, UTC —
   * the node refuses to run.
   *
   * @throws {NodeConfigurationError} If the node's sunset date has passed
   */
  private checkDeprecationLifecycle(): void {
    const dep = this.getDefinition().deprecation;
    if (!dep) return;

    const name = this.getDefinition().slug;
    const replacement = dep.replacement_slug || "unspecified";

    if (dep.sunset_date) {
      const today = new Date().toISOString().slice(0, 10);
      if (today > dep.sunset_date) {
        throw new NodeConfigurationError(
          `Node '${name}' was sunset on ${dep.sunset_date} and refuses to run; migrate to '${replacement}' (${dep.notice})`,
        );
      }
    }

    logger.warn(
      `Node '${name}' is deprecated (since ${dep.deprecated_at ?? "unknown date"}): ${dep.notice} — migrate to '${replacement}'`,
    );
  }

  /**
   * Validates inputs against the node's input schema.
   * @param inputs - Input data to validate
   * @throws {NodeValidationError} If validation fails
   */
  private validateInputs(inputs: Record<string, unknown>): void {
    const def = this.getDefinition();
    const validate = compileSchema(def.input_schema as Record<string, unknown>);
    if (!validate) return;

    if (!validate(inputs)) {
      const errors = formatAjvErrors(validate.errors ?? []);
      throw new NodeValidationError(
        `Input validation failed: ${errors[0]?.message ?? "unknown error"}`,
        { errors },
      );
    }
  }

  /**
   * Validates outputs against the node's output schema.
   * @param outputs - Output data to validate
   * @throws {NodeOutputValidationError} If validation fails
   */
  private validateOutputs(outputs: Record<string, unknown>): void {
    const def = this.getDefinition();
    const validate = compileSchema(def.output_schema as Record<string, unknown>);
    if (!validate) return;

    if (!validate(outputs)) {
      const errors = formatAjvErrors(validate.errors ?? []);
      throw new NodeOutputValidationError(
        `Output validation failed: ${errors[0]?.message ?? "unknown error"}`,
        { errors },
      );
    }
  }

  /**
   * Downloads file inputs from URLs and validates them.
   *
   * Enforces the SSRF URL policy on every request and redirect hop,
   * a mid-stream byte cap, a total download deadline, and cleans up
   * partial files on any failure.
   *
   * @param inputs - Input data containing URL references
   * @param context - Execution context for download tracking
   * @returns Inputs with URLs replaced by local file paths
   * @throws {NodeIOError} If file download fails
   * @throws {NodeValidationError} If file constraints are violated
   */
  private async prepareFileInputs(
    inputs: Record<string, unknown>,
    context: ExecutionContext,
  ): Promise<Record<string, unknown>> {
    const def = this.getDefinition();
    const fileFields = getFileInputFields(def);
    const downloaded: string[] = [];

    try {
      for (const fieldName of fileFields) {
        const value = inputs[fieldName];

        if (value == null || typeof value !== "string" || !value.trim()) continue;
        if (!value.startsWith("http://") && !value.startsWith("https://")) continue;

        context.reportProgress(0.05, `Downloading ${fieldName}`);

        const localPath = await this.downloadOne(fieldName, value, context);
        // Register the path BEFORE validation so a post-download validation
        // failure still triggers cleanup of the completed file.
        downloaded.push(localPath);

        const fileSize = statSync(localPath).size;

        validateFileInput(def, fieldName, localPath, fileSize);

        context.metadata[fieldName] = {
          original_url: value,
          local_path: localPath,
          size_bytes: fileSize,
        };

        inputs[fieldName] = localPath;
        context.reportProgress(0.1, `Downloaded ${fieldName} (${fileSize} bytes)`);
      }
    } catch (err) {
      for (const p of downloaded) {
        try { unlinkSync(p); } catch { /* ignore cleanup errors */ }
      }
      throw err;
    }

    return inputs;
  }

  /**
   * Executes the node with full validation, middleware, and error handling.
   * @param request - Execution request with inputs and metadata
   * @returns Execution response with outputs or error details
   */
  /**
   * Sets a cooperative cancellation signal propagated to the execution
   * context. Called by the app server before `run()` so a timed-out
   * request can stop in-flight file downloads. `execute()` itself cannot
   * be interrupted.
   */
  setCancelSignal(signal: AbortSignal | null): void {
    this._cancelSignal = signal;
  }

  /**
   * Reports mid-run progress to the workflow engine (DA-3232).
   *
   * Fire-and-forget POST to the engine's progress route
   * (`{callback_url}/progress`, engine #495) carrying this run's
   * `execution_id`. Best-effort — transport failures are swallowed and
   * logged, never thrown into node logic (same philosophy as DA-2887
   * telemetry). Safe no-op outside a workflow run (local dev) or when the
   * request carries no callback URL: nothing is sent, nothing raises.
   *
   * Call from inside `execute()`:
   *
   * ```ts
   * this.reportProgress(50, "still calculating");
   * ```
   *
   * Note: the ticket/engine spec names this helper `report_progress`;
   * this TypeScript leg uses camelCase per house convention, matching the
   * existing `ExecutionContext.reportProgress`. The percent is 0–100 (the
   * context-level method takes 0–1).
   *
   * @param percent - Progress percentage 0–100 (clamped)
   * @param message - Optional human-readable status; capped at 1000 chars
   */
  reportProgress(percent = 0, message = ""): void {
    const ctx = executionContextStorage.getStore();
    if (!ctx) return;
    ctx.reportProgress(percent / 100, message);
  }

  async run(request: NodeExecutionRequest): Promise<NodeExecutionResponse> {
    const executionId = randomUUID();
    const startTime = performance.now();
    const def = this.getDefinition();

    try {
      this.checkDeprecationLifecycle();

      this.validateInputs(request.inputs);

      const context = new ExecutionContext({
        request,
        cancelSignal: this._cancelSignal ?? null,
        executionId,
      });

      // Ambient context for BaseNode.reportProgress() during this run,
      // including awaited continuations (DA-3232).
      return await executionContextStorage.run(context, async () => {
        let inputs = { ...request.inputs };

        const fileFields = getFileInputFields(def);
        if (fileFields.length > 0) {
          inputs = await this.prepareFileInputs(inputs, context);
        }

        for (const mw of this._middleware) {
          inputs = mw.onBeforeExecute(inputs, context);
        }

        const outputs = await this.execute(inputs, context);

        this.validateOutputs(outputs);

        const durationMs = Math.round(performance.now() - startTime);

        for (const mw of this._middleware) {
          mw.onAfterExecute(inputs, outputs, context, durationMs);
        }

        const tokenUsage = context.tokenUsage.total_tokens || def.token_cost;

        this._metricsCollector.record(
          createExecutionMetric({
            runId: context.runId,
            nodeId: context.nodeId,
            nodeName: def.slug,
            status: "pass",
            durationMs,
            tokenUsage,
          }),
        );

        return NodeExecutionResponseFactory.success(executionId, outputs, durationMs, tokenUsage);
      });
    } catch (err) {
      const durationMs = Math.round(performance.now() - startTime);
      this.recordError(request, err as Error, durationMs);

      if (err instanceof NodeExecutionError) {
        return NodeExecutionResponseFactory.failure(
          executionId,
          err.message,
          err.constructor.name,
          durationMs,
          err.errorCode,
        );
      }

      const error = err as Error;
      return NodeExecutionResponseFactory.failure(
        executionId,
        error.message ?? String(error),
        error.constructor?.name ?? "Error",
        durationMs,
      );
    }
  }

  /**
   * Records execution error to middleware and metrics.
   * @param request - Execution request
   * @param error - Error that occurred
   * @param durationMs - Execution duration in milliseconds
   */
  private recordError(
    request: NodeExecutionRequest,
    error: Error,
    durationMs: number,
  ): void {
    const context = new ExecutionContext({ request });
    for (const mw of this._middleware) {
      mw.onError(request.inputs, error, context, durationMs);
    }

    const errorCode = (error as NodeExecutionError).errorCode ?? undefined;
    this._metricsCollector.record(
      createExecutionMetric({
        runId: request.run_id,
        nodeId: request.node_id,
        nodeName: this.getDefinition().slug,
        status: "fail",
        durationMs,
        errorType: error.constructor.name,
        errorCode,
        tokenUsage: 0,
      }),
    );
  }

  /**
   * Performs a health check on the node.
   * @returns Health status indicators
   */
  healthCheck(): Record<string, boolean> {
    return {};
  }

  /**
   * Webhook handler for external events.
   * @param _payload - Webhook payload
   * @returns Response data or null
   */
  hook(_payload: Record<string, unknown>): Record<string, unknown> | null {
    return null;
  }

  /**
   * Called when the node app starts up.
   * Override for initialization logic.
   */
  async onStartup(): Promise<void> {
    // no-op
  }

  /**
   * Called when the node app shuts down.
   * Override for cleanup logic.
   */
  async onShutdown(): Promise<void> {
    // no-op
  }

  /**
   * Creates an Express app for this node.
   * @param opts - App creation options
   * @returns Express application
   */
  createApp(opts?: CreateNodeAppOptions): unknown {
    return createNodeApp(this, opts);
  }
}
