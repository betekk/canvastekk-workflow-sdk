import { z } from "zod";
import { VERSION } from "./version.js";
import { NodeValidationError } from "./exceptions.js";

const SLUG_PATTERN = /^[a-z]([a-z0-9-]*[a-z0-9])?$/;
// DA-2627: marker for the ambiguous name-only construction. Set by the
// preprocess below and reported by the slug field's superRefine as a proper
// zod issue — a throw here would escape safeParse (zod v3 does not catch
// effect throws). Can never collide: not a valid slug by pattern.
const AMBIGUOUS_NAME_SENTINEL = "__ambiguous_name__";
const SEMVER_PATTERN = /^(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)$/;

export const ColorPresetSchema = z.union([
  z.literal("purple"),
  z.literal("red"),
  z.literal("gray"),
  z.literal("cyan"),
  z.literal("emerald"),
  z.literal("orange"),
  z.literal("amber"),
  z.literal("sky"),
  z.literal("violet"),
  z.literal("teal"),
  z.literal("indigo"),
  z.literal("slate"),
  z.literal("blue"),
  z.literal("green"),
  z.literal("pink"),
  z.literal("yellow"),
  z.literal("rose"),
  z.literal("lime"),
  z.literal("fuchsia"),
  z.literal("emerald-light"),
  z.literal("indigo-light"),
  z.literal("slate-light"),
  z.literal("red-dark"),
  z.literal("sky-dark"),
  z.literal("teal-dark"),
  z.literal("emerald-dark"),
]);

/** Color preset for node UI styling. */
export type ColorPreset = z.infer<typeof ColorPresetSchema>;

export const WorkflowNodeStylesSchema = z.object({
  icon: z.string().nullable().default(null),
  color: ColorPresetSchema.nullable().default(null),
});

export type WorkflowNodeStyles = z.infer<typeof WorkflowNodeStylesSchema>;

export const RetryConfigSchema = z.object({
  max_attempts: z.number().int().min(1).default(1),
  initial_delay_ms: z.number().int().min(0).default(1000),
  backoff_multiplier: z.number().min(1.0).default(2.0),
  max_delay_ms: z.number().int().min(0).default(30000),
});

/** Retry configuration with exponential backoff. */
export type RetryConfig = z.infer<typeof RetryConfigSchema>;

export const WorkflowNodeRoleSchema = z.enum(["start", "end", "error_gate", "operation"]).default("operation");

export type WorkflowNodeRole = z.infer<typeof WorkflowNodeRoleSchema>;

/**
 * Advisory deprecation metadata for a node manifest (DA-1582).
 *
 * Migration signal, orthogonal to `node_status` (the operational routing
 * lever). Mirrors RFC 9745 (Deprecation) / RFC 8594 (Sunset) semantics at the
 * data-model level. Dates are ISO 8601 strings (not `Date`) to stay
 * JSON-round-trip compatible with the Python SDK and the engine wire format.
 */
export const DeprecationInfoSchema = z
  .object({
    // Strict YYYY-MM-DD (zod .date()) so lexicographic ordering in the
    // superRefine check and the runtime sunset guard stays chronological —
    // Python types these as pydantic `date` (DA-2312 parity).
    deprecated_at: z.string().date().nullable().default(null),
    sunset_date: z.string().date().nullable().default(null),
    replacement_slug: z.string().nullable().default(null),
    migration_url: z.string().nullable().default(null),
    notice: z.string(),
  })
  .superRefine((dep, ctx) => {
    // ISO 8601 dates (YYYY-MM-DD) compare lexicographically = chronologically.
    // Boundary sunset_date == deprecated_at is allowed (DA-2312, parity with
    // Python DeprecationInfo._validate_sunset_after_deprecation).
    if (
      dep.deprecated_at !== null &&
      dep.sunset_date !== null &&
      dep.sunset_date < dep.deprecated_at
    ) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: `DeprecationInfo sunset_date ${dep.sunset_date} is before deprecated_at ${dep.deprecated_at}`,
      });
    }
  });

/** Deprecation metadata for a node manifest. */
export type DeprecationInfo = z.infer<typeof DeprecationInfoSchema>;

/**
 * Validates that file fields in a schema have the correct format.
 *
 * @param schema - JSON Schema object to validate
 * @throws {Error} If a field uses the deprecated 'binary' format or 'file' format without string type
 */
function validateFileFieldFormats(
  schema: Record<string, unknown>,
): void {
  const properties = (schema.properties ?? {}) as Record<
    string,
    Record<string, unknown>
  >;
  for (const [name, propSchema] of Object.entries(properties)) {
    const fieldFormat = propSchema.format as string | undefined;
    const fieldType = propSchema.type as string | undefined;

    if (fieldFormat === "binary") {
      throw new Error(
        `Field '${name}' uses format 'binary' which is no longer supported. Use format 'file' instead. (See DA-894 migration guide.)`,
      );
    }

    if (fieldFormat === "file" && fieldType !== "string") {
      throw new Error(
        `Field '${name}' has format 'file' but type is '${fieldType}'. File fields must have type 'string'.`,
      );
    }
  }
}

const WorkflowNodeManifestObjectSchema = z
  .object({
    id: z.unknown().optional(),
    slug: z.string().superRefine((v, ctx) => {
      if (v === AMBIGUOUS_NAME_SENTINEL) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["slug"],
          message:
            `Node manifest received name without slug or title — ambiguous. ` +
            "Identity goes in slug=; display goes in name=. " +
            "(Legacy name=<slug>+title=<display> construction still works.)",
        });
        return;
      }
      if (!SLUG_PATTERN.test(v)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["slug"],
          message: `Node slug must be a lowercase slug (alphanumeric and hyphens only, no leading/trailing hyphens). Got: '${v}'`,
        });
      }
    }),
    version: z.string().refine((v) => SEMVER_PATTERN.test(v), (v) => ({
      message: `Node version must be semantic version (X.Y.Z). Got: '${v}'`,
    })),
    name: z.string(),
    description: z.string(),
    input_schema: z.record(z.unknown()),
    output_schema: z.record(z.unknown()),
    token_cost: z.number().min(0.0).default(0.0),
    default_retry: RetryConfigSchema.default(RetryConfigSchema.parse({})),
    category: z.string().default("utility"),
    timeout_seconds: z.number().int().min(1).default(30),
    // DA-3499: host-enforced runtime ceiling bounding timeout_seconds. Hosts
    // enforce min(timeout_seconds, hard_max_runtime_seconds); a declared
    // budget above the ceiling fails the probe unless the node explicitly
    // overrides the ceiling. Default: 7200 (2 hours). Host-side contract —
    // never sent in the engine registration request.
    hard_max_runtime_seconds: z.number().int().min(1).default(7200),
    role: WorkflowNodeRoleSchema,
    styles: WorkflowNodeStylesSchema.nullable().default(null),
    deprecation: DeprecationInfoSchema.nullable().default(null),
    // DA-3359: SDK provenance is STAMPED (defaults to the installed VERSION);
    // the legacy minimum/maximum fields stay optional for one release.
    sdk_version: z
      .string()
      .default(VERSION)
      .readonly(),
    minimum_sdk_version: z
      .string()
      .refine((v) => SEMVER_PATTERN.test(v), (v) => ({
        message: `SDK version must be semantic version (X.Y.Z). Got: '${v}'`,
      }))
      .nullable()
      .default(null),
    maximum_sdk_version: z
      .string()
      .refine((v) => SEMVER_PATTERN.test(v), (v) => ({
        message: `SDK version must be semantic version (X.Y.Z). Got: '${v}'`,
      }))
      .nullable()
      .default(null),
    docs_url: z
      .string()
      .refine((v) => v.startsWith("http://") || v.startsWith("https://"), (v) => ({
        message: `docs_url must be an http(s) URL. Got: '${v}'`,
      }))
      .nullable()
      .default(null),
    changelog_url: z
      .string()
      .refine((v) => v.startsWith("http://") || v.startsWith("https://"), (v) => ({
        message: `changelog_url must be an http(s) URL. Got: '${v}'`,
      }))
      .nullable()
      .default(null),
  })
  .transform((data, ctx) => {
    const { id: _id, ...rest } = data;

    try {
      validateFileFieldFormats(rest.input_schema as Record<string, unknown>);
      validateFileFieldFormats(rest.output_schema as Record<string, unknown>);
    } catch (e) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        message: (e as Error).message,
      });
      return z.NEVER;
    }

    return rest;
  });

export const WorkflowNodeManifestSchema = z.preprocess(mapLegacyVocabulary, WorkflowNodeManifestObjectSchema);

/** Complete node manifest including metadata, schemas, and configuration. */
export type WorkflowNodeManifest = z.infer<typeof WorkflowNodeManifestSchema>;

/**
 * Runtime bound every HOST enforces: the declared budget capped by the hard
 * ceiling (DA-3499). Hosts (the inline execute AbortController, external task
 * runners) must derive their runtime bound from this, never from the raw
 * `timeout_seconds`. Mirrors python's `effective_runtime_seconds` property.
 */
export function effectiveRuntimeSeconds(
  def: Pick<WorkflowNodeManifest, "timeout_seconds" | "hard_max_runtime_seconds">,
): number {
  return Math.min(def.timeout_seconds, def.hard_max_runtime_seconds);
}

/**
 * Resolves the legacy `name`/`title` construction vocabulary (DA-2627).
 *
 * The manifest's identity field is `slug` and its display field is `name`.
 * Because `name` changed meaning, compatibility is resolved here — at
 * construction, deterministically — never on the wire:
 *
 * - `slug` absent AND both `name` and `title` present (legacy call):
 *   `slug = name`, display `name = title`, with a console warning.
 * - `name` only (no `slug`, no `title`): error — ambiguous in both
 *   vocabularies; the message disambiguates.
 * - `slug` present AND `title` present: `title` is ignored with a warning
 *   (display comes from `name`).
 * - A `slug ?? name` fallback is deliberately NOT implemented: it would
 *   silently map a lowercase display name into identity.
 */
function mapLegacyVocabulary(data: unknown): unknown {
  if (typeof data !== "object" || data === null || Array.isArray(data)) {
    return data;
  }
  const d = { ...(data as Record<string, unknown>) };
  const hasSlug = "slug" in d;
  const hasName = "name" in d;
  const hasTitle = "title" in d;

  if (!hasSlug && hasName && hasTitle) {
    console.warn(
      "[canvastekk-workflow-sdk] NodeDefinition legacy construction (name=<slug>, title=<display>) is deprecated; " +
        "use slug=<id> and name=<display>. The legacy mapping keeps working but will be removed in a future major version.",
    );
    d.slug = d.name;
    d.name = d.title;
    delete d.title;
  } else if (!hasSlug && hasName && !hasTitle) {
    // Sentinel (not a throw): zod v3 safeParse does not catch throws from
    // effects — the slug superRefine turns this into a proper issue.
    d.slug = AMBIGUOUS_NAME_SENTINEL;
  } else if (hasSlug && hasTitle) {
    console.warn(
      "[canvastekk-workflow-sdk] NodeDefinition received both slug= and title=; title is ignored (display name comes from name=).",
    );
    delete d.title;
  }

  return d;
}

/**
 * Generates a node ID from slug and version.
 * @param def - Object containing node slug and version
 * @returns Node ID in format "slug-vX.Y.Z"
 */
export function getNodeId(def: Pick<WorkflowNodeManifest, "slug" | "version">): string {
  return `${def.slug}-v${def.version}`;
}

/**
 * Extracts the names of file input fields from a node's input schema.
 *
 * File fields are identified by `format: "file"` in their JSON Schema definition.
 *
 * @param def - Node definition to inspect
 * @returns Array of field names that have `format: "file"`
 */
export function getFileInputFields(def: WorkflowNodeManifest): string[] {
  const properties = ((def.input_schema as Record<string, unknown>)?.properties ?? {}) as Record<
    string,
    Record<string, unknown>
  >;
  return Object.entries(properties)
    .filter(([, schema]) => schema.format === "file")
    .map(([name]) => name);
}

/**
 * Extracts the names of file output fields from a node's output schema.
 *
 * File fields are identified by `format: "file"` in their JSON Schema definition.
 *
 * @param def - Node definition to inspect
 * @returns Array of field names that have `format: "file"`
 */
export function getFileOutputFields(def: WorkflowNodeManifest): string[] {
  const properties = ((def.output_schema as Record<string, unknown>)?.properties ?? {}) as Record<
    string,
    Record<string, unknown>
  >;
  return Object.entries(properties)
    .filter(([, schema]) => schema.format === "file")
    .map(([name]) => name);
}

/**
 * Validates a downloaded file against schema constraints.
 *
 * Checks the file extension against `x-accept` (allowed extensions)
 * and the file size against `x-maxSizeBytes` (maximum size in bytes).
 *
 * @param def - Node definition containing the input schema
 * @param fieldName - Name of the file input field
 * @param filePath - Local path to the downloaded file
 * @param fileSize - Size of the downloaded file in bytes
 * @throws {NodeValidationError} If file extension or size violates constraints
 */
export function validateFileInput(
  def: WorkflowNodeManifest,
  fieldName: string,
  filePath: string,
  fileSize?: number,
): void {
  const properties = ((def.input_schema as Record<string, unknown>)?.properties ?? {}) as Record<
    string,
    Record<string, unknown>
  >;
  const schema = properties[fieldName] ?? {};

  const xAccept = schema["x-accept"] as string[] | undefined;
  if (xAccept) {
    const ext = filePath.substring(filePath.lastIndexOf(".")).toLowerCase();
    const allowed = xAccept.map((e: string) => e.toLowerCase());
    if (!allowed.includes(ext)) {
      throw new NodeValidationError(
        `File extension '${ext}' is not allowed for field '${fieldName}'. Allowed extensions: ${JSON.stringify(xAccept)}`,
      );
    }
  }

  const xMaxSizeBytes = schema["x-maxSizeBytes"] as number | undefined;
  if (xMaxSizeBytes !== undefined && fileSize !== undefined) {
    if (fileSize > xMaxSizeBytes) {
      throw new NodeValidationError(
        `File size ${fileSize} bytes exceeds maximum allowed size ${xMaxSizeBytes} bytes for field '${fieldName}'`,
      );
    }
  }
}
