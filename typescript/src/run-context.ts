import { z } from "zod";

/**
 * Versioned run identity the workflow engine (CWE) sends with every
 * `/execute` call once canvastekk-workflow-engine#1443 is live (#281,
 * epic betekk/canvastekk-tracker#4320).
 *
 * Built by CWE at run creation and stamped with `started_at` by the
 * executor. Additive keys bump `run_context_version`'s minor — consumers
 * must ignore unknown keys (zod strips them here).
 *
 * Wire fields are snake_case, matching {@link NodeExecutionRequestSchema}.
 */
export const RunContextSchema = z.object({
  run_context_version: z.string().describe("Semver of the run_context shape (v1: '1.0.0')."),
  workflow_run_id: z
    .string()
    .describe("The workflow run id — one id per run, also the Temporal workflow id since CWE #1440."),
  workflow_definition_id: z.string().optional().describe("Definition id the run executes."),
  workflow_definition_slug: z.string().optional().describe("Registered definition slug."),
  workflow_definition_version: z.string().optional().describe("Semver of the definition."),
  account_id: z.number().int().min(1).optional().describe("Account the run is attributed to."),
  started_at: z
    .string()
    .optional()
    .describe("ISO 8601 instant the executor started the run (workflow.now()) — not the create time."),
});

/** Parsed run context (wire snake_case). */
export type RunContext = z.infer<typeof RunContextSchema>;
