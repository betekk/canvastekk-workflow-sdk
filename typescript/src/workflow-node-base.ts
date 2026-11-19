import { randomUUID } from "node:crypto";
import { enforceSupportHorizon } from "./support-horizon.js";
import { unlinkSync, statSync } from "node:fs";
import { createWriteStream } from "node:fs";
import { join, basename } from "node:path";
import { once } from "node:events";
import AjvModule from "ajv";
const Ajv = AjvModule.default ?? AjvModule;
import type { ValidateFunction } from "ajv";
import type { WorkflowNodeManifest } from "./workflow-node-manifest.js";
import { WorkflowNodeManifestSchema, getFileInputFields, validateFileInput, effectiveRuntimeSeconds, effectiveContract } from "./workflow-node-manifest.js";
import {
  DEFAULT_MAX_DOWNLOAD_BYTES,
  MAX_REDIRECT_HOPS,
  UrlPolicyError,
  validateExternalUrl,
} from "./url-policy.js";
import { NodeExecutionContext, executionContextStorage } from "./node-execution-context.js";
import type { NodeMiddleware } from "./middleware.js";
import { LoggingMiddleware } from "./middleware.js";
import { NodeExecutionMetricsCollector, createNodeExecutionMetric } from "./observability.js";
import type { NodeExecutionRequest } from "./node-execution-request.js";
import { NodeExecutionResponseFactory, type NodeExecutionResponse } from "./node-execution-response.js";
import {
  NodeExecutionError,
  NodeInputValidationError,
  NodeOutputValidationError,
  NodeIOError,
  NodeConfigurationError,
  IO_SUBCODE_DOWNLOAD_FAILED,
  IO_SUBCODE_SIZE_EXCEEDED,
  IO_SUBCODE_URL_POLICY_BLOCKED,
} from "./exceptions.js";
import { createLogger } from "./logging.js";
/**
 * Options for building a node's HTTP server. Structural core-safe view —
 * the `/express` subpath exposes the precisely-typed express version.
 */
export interface CreateNodeAppOptions {
  /** Middleware applied to every route (express-compatible handlers). */
  dependencies?: unknown[];
  /** Extra routers to mount (express Router instances — typed on the subpath). */
  extraRoutes?: unknown[];
}

const ajv = new Ajv({ strict: false });

const logger = createLogger("base-node");

// ADR 0001 (#271): the NodeValidationError split must not change the wire.
// errorType historically carried the base class name; keep the historical
// wire names until the 1.0.0 alias removal (#272).
const WIRE_ERROR_NAMES: Record<string, string> = {
  WorkflowNodeManifestValidationError: "NodeValidationError",
  NodeInputValidationError: "NodeValidationError",
  WorkflowRunError: "WorkflowRunError",
  WorkflowDefinitionValidationError: "WorkflowDefinitionValidationError",
};

function wireErrorType(error: Error): string {
  const name = error.constructor.name;
  return WIRE_ERROR_NAMES[name] ?? name;
}

const DOWNLOAD_BUDGET_FRACTION = 0.8;

/**
 * Computes a wall-clock deadline (Date.now() ms) for all file-input
 * downloads: a fraction of the node's runtime bound (the effective
 * runtime ceiling — callers pass `effectiveRuntimeSeconds(def)`, #3515),
 * never below 30 s (matching the previous fixed behavior).
 */
export function downloadDeadline(runtimeSeconds: number | undefined): number {
  const budget = Math.max((runtimeSeconds ?? 30) * DOWNLOAD_BUDGET_FRACTION, 30);
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
 * 1. Define a `manifest` class attribute with a valid WorkflowNodeManifest
 *    (legacy `definition` fields still resolve, deprecated — ADR 0001, #271)
 * 2. Implement the `execute()` method
 *
 * The SDK validates the manifest at construction time and auto-downloads
 * file inputs before calling `execute()`. Output validation runs after
 * `execute()` returns.
 *
 * @example
 * ```typescript
 * class EchoNode extends WorkflowNodeBase {
 *   definition = {
 *     slug: "echo",
 *     version: "1.0.0",
 *     name: "Echo Node",
 *     description: "Passes inputs through unchanged",
 *     input_schema: { type: "object", properties: { data: { type: "string" } } },
 *     output_schema: { type: "object", properties: { data: { type: "string" } } },
 *   };
 *
 *   execute(inputs: Record<string, unknown>, context: NodeExecutionContext) {
 *     return inputs;
 *   }
 * }
 * ```
 */
export abstract class WorkflowNodeBase {
  // Manifest attribute contract (ADR 0001, #271): subclasses declare a
  // `manifest` class field (legacy `definition` still resolves). Presence is
  // enforced at runtime by getWorkflowNodeManifest's schema parse — TS
  // cannot express "either attribute name" as an abstract member.

  private _middleware: NodeMiddleware[] = [new LoggingMiddleware()];
  private _metricsCollector: NodeExecutionMetricsCollector = new NodeExecutionMetricsCollector();
  private _cancelSignal: AbortSignal | null = null;
  private _validatedDefinition: WorkflowNodeManifest | null = null;

  /**
   * Creates a new WorkflowNodeBase instance.
   * Validates the node manifest at construction time.
   */
  constructor() {
    // Constructor-time validation replaces Python's __init_subclass__
  }

  get nodeDefinition(): WorkflowNodeManifest {
    return this.getWorkflowNodeManifest();
  }

  /**
   * @deprecated use getWorkflowNodeManifest (ADR 0001, #271; removal in 1.0.0, #272)
   */
  protected getDefinition(): WorkflowNodeManifest {
    return this.getWorkflowNodeManifest();
  }

  /**
   * The node's workflow node manifest (ADR 0001, #271). Canonical name for
   * the class attribute; legacy `definition` fields still resolve here.
   */
  get manifest(): WorkflowNodeManifest {
    return this.getWorkflowNodeManifest();
  }

  /**
   * @deprecated legacy attribute name — use `manifest` (ADR 0001, #271;
   * removal in 1.0.0, #272). Subclasses declaring their own `definition`
   * field shadow this getter, which is exactly the legacy pattern.
   */
  get definition(): WorkflowNodeManifest {
    return this.getWorkflowNodeManifest();
  }

  get metricsCollector(): NodeExecutionMetricsCollector {
    return this._metricsCollector;
  }

  /**
   * Gets the validated node definition.
   * Caches the validated definition after first call.
   * @returns Validated workflow node manifest
   */
  protected getWorkflowNodeManifest(): WorkflowNodeManifest {
    if (!this._validatedDefinition) {
      // ADR 0001 (#271): prefer the canonical own `manifest` field; fall back
      // to the legacy own `definition` field. Own-property reads only — the
      // prototype `manifest` getter routes back here (recursion guard).
      const self = this as unknown as Record<string, unknown>;
      const hasOwn = Object.prototype.hasOwnProperty.call(this, "manifest");
      const rawManifest = (hasOwn ? self.manifest : undefined) ?? self.definition;
      this._validatedDefinition = WorkflowNodeManifestSchema.parse(rawManifest);
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
  setMetricsCollector(collector: NodeExecutionMetricsCollector): this {
    this._metricsCollector = collector;
    return this;
  }

  abstract execute(
    inputs: Record<string, unknown>,
    context: NodeExecutionContext,
  ): Record<string, unknown> | Promise<Record<string, unknown>>;

  /**
   * Resolves the effective byte cap for a file-input field.
   *
   * Prefers the manifest `x-maxSizeBytes`; falls back to the
   * `CANVASTEKK_MAX_DOWNLOAD_BYTES` env override, then to the 10 GiB
   * default (point clouds in this domain are multi-GB).
   */
  private maxDownloadBytes(fieldName: string): number {
    const def = this.getWorkflowNodeManifest();
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
    context: NodeExecutionContext,
  ): Promise<string> {
    const maxBytes = this.maxDownloadBytes(fieldName);
    const deadline = downloadDeadline(effectiveRuntimeSeconds(this.getWorkflowNodeManifest()));

    try {
      return await this.downloadOneInner(fieldName, url, context, maxBytes, deadline);
    } catch (err) {
      if (err instanceof UrlPolicyError) {
        throw new NodeIOError(`Blocked URL for field '${fieldName}': ${err}`, {
          details: { sub_code: IO_SUBCODE_URL_POLICY_BLOCKED },
        });
      }
      throw err;
    }
  }

  private async downloadOneInner(
    fieldName: string,
    url: string,
    context: NodeExecutionContext,
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
          { path: currentUrl, details: { sub_code: IO_SUBCODE_DOWNLOAD_FAILED } },
        );
      }

      if ([301, 302, 303, 307, 308].includes(resp.status)) {
        hops += 1;
        if (hops > MAX_REDIRECT_HOPS) {
          throw new NodeIOError(
            `Too many redirects downloading file for field '${fieldName}'`,
            { details: { sub_code: IO_SUBCODE_DOWNLOAD_FAILED } },
          );
        }
        const location = resp.headers.get("location");
        if (!location) {
          throw new NodeIOError(
            `Redirect without Location header downloading file for field '${fieldName}'`,
            { details: { sub_code: IO_SUBCODE_DOWNLOAD_FAILED } },
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
          { path: currentUrl, details: { sub_code: IO_SUBCODE_DOWNLOAD_FAILED } },
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
            { details: { sub_code: IO_SUBCODE_SIZE_EXCEEDED } },
          );
        }
      }

      const body = resp.body;
      if (!body) {
        throw new NodeIOError(`Empty response body for field '${fieldName}'`, { path: currentUrl });
      }

      const reader = body.getReader();
      const file = createWriteStream(localPath, { flags: "w" });
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
              { details: { sub_code: IO_SUBCODE_SIZE_EXCEEDED } },
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
        try { unlinkSync(localPath); } catch { }
        throw err;
      } finally {
        try { reader.releaseLock(); } catch { }
      }

      return localPath;
    }
  }

  /**
   * Enforces the advisory deprecation lifecycle at run time (DA-2312,
   * parity with Python WorkflowNodeBase._check_deprecation_lifecycle).
   *
   * Deprecation is advisory: a deprecated node still runs, with a warning
   * naming the replacement. Once `sunset_date` passes — day-inclusive, UTC —
   * the node refuses to run.
   *
   * @throws {NodeConfigurationError} If the node's sunset date has passed
   */
  private checkDeprecationLifecycle(): void {
    const dep = this.getWorkflowNodeManifest().deprecation;
    if (!dep) return;

    const name = this.getWorkflowNodeManifest().slug;
    const replacement = dep.replacement_slug || "unspecified";

    if (dep.sunset_date) {
      const today = new Date().toISOString().slice(0, 10);
      if (today > dep.sunset_date) {
        throw new NodeConfigurationError(
          `Node '${name}' was sunset on ${dep.sunset_date} and refuses to run; migrate to '${replacement}' (${dep.notice})`,
          {
            errorCode: "NODE_SUNSET",
            details: {
              sunset_date: dep.sunset_date,
              replacement_slug: replacement,
            },
          },
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
    const def = this.getWorkflowNodeManifest();
    const validate = compileSchema(def.input_schema as Record<string, unknown>);
    if (!validate) return;

    if (!validate(inputs)) {
      const errors = formatAjvErrors(validate.errors ?? []);
      throw new NodeInputValidationError(
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
    const def = this.getWorkflowNodeManifest();
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
    context: NodeExecutionContext,
  ): Promise<Record<string, unknown>> {
    const def = this.getWorkflowNodeManifest();
    const fileFields = getFileInputFields(def);
    const downloaded: string[] = [];

    try {
      for (const fieldName of fileFields) {
        const value = inputs[fieldName];

        if (Array.isArray(value)) {
          const entries: Array<Record<string, unknown>> = [];
          const newElements: unknown[] = [];
          for (const element of value) {
            if (
              typeof element === "string" &&
              element.trim() &&
              (element.startsWith("http://") || element.startsWith("https://"))
            ) {
              context.reportProgress(0.05, `Downloading ${fieldName}`);
              const localPath = await this.downloadOne(fieldName, element, context);
              downloaded.push(localPath);
              const fileSize = statSync(localPath).size;
              validateFileInput(def, fieldName, localPath, fileSize);
              entries.push({
                original_url: element,
                local_path: localPath,
                size_bytes: fileSize,
              });
              newElements.push(localPath);
            } else {
              newElements.push(element);
            }
          }
          if (entries.length > 0) {
            context.metadata[fieldName] = entries;
            inputs[fieldName] = newElements;
            context.reportProgress(
              0.1,
              `Downloaded ${entries.length} element(s) of ${fieldName}`,
            );
          }
          continue;
        }

        if (value == null || typeof value !== "string" || !value.trim()) continue;
        if (!value.startsWith("http://") && !value.startsWith("https://")) continue;

        context.reportProgress(0.05, `Downloading ${fieldName}`);

        const localPath = await this.downloadOne(fieldName, value, context);
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
        try { unlinkSync(p); } catch { }
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
   * existing `NodeExecutionContext.reportProgress`. The percent is 0–100 (the
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
    enforceSupportHorizon();
    const executionId = request.execution_id ?? randomUUID();
    const startTime = performance.now();
    const def = this.getWorkflowNodeManifest();

    try {
      this.checkDeprecationLifecycle();

      this.validateInputs(request.inputs);

      if (request.dry_run) {
        const dryDurationMs = Math.round(performance.now() - startTime);
        if (!effectiveContract(def).capabilities.dry_run) {
          logger.info(`dry-run refused (capability not declared) slug=${def.slug}`);
          return NodeExecutionResponseFactory.failure(
            executionId,
            "dry_run requested but the node does not declare contract.capabilities.dry_run",
            "NodeConfigurationError",
            dryDurationMs,
            "DRY_RUN_NOT_SUPPORTED",
            true,
          );
        }
        logger.info(`execution slug=${def.slug} status=pass duration_ms=${dryDurationMs} dry_run=true`);
        return NodeExecutionResponseFactory.success(
          `dryrun-${executionId}`,
          {},
          dryDurationMs,
          0.0,
          true,
        );
      }

      const context = new NodeExecutionContext({
        request,
        cancelSignal: this._cancelSignal ?? null,
        executionId,
      });

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
        logger.info(`execution slug=${def.slug} status=pass duration_ms=${durationMs}`);

        for (const mw of this._middleware) {
          mw.onAfterExecute(inputs, outputs, context, durationMs);
        }

        const tokenUsage = context.tokenUsage.total_tokens || def.token_cost;

        this._metricsCollector.record(
          createNodeExecutionMetric({
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
    const context = new NodeExecutionContext({ request });
    for (const mw of this._middleware) {
      mw.onError(request.inputs, error, context, durationMs);
    }

    const errorCode = (error as NodeExecutionError).errorCode ?? undefined;
    this._metricsCollector.record(
      createNodeExecutionMetric({
        runId: request.run_id,
        nodeId: request.node_id,
        nodeName: this.getWorkflowNodeManifest().slug,
        status: "fail",
        durationMs,
        errorType: wireErrorType(error),
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
  }

  /**
   * Called when the node app shuts down.
   * Override for cleanup logic.
   */
  async onShutdown(): Promise<void> {
  }

  /**
   * Creates an Express app for this node.
   *
   * Lazily loads the express adapter (`@betekk/canvastekk-workflow-sdk/express`);
   * express is an optional peer dependency and must be installed when this is
   * called.
   * @param opts - App creation options
   * @returns Promise resolving to the Express application
   */
  async createApp(opts?: CreateNodeAppOptions): Promise<unknown> {
    const { createWorkflowNodeApp } = await import("./workflow-node-app.js");
    return createWorkflowNodeApp(this, opts as Parameters<typeof createWorkflowNodeApp>[1]);
  }
}
