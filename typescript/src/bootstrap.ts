/**
 * Canonical node-service bootstrap (sdk#220) — TypeScript parity.
 *
 * Mirrors `python/canvastekk_workflow_sdk/bootstrap.py`:
 * - `createAuthedApp` — `createNodeApp` + `NodeAuth.central()` (central-only
 *   by default; `legacyKeyEnvVar` keeps a dual-accept window alive).
 * - `mountNode` — dual-purpose services: your routes stay on the root
 *   express app; the authed node sub-app mounts under a prefix.
 *
 * `createLambdaHandler` is deliberately python-only — see the parity
 * exception in `docs/NODE-SERVICE-LAYOUT.md`.
 */

import type { Application } from "express";
import { createNodeApp, type CreateNodeAppOptions } from "./app.js";
import { NodeAuth } from "./auth.js";
import type { BaseNode } from "./base-node.js";

export interface AuthedAppOptions extends CreateNodeAppOptions {
  /** Env var holding the legacy static key during a dual-accept window. `null` (default) = central-only. */
  legacyKeyEnvVar?: string | null;
}

/**
 * Creates a node app with central token auth on all node endpoints.
 *
 * @throws If `extraRoutes` is passed — the SDK mounts them without the auth
 *   middleware, so auth would not cover them.
 */
export function createAuthedApp(node: BaseNode, opts: AuthedAppOptions = {}): Application {
  const { legacyKeyEnvVar = null, ...rest } = opts;
  if (rest.extraRoutes && rest.extraRoutes.length > 0) {
    throw new Error(
      "createAuthedApp does not support extraRoutes — SDK mounts them without the auth middleware",
    );
  }
  // Auth is APPENDED to caller-supplied dependencies (python create_node_app semantics) —
  // never a spread-overwrite, which would silently drop caller middleware.
  return createNodeApp(node, {
    ...rest,
    dependencies: [NodeAuth.central({ legacyKeyEnvVar }), ...(rest.dependencies ?? [])],
  });
}

export interface MountNodeOptions extends AuthedAppOptions {
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
export function mountNode(rootApp: Application, node: BaseNode, opts: MountNodeOptions = {}): Application {
  const { prefix = "/node", ...rest } = opts;
  rootApp.use(prefix, createAuthedApp(node, rest));
  return rootApp;
}
