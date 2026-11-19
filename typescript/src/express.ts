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
/** @deprecated use createWorkflowNodeApp (ADR 0001, #271) */
export { createWorkflowNodeApp as createNodeApp } from "./workflow-node-app.js";
/** @deprecated use createMultiWorkflowNodeApp (ADR 0001, #271) */
export { createMultiWorkflowNodeApp as createMultiNodeApp } from "./workflow-node-app.js";
export type { CreateNodeAppOptions } from "./workflow-node-app.js";
export { createAuthedWorkflowNodeApp, mountWorkflowNode } from "./bootstrap.js";
/** @deprecated use mountWorkflowNode (ADR 0001, #271) */
export { mountNode } from "./bootstrap.js";
/** @deprecated use createAuthedWorkflowNodeApp (ADR 0001, #271) */
export { createAuthedApp } from "./bootstrap.js";
export type { AuthedWorkflowNodeAppOptions, MountWorkflowNodeOptions } from "./bootstrap.js";
