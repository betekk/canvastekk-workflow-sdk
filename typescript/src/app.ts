import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import express from "express";
import type { Request, Response, NextFunction } from "express";
import { VERSION } from "./version.js";
import { getNodeId, getFileOutputFields } from "./definition.js";
import { NodeTimeoutError, NodeExecutionError, getHttpStatusForError } from "./exceptions.js";
import { configureLogging } from "./logging.js";
import { SDKVersionMiddleware } from "./middleware.js";
import { CANVASTEKK_AUTH_MARKER } from "./auth.js";
import type { BaseNode } from "./base-node.js";
import { NodeExecutionRequestSchema } from "./request.js";
import { HealthResponseSchema } from "./response.js";
import { getDefaultUploader, type UploadTarget } from "./uploads.js";
import { isDevMode } from "./url-policy.js";

export interface CreateNodeAppOptions {
  dependencies?: Array<(req: Request, res: Response, next: NextFunction) => void>;
  extraRoutes?: express.Router[];
}

/**
 * Creates an Express application for a single CanvasTEKK node.
 *
 * Registers 8 endpoints: POST /execute, GET /health, GET /manifest,
 * GET /definition (redirect), POST /hook, GET /metrics, GET /live, GET /ready.
 * Includes JSON body parsing, SDK version header, error handling, and
 * startup/shutdown lifecycle hooks.
 *
 * @param node - BaseNode instance to serve
 * @param opts - Optional configuration for dependencies and extra routes
 * @returns Configured Express application
 */
/** True when any dependency middleware was produced by NodeAuth (DA-1955). */
function hasAuthDependency(
  dependencies?: Array<(req: Request, res: Response, next: NextFunction) => void>,
): boolean {
  return (
    dependencies?.some(
      (dep) => (dep as unknown as Record<string, unknown>)[CANVASTEKK_AUTH_MARKER] === true,
    ) ?? false
  );
}

/**
 * sha256 over the source bytes of the module that called createNodeApp.
 * Resolved via the structured-stack trick (Node's util.getCallSite is still
 * experimental). Returns null when the caller's file cannot be resolved —
 * the manifest then omits code_digest (engine treats absent as unverifiable).
 */
function handlerCodeDigest(): string | null {
  const original = Error.prepareStackTrace;
  Error.prepareStackTrace = (_err: Error, sites: NodeJS.CallSite[]) => sites;
  try {
    const sites = new Error().stack as unknown as NodeJS.CallSite[];
    // [0] handlerCodeDigest (Error constructed here) · [1] createNodeApp · [2] caller
    const file = sites[2]?.getFileName?.();
    if (!file) return null;
    const path = file.startsWith("file://") ? new URL(file).pathname : file;
    return createHash("sha256").update(readFileSync(path)).digest("hex");
  } catch {
    return null;
  } finally {
    Error.prepareStackTrace = original;
  }
}

export function createNodeApp(
  node: BaseNode,
  opts: CreateNodeAppOptions = {},
): express.Application {
  const app = express();

  app.use(express.json({ limit: "50mb" }));

  // DA-2603: code digest computed once at startup — sha256 over the source
  // bytes of the module that called createNodeApp (the handler module).
  // ponytail: single-file digest; walk the package if nodes grow multi-file.
  const codeDigest = handlerCodeDigest();
  if (codeDigest === null) {
    console.warn(
      "[canvastekk] Could not resolve handler source for code_digest; " +
        "/manifest will serve without it",
    );
  }

  configureLogging();

  // Loud auth-posture warnings (DA-1711 3.3): surface misconfiguration at
  // startup instead of failing silently in production.
  if (isDevMode()) {
    console.warn(
      "[canvastekk] CANVASTEKK_DEV_MODE is active: ALL authentication is bypassed " +
        "and URL policy restrictions are lifted. Never enable in production.",
    );
  } else if (!hasAuthDependency(opts.dependencies)) {
    console.warn(
      "[canvastekk] Node server starting with NO authentication configured. " +
        "Every endpoint (incl. /execute, /metrics) is unauthenticated. " +
        "Pass auth middleware via createNodeApp(opts.dependencies) or ensure " +
        "the node is network-isolated.",
    );
  }

  const sdkVersion = new SDKVersionMiddleware(VERSION);
  app.use(sdkVersion.handler());

  if (opts.dependencies) {
    for (const dep of opts.dependencies) {
      app.use(dep);
    }
  }

  const router = express.Router();

  /** POST /execute — Runs the node with the provided inputs. Validates request, enforces timeout, uploads file outputs if output_upload_url is provided. */
  router.post("/execute", async (req: Request, res: Response, next: NextFunction) => {
    let body: unknown;
    try {
      body = req.body;
    } catch {
      res.status(400).json({ detail: "Invalid JSON body" });
      return;
    }

    const parsed = NodeExecutionRequestSchema.safeParse(body);
    if (!parsed.success) {
      res.status(400).json({ detail: "Invalid request body", errors: parsed.error.issues });
      return;
    }
    const execRequest = parsed.data;

    const def = node.nodeDefinition;
    const timeout = def.timeout_seconds;

    try {
      let response;
      if (timeout && timeout > 0) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeout * 1000);
        try {
          // Thread the abort signal into the node so in-flight file
          // downloads stop cooperatively when the deadline expires.
          node.setCancelSignal(controller.signal);
          response = await Promise.race([
            node.run(execRequest),
            new Promise<never>((_, reject) =>
              controller.signal.addEventListener("abort", () =>
                reject(new NodeTimeoutError(timeout)),
              ),
            ),
          ]);
        } finally {
          clearTimeout(timer);
          node.setCancelSignal(null);
        }
      } else {
        response = await node.run(execRequest);
      }

      if (execRequest.output_upload_url && response.status === "pass") {
        const fileOutputFields = getFileOutputFields(def);
        if (fileOutputFields.length > 0) {
          try {
            // The parse union still admits legacy string targets (request.ts);
            // uploadFile rejects them at runtime with NodeIOError (DA-3340),
            // so the cast only re-widens the type for this call — a string
            // value surfaces as UPLOAD_FAILED below, never a silent fallback.
            await getDefaultUploader().uploadOutputs(
              response,
              execRequest.output_upload_url as Record<string, UploadTarget>,
              fileOutputFields,
            );
          } catch (err) {
            // A declared file output that could not be uploaded means the
            // engine would receive a local path it cannot fetch — fail the
            // execution instead of silently passing (DA-1711 4.1).
            console.error("[canvastekk] Output upload failed:", err);
            response = {
              ...response,
              status: "fail",
              error: `Output upload failed: ${err}`,
              error_code: "UPLOAD_FAILED",
            };
          }
        }
      }

      res.json(response);
    } catch (err) {
      next(err);
    }
  });

  /** GET /health — Returns node health status. Aggregates healthCheck() results into healthy/degraded/unhealthy status. */
  router.get("/health", (_req: Request, res: Response, next: NextFunction) => {
    try {
      const checks = node.healthCheck();
      let status: "healthy" | "unhealthy" | "degraded";

      if (Object.keys(checks).length === 0) {
        status = "healthy";
      } else if (Object.values(checks).every(Boolean)) {
        status = "healthy";
      } else if (Object.values(checks).some(Boolean)) {
        status = "degraded";
      } else {
        status = "unhealthy";
      }

      const def = node.nodeDefinition;
      const resp = HealthResponseSchema.parse({
        status,
        node_id: getNodeId(def),
        version: def.version,
        checks,
      });
      res.json(resp);
    } catch (err) {
      next(err);
    }
  });

  /** GET /manifest — Returns the node definition with auto-injected sdk_version and mode fields. */
  router.get("/manifest", (_req: Request, res: Response, next: NextFunction) => {
    try {
      const def = node.nodeDefinition;
      const content: Record<string, unknown> = { ...def };
      content.id = getNodeId(def);
      content.sdk_version = VERSION;
      if (codeDigest !== null) content.code_digest = codeDigest;

      // DA-1955: parity with python drop-when-none serialization — omit null
      // optional keys instead of leaking them as explicit nulls.
      for (const key of [
        "deprecation",
        "minimum_sdk_version",
        "maximum_sdk_version",
        "docs_url",
        "changelog_url",
      ] as const) {
        if (content[key] === null) {
          delete content[key];
        }
      }

      const rawEnv = (process.env.CANVASTEKK_NODE_ENV ?? "dev").toLowerCase();
      let mode: string;
      if (["dev", "development", "test"].includes(rawEnv)) {
        mode = "dev";
      } else if (["uat", "staging"].includes(rawEnv)) {
        mode = "uat";
      } else {
        mode = "production";
      }
      content.mode = mode;

      res.json(content);
    } catch (err) {
      next(err);
    }
  });

  /** POST /hook — Handles lifecycle hook payloads. Returns 501 if the node does not implement hooks. */
  router.post("/hook", async (req: Request, res: Response, next: NextFunction) => {
    try {
      const result = node.hook(req.body as Record<string, unknown>);
      if (result === null) {
        res.status(501).json({ detail: "Hook not implemented for this node" });
        return;
      }
      res.json(result);
    } catch (err) {
      next(err);
    }
  });

  /** GET /metrics — Returns execution metrics summary (total runs, pass/fail counts, durations). */
  router.get("/metrics", (_req: Request, res: Response) => {
    res.json(node.metricsCollector.getSummary());
  });

  /** GET /live — Kubernetes liveness probe. Returns 200 if the process is alive. */
  router.get("/live", (_req: Request, res: Response) => {
    res.json({ status: "alive" });
  });

  /** GET /ready — Kubernetes readiness probe. Returns 200 if healthy, 503 if not ready. */
  router.get("/ready", (_req: Request, res: Response, next: NextFunction) => {
    try {
      const checks = node.healthCheck();
      const def = node.nodeDefinition;
      if (Object.keys(checks).length === 0 || Object.values(checks).every(Boolean)) {
        res.json({ status: "ready", node_id: getNodeId(def), checks });
      } else {
        res.status(503).json({ status: "not_ready", node_id: getNodeId(def), checks });
      }
    } catch (err) {
      next(err);
    }
  });

  app.use(router);

  if (opts.extraRoutes) {
    for (const extraRouter of opts.extraRoutes) {
      app.use(extraRouter);
    }
  }

  app.use((err: Error, _req: Request, res: Response, _next: NextFunction) => {
    if (err instanceof NodeExecutionError) {
      const status = getHttpStatusForError(err);
      res.status(status).json({
        detail: err.message,
        error_type: err.constructor.name,
        error_code: err.errorCode,
        ...err.details,
      });
      return;
    }
    // Unexpected exceptions: log full detail server-side; the client gets a
    // generic message (no internals/paths/URLs leak to callers).
    console.error("[canvastekk] Unhandled exception:", err);
    res.status(500).json({
      detail: "Internal server error",
      error_type: err.constructor?.name ?? "Error",
    });
  });

  node.onStartup().catch(console.error);

  const originalListen = app.listen.bind(app);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (app as any).listen = function (this: express.Application, ...args: any[]) {
    const server = originalListen(...args);
    server.on("close", () => {
      node.onShutdown().catch(console.error);
    });
    return server;
  };

  return app;
}

/**
 * Creates an Express application hosting multiple nodes under URL prefixes.
 *
 * Each key in `nodes` becomes a URL prefix with its own set of node endpoints.
 * For example, `{ "segment": nodeA }` creates `POST /segment/execute`, etc.
 *
 * @param nodes - Mapping of URL prefix to BaseNode instance
 * @param opts - Optional configuration for dependencies and extra routes
 * @returns Configured Express application with all node endpoints mounted
 */
export function createMultiNodeApp(
  nodes: Record<string, BaseNode>,
  opts: CreateNodeAppOptions = {},
): express.Application {
  const app = express();
  app.use(express.json({ limit: "50mb" }));

  const sdkVersion = new SDKVersionMiddleware(VERSION);
  app.use(sdkVersion.handler());

  for (const [prefix, node] of Object.entries(nodes)) {
    const nodeApp = createNodeApp(node, {
      dependencies: opts.dependencies,
    });
    app.use(`/${prefix}`, nodeApp);
  }

  app.get("/health", (_req: Request, res: Response) => {
    res.json({ status: "healthy", nodes: Object.keys(nodes) });
  });

  return app;
}
