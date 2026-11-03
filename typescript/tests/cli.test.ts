import { describe, it, expect, vi, beforeEach, afterEach, beforeAll } from "vitest";
import { VERSION } from "../src/version.js";
import { writeFileSync, rmSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { buildEngineRequest, probeManifest, cliMain, applyRegistryDiff } from "../src/cli.js";
import { WorkflowNodeManifestSchema } from "../src/definition.js";

const canonicalManifest = {
  slug: "echo",
  version: "1.0.0",
  name: "Echo",
  description: "Echo node",
  input_schema: { type: "object" },
  output_schema: { type: "object" },
  role: "operation",
};

const dir = mkdtempSync(join(tmpdir(), "sdk-cli-"));
const manifestPath = join(dir, "manifest.json");
writeFileSync(manifestPath, JSON.stringify(canonicalManifest));

const legacyManifest = {
  name: "echo",
  title: "Echo",
  version: "1.0.0",
  description: "Echo node",
  input_schema: { type: "object" },
  output_schema: { type: "object" },
  role: "operation",
};

function parseManifest(raw: unknown) {
  return WorkflowNodeManifestSchema.parse(raw);
}

describe("buildEngineRequest (DA-2603)", () => {
  it("maps manifest slug/name to engine name/label, never a slug key", () => {
    const payload = buildEngineRequest(parseManifest(canonicalManifest));
    expect(payload["name"]).toBe("echo");
    expect(payload["label"]).toBe("Echo");
    expect(payload["description"]).toBe("Echo node");
    expect("slug" in payload).toBe(false);
  });

  it("never carries the host-side ceiling into the engine request (DA-3609)", () => {
    const payload = buildEngineRequest(
      parseManifest({ ...canonicalManifest, hard_max_runtime_seconds: 3600 }),
    );
    expect("hard_max_runtime_seconds" in payload).toBe(false);
  });

  it("honors invokeUrl and nameSuffix", () => {
    const payload = buildEngineRequest(parseManifest(canonicalManifest), {
      invokeUrl: "https://nodes.example.com/echo/execute",
      nameSuffix: "-lambda",
    });
    expect(payload["name"]).toBe("echo-lambda");
    expect(payload["invoke_type"]).toBe("http");
    expect(payload["invoke_url"]).toBe("https://nodes.example.com/echo/execute");
  });

  it("carries the declared contract inside constraints (D8 #110)", () => {
    const withContract = parseManifest({
      ...canonicalManifest,
      contract: { routes: ["/execute", "/health", "/manifest"] },
    });
    const payload = buildEngineRequest(withContract);
    const constraints = payload["constraints"] as Record<string, unknown>;
    const contract = constraints["contract"] as Record<string, unknown>;
    expect(contract["routes"]).toEqual(["/execute", "/health", "/manifest"]);
    expect(contract["transport"]).toBe("http");
    expect(contract["openapi"]).toBe("3.2");
    expect(payload["contract"]).toBeUndefined();
  });

  it("omits contract when undeclared (D8 #110)", () => {
    const payload = buildEngineRequest(parseManifest(canonicalManifest));
    const constraints = payload["constraints"] as Record<string, unknown>;
    expect(constraints["contract"]).toBeUndefined();
  });

  it("maps sdk constraints and stays within the engine whitelist (#123: version keys stripped)", () => {
    const payload = buildEngineRequest(
      parseManifest({ ...canonicalManifest, minimum_sdk_version: "0.27.0", docs_url: "https://docs.example.com" }),
    );
    const constraints = payload["constraints"] as Record<string, unknown>;
    expect(constraints).not.toHaveProperty("minimum_sdk_version");
    expect(constraints.docs_url).toBe("https://docs.example.com");
    expect(constraints.sdk_version).toBe(VERSION);
    const allowed = new Set([
      "name", "version", "label", "description", "input_schema", "output_schema",
      "invoke_type", "invoke_url", "invoke_config", "category", "tags", "styles",
      "constraints", "token_cost", "timeout_seconds", "deprecation",
    ]);
    for (const key of Object.keys(payload)) expect(allowed.has(key)).toBe(true);
  });
});

describe("probeManifest (DA-2603, offline)", () => {
  it("passes a canonical manifest through all three probes", () => {
    const report = probeManifest(canonicalManifest);
    expect(report.valid).toBe(true);
    expect(report.probes).toEqual(["manifest", "engine-request-mirror", "host-ceiling"]);
  });

  it("accepts a legacy manifest via the SDK compat layer", () => {
    const report = probeManifest(legacyManifest);
    expect(report.valid).toBe(true);
  });

  it("fails a broken schema", () => {
    const report = probeManifest({ ...canonicalManifest, version: "not-semver" });
    expect(report.valid).toBe(false);
    expect(report.errors.length).toBeGreaterThan(0);
  });
});

describe("cliMain register (DA-2603)", () => {
  const realFetch = globalThis.fetch;

  function mockFetch(status: number, body: unknown = {}) {
    return vi.fn(async () => new Response(JSON.stringify(body), { status })) as unknown as typeof fetch;
  }

  beforeEach(() => {
    vi.stubEnv("CANVASTEKK_NODE_REGISTRATION_KEY", "t0ps3cret");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    globalThis.fetch = realFetch;
  });

  afterAll(() => rmSync(dir, { recursive: true, force: true }));

  it("exit 2 without engine url", async () => {
    expect(await cliMain(["register", "--manifest", manifestPath])).toBe(2);
  });

  it("exit 2 without token", async () => {
    vi.stubEnv("CANVASTEKK_NODE_REGISTRATION_KEY", "");
    expect(
      await cliMain(["register", "--manifest", manifestPath, "--engine-url", "https://eng"]),
    ).toBe(2);
  });

  it("exit 0 on success, verifying by-name", async () => {
    const fetchMock = vi.fn(async (input: unknown) => {
      const url = String(input);
      return url.includes("by-name/")
        ? new Response(JSON.stringify({ id: "node-1" }), { status: 200 })
        : new Response("{}", { status: 201 });
    }) as unknown as typeof fetch;
    globalThis.fetch = fetchMock;
    expect(
      await cliMain(["register", "--manifest", manifestPath, "--engine-url", "https://eng"]),
    ).toBe(0);
    const calls = (fetchMock as unknown as { mock: { calls: unknown[][] } }).mock.calls.map(
      (c) => String(c[0]),
    );
    expect(calls[0]).toBe("https://eng/api/workflows/nodes/");
    expect(calls[1]).toBe("https://eng/api/workflows/nodes/by-name/echo");
  });

  it("exit 3 on auth failure (token never printed)", async () => {
    globalThis.fetch = mockFetch(401);
    const err = vi.spyOn(process.stderr, "write").mockReturnValue(true);
    expect(
      await cliMain(["register", "--manifest", manifestPath, "--engine-url", "https://eng"]),
    ).toBe(3);
    const written = err.mock.calls.map((c) => String(c[0])).join("");
    expect(written).not.toContain("t0ps3cret");
    err.mockRestore();
  });

  it("exit 4 on 4xx rejection", async () => {
    globalThis.fetch = mockFetch(422, { detail: "slug" });
    const err = vi.spyOn(process.stderr, "write").mockReturnValue(true);
    expect(
      await cliMain(["register", "--manifest", manifestPath, "--engine-url", "https://eng"]),
    ).toBe(4);
    err.mockRestore();
  });

  it("exit 6 on network error", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch;
    expect(
      await cliMain(["register", "--manifest", manifestPath, "--engine-url", "https://eng"]),
    ).toBe(6);
  });
});

describe("probeManifest value domain (DA-2603 review)", () => {
  it("rejects a category outside the engine enum", () => {
    const report = probeManifest({ ...canonicalManifest, category: "transform" });
    expect(report.valid).toBe(false);
    expect(report.errors.some((e) => e.includes("category"))).toBe(true);
  });

  it("rejects timeout over the engine ceiling", () => {
    const report = probeManifest({ ...canonicalManifest, timeout_seconds: 100000 });
    expect(report.valid).toBe(false);
    expect(report.errors.some((e) => e.includes("timeout_seconds"))).toBe(true);
  });

  it("rejects a budget over the node's own hard ceiling (DA-3609)", () => {
    const report = probeManifest({ ...canonicalManifest, timeout_seconds: 7201 });
    expect(report.valid).toBe(false);
    expect(report.errors.some((e) => e.includes("hard_max_runtime_seconds 7200"))).toBe(true);
    expect(report.probes).toEqual(["manifest", "engine-request-mirror", "host-ceiling"]);
  });

  it("accepts a budget exactly at the hard ceiling (DA-3609)", () => {
    const report = probeManifest({ ...canonicalManifest, timeout_seconds: 7200 });
    expect(report.valid).toBe(true);
  });

  it("register exits 2 on a malformed --name-suffix", async () => {
    expect(
      await cliMain([
        "register", "--manifest", manifestPath, "--engine-url", "https://eng",
        "--name-suffix", "bad suffix!",
      ]),
    ).toBe(2);
  });
});

describe("applyRegistryDiff — probe --engine-url (#233)", () => {
  const realFetch = globalThis.fetch;
  const diffDir = mkdtempSync(join(tmpdir(), "sdk-cli-diff-"));
  const diffManifestPath = join(diffDir, "manifest.json");
  beforeAll(() => writeFileSync(diffManifestPath, JSON.stringify(canonicalManifest)));
  afterAll(() => rmSync(diffDir, { recursive: true, force: true }));
  afterEach(() => {
    globalThis.fetch = realFetch;
    vi.unstubAllEnvs();
  });

  function payload(version = "1.9.1", timeout_seconds = 7200) {
    const manifest = { ...canonicalManifest, version, timeout_seconds };
    return buildEngineRequest(parseManifest(manifest));
  }

  function engine(body: unknown | null) {
    return vi.fn(async () =>
      body === null ? new Response("{}", { status: 404 }) : new Response(JSON.stringify(body), { status: 200 }),
    ) as unknown as typeof fetch;
  }

  function published(version: string, timeout_seconds = 3600) {
    return {
      name: "echo",
      label: "Echo",
      version,
      timeout_seconds,
      description: "Echo node",
      input_schema: { type: "object" },
      output_schema: { type: "object" },
    };
  }

  it("no engine-url skips with warning", async () => {
    const report = probeManifest(canonicalManifest);
    await applyRegistryDiff(report, payload(), undefined, "ctk_x");
    expect(report.valid).toBe(true);
    expect(report.registry_diff?.status).toBe("skipped");
    expect(report.warnings.some((w) => w.includes("no --engine-url"))).toBe(true);
  });

  it("missing token skips with warning", async () => {
    const report = probeManifest(canonicalManifest);
    await applyRegistryDiff(report, payload(), "https://eng", undefined);
    expect(report.valid).toBe(true);
    expect(report.warnings.some((w) => w.includes("CANVASTEKK_NODE_REGISTRATION_KEY"))).toBe(true);
  });

  it("engine error skips without failing", async () => {
    globalThis.fetch = vi.fn(async () => {
      throw new Error("boom");
    }) as unknown as typeof fetch;
    const report = probeManifest(canonicalManifest);
    await applyRegistryDiff(report, payload(), "https://eng", "ctk_x");
    expect(report.valid).toBe(true);
    expect(report.registry_diff?.status).toBe("skipped");
    expect(report.warnings.some((w) => w.includes("engine error"))).toBe(true);
  });

  it("new node passes", async () => {
    globalThis.fetch = engine(null);
    const report = probeManifest(canonicalManifest);
    await applyRegistryDiff(report, payload(), "https://eng", "ctk_x");
    expect(report.valid).toBe(true);
    expect(report.registry_diff?.status).toBe("new-node");
  });

  it("same version, identical data passes unchanged", async () => {
    globalThis.fetch = engine(published("1.9.1", 7200));
    const report = probeManifest(canonicalManifest);
    await applyRegistryDiff(report, payload(), "https://eng", "ctk_x");
    expect(report.valid).toBe(true);
    expect(report.registry_diff?.status).toBe("unchanged");
  });

  it("same version, changed data fails naming fields", async () => {
    globalThis.fetch = engine(published("1.9.1", 3600));
    const report = probeManifest(canonicalManifest);
    await applyRegistryDiff(report, payload(), "https://eng", "ctk_x");
    expect(report.valid).toBe(false);
    expect(report.registry_diff?.status).toBe("changed");
    expect(report.registry_diff?.changed_fields).toContain("timeout_seconds");
    expect(report.errors.some((e) => e.includes("bump the version"))).toBe(true);
  });

  it("newer version with changed data passes", async () => {
    globalThis.fetch = engine(published("1.9.0", 3600));
    const report = probeManifest(canonicalManifest);
    await applyRegistryDiff(report, payload(), "https://eng", "ctk_x");
    expect(report.valid).toBe(true);
    expect(report.registry_diff?.status).toBe("newer-version");
  });

  it("newer version with identical data warns but passes", async () => {
    globalThis.fetch = engine(published("1.9.0", 7200));
    const report = probeManifest(canonicalManifest);
    await applyRegistryDiff(report, payload(), "https://eng", "ctk_x");
    expect(report.valid).toBe(true);
    expect(report.warnings.some((w) => w.includes("identical — intentional?"))).toBe(true);
  });

  it("older version fails", async () => {
    globalThis.fetch = engine(published("2.0.0"));
    const report = probeManifest(canonicalManifest);
    await applyRegistryDiff(report, payload(), "https://eng", "ctk_x");
    expect(report.valid).toBe(false);
    expect(report.registry_diff?.status).toBe("older-version");
    expect(report.errors.some((e) => e.includes("older than published"))).toBe(true);
  });

  it("cliMain probe --engine-url exits 1 on same-version drift", async () => {
    vi.stubEnv("CANVASTEKK_NODE_REGISTRATION_KEY", "ctk_x");
    globalThis.fetch = engine(published("1.0.0", 3600));
    expect(await cliMain(["probe", "--manifest", diffManifestPath, "--engine-url", "https://eng"])).toBe(1);
  });
});
