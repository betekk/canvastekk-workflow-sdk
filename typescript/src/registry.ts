import { VERSION } from "./version.js";
import { writeFileSync, mkdirSync } from "node:fs";
import { dirname } from "node:path";
import type { WorkflowNodeManifest } from "./definition.js";
import { DeprecationInfoSchema } from "./definition.js";
import { RegistrationError } from "./exceptions.js";

/** Node invocation type. */
export type InvokeType = "http" | "lambda" | "sagemaker" | "in-process";

const VALID_INVOKE_TYPES: Set<string> = new Set(["http", "lambda", "sagemaker", "in-process"]);

/**
 * Registry credential shape, mirroring CDS ``ApiKeyUtil`` (DA-1948):
 * ``ctk_`` + 43 chars of base62 minus lookalikes (``0 O I l``) = 47 total.
 * A future CDS format change must touch this mirror and the Python
 * ``registry_auth_header`` together — ``tests/test_parity.py`` pins them equal.
 */
export const CTK_PREFIX = "ctk_";
export const CTK_BODY_LENGTH = 43;
const CTK_BODY_ALPHABET: ReadonlySet<string> = new Set(
  "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz123456789",
);

/**
 * Return why ``token`` is not a usable registry credential, else ``null``.
 *
 * Local, offline validation (no network call): non-``ctk_`` credentials are
 * rejected outright — the engine retired ``X-Service-Token``/``X-API-Key``
 * registry auth (#3760), so sending one can only produce an unexplained 401;
 * malformed ``ctk_`` keys (wrong length/alphabet) get a truncation hint.
 * Mirror of the Python SDK's ``invalid_ctk_reason`` (#239).
 */
export function invalidCtkReason(token: string): string | null {
  if (!token.startsWith(CTK_PREFIX)) {
    return (
      "registry credentials must be ctk_ API keys — the engine retired " +
      "X-Service-Token registry auth (#3760); ask ops to rotate"
    );
  }
  const body = token.slice(CTK_PREFIX.length);
  if (body.length !== CTK_BODY_LENGTH || [...body].some((c) => !CTK_BODY_ALPHABET.has(c))) {
    return (
      `malformed ctk_ key: expected ${CTK_PREFIX.length + CTK_BODY_LENGTH} chars ` +
      `(ctk_ + ${CTK_BODY_LENGTH}, DA-1948), got ${token.length} — looks truncated or mistyped`
    );
  }
  return null;
}

/**
 * Wire form for a registry credential (#239) — ``ctk_`` API keys only.
 *
 * A valid ``ctk_`` key rides ``Authorization: Bearer <token>`` (the engine's
 * DA-1949 ctk_ dispatch). Anything else — legacy service tokens included —
 * throws before any network call: the engine retired those registry legs
 * (#3760), so the only honest outcome is a local error naming the fix.
 * Mirror of the Python SDK's ``registry_auth_header``.
 *
 * @throws Error via {@link invalidCtkReason} when the token is not a
 * well-formed ``ctk_`` key (rotation guidance for foreign tokens, a
 * truncation hint for malformed ones).
 */
export function registryAuthHeader(serviceToken: string): [string, string] {
  const reason = invalidCtkReason(serviceToken);
  if (reason) throw new Error(reason);
  return ["Authorization", `Bearer ${serviceToken}`];
}

/** Result from node registration. */
export interface RegisterNodeResult {
  node: Record<string, unknown>;
  action?: string | null;
  revisionId?: string | null;
  previousVersion?: string | null;
  changes?: string[] | null;
}

/**
 * Gets a value from registration result with default fallback.
 * @param result - Registration result
 * @param key - Key to retrieve
 * @param defaultValue - Default value if key not found
 * @returns Value or default
 */
export function registerNodeResultGet(result: RegisterNodeResult, key: string, defaultValue?: unknown): unknown {
  return result.node[key] ?? defaultValue;
}

/**
 * Checks if a key exists in registration result.
 * @param result - Registration result
 * @param key - Key to check
 * @returns True if key exists
 */
export function registerNodeResultHas(result: RegisterNodeResult, key: string): boolean {
  return key in result.node;
}

/**
 * Builds payload for node registration.
 * @param definition - Node definition
 * @param opts - Registration options
 * @returns Registration payload dictionary
 */
export function buildRegistryPayload(
  definition: WorkflowNodeManifest,
  opts: {
    invokeType?: InvokeType;
    invokeUrl?: string;
    invokeConfig?: Record<string, unknown>;
    tags?: string[];
    constraints?: Record<string, unknown>;
    nodeStatus?: string;
  } = {},
): Record<string, unknown> {
  const {
    invokeType = "http",
    invokeUrl,
    invokeConfig,
    tags,
    constraints,
  } = opts;

  const resolvedStyles = definition.styles ?? null;

  const resolvedConstraints: Record<string, unknown> = { ...(constraints ?? {}) };
  const manifestConstraintFields: [string, string | null][] = [
    ["docs_url", definition.docs_url ?? null],
    ["changelog_url", definition.changelog_url ?? null],
  ];
  for (const [key, value] of manifestConstraintFields) {
    if (value !== null && !(key in resolvedConstraints)) {
      resolvedConstraints[key] = value;
    }
  }
  resolvedConstraints.sdk_version = VERSION;

  if (definition.contract !== null && !("contract" in resolvedConstraints)) {
    resolvedConstraints.contract = definition.contract;
  }

  const payload: Record<string, unknown> = {
    name: definition.slug,
    label: definition.name,
    version: definition.version,
    description: definition.description,
    input_schema: definition.input_schema,
    output_schema: definition.output_schema,
    invoke_type: invokeType,
    category: definition.category,
    token_cost: definition.token_cost,
    timeout_seconds: definition.timeout_seconds,
    tags: tags ?? [],
    styles: resolvedStyles,
  };

  if (invokeUrl !== undefined) {
    payload.invoke_url = invokeUrl;
  }
  if (invokeConfig !== undefined) {
    payload.invoke_config = invokeConfig;
  }
  if (Object.keys(resolvedConstraints).length > 0) {
    payload.constraints = resolvedConstraints;
  }
  if (definition.deprecation != null) {
    payload.deprecation = DeprecationInfoSchema.parse(definition.deprecation);
  }

  return payload;
}

/**
 * Extracts node data from API response payload.
 * @param payload - API response payload
 * @returns Node data dictionary
 */
export function extractNodeData(payload: Record<string, unknown>): Record<string, unknown> {
  if ("node" in payload && typeof payload.node === "object" && payload.node !== null) {
    return payload.node as Record<string, unknown>;
  }
  if ("data" in payload && typeof payload.data === "object" && payload.data !== null) {
    return payload.data as Record<string, unknown>;
  }
  return payload;
}

/**
 * Registers a node with the CanvasTEKK registry.
 * @param node - Node with definition
 * @param registryUrl - Registry API URL
 * @param opts - Registration options
 * @returns Registration result
 * @throws RegistrationError if registration fails
 */
export async function registerNode(
  node: { definition: WorkflowNodeManifest },
  registryUrl: string,
  opts: {
    invokeUrl?: string;
    invokeType?: InvokeType;
    /** Registry credential — a ``ctk_`` API key (required; #239). */
    serviceToken?: string;
    tags?: string[];
    invokeConfig?: Record<string, unknown>;
    timeout?: number;
  } = {},
): Promise<RegisterNodeResult> {
  const { invokeUrl, invokeType = "http", serviceToken, tags, invokeConfig, timeout = 30 } = opts;

  if (!serviceToken) {
    throw new Error(
      "serviceToken (a ctk_ API key) is required for registration — " +
        "the engine retired X-API-Key/X-Service-Token registry auth (#3760)",
    );
  }

  if (!VALID_INVOKE_TYPES.has(invokeType)) {
    throw new Error(
      `Invalid invoke_type '${invokeType}'. Must be one of: ${[...VALID_INVOKE_TYPES].sort().join(", ")}`,
    );
  }

  const manifest = buildRegistryPayload(node.definition, {
    invokeType,
    invokeUrl,
    tags,
    invokeConfig,
  });

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Accept: "application/json",
  };
  const [authName, authValue] = registryAuthHeader(serviceToken);
  headers[authName] = authValue;

  try {
    const resp = await fetch(registryUrl, {
      method: "POST",
      body: JSON.stringify(manifest),
      headers,
      signal: AbortSignal.timeout(timeout * 1000),
    });

    if (!resp.ok) {
      const body = await resp.text().catch(() => "");
      let parsed: Record<string, unknown>;
      try {
        parsed = JSON.parse(body) as Record<string, unknown>;
      } catch {
        parsed = { detail: body };
      }
      throw new RegistrationError(resp.status, parsed);
    }

    const responseData = await resp.json() as Record<string, unknown>;
    const action = responseData.action as string | undefined;
    const revisionId = responseData.revision_id as string | undefined;
    const previousVersion = responseData.previous_version as string | undefined;
    const changes = responseData.changes as string[] | undefined;

    const nodeData = extractNodeData(responseData);
    return {
      node: nodeData,
      action,
      revisionId,
      previousVersion,
      changes,
    };
  } catch (err) {
    if (err instanceof RegistrationError) throw err;
    throw new RegistrationError(500, { detail: `Registration failed: ${(err as Error).message}` });
  }
}

/**
 * Exports node definition to a JSON file.
 * @param definition - Node definition
 * @param outputPath - Output file path
 * @param opts - Export options
 * @returns Output file path
 */
export function exportDefinition(
  definition: WorkflowNodeManifest,
  outputPath: string,
  opts: {
    invokeType?: InvokeType;
    invokeUrl?: string;
    nodeStatus?: string;
    tags?: string[];
    styles?: Record<string, unknown> | null;
    constraints?: Record<string, unknown>;
  } = {},
): string {
  const registryDict = buildRegistryPayload(definition, {
    invokeType: opts.invokeType,
    invokeUrl: opts.invokeUrl,
    tags: opts.tags,
    constraints: opts.constraints,
    nodeStatus: opts.nodeStatus,
  });

  registryDict.node_role = definition.role;
  registryDict.retry = definition.default_retry;
  registryDict.node_status = opts.nodeStatus ?? "active";

  if (opts.styles !== undefined && opts.styles !== null) {
    registryDict.styles = opts.styles;
  }

  mkdirSync(dirname(outputPath), { recursive: true });
  writeFileSync(outputPath, JSON.stringify(registryDict, null, 2) + "\n");
  return outputPath;
}

/**
 * Fields the engine assigns itself and excludes from its registration
 * immutability diff (``workflow_node_service.NON_COMPARISON_FIELDS`` in
 * canvastekk-workflow-engine). The probe diff mirrors this set so
 * "passes locally ⇔ passes registration" holds field-for-field.
 * Mirror of the Python SDK's ``ENGINE_NON_COMPARISON_FIELDS`` (#233).
 */
export const ENGINE_NON_COMPARISON_FIELDS: ReadonlySet<string> = new Set([
  "id",
  "name",
  "owner",
  "source",
  "registered_at",
  "node_status",
  "last_registered_by",
]);

/** Options for {@link fetchPublishedDefinition}. */
export interface FetchPublishedOptions {
  /** Credential; wire form per {@link registryAuthHeader}. */
  token?: string;
  /** Request timeout in milliseconds (default 10s). */
  timeoutMs?: number;
}

/**
 * Fetch the published node definition from the engine registry by name.
 *
 * GETs ``{engineUrl}/api/workflows/nodes/by-name/{name}`` — the same route
 * registration verifies against. Register-style full-endpoint URLs
 * (``.../api/workflows/nodes``) are tolerated and normalized. Intended for
 * the pre-registration self-check (``probe --engine-url``, #233) so node
 * authors can diff against registry truth before a deploy burns a CI cycle
 * on a 409 ``node_version_immutable``.
 *
 * Returns ``null`` on 404 (name never published — the new-node case).
 * Throws on transport failures and non-404 HTTP errors — callers degrade
 * to a skip note, never a hard failure.
 */
export async function fetchPublishedDefinition(
  engineUrl: string,
  name: string,
  options: FetchPublishedOptions = {},
): Promise<Record<string, unknown> | null> {
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.token) {
    const [authName, authValue] = registryAuthHeader(options.token);
    headers[authName] = authValue;
  }
  let base = engineUrl.replace(/\/+$/, "");
  const nodesPath = "/api/workflows/nodes";
  if (base.endsWith(nodesPath)) base = base.slice(0, -nodesPath.length);
  const resp = await fetch(`${base}${nodesPath}/by-name/${encodeURIComponent(name)}`, {
    headers,
    signal: AbortSignal.timeout(options.timeoutMs ?? 10_000),
  });
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`Engine error (HTTP ${resp.status})`);
  return (await resp.json()) as Record<string, unknown>;
}

/** Canonical JSON form for structural comparison (sorted keys, no undefined). */
function canonical(value: unknown): string {
  if (value === null || typeof value !== "object") return JSON.stringify(value) ?? "null";
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, v]) => v !== undefined)
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`);
  return `{${entries.join(",")}}`;
}

/**
 * Mirror the engine's registration-immutability diff, field for field.
 *
 * Compares the fields a registration would carry against the published
 * definition: every shared field except {@link ENGINE_NON_COMPARISON_FIELDS}
 * must be identical for a same-version re-registration to succeed. Keys
 * absent from either side are skipped — the engine drops unknown incoming
 * fields at validation and computed response fields never reach its diff.
 * Mirror of the Python SDK's ``diff_against_published`` (#233).
 *
 * Returns the sorted changed field names (empty when a same-version
 * re-registration would be accepted as ``unchanged``).
 */
export function diffAgainstPublished(
  localPayload: Record<string, unknown>,
  published: Record<string, unknown>,
): string[] {
  return Object.keys(localPayload)
    .filter((key) => !ENGINE_NON_COMPARISON_FIELDS.has(key) && key in published)
    .filter((key) => canonical(localPayload[key]) !== canonical(published[key]))
    .sort();
}
