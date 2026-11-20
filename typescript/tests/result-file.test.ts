import { describe, it, expect, beforeEach } from "vitest";
import { mkdtempSync, readdirSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import AjvModule from "ajv";
import { NodeExecutionContext } from "../src/node-execution-context.js";
import { NodeOutputValidationError } from "../src/exceptions.js";
import { WorkflowNodeManifestSchema } from "../src/workflow-node-manifest.js";
import {
  RESULT_FILE_END_VALUE_SCHEMA_1_0_0,
  RESULT_FILE_HEADER_KEYS,
  RESULT_FILE_OUTPUT_FIELD,
  RESULT_FILE_SCHEMA_1_0_0,
  ResultFileFormatError,
  buildResultFileHeader,
  resultFileOutputSchema,
  validateResultFileHeader,
  writeResultFile,
  type WriteResultFileOptions,
} from "../src/result-file.js";
import * as sdk from "../src/index.js";

const Ajv = AjvModule.default ?? AjvModule;
const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CANONICAL = join(REPO, "schemas", "result-file");
const FIXED = new Date("2026-11-20T10:00:00.123Z");

let ctx: NodeExecutionContext;

beforeEach(() => {
  const root = mkdtempSync(join(tmpdir(), "rf-"));
  ctx = new NodeExecutionContext({ outputDir: join(root, "run-abc", "check-1") });
});

function write(extra: Partial<WriteResultFileOptions> = {}) {
  return writeResultFile(ctx, {
    resultSchema: "model_check.rule",
    resultSchemaVersion: "0.1.0",
    body: { ok: true },
    ...extra,
  });
}

describe("result file schemas", () => {
  it("embedded schemas equal the canonical files", () => {
    expect(RESULT_FILE_SCHEMA_1_0_0).toEqual(JSON.parse(readFileSync(join(CANONICAL, "1.0.0.json"), "utf8")));
    expect(RESULT_FILE_END_VALUE_SCHEMA_1_0_0).toEqual(
      JSON.parse(readFileSync(join(CANONICAL, "end-value-1.0.0.json"), "utf8")),
    );
  });

  it("are exported from the package root", () => {
    expect(sdk.writeResultFile).toBe(writeResultFile);
    expect(sdk.RESULT_FILE_VERSION).toBe("1.0.0");
  });
});

describe("writeResultFile", () => {
  it("returns the result_file output and a valid document", () => {
    const out = write({ summary: { verdict: "FAIL", fail_count: 14 }, generatedAt: FIXED });
    expect(Object.keys(out)).toEqual([RESULT_FILE_OUTPUT_FIELD]);
    expect(basename(out.result_file)).toBe("result.json");
    const doc = JSON.parse(readFileSync(out.result_file, "utf8"));
    const ajv = new Ajv({ strict: false });
    const schema = { ...RESULT_FILE_SCHEMA_1_0_0 };
    delete (schema as Record<string, unknown>).$id;
    expect(ajv.validate(schema, doc)).toBe(true);
    expect(doc.workflow_run_id).toBe("run-abc");
    expect(doc.generated_at).toBe("2026-11-20T10:00:00.123Z");
  });

  it("writes header keys before body", () => {
    const out = write({ summary: { verdict: "PASS" }, generatedAt: FIXED });
    const text = readFileSync(out.result_file, "utf8");
    const positions = RESULT_FILE_HEADER_KEYS.map((key) => text.indexOf(`"${key}":`));
    expect(positions).toEqual([...positions].sort((a, b) => a - b));
    expect(positions.at(-1)!).toBeLessThan(text.indexOf('"body":'));
  });

  const bad: Record<string, Partial<WriteResultFileOptions>> = {
    "nested summary": { summary: { counts: { fail: 1 } } as never },
    "list in summary": { summary: { ids: [1, 2] } as never },
    "camelCase key": { summary: { failCount: 1 } },
    "kebab key": { summary: { "fail-count": 1 } },
    "summary over 2 KB": { summary: { note: "x".repeat(2100) } },
    "summary NaN": { summary: { ratio: Number.NaN } },
    "multibyte over 2 KB": { summary: { note: "é".repeat(1100) } },
    "label without dot": { resultSchema: "modelcheck" },
    "label with hyphen": { resultSchema: "model-check.rule" },
    "version not semver": { resultSchemaVersion: "1.0" },
    "body undefined": { body: undefined },
    "body Infinity": { body: { x: Number.POSITIVE_INFINITY } },
    "invalid date": { generatedAt: new Date("nope") },
  };

  for (const [name, extra] of Object.entries(bad)) {
    it(`rejects ${name} and writes no file`, () => {
      let caught: unknown;
      try {
        write(extra);
      } catch (e) {
        caught = e;
      }
      expect(caught).toBeInstanceOf(ResultFileFormatError);
      expect(caught).toBeInstanceOf(NodeOutputValidationError);
      expect((caught as NodeOutputValidationError).errorCode).toBe("OUTPUT_VALIDATION_ERROR");
      expect(readdirSync(ctx.outputDir)).toEqual([]);
    });
  }

  it("accepts a summary exactly at the limit", () => {
    write({ summary: { note: "x".repeat(2048 - '{"note":""}'.length) } });
  });

  it("rejects filename traversal", () => {
    expect(() => write({ filename: "../escape.json" })).toThrow();
  });
});

describe("validateResultFileHeader", () => {
  it("rejects unknown, missing and unsupported", () => {
    const header = buildResultFileHeader(
      { resultSchema: "a.b", resultSchemaVersion: "1.0.0", generatedAt: FIXED },
      "r",
    );
    expect(() => validateResultFileHeader({ ...header, extra: 1 })).toThrow(ResultFileFormatError);
    const { workflow_run_id: _omit, ...missing } = header;
    expect(() => validateResultFileHeader(missing)).toThrow(ResultFileFormatError);
    expect(() => validateResultFileHeader({ ...header, result_file_version: "2.0.0" })).toThrow(/Unsupported/);
    expect(() => validateResultFileHeader({ ...header, body: {} })).toThrow(/body/);
  });
});

describe("manifest convention", () => {
  const base = {
    slug: "result-node",
    version: "1.0.0",
    name: "Result node",
    description: "d",
    input_schema: { type: "object", properties: {} },
  };

  it("accepts a result_file output", () => {
    const parsed = WorkflowNodeManifestSchema.parse({
      ...base,
      output_schema: { type: "object", properties: { result_file: resultFileOutputSchema("The result") } },
    });
    expect((parsed.output_schema.properties as Record<string, Record<string, unknown>>).result_file["x-result-file"]).toBe(
      true,
    );
  });

  const wrong: Record<string, Record<string, unknown>> = {
    "no marker": { result_file: { type: "string", format: "file" } },
    "not a file": { result_file: { type: "string" } },
    array: { result_file: { type: "array", items: { type: "string", format: "file" }, "x-result-file": true } },
    "wrong media type": { result_file: { ...resultFileOutputSchema(), contentMediaType: "text/csv" } },
    "marker elsewhere": { other: resultFileOutputSchema() },
  };
  for (const [name, properties] of Object.entries(wrong)) {
    it(`rejects ${name}`, () => {
      expect(() =>
        WorkflowNodeManifestSchema.parse({ ...base, output_schema: { type: "object", properties } }),
      ).toThrow(/result/);
    });
  }

  it("rejects the marker on inputs", () => {
    expect(() =>
      WorkflowNodeManifestSchema.parse({
        ...base,
        input_schema: { type: "object", properties: { result_file: resultFileOutputSchema() } },
        output_schema: { type: "object", properties: {} },
      }),
    ).toThrow(/outputs only/);
  });
});

describe("golden parity with the Python writer", () => {
  it("reproduces schemas/result-file/golden/expected.json byte for byte", () => {
    const input = JSON.parse(readFileSync(join(CANONICAL, "golden", "input.json"), "utf8"));
    const root = mkdtempSync(join(tmpdir(), "rf-golden-"));
    const goldenCtx = new NodeExecutionContext({ outputDir: join(root, input.workflow_run_id, "n") });
    const out = writeResultFile(goldenCtx, {
      resultSchema: input.result_schema,
      resultSchemaVersion: input.result_schema_version,
      summary: input.summary,
      body: input.body,
      generatedAt: new Date(input.generated_at),
    });
    const expected = readFileSync(join(CANONICAL, "golden", "expected.json")).toString("utf8").replace(/\n$/, "");
    expect(readFileSync(out.result_file).toString("utf8")).toBe(expected);
  });
});
