/**
 * Express adapter — optional peer dependency.
 *
 * Import server construction from this subpath; the core entry
 * (`@betekk/canvastekk-workflow-sdk`) stays express-free:
 *
 * ```ts
 * import { createWorkflowNodeApp } from "@betekk/canvastekk-workflow-sdk/express";
 * ```
 *
 * Install express yourself (`npm install express`) — it is an optional peer.
 */
export { createWorkflowNodeApp, createMultiWorkflowNodeApp } from "./workflow-node-app.js";
export type { CreateNodeAppOptions } from "./workflow-node-app.js";
export { createAuthedApp, mountNode } from "./bootstrap.js";
export type { AuthedAppOptions, MountNodeOptions } from "./bootstrap.js";
