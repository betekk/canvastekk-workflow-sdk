/**
 * Express adapter — optional peer dependency.
 *
 * Import server construction from this subpath; the core entry
 * (`@betekk/canvastekk-workflow-sdk`) stays express-free:
 *
 * ```ts
 * import { createNodeApp } from "@betekk/canvastekk-workflow-sdk/express";
 * ```
 *
 * Install express yourself (`npm install express`) — it is an optional peer.
 */
export { createNodeApp, createMultiNodeApp } from "./app.js";
export type { CreateNodeAppOptions } from "./app.js";
