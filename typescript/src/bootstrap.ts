/**
 * Canonical node-service bootstrap (sdk#220) — TypeScript parity.
 *
 * Mirrors `python/canvastekk_workflow_sdk/bootstrap.py`:
 * - `createAuthedWorkflowNodeApp` — `createWorkflowNodeApp` + `TekkNodeAuth.central()` (central-only
 *   by default; `legacyKeyEnvVar` keeps a dual-accept window alive).
 * - `mountWorkflowNode` — dual-purpose services: your routes stay on the root
 *   express app; the authed node sub-app mounts under a prefix.
 *
 * `createLambdaHandler` is deliberately python-only — see the parity
 * exception in `docs/NODE-SERVICE-LAYOUT.md`.
 */

import type { Application } from "express";
import { createWorkflowNodeApp, type CreateNodeAppOptions } from "./workflow-node-app.js";
import { TekkNodeAuth } from "./auth.js";
import type { WorkflowNodeBase } from "./workflow-node-base.js";

export interface AuthedWorkflowNodeAppOptions extends CreateNodeAppOptions {
  /** Env var holding the legacy static key during a dual-accept window. `null` (default) = central-only. */
  legacyKeyEnvVar?: string | null;
}

/**
 * Creates a node app with central token auth on all node endpoints.
 *
 * @throws If `extraRoutes` is passed — the SDK mounts them without the auth
 *   middleware, so auth would not cover them.
 */
export function createAuthedWorkflowNodeApp(node: WorkflowNodeBase, opts: AuthedWorkflowNodeAppOptions = {}): Application {
  const { legacyKeyEnvVar = null, ...rest } = opts;
  if (rest.extraRoutes && rest.extraRoutes.length > 0) {
    throw new Error(
      "createAuthedWorkflowNodeApp does not support extraRoutes — SDK mounts them without the auth middleware",
    );
  }
  // Auth is APPENDED to caller-supplied dependencies (python create_node_app semantics) —
  // never a spread-overwrite, which would silently drop caller middleware.
  return createWorkflowNodeApp(node, {
    ...rest,
    dependencies: [TekkNodeAuth.central({ legacyKeyEnvVar }), ...(rest.dependencies ?? [])],
  });
}

export interface MountWorkflowNodeOptions extends AuthedWorkflowNodeAppOptions {
  /** Mount path for the node sub-app (default "/node"). */
  prefix?: string;
}

/**
 * Mounts an authed node sub-app onto an existing (dual-purpose) express app.
 *
 * Root-app routes keep their own middleware; the node contract serves under
 * `prefix` behind central auth.
 *
 * @returns `rootApp` for chaining.
 */
export function mountWorkflowNode(rootApp: Application, node: WorkflowNodeBase, opts: MountWorkflowNodeOptions = {}): Application {
  const { prefix = "/node", ...rest } = opts;
  rootApp.use(prefix, createAuthedWorkflowNodeApp(node, rest));
  return rootApp;
}

// Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
/** @deprecated use mountWorkflowNode (ADR 0001, #271; removal in 1.0.0, #272) */
export const mountNode: typeof mountWorkflowNode = mountWorkflowNode;
/** @deprecated use createAuthedWorkflowNodeApp (ADR 0001, #271; removal in 1.0.0, #272) */
export const createAuthedApp: typeof createAuthedWorkflowNodeApp = createAuthedWorkflowNodeApp;
