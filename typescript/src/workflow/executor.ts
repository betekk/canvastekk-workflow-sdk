/**
 * Deprecated alias module — renamed to ./node-executor.js (ADR 0001, #271).
 * Every old module path keeps working; removed in 1.0.0 (#272).
 *
 * @deprecated import from "./node-executor.js" instead
 */
export * from "./node-executor.js";
/** @deprecated use WorkflowRunNodeExecutor */
export { WorkflowRunNodeExecutor as NodeExecutor } from "./node-executor.js";
/** @deprecated use InProcessNodeExecutor */
export { InProcessNodeExecutor as InProcessExecutor } from "./node-executor.js";
/** @deprecated use HttpNodeExecutor */
export { HttpNodeExecutor as HttpExecutor } from "./node-executor.js";
