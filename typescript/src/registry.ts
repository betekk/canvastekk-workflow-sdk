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
 * Wire form for a registry credential (#135) — follows credential type.
 *
 * ``ctk_`` keys ride ``Authorization: Bearer <token>`` (the engine's
 * DA-1949 ctk_ dispatch — an ``X-Service-Token`` carrying a ctk_ value
 * never authenticates). Legacy service tokens keep ``X-Service-Token``
 * byte-identically (dated bridge; the engine's #699 sweep removes that
 * leg later). Mirror of the Python SDK's ``_registry_auth_header``
 * (#134, wheel v0.51.0).
 */
export function registryAuthHeader(serviceToken: string): [string, string] {
  if (serviceToken.startsWith("ctk_")) {
    return ["Authorization", `Bearer ${serviceToken}`];
  }
  return ["X-Service-Token", serviceToken];
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
    apiKey?: string;
    serviceToken?: string;
    tags?: string[];
    invokeConfig?: Record<string, unknown>;
    timeout?: number;
  } = {},
): Promise<RegisterNodeResult> {
  const {
    invokeUrl,
    invokeType = "http",
    apiKey,
    serviceToken,
    tags,
    invokeConfig,
    timeout = 30,
  } = opts;

  if (!apiKey && !serviceToken) {
    throw new Error("Either 'apiKey' or 'serviceToken' must be provided for registration.");
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
  if (serviceToken) {
    const [authName, authValue] = registryAuthHeader(serviceToken);
    headers[authName] = authValue;
  } else if (apiKey) {
    headers["X-API-Key"] = apiKey;
  }

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
