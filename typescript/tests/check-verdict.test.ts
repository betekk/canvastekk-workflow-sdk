import { describe, it, expect } from "vitest";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import AjvModule from "ajv";
import { NodeExecutionContext } from "../src/node-execution-context.js";
import { NodeExecutionRequestSchema } from "../src/node-execution-request.js";
import { WorkflowNodeManifestSchema } from "../src/workflow-node-manifest.js";
import { buildWorkflowNodeRegistryPayload } from "../src/workflow-node-registry.js";
import {
  CHECK_RESULT_SCHEMA_VERSION,
  CHECK_RESULT_SCHEMA_VERSION_2_0_0,
  CHECK_RESULT_SCHEMA_VERSION_2_2_0,
  CheckSpecSchema,
  MODEL_CHECK_CHECK_BODY_SCHEMA_1_0_0,
  MODEL_CHECK_CHECK_BODY_SCHEMA_2_0_0,
  MODEL_CHECK_CHECK_BODY_SCHEMA_2_1_0,
  MODEL_CHECK_CHECK_BODY_SCHEMA_2_2_0,
  VERDICT_PRECEDENCE,
  rollupVerdicts,
} from "../src/check-verdict.js";
import {
  RESULT_FILE_HEADER_KEYS_BY_VERSION,
  RESULT_FILE_SCHEMA_1_1_0,
  ResultFileFormatError,
  buildResultFileHeader,
  serializeResultFileHeaderPrefix,
  validateResultFileHeader,
  writeResultFile,
} from "../src/result-file.js";
import * as sdk from "../src/index.js";

const Ajv = AjvModule.default ?? AjvModule;
const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CANONICAL = join(REPO, "schemas", "result-file");
const BODY = join(REPO, "schemas", "result-body", "model_check.check", "1.0.0.json");

const RUN_CONTEXT = {
  run_context_version: "1.0.0",
  workflow_run_id: "3b2cfd18-0000-4000-8000-000000000001",
  workflow_definition_id: "model-checker-beam-length-v1.0.0",
  workflow_definition_slug: "model-checker-beam-length",
  workflow_definition_version: "1.0.0",
};

function contextWithRun(withRunContext = true): NodeExecutionContext {
  const request = NodeExecutionRequestSchema.parse({
    run_id: RUN_CONTEXT.workflow_run_id,
    node_id: "check-1",
    ...(withRunContext ? { run_context: RUN_CONTEXT } : {}),
  });
  return new NodeExecutionContext({ request, outputDir: mkdtempSync(join(tmpdir(), "cv-")) });
}

describe("embedded schemas (#283)", () => {
  it("equal the canonical files", () => {
    expect(RESULT_FILE_SCHEMA_1_1_0).toEqual(JSON.parse(readFileSync(join(CANONICAL, "1.1.0.json"), "utf8")));
    expect(MODEL_CHECK_CHECK_BODY_SCHEMA_1_0_0).toEqual(JSON.parse(readFileSync(BODY, "utf8")));
  });

  it("are exported from the package root", () => {
    expect(sdk.RESULT_FILE_SCHEMA_1_1_0).toBe(RESULT_FILE_SCHEMA_1_1_0);
    expect(sdk.MODEL_CHECK_CHECK_BODY_SCHEMA_1_0_0).toBe(MODEL_CHECK_CHECK_BODY_SCHEMA_1_0_0);
    expect(sdk.MODEL_CHECK_CHECK_BODY_SCHEMA_2_0_0).toBe(MODEL_CHECK_CHECK_BODY_SCHEMA_2_0_0);
    expect(sdk.MODEL_CHECK_CHECK_BODY_SCHEMA_2_1_0).toBe(MODEL_CHECK_CHECK_BODY_SCHEMA_2_1_0);
    expect(sdk.MODEL_CHECK_CHECK_BODY_SCHEMA_2_2_0).toBe(MODEL_CHECK_CHECK_BODY_SCHEMA_2_2_0);
    expect(sdk.CHECK_RESULT_SCHEMA_VERSION_2_2_0).toBe(CHECK_RESULT_SCHEMA_VERSION_2_2_0);
    expect(sdk.VERDICT_MARK).toBe("x-verdict");
    expect(sdk.TekkWorkflowRunVerdictEnum.NOT_EVALUABLE).toBe("NOT_EVALUABLE");
  });
});

describe("nested check result body", () => {
  const folder = dirname(BODY);
  const body = JSON.parse(readFileSync(join(folder, "examples", "nested-2.0.0.json"), "utf8"));
  const validate = new Ajv().compile(MODEL_CHECK_CHECK_BODY_SCHEMA_2_0_0);

  it("validates the same contract as Python and keeps the version-one write default", () => {
    expect(MODEL_CHECK_CHECK_BODY_SCHEMA_2_0_0).toEqual(JSON.parse(readFileSync(join(folder, "2.0.0.json"), "utf8")));
    expect(CHECK_RESULT_SCHEMA_VERSION_2_0_0).toBe("2.0.0");
    expect(CHECK_RESULT_SCHEMA_VERSION).toBe("1.0.0");
    expect(validate(body)).toBe(true);
  });

  it.each([
    ["a missing verdict", { verdict: undefined }],
    ["a legacy row check", { check: "another_check" }],
    ["unverified original file", { element_id_source_file: 42 }],
    ["an identity without a type", { element_id: "2h7VCQmP56uPcWBc9vN$1A" }],
  ])("rejects a finding with %s", (_label, patch) => {
    const first = body.checks[0];
    const row = { ...first.measurements[0], ...patch };
    expect(validate({ checks: [{ ...first, measurements: [row] }] })).toBe(false);
  });

  it("rejects flat measurements in the new body", () => {
    expect(validate({ ...body, measurements: [] })).toBe(false);
  });

  it("validates the additive drawing contract in both SDKs", () => {
    const schema = JSON.parse(readFileSync(join(folder, "2.1.0.json"), "utf8"));
    const example = JSON.parse(readFileSync(join(folder, "examples", "nested-2.1.0.json"), "utf8"));
    expect(MODEL_CHECK_CHECK_BODY_SCHEMA_2_1_0).toEqual(schema);
    const validateVisuals = new Ajv().compile(MODEL_CHECK_CHECK_BODY_SCHEMA_2_1_0);
    expect(validateVisuals(body)).toBe(true);
    expect(validateVisuals(example)).toBe(true);
    example.report_visuals["basin-1-plan"].crop_xy_mm = [0, 1];
    expect(validateVisuals(example)).toBe(false);
  });

  it("validates layout plans and spatial observations without breaking 2.1.0 content", () => {
    const schema = JSON.parse(readFileSync(join(folder, "2.2.0.json"), "utf8"));
    const previous = JSON.parse(readFileSync(join(folder, "examples", "nested-2.1.0.json"), "utf8"));
    const example = JSON.parse(readFileSync(join(folder, "examples", "nested-2.2.0.json"), "utf8"));
    expect(CHECK_RESULT_SCHEMA_VERSION_2_2_0).toBe("2.2.0");
    expect(MODEL_CHECK_CHECK_BODY_SCHEMA_2_2_0).toEqual(schema);
    const validateBody = new Ajv().compile(MODEL_CHECK_CHECK_BODY_SCHEMA_2_2_0);
    expect(validateBody(previous)).toBe(true);
    expect(validateBody(example)).toBe(true);

    const unknownKind = structuredClone(example);
    unknownKind.report_visuals["level-1-layout"].kind = "future_drawing";
    expect(validateBody(unknownKind)).toBe(false);

    const unknownMeasurementKey = structuredClone(example);
    unknownMeasurementKey.checks[0].measurements[0].level_id = "S1";
    expect(validateBody(unknownMeasurementKey)).toBe(false);

    const unknownLayoutKey = structuredClone(example);
    unknownLayoutKey.report_visuals["level-1-layout"].level_id = "S1";
    expect(validateBody(unknownLayoutKey)).toBe(false);
  });

  it("preserves optional subcheck descriptions", () => {
    expect(CheckSpecSchema.parse({ label: "Width" })).not.toHaveProperty("description");
    expect(CheckSpecSchema.parse({ label: "Width", description: "The opening's clear width." }).description)
      .toBe("The opening's clear width.");
    expect(CheckSpecSchema.safeParse({ label: "Width", description: "" }).success).toBe(false);
  });
});

describe("rollupVerdicts", () => {
  it("uses FAIL > NOT_EVALUABLE > WARNING > PASS", () => {
    expect(VERDICT_PRECEDENCE).toEqual(["FAIL", "NOT_EVALUABLE", "WARNING", "PASS"]);
    expect(rollupVerdicts(["PASS", "NOT_EVALUABLE"])).toBe("NOT_EVALUABLE");
    expect(rollupVerdicts(["WARNING", "PASS"])).toBe("WARNING");
    expect(rollupVerdicts(["NOT_EVALUABLE", "FAIL"])).toBe("FAIL");
    expect(rollupVerdicts([])).toBe("NOT_EVALUABLE");
    expect(() => rollupVerdicts(["MAYBE"])).toThrow();
  });
});

describe("layout 1.1.0", () => {
  it("adds three keys to 1.0.0 without reordering it", () => {
    const old = RESULT_FILE_HEADER_KEYS_BY_VERSION["1.0.0"];
    const next = RESULT_FILE_HEADER_KEYS_BY_VERSION["1.1.0"];
    expect(next.filter((k) => !old.includes(k))).toEqual(["workflow_definition", "inputs", "verdict"]);
    expect(next.filter((k) => old.includes(k))).toEqual([...old]);
  });

  it("stamps workflow_definition from the run context", () => {
    const out = writeResultFile(contextWithRun(), {
      resultSchema: "model_check.check",
      resultSchemaVersion: "1.0.0",
      body: { checks: [], measurements: [] },
      resultFileVersion: "1.1.0",
      inputs: { threshold_mm: 1000 },
      verdict: "PASS",
    });
    const doc = JSON.parse(readFileSync(out.result_file, "utf8"));
    expect(doc.workflow_definition).toEqual({
      id: RUN_CONTEXT.workflow_definition_id,
      slug: RUN_CONTEXT.workflow_definition_slug,
      version: RUN_CONTEXT.workflow_definition_version,
    });
    expect(doc.verdict).toBe("PASS");
  });

  it("omits workflow_definition without a run context", () => {
    const out = writeResultFile(contextWithRun(false), {
      resultSchema: "model_check.check",
      resultSchemaVersion: "1.0.0",
      body: {},
      resultFileVersion: "1.1.0",
    });
    expect(JSON.parse(readFileSync(out.result_file, "utf8"))).not.toHaveProperty("workflow_definition");
  });

  const bad: [string, Record<string, unknown>][] = [
    ["a 1.1.0 key on layout 1.0.0", { verdict: "PASS" }],
    ["an unknown verdict", { resultFileVersion: "1.1.0", verdict: "MAYBE" }],
    ["inputs over 16 KB", { resultFileVersion: "1.1.0", inputs: { big: "x".repeat(17000) } }],
    ["an incomplete workflow_definition", { resultFileVersion: "1.1.0", workflowDefinition: { id: "a", slug: "b" } }],
    ["an unknown layout", { resultFileVersion: "9.9.9" }],
  ];
  for (const [name, extra] of bad) {
    it(`rejects ${name}`, () => {
      expect(() =>
        buildResultFileHeader(
          { resultSchema: "model_check.check", resultSchemaVersion: "1.0.0", ...(extra as object) },
          "r",
        ),
      ).toThrow(ResultFileFormatError);
    });
  }

  it("validates a header the Python reader accepts", () => {
    const header = buildResultFileHeader(
      { resultSchema: "a.b", resultSchemaVersion: "1.0.0", resultFileVersion: "1.1.0", verdict: "FAIL" },
      "r",
    );
    expect(validateResultFileHeader(header).verdict).toBe("FAIL");
    expect(serializeResultFileHeaderPrefix(header)).toMatch(/"generated_at":"[^"]+","verdict":"FAIL","body":$/);
  });
});

describe("golden parity with the Python writer (1.1.0)", () => {
  it("reproduces schemas/result-file/golden/expected-1.1.0.json byte for byte", () => {
    const input = JSON.parse(readFileSync(join(CANONICAL, "golden", "input-1.1.0.json"), "utf8"));
    const root = mkdtempSync(join(tmpdir(), "rf-golden-11-"));
    const goldenCtx = new NodeExecutionContext({ outputDir: join(root, input.workflow_run_id, "n") });
    const out = writeResultFile(goldenCtx, {
      resultSchema: input.result_schema,
      resultSchemaVersion: input.result_schema_version,
      summary: input.summary,
      body: input.body,
      generatedAt: new Date(input.generated_at),
      resultFileVersion: input.result_file_version,
      workflowDefinition: input.workflow_definition,
      inputs: input.inputs,
      verdict: input.verdict,
    });
    const expected = readFileSync(join(CANONICAL, "golden", "expected-1.1.0.json")).toString("utf8").replace(/\n$/, "");
    expect(readFileSync(out.result_file).toString("utf8")).toBe(expected);
    const doc = JSON.parse(expected);
    const ajv = new Ajv({ allErrors: true, strict: false });
    expect(ajv.validate({ ...RESULT_FILE_SCHEMA_1_1_0, $id: undefined }, doc)).toBe(true);
    expect(ajv.validate({ ...MODEL_CHECK_CHECK_BODY_SCHEMA_1_0_0, $id: undefined }, doc.body)).toBe(true);
  });
});

describe("manifest checks map", () => {
  const base = {
    slug: "ifc-beam-length",
    version: "1.0.0",
    name: "Beam length",
    description: "d",
    input_schema: { type: "object" },
    output_schema: { type: "object" },
  };

  it("keeps a declared checks map and registers it", () => {
    const manifest = WorkflowNodeManifestSchema.parse({
      ...base,
      checks: { beam_length: { label: "Beam length", unit: "mm", resolution: { step: 1 } } },
    });
    expect(manifest.checks?.beam_length.unit).toBe("mm");
    expect(buildWorkflowNodeRegistryPayload(manifest).checks).toEqual(manifest.checks);
  });

  it("leaves manifests without checks unchanged", () => {
    const manifest = WorkflowNodeManifestSchema.parse(base);
    expect(manifest.checks).toBeNull();
    expect(buildWorkflowNodeRegistryPayload(manifest)).not.toHaveProperty("checks");
  });

  it("rejects an unknown key in a check entry", () => {
    expect(() => WorkflowNodeManifestSchema.parse({ ...base, checks: { a: { label: "A", colour: "red" } } })).toThrow();
  });
});
