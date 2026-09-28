import { mkdirSync } from "node:fs";
import { join, resolve, sep } from "node:path";
// Unprefixed form: tsup's dts pass doesn't recognize "node:async_hooks" as a
// resolvable builtin external (while "node:fs" works) — bare "async_hooks"
// resolves to the same module at runtime and through @types/node.
import { AsyncLocalStorage } from "async_hooks";
import type { NodeExecutionRequest } from "./request.js";
import { getNodeLogger, type SdkLogger } from "./logging.js";

/** Max characters of a progress-ping message (engine payload cap, #495). */
const PROGRESS_MESSAGE_MAX_CHARS = 1000;

/** Per-ping timeout — a slow or hung engine must not leak sockets (DA-3232). */
const PROGRESS_PING_TIMEOUT_MS = 5000;

/**
 * Ambient per-run execution context (DA-3232).
 *
 * `BaseNode.run()` enters the run's `ExecutionContext` for the duration of
 * execution (including awaited continuations), so `BaseNode.reportProgress()`
 * can resolve the current run without threading the context through node
 * signatures. Async-local storage keeps concurrent runs of one shared node
 * instance isolated — instance-held state would cross-run race.
 */
export const executionContextStorage = new AsyncLocalStorage<ExecutionContext>();

/**
 * Context provided to node execute() method.
 *
 * Provides access to:
 * - Run and node identifiers (`runId`, `nodeId`)
 * - Output directory for writing result files (`outputDir`, `outputPath()`)
 * - Downloads directory for auto-downloaded file inputs (`downloadsDir`)
 * - Metadata dict for download tracking (`metadata`)
 * - Logger with run/node context (`logger`)
 * - Progress reporting for long-running operations (`reportProgress()`)
 * - Token usage tracking for LLM-based nodes (`recordTokenUsage()`)
 * - Cooperative cancellation (`cancelSignal`) — aborted by the server when
 *   the request deadline expires; checked between download chunks.
 *   `execute()` itself cannot be interrupted.
 */
export class ExecutionContext {
  private _request: NodeExecutionRequest | null;
  private _outputDir: string;
  private _logger: SdkLogger;
  private _tokenUsage: Record<string, number>;
  private _metadata: Record<string, unknown>;
  private _downloadsDir: string | null;
  private _cancelSignal: AbortSignal | null;
  private _executionId: string | null;

  /**
   * Creates a new execution context.
   * @param opts - Context options
   */
  constructor(opts: {
    request?: NodeExecutionRequest | null;
    outputDir?: string;
    runId?: string;
    nodeId?: string;
    cancelSignal?: AbortSignal | null;
    executionId?: string | null;
  } = {}) {
    const {
      request = null,
      outputDir,
      runId,
      nodeId,
      cancelSignal = null,
      executionId = null,
    } = opts;

    this._request = request;
    const resolvedRunId = runId ?? request?.run_id ?? "local";
    const resolvedNodeId = nodeId ?? request?.node_id ?? "unknown";

    if (outputDir) {
      this._outputDir = outputDir;
    } else {
      const baseDir = process.env.CANVASTEKK_OUTPUT_DIR;
      if (baseDir) {
        this._outputDir = join(baseDir, resolvedRunId, resolvedNodeId);
      } else {
        this._outputDir = join("/tmp", resolvedRunId, resolvedNodeId);
      }
    }
    mkdirSync(this._outputDir, { recursive: true });

    this._logger = getNodeLogger(resolvedNodeId);
    this._tokenUsage = {};
    this._metadata = {};
    this._downloadsDir = null;
    this._cancelSignal = cancelSignal;
    this._executionId = executionId;
  }

  /** Cooperative cancellation signal — aborted when the request deadline expires. */
  get cancelSignal(): AbortSignal | null {
    return this._cancelSignal;
  }

  /**
   * Execution ID minted by `BaseNode.run()` for this execution.
   *
   * Carried on the context so mid-run progress pings can echo the same
   * `execution_id` the engine validated at dispatch time (DA-3232). `null`
   * for locally constructed contexts (no run).
   */
  get executionId(): string | null {
    return this._executionId;
  }

  get runId(): string {
    if (this._request) return this._request.run_id;
    return this._outputDir.split("/").slice(-2, -1)[0] ?? "local";
  }

  get nodeId(): string {
    if (this._request) return this._request.node_id;
    return this._outputDir.split("/").pop() ?? "unknown";
  }

  get outputDir(): string {
    return this._outputDir;
  }

  get logger(): SdkLogger {
    return this._logger;
  }

  /**
   * Gets the full path for a file in the output directory.
   * @param filename - Filename to join with output directory
   * @returns Full file path
   * @throws {Error} If the filename escapes the output directory
   *   (path traversal — absolute paths or `..` segments).
   */
  outputPath(filename: string): string {
    const candidate = resolve(join(this._outputDir, filename));
    if (!candidate.startsWith(resolve(this._outputDir) + sep)) {
      throw new Error(`Output filename '${filename}' escapes the output directory`);
    }
    return candidate;
  }

  get downloadsDir(): string {
    if (this._downloadsDir === null) {
      this._downloadsDir = join(this._outputDir, "downloads");
      mkdirSync(this._downloadsDir, { recursive: true });
    }
    return this._downloadsDir;
  }

  get metadata(): Record<string, unknown> {
    return this._metadata;
  }

  set metadata(value: Record<string, unknown>) {
    this._metadata = value;
  }

  /**
   * Reports execution progress.
   *
   * Logs locally and, when running inside a workflow with a callback URL and
   * execution ID (DA-3232), fires a best-effort progress ping to the engine.
   * Local/dev contexts without a callback URL log exactly as before.
   *
   * @param progress - Progress value between 0 and 1
   * @param message - Optional progress message
   */
  reportProgress(progress: number, message = ""): void {
    const percent = Math.round(progress * 100);
    let logMsg = `Progress: ${percent}%`;
    if (message) logMsg += ` - ${message}`;
    this._logger.info(logMsg);
    this._sendProgressPing(percent, message);
  }

  /**
   * Fire-and-forget progress ping to the engine's progress route (DA-3232).
   *
   * POSTs `{execution_id, percent, message}` to `${callback_url}/progress`
   * (engine #495: the completion callback URL plus `/progress`). Never
   * throws into caller code and never leaves an unhandled rejection —
   * transport failures are swallowed and logged at warn level, matching the
   * DA-2887 telemetry philosophy: progress reporting must never affect the
   * node outcome. Safe no-op when either the callback URL or the execution
   * ID is missing (local dev, request-less contexts).
   *
   * @param percent - Progress percentage; clamped to [0, 100]
   * @param message - Optional message; truncated to 1000 chars (engine
   *   payload cap)
   */
  private _sendProgressPing(percent = 0, message = ""): void {
    // Engine-issued orchestrator URL, deliberately NOT run through
    // url-policy: the engine legitimately lives on private/loopback
    // addresses in-cluster, which the SSRF guard would block.
    const callbackUrl = this._request?.callback_url?.replace(/\/+$/, "") ?? null;
    if (!callbackUrl || !this._executionId) return;

    const clamped = Math.min(100, Math.max(0, percent));
    const cappedMessage = message.slice(0, PROGRESS_MESSAGE_MAX_CHARS);
    const payload: Record<string, unknown> = {
      execution_id: this._executionId,
      percent: clamped,
    };
    if (cappedMessage) payload.message = cappedMessage;

    void fetch(`${callbackUrl}/progress`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      signal: AbortSignal.timeout(PROGRESS_PING_TIMEOUT_MS),
    }).catch((err: unknown) => {
      this._logger.warn(
        `Progress ping failed (best-effort, ignored): ${err instanceof Error ? err.message : String(err)}`,
      );
    });
  }

  recordTokenUsage(opts: {
    promptTokens?: number;
    completionTokens?: number;
    totalTokens?: number;
  } = {}): void {
    this._tokenUsage = {
      prompt_tokens: opts.promptTokens ?? 0,
      completion_tokens: opts.completionTokens ?? 0,
      total_tokens: opts.totalTokens ?? 0,
    };
    this._logger.info(
      `Token usage: prompt=${this._tokenUsage.prompt_tokens}, completion=${this._tokenUsage.completion_tokens}, total=${this._tokenUsage.total_tokens}`,
    );
  }

  get tokenUsage(): Record<string, number> {
    return { ...this._tokenUsage };
  }
}
