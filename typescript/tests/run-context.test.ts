import { describe, it, expect } from "vitest";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { NodeExecutionContext } from "../src/node-execution-context.js";
import { NodeExecutionRequestSchema } from "../src/node-execution-request.js";
import { RunContextSchema } from "../src/run-context.js";
import { writeResultFile } from "../src/result-file.js";

const V1_SAMPLE = {
  run_context_version: "1.0.0",
  workflow_run_id: "3f2b8a2e-1111-4222-8333-444455556666",
  workflow_definition_id: "def-uuid-1",
  workflow_definition_slug: "model-checker",
  workflow_definition_version: "1.4.0",
  account_id: 42,
  started_at: "2026-11-21T12:00:00+00:00",
};

describe("RunContextSchema", () => {
  it("parses the v1 sample", () => {
    const ctx = RunContextSchema.parse(V1_SAMPLE);
    expect(ctx.workflow_run_id).toBe(V1_SAMPLE.workflow_run_id);
    expect(ctx.workflow_definition_slug).toBe("model-checker");
    expect(ctx.account_id).toBe(42);
  });

  it("rejects a missing workflow_run_id", () => {
    expect(() => RunContextSchema.parse({ run_context_version: "1.0.0" })).toThrow();
  });

  it("optional fields may be absent", () => {
    const ctx = RunContextSchema.parse({
      run_context_version: "1.0.0",
      workflow_run_id: "r-1",
    });
    expect(ctx.workflow_definition_id).toBeUndefined();
    expect(ctx.started_at).toBeUndefined();
  });
});

describe("request + context", () => {
  it("populates runContext from a request carrying run_context", () => {
    const request = NodeExecutionRequestSchema.parse({
      run_id: "r-1",
      node_id: "n-1",
      run_context: V1_SAMPLE,
    });
    const ctx = new NodeExecutionContext({ request });
    expect(ctx.runContext?.workflow_run_id).toBe(V1_SAMPLE.workflow_run_id);
  });

  it("leaves runContext null without run_context", () => {
    const request = NodeExecutionRequestSchema.parse({ run_id: "r-1", node_id: "n-1" });
    const ctx = new NodeExecutionContext({ request });
    expect(ctx.runContext).toBeNull();
  });

  it("local contexts have no runContext", () => {
    const ctx = new NodeExecutionContext({ outputDir: "/tmp/r-1/n-1" });
    expect(ctx.runContext).toBeNull();
  });
});

describe("result-file header id", () => {
  const root = mkdtempSync(join(tmpdir(), "runctx-"));

  function write(ctx: NodeExecutionContext) {
    const out = writeResultFile(ctx, {
      resultSchema: "model_check.rule",
      resultSchemaVersion: "0.1.0",
      body: { ok: true },
    });
    return JSON.parse(readFileSync(out.result_file, "utf8")) as { workflow_run_id: string };
  }

  it("prefers run_context.workflow_run_id", () => {
    const request = NodeExecutionRequestSchema.parse({
      run_id: "wire-run-id",
      node_id: "n-1",
      run_context: V1_SAMPLE,
    });
    const ctx = new NodeExecutionContext({ request });
    expect(write(ctx).workflow_run_id).toBe(V1_SAMPLE.workflow_run_id);
  });

  it("falls back to runId without run_context", () => {
    const ctx = new NodeExecutionContext({ outputDir: join(root, "wire-run-id", "n-1") });
    expect(write(ctx).workflow_run_id).toBe("wire-run-id");
  });
});
