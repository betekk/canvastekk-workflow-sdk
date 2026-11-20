/**
 * Workflow run result files: the platform standard (#278, epic tracker#4309).
 *
 * TypeScript twin of `canvastekk_workflow_sdk.result_file`. The SDK owns the
 * layout; `body` belongs to the producing app and is never validated here.
 * Both runtimes write byte-identical headers for the same input (shared
 * golden file in `schemas/result-file/golden/`).
 *
 * Layout 1.0.0, header keys first and in this order: `result_file_version`,
 * `result_schema`, `result_schema_version`, `workflow_run_id`,
 * `generated_at`, optional `summary`, then `body`.
 *
 * See `docs/RESULT-FILE.md`.
 */
import { mkdirSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { randomUUID } from "node:crypto";
import AjvModule from "ajv";
const Ajv = AjvModule.default ?? AjvModule;
import type { ValidateFunction } from "ajv";
import { NodeOutputValidationError } from "./exceptions.js";
import type { NodeExecutionContext } from "./node-execution-context.js";

/** Version of the platform layout written by this SDK. */
export const RESULT_FILE_VERSION = "1.0.0";
/** Layout versions the header validator accepts. */
export const SUPPORTED_RESULT_FILE_VERSIONS: readonly string[] = ["1.0.0"];
/** Name of the node output (and of the reserved `__end__` key) that carries the file. */
export const RESULT_FILE_OUTPUT_FIELD = "result_file";
/** Output-schema extension marking the `result_file` output (manifest convention). */
export const RESULT_FILE_MARKER = "x-result-file";
export const RESULT_FILE_CONTENT_TYPE = "application/json";
export const RESULT_FILE_DEFAULT_NAME = "result.json";
/** Upper bound for `summary` as compact UTF-8 JSON. */
export const RESULT_FILE_SUMMARY_MAX_BYTES = 2048;
/** Header keys in their required order (`summary` is optional). */
export const RESULT_FILE_HEADER_KEYS: readonly string[] = [
  "result_file_version",
  "result_schema",
  "result_schema_version",
  "workflow_run_id",
  "generated_at",
  "summary",
];

/** Layout JSON Schema 1.0.0 — must equal `schemas/result-file/1.0.0.json` (test-enforced). */
export const RESULT_FILE_SCHEMA_1_0_0: Readonly<Record<string, unknown>> = {
  $schema: "http://json-schema.org/draft-07/schema#",
  $id: "urn:canvastekk:result-file:1.0.0",
  title: "CanvasTEKK workflow run result file, layout 1.0.0",
  description:
    "Platform-owned layout of a workflow run result file. Header keys come first, in this order: result_file_version, result_schema, result_schema_version, workflow_run_id, generated_at, summary (optional); body comes last. body is owned by the producing app and is never validated by the platform. summary must also be at most 2048 bytes as compact UTF-8 JSON (checked in code; JSON Schema cannot express it).",
  type: "object",
  required: [
    "result_file_version",
    "result_schema",
    "result_schema_version",
    "workflow_run_id",
    "generated_at",
    "body",
  ],
  additionalProperties: false,
  properties: {
    result_file_version: {
      description: "Version of this platform layout.",
      const: "1.0.0",
    },
    result_schema: {
      description:
        "App-chosen label naming the shape of body: app.kind, snake_case parts (e.g. model_check.rule).",
      type: "string",
      maxLength: 128,
      pattern: "^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*)+$",
    },
    result_schema_version: {
      description: "App-chosen semver of that shape (X.Y.Z).",
      type: "string",
      maxLength: 64,
      pattern: "^(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)\\.(0|[1-9][0-9]*)$",
    },
    workflow_run_id: {
      description: "Run id from the node execution request.",
      type: "string",
      minLength: 1,
      maxLength: 128,
    },
    generated_at: {
      description: "UTC timestamp, ISO 8601 with a Z suffix.",
      type: "string",
      pattern: "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,6})?Z$",
    },
    summary: {
      description:
        "Optional flat key-value pairs, app-defined keys, scalar values only, at most 2048 bytes.",
      type: "object",
      propertyNames: {
        maxLength: 64,
        pattern: "^[a-z][a-z0-9_]*$",
      },
      additionalProperties: {
        type: ["string", "number", "boolean", "null"],
      },
    },
    body: {
      description: "App-owned content. Any JSON value.",
    },
  },
};

/** `__end__.result_file` value schema 1.0.0 — must equal `schemas/result-file/end-value-1.0.0.json`. */
export const RESULT_FILE_END_VALUE_SCHEMA_1_0_0: Readonly<Record<string, unknown>> = {
  $schema: "http://json-schema.org/draft-07/schema#",
  $id: "urn:canvastekk:result-file:end-value:1.0.0",
  title: "Value of the reserved __end__.result_file key",
  description:
    "The storage pointer the engine stamps on a node's result_file file output and wires into __end__.result_file. Internal: never returned to users.",
  type: "string",
  minLength: 6,
  pattern: "^s3://",
};

/** Summary value types allowed by the layout. */
export type ResultFileSummaryValue = string | number | boolean | null;

/** A validated result file header (no `body`). */
export interface ResultFileHeader {
  result_file_version: string;
  result_schema: string;
  result_schema_version: string;
  workflow_run_id: string;
  generated_at: string;
  summary?: Record<string, ResultFileSummaryValue>;
}

/** A result file (or the data meant for one) breaks the platform layout. */
export class ResultFileFormatError extends NodeOutputValidationError {
  constructor(message: string, errors?: Record<string, unknown>[]) {
    super(message, { errors });
    this.name = "ResultFileFormatError";
  }
}

let headerValidator: ValidateFunction | null = null;

function getHeaderValidator(): ValidateFunction {
  if (headerValidator) return headerValidator;
  const schema = structuredClone(RESULT_FILE_SCHEMA_1_0_0) as Record<string, unknown>;
  schema.required = (schema.required as string[]).filter((key) => key !== "body");
  delete (schema.properties as Record<string, unknown>).body;
  delete schema.$id;
  const ajv = new Ajv({ allErrors: true, strict: false });
  headerValidator = ajv.compile(schema);
  return headerValidator;
}

function compact(value: unknown): string {
  return JSON.stringify(value, (_key, v: unknown) => {
    if (typeof v === "number" && !Number.isFinite(v)) {
      throw new ResultFileFormatError(`Result file value is not valid JSON: ${String(v)}`);
    }
    return v;
  });
}

/**
 * Check a header (every layout key except `body`).
 *
 * @param header - The header object.
 * @returns A shallow copy of the header.
 * @throws {ResultFileFormatError} With one entry per problem in `errors`.
 */
export function validateResultFileHeader(header: unknown): ResultFileHeader {
  if (header === null || typeof header !== "object" || Array.isArray(header)) {
    throw new ResultFileFormatError("Result file header must be a JSON object");
  }
  const data = { ...(header as Record<string, unknown>) };
  if ("body" in data) {
    throw new ResultFileFormatError("Result file header must not contain body");
  }
  const version = data.result_file_version;
  if (typeof version !== "string" || !SUPPORTED_RESULT_FILE_VERSIONS.includes(version)) {
    throw new ResultFileFormatError(
      `Unsupported result_file_version ${JSON.stringify(version ?? null)}; supported: ${JSON.stringify(SUPPORTED_RESULT_FILE_VERSIONS)}`,
    );
  }
  const validate = getHeaderValidator();
  const errors: Record<string, unknown>[] = [];
  if (!validate(data)) {
    for (const err of validate.errors ?? []) {
      errors.push({ path: err.instancePath.replace(/^\//, "") || "(root)", message: err.message ?? "invalid" });
    }
  }
  const summary = data.summary;
  if (errors.length === 0 && summary !== undefined && summary !== null && typeof summary === "object") {
    let size = 0;
    try {
      size = Buffer.byteLength(compact(summary), "utf8");
    } catch (e) {
      errors.push({ path: "summary", message: `summary is not valid JSON: ${(e as Error).message}` });
    }
    if (size > RESULT_FILE_SUMMARY_MAX_BYTES) {
      errors.push({
        path: "summary",
        message: `summary is ${size} bytes; the limit is ${RESULT_FILE_SUMMARY_MAX_BYTES}`,
      });
    }
  }
  if (errors.length > 0) {
    throw new ResultFileFormatError(
      "Result file header is invalid: " + errors.map((e) => `${String(e.path)}: ${String(e.message)}`).join("; "),
      errors,
    );
  }
  return data as unknown as ResultFileHeader;
}

/** Options shared by {@link buildResultFileHeader} and {@link writeResultFile}. */
export interface ResultFileHeaderOptions {
  /** App label for the body's shape, e.g. `model_check.rule`. */
  resultSchema: string;
  /** Semver of that shape, e.g. `0.1.0`. */
  resultSchemaVersion: string;
  /** Optional flat key-value pairs (≤2 KB). */
  summary?: Record<string, ResultFileSummaryValue>;
  /** Timestamp; defaults to now. Written as UTC with milliseconds and `Z`. */
  generatedAt?: Date;
}

/**
 * Build and validate a header in the required key order.
 *
 * @param opts - Labels, optional summary and timestamp.
 * @param workflowRunId - The run id (`context.runId`).
 * @returns The validated header.
 * @throws {ResultFileFormatError} If any header value breaks the layout.
 */
export function buildResultFileHeader(opts: ResultFileHeaderOptions, workflowRunId: string): ResultFileHeader {
  const generatedAt = opts.generatedAt ?? new Date();
  if (Number.isNaN(generatedAt.getTime())) {
    throw new ResultFileFormatError("generated_at is not a valid date");
  }
  const header: Record<string, unknown> = {
    result_file_version: RESULT_FILE_VERSION,
    result_schema: opts.resultSchema,
    result_schema_version: opts.resultSchemaVersion,
    workflow_run_id: workflowRunId,
    generated_at: generatedAt.toISOString(),
  };
  if (opts.summary !== undefined) header.summary = opts.summary;
  return validateResultFileHeader(header);
}

/**
 * Return the file text up to and including `"body":` (golden-test seam).
 *
 * @param header - A validated header.
 * @returns `{"result_file_version":...,"body":` with keys in layout order.
 */
export function serializeResultFileHeaderPrefix(header: ResultFileHeader): string {
  const record = header as unknown as Record<string, unknown>;
  const parts = RESULT_FILE_HEADER_KEYS.filter((key) => key in record && record[key] !== undefined).map(
    (key) => `${JSON.stringify(key)}:${compact(record[key])}`,
  );
  return `{${parts.join(",")},"body":`;
}

/** Options for {@link writeResultFile}. */
export interface WriteResultFileOptions extends ResultFileHeaderOptions {
  /** Any JSON value (app-owned; not validated). */
  body: unknown;
  /** File name inside the context's output folder (default `result.json`). */
  filename?: string;
}

/**
 * Write the run's result file and return it as the `result_file` output.
 *
 * The header and `summary` are validated before anything is written; the
 * document goes to a temporary file that is renamed into place only when
 * encoding succeeded, so a failure never leaves a file behind.
 *
 * @example
 * return { verdict, ...writeResultFile(context, {
 *   resultSchema: "model_check.rule", resultSchemaVersion: "0.1.0",
 *   body: result, summary: { verdict } }) };
 *
 * @param context - Node execution context (supplies `runId` and the output folder).
 * @param opts - Labels, body, optional summary, filename and timestamp.
 * @returns `{ result_file: "<local path>" }`; the SDK uploads it after `execute`.
 * @throws {ResultFileFormatError} Invalid header, `summary` or non-JSON `body`.
 */
export function writeResultFile(
  context: NodeExecutionContext,
  opts: WriteResultFileOptions,
): { result_file: string } {
  const header = buildResultFileHeader(opts, context.runId);
  const target = context.outputPath(opts.filename ?? RESULT_FILE_DEFAULT_NAME);
  let text: string;
  try {
    const encodedBody = opts.body === undefined ? undefined : compact(opts.body);
    if (encodedBody === undefined) {
      throw new ResultFileFormatError("Result file body is not valid JSON: undefined");
    }
    text = `${serializeResultFileHeaderPrefix(header)}${encodedBody}}`;
  } catch (e) {
    if (e instanceof ResultFileFormatError) throw e;
    throw new ResultFileFormatError(`Result file body is not valid JSON: ${(e as Error).message}`);
  }
  mkdirSync(dirname(target), { recursive: true });
  const tmp = join(dirname(target), `.result-file-${randomUUID()}.tmp`);
  try {
    writeFileSync(tmp, text, { encoding: "utf8" });
    renameSync(tmp, target);
  } catch (e) {
    try {
      unlinkSync(tmp);
    } catch {
      // already gone
    }
    throw e;
  }
  return { [RESULT_FILE_OUTPUT_FIELD]: target } as { result_file: string };
}

/**
 * Return the output-schema property that declares a node's result file.
 *
 * Use it as `output_schema.properties.result_file`.
 *
 * @param description - Optional field description.
 * @returns The property schema with the `x-result-file` marker.
 */
export function resultFileOutputSchema(description?: string): Record<string, unknown> {
  const schema: Record<string, unknown> = {
    type: "string",
    format: "file",
    contentMediaType: RESULT_FILE_CONTENT_TYPE,
    [RESULT_FILE_MARKER]: true,
  };
  if (description) schema.description = description;
  return schema;
}

/**
 * Return manifest problems with the result-file convention (empty = fine).
 *
 * @param properties - `input_schema` / `output_schema` properties.
 * @param schemaName - `"input_schema"` or `"output_schema"`.
 * @returns Human-readable problems.
 */
export function resultFileDeclarationErrors(
  properties: Record<string, unknown>,
  schemaName: string,
): string[] {
  const problems: string[] = [];
  for (const [name, raw] of Object.entries(properties)) {
    if (raw === null || typeof raw !== "object") continue;
    const prop = raw as Record<string, unknown>;
    const marked = prop[RESULT_FILE_MARKER] !== undefined && prop[RESULT_FILE_MARKER] !== null;
    if (schemaName !== "output_schema") {
      if (marked) problems.push(`Input field '${name}' must not carry '${RESULT_FILE_MARKER}' (outputs only).`);
      continue;
    }
    if (name === RESULT_FILE_OUTPUT_FIELD) {
      const ok =
        prop.type === "string" &&
        prop.format === "file" &&
        prop[RESULT_FILE_MARKER] === true &&
        (prop.contentMediaType ?? RESULT_FILE_CONTENT_TYPE) === RESULT_FILE_CONTENT_TYPE;
      if (!ok) {
        problems.push(
          `Output '${RESULT_FILE_OUTPUT_FIELD}' is reserved for the result file: declare it with ` +
            `resultFileOutputSchema() / result_file_output_schema() (type string, format file, contentMediaType application/json, ` +
            `'${RESULT_FILE_MARKER}': true). See docs/RESULT-FILE.md.`,
        );
      }
    } else if (marked) {
      problems.push(`Output '${name}' carries '${RESULT_FILE_MARKER}'; only '${RESULT_FILE_OUTPUT_FIELD}' may.`);
    }
  }
  return problems;
}
