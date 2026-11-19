import type { NodeExecutionContext } from "../node-execution-context.js";

/**
 * Handler function for control flow nodes (START, END).
 *
 * Receives raw inputs and context, returns outputs to pass downstream.
 * Control flow nodes do not perform computation — they route data.
 *
 * @param inputs - Node input values
 * @param context - Execution context
 * @returns Node outputs
 */
type ControlFlowHandler = (inputs: Record<string, unknown>, context: NodeExecutionContext) => Record<string, unknown>;

/**
 * Built-in control flow handlers for special node slugs.
 *
 * - `__start__` — Passes inputs through unchanged (entry point)
 * - `__end__` — Passes inputs through unchanged (terminal point)
 *
 * To add custom control flow, extend this record before building the workflow.
 */
export const CONTROL_FLOW_HANDLERS: Record<string, ControlFlowHandler> = {
  __start__: (inputs) => ({ ...inputs }),
  __end__: (inputs) => ({ ...inputs }),
};