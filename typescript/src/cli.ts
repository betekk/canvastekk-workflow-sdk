/**
 * CLI entrypoint for @betekk/canvastekk-workflow-sdk (DA-2603).
 *
 * Usage:
 *   canvastekk-workflow-sdk register --manifest <file.json|URL> --engine-url URL
 *                                    [--invoke-url URL] [--name-suffix S] [--json]
 *   canvastekk-workflow-sdk probe --manifest <file.json> [--engine-url URL] [--json]
 *
 * register maps the canonical manifest to the engine request vocabulary
 * (name=slug, label=display name; NEVER a client-sent slug key) and POSTs to
 * {engine}/api/workflows/nodes/, then verifies via by-name/{name}. The
 * credential's wire form follows its type (#135): a ctk_ token rides
 * Authorization: Bearer (engine DA-1949); a legacy service token rides
 * X-Service-Token. Read from CANVASTEKK_NODE_REGISTRATION_KEY, never printed.
 *
 * Exit codes: 0 ok · 2 usage · 3 auth (401/403) · 4 other 4xx · 5 5xx/server
 * · 6 network. The token is never printed.
 *
 * probe runs offline by default: zod manifest validation, the engine-request
 * mirror (required keys, no slug key, whitelist), and the host-ceiling
 * check (DA-3499) — strictly stricter than registration: passing here
 * implies registration passes (not biconditional). With --engine-url
 * (#233) it additionally applies the pre-flight registry diff — same
 * failure semantics as the python CLI's ctk probe --engine-url.
 */
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";
import process from "node:process";

import { WorkflowNodeManifestSchema, type WorkflowNodeManifest } from "./definition.js";
import { buildRegistryPayload, registryAuthHeader, fetchPublishedDefinition, diffAgainstPublished } from "./registry.js";
import { versionTuple, compareVersionTuples } from "./diff.js";

const ENGINE_REQUEST_ALLOWED = new Set([
  "name",
  "version",
  "label",
  "description",
  "input_schema",
  "output_schema",
  "invoke_type",
  "invoke_url",
  "invoke_config",
  "category",
  "tags",
  "styles",
  "constraints",
  "token_cost",
  "timeout_seconds",
  "deprecation",
] as const);

const ENGINE_REQUEST_REQUIRED = [
  "name",
  "version",
  "label",
  "description",
  "input_schema",
  "output_schema",
] as const;

const ENGINE_NAME_PATTERN = /^[a-zA-Z0-9_-]+$/;
const ENGINE_CATEGORIES = new Set([
  "control",
  "utility",
  "io",
  "conversion",
  "measurement",
  "geometry",
  "inspection",
  "ai",
  "custom",
] as const);
const ENGINE_MAX_TIMEOUT_SECONDS = 86400;

export interface BuildEngineRequestOptions {
  invokeUrl?: string;
  nameSuffix?: string;
}

/** Map a canonical manifest to the engine registration request (DA-2666 semantics).
 *
 * Delegates the field mapping to the shipped, engine-boundary-tested
 * buildRegistryPayload (single source of truth — the engine request is
 * extra="forbid"), then applies the CLI-only name suffix.
 */
export function buildEngineRequest(
  def: WorkflowNodeManifest,
  opts: BuildEngineRequestOptions = {},
): Record<string, unknown> {
  const payload = buildRegistryPayload(def, { invokeUrl: opts.invokeUrl });
  if (opts.nameSuffix) payload.name = def.slug + opts.nameSuffix;
  return payload;
}

/** Offline registration probes: manifest validity + engine-request mirror. */
export function probeManifest(raw: unknown): {
  valid: boolean;
  errors: string[];
  warnings: string[];
  probes: string[];
  registry_diff?: RegistryDiffReport;
} {
  const errors: string[] = [];
  const warnings: string[] = [];
  const parsed = WorkflowNodeManifestSchema.safeParse(raw);
  if (!parsed.success) {
    for (const issue of parsed.error.issues) {
      errors.push(`${issue.path.join(".")}: ${issue.message}`);
    }
    return { valid: false, errors, warnings, probes: ["manifest", "engine-request-mirror", "host-ceiling"] };
  }
  const payload = buildEngineRequest(parsed.data);
  const missing = ENGINE_REQUEST_REQUIRED.filter((k) => {
    const v = payload[k];
    return v == null || v === "" || (Array.isArray(v) && v.length === 0);
  });
  if (missing.length > 0) errors.push(`Engine request missing required keys: ${missing.join(", ")}`);
  if ("slug" in payload) errors.push("Engine request must not carry a client-set 'slug' key (engine rejects it)");
  const extra = Object.keys(payload).filter((k) => !ENGINE_REQUEST_ALLOWED.has(k as never));
  if (extra.length > 0) errors.push(`Engine request carries keys outside the engine whitelist: ${extra.join(", ")}`);
  if (!ENGINE_CATEGORIES.has(parsed.data.category as never)) {
    errors.push(`category '${parsed.data.category}' is outside the engine's enum`);
  }
  if (parsed.data.timeout_seconds > ENGINE_MAX_TIMEOUT_SECONDS) {
    errors.push(`timeout_seconds ${parsed.data.timeout_seconds} exceeds the engine ceiling 86400`);
  }
  if (parsed.data.timeout_seconds > parsed.data.hard_max_runtime_seconds) {
    errors.push(
      `timeout_seconds ${parsed.data.timeout_seconds} exceeds the node's ` +
        `hard_max_runtime_seconds ${parsed.data.hard_max_runtime_seconds}`,
    );
  }
  if (!ENGINE_NAME_PATTERN.test(String(payload.name))) {
    errors.push(`engine name '${String(payload.name)}' does not match ${ENGINE_NAME_PATTERN}`);
  }
  return {
    valid: errors.length === 0,
    errors,
    warnings,
    probes: ["manifest", "engine-request-mirror", "host-ceiling"],
  };
}

/** Pre-flight registry diff block (#233) — mirrors the Python SDK's matrix. */
export interface RegistryDiffReport {
  status: "skipped" | "new-node" | "unchanged" | "changed" | "newer-version" | "older-version";
  published_version: string | null;
  changed_fields: string[];
}

async function loadManifest(source: string): Promise<unknown> {
  if (/^https?:\/\//.test(source)) {
    const resp = await fetch(source);
    if (!resp.ok) throw new Error(`Fetching manifest from ${source} failed: HTTP ${resp.status}`);
    return resp.json();
  }
  return JSON.parse(readFileSync(source, "utf8"));
}

function flag(args: string[], name: string): string | undefined {
  const i = args.indexOf(name);
  if (i >= 0 && i + 1 < args.length) return args[i + 1];
  const prefix = `${name}=`;
  const hit = args.find((a) => a.startsWith(prefix));
  return hit?.slice(prefix.length);
}

function usage(): number {
  process.stderr.write(
    "Usage: canvastekk-workflow-sdk <command> [options]\n" +
      "  register --manifest <file.json|URL> --engine-url URL [--invoke-url URL] [--name-suffix S] [--json]\n" +
      "  probe --manifest <file.json> [--engine-url URL] [--json]\n",
  );
  return 2;
}

/**
 * Apply the #233 registry diff to a probe report, in place.
 *
 * Behavior matrix (never asserts the bump level — patch/minor/major stays
 * author intent): no flag / no credential / engine error → skip warning,
 * validity unchanged; name not published → new-node pass; same version +
 * identical data → unchanged pass; same version + changed data → fail
 * naming the changed fields (engine 409 node_version_immutable); higher
 * version → pass (+ "bumped but nothing changed" warning when identical);
 * lower version → fail (engine rejects downgrades).
 */
export async function applyRegistryDiff(
  report: { valid: boolean; errors: string[]; warnings: string[]; registry_diff?: RegistryDiffReport },
  payload: Record<string, unknown>,
  engineUrl: string | undefined,
  token: string | undefined,
): Promise<void> {
  report.registry_diff = { status: "skipped", published_version: null, changed_fields: [] };
  if (!engineUrl) {
    report.warnings.push("registry diff skipped (no --engine-url — offline probes only)");
    return;
  }
  if (!token) {
    report.warnings.push("registry diff skipped (no credential: set CANVASTEKK_NODE_REGISTRATION_KEY)");
    return;
  }
  let published: Record<string, unknown> | null;
  try {
    published = await fetchPublishedDefinition(engineUrl, String(payload.name ?? ""), { token });
  } catch (e) {
    report.warnings.push(`registry diff skipped (engine error: ${(e as Error).message})`);
    return;
  }
  if (published === null) {
    report.registry_diff = { status: "new-node", published_version: null, changed_fields: [] };
    return;
  }
  const publishedVersion = String(published.version ?? "");
  const localVersion = String(payload.version ?? "");
  let older: boolean;
  try {
    older = compareVersionTuples(versionTuple(localVersion), versionTuple(publishedVersion)) < 0;
  } catch {
    report.warnings.push(
      `registry diff skipped (unparsable version pair '${localVersion}' vs '${publishedVersion}')`,
    );
    return;
  }
  const changed = diffAgainstPublished(payload, published).filter((f) => f !== "version");
  if (older) {
    report.registry_diff = { status: "older-version", published_version: publishedVersion, changed_fields: changed };
    report.valid = false;
    report.errors.push(
      `version ${localVersion} is older than published ${publishedVersion} — ` +
        "the engine rejects downgrades (publish a higher semver)",
    );
  } else if (localVersion === publishedVersion) {
    report.registry_diff = {
      status: changed.length === 0 ? "unchanged" : "changed",
      published_version: publishedVersion,
      changed_fields: changed,
    };
    if (changed.length > 0) {
      report.valid = false;
      report.errors.push(
        `definition data changed but version is still ${localVersion} ` +
          `(changed: ${changed.join(", ")}) — bump the version before deploying`,
      );
    }
  } else {
    report.registry_diff = { status: "newer-version", published_version: publishedVersion, changed_fields: changed };
    if (changed.length === 0) {
      report.warnings.push(
        `version bumped ${publishedVersion} -> ${localVersion} but definition data is identical — intentional?`,
      );
    }
  }
}

async function runRegister(args: string[]): Promise<number> {
  const manifestSource = flag(args, "--manifest");
  const engineUrl = flag(args, "--engine-url");
  if (!manifestSource || !engineUrl) return usage();

  const token = (process.env.CANVASTEKK_NODE_REGISTRATION_KEY ?? process.env.CANVASTEKK_REGISTRY_TOKEN) ?? "";
  if (!token) {
    process.stderr.write("Error: CANVASTEKK_NODE_REGISTRATION_KEY is not set (service credential)\n");
    return 2;
  }

  const nameSuffix = flag(args, "--name-suffix") ?? "";
  if (nameSuffix && !ENGINE_NAME_PATTERN.test(nameSuffix)) {
    process.stderr.write(`Error: --name-suffix '${nameSuffix}' does not match ${ENGINE_NAME_PATTERN}\n`);
    return 2;
  }

  const useJson = args.includes("--json");
  const exit = (code: number, message: string, extra: Record<string, unknown> = {}): number => {
    const stream = code === 0 ? process.stdout : process.stderr;
    if (useJson) {
      process.stdout.write(JSON.stringify({ ok: code === 0, message, ...extra }, null, 2) + "\n");
    } else {
      stream.write(message + "\n");
    }
    return code;
  };

  let raw: unknown;
  try {
    raw = await loadManifest(manifestSource);
  } catch (e) {
    return exit(2, `Error loading manifest: ${(e as Error).message}`);
  }
  const probe = probeManifest(raw);
  if (!probe.valid) {
    return exit(4, `Manifest failed registration probes: ${probe.errors.join("; ")}`);
  }
  const parsed = WorkflowNodeManifestSchema.parse(raw);
  const payload = buildEngineRequest(parsed, {
    invokeUrl: flag(args, "--invoke-url"),
    nameSuffix,
  });
  const base = engineUrl.replace(/\/+$/, "") + "/api/workflows/nodes/";
  const [authName, authValue] = registryAuthHeader(token);
  const headers = { "Content-Type": "application/json", [authName]: authValue };

  let resp: Response;
  try {
    resp = await fetch(base, { method: "POST", headers, body: JSON.stringify(payload) });
  } catch (e) {
    return exit(6, `Network error reaching ${base}: ${(e as Error).message}`);
  }
  if (resp.status === 401 || resp.status === 403) {
    return exit(3, `Auth failed (HTTP ${resp.status}) for ${String(payload.name)}`);
  }
  if (resp.status >= 500) {
    const detail = (await resp.text()).slice(0, 300);
    return exit(5, `Engine error (HTTP ${resp.status}): ${detail}`);
  }
  if (resp.status >= 400) {
    const detail = (await resp.text()).slice(0, 300);
    return exit(4, `Rejected (HTTP ${resp.status}): ${detail}`);
  }

  let nodeId = "";
  try {
    const byName = await fetch(base + "by-name/" + encodeURIComponent(String(payload.name)), { headers });
    if (byName.ok) nodeId = ((await byName.json()) as { id?: string }).id ?? "";
  } catch {
    nodeId = "";
  }
  return exit(0, `Registered ${String(payload.name)} v${String(payload.version)}`, { id: nodeId });
}

async function runProbe(args: string[]): Promise<number> {
  const manifestSource = flag(args, "--manifest");
  if (!manifestSource || /^https?:\/\//.test(manifestSource)) return usage();

  const useJson = args.includes("--json");
  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(manifestSource, "utf8"));
  } catch (e) {
    if (useJson) {
      process.stdout.write(JSON.stringify({ valid: false, errors: [(e as Error).message] }, null, 2) + "\n");
    } else {
      process.stderr.write(`Error loading manifest: ${(e as Error).message}\n`);
    }
    return 2;
  }
  const report = probeManifest(raw);
  const engineUrl = flag(args, "--engine-url");
  const token = (process.env.CANVASTEKK_NODE_REGISTRATION_KEY ?? process.env.CANVASTEKK_REGISTRY_TOKEN) ?? "";
  if (engineUrl && WorkflowNodeManifestSchema.safeParse(raw).success) {
    const parsed = WorkflowNodeManifestSchema.parse(raw);
    await applyRegistryDiff(report, buildEngineRequest(parsed), engineUrl, token || undefined);
  } else if (engineUrl) {
    report.registry_diff = { status: "skipped", published_version: null, changed_fields: [] };
  }
  if (useJson) {
    process.stdout.write(JSON.stringify(report, null, 2) + "\n");
  } else {
    process.stdout.write(
      report.valid ? "PASS: manifest passes all registration probes\n" : "FAIL: manifest has errors\n",
    );
    for (const err of report.errors) process.stdout.write(`  ERROR: ${err}\n`);
    for (const warn of report.warnings) process.stdout.write(`  WARN: ${warn}\n`);
    if (report.registry_diff) {
      process.stdout.write(
        `  Registry diff: ${report.registry_diff.status}` +
          (report.registry_diff.published_version
            ? ` (published ${report.registry_diff.published_version})`
            : "") +
          (report.registry_diff.changed_fields.length > 0
            ? ` — changed: ${report.registry_diff.changed_fields.join(", ")}`
            : "") +
          "\n",
      );
    }
  }
  return report.valid ? 0 : 1;
}

export async function cliMain(argv: string[] = process.argv.slice(2)): Promise<number> {
  const [cmd, ...rest] = argv;
  if (cmd === "register") return runRegister(rest);
  if (cmd === "probe") return runProbe(rest);
  return usage();
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  cliMain().then((code) => process.exit(code));
}
