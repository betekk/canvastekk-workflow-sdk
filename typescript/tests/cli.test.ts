import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { VERSION } from "../src/version.js";
import { writeFileSync, rmSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

import { buildEngineRequest, probeManifest, cliMain } from "../src/cli.js";
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

  it("honors invokeUrl and nameSuffix", () => {
    const payload = buildEngineRequest(parseManifest(canonicalManifest), {
      invokeUrl: "https://nodes.example.com/echo/execute",
      nameSuffix: "-lambda",
    });
    expect(payload["name"]).toBe("echo-lambda");
    expect(payload["invoke_type"]).toBe("http");
    expect(payload["invoke_url"]).toBe("https://nodes.example.com/echo/execute");
  });

  it("maps sdk constraints and stays within the engine whitelist", () => {
    const payload = buildEngineRequest(
      parseManifest({ ...canonicalManifest, minimum_sdk_version: "0.27.0", docs_url: "https://docs.example.com" }),
    );
    const constraints = payload["constraints"] as Record<string, unknown>;
    expect(constraints.minimum_sdk_version).toBe("0.27.0");
    expect(constraints.docs_url).toBe("https://docs.example.com");
    // DA-3359: the stamped provenance rides along
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
  it("passes a canonical manifest through both probes", () => {
    const report = probeManifest(canonicalManifest);
    expect(report.valid).toBe(true);
    expect(report.probes).toEqual(["manifest", "engine-request-mirror"]);
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
    vi.stubEnv("CANVASTEKK_REGISTRY_TOKEN", "t0ps3cret");
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
    vi.stubEnv("CANVASTEKK_REGISTRY_TOKEN", "");
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

  it("register exits 2 on a malformed --name-suffix", async () => {
    expect(
      await cliMain([
        "register", "--manifest", manifestPath, "--engine-url", "https://eng",
        "--name-suffix", "bad suffix!",
      ]),
    ).toBe(2);
  });
});
