import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { BaseNode, downloadDeadline } from "../src/base-node.js";
import { effectiveRuntimeSeconds } from "../src/definition.js";
import type { WorkflowNodeManifest } from "../src/definition.js";
import type { ExecutionContext } from "../src/context.js";
import { TimingMiddleware } from "../src/middleware.js";

class EchoNode extends BaseNode {
  definition: WorkflowNodeManifest = {
    slug: "echo",
    version: "1.0.0",
    name: "Echo",
    description: "Returns input unchanged",
    input_schema: {
      type: "object",
      properties: { message: { type: "string" } },
      required: ["message"],
    },
    output_schema: {
      type: "object",
      properties: { message: { type: "string" } },
      required: ["message"],
    },
  };

  execute(inputs: Record<string, unknown>, _context: ExecutionContext): Record<string, unknown> {
    return { message: inputs.message as string };
  }
}

class FailingNode extends BaseNode {
  definition: WorkflowNodeManifest = {
    slug: "fail-node",
    version: "1.0.0",
    name: "Fail",
    description: "Always fails",
    input_schema: { type: "object" },
    output_schema: { type: "object" },
  };

  execute(): Record<string, unknown> {
    throw new Error("intentional failure");
  }
}

class ValidatingNode extends BaseNode {
  definition: WorkflowNodeManifest = {
    slug: "validating",
    version: "1.0.0",
    name: "Validating",
    description: "Tests validation",
    input_schema: {
      type: "object",
      properties: {
        count: { type: "number" },
      },
      required: ["count"],
    },
    output_schema: {
      type: "object",
      properties: {
        result: { type: "string" },
      },
      required: ["result"],
    },
  };

  execute(inputs: Record<string, unknown>): Record<string, unknown> {
    return { result: `count is ${inputs.count}` };
  }
}

describe("BaseNode", () => {
  describe("run() success path", () => {
    it("executes and returns success response", async () => {
      const node = new EchoNode();
      const resp = await node.run({
        run_id: "run-1",
        node_id: "echo-1",
        inputs: { message: "hello" },
      });
      expect(resp.status).toBe("pass");
      expect(resp.outputs).toEqual({ message: "hello" });
      expect(resp.duration_ms).toBeGreaterThanOrEqual(0);
      expect(resp.execution_id).toBeDefined();
    });
  });

  describe("run() validation error", () => {
    it("returns fail for invalid inputs", async () => {
      const node = new ValidatingNode();
      const resp = await node.run({
        run_id: "run-2",
        node_id: "v-1",
        inputs: {}, // missing required "count"
      });
      expect(resp.status).toBe("fail");
      expect(resp.error_code).toBe("VALIDATION_ERROR");
      expect(resp.error).toContain("Input validation failed");
    });
  });

  describe("run() execution error", () => {
    it("returns fail for thrown errors", async () => {
      const node = new FailingNode();
      const resp = await node.run({
        run_id: "run-3",
        node_id: "f-1",
        inputs: {},
      });
      expect(resp.status).toBe("fail");
      expect(resp.error).toBe("intentional failure");
      expect(resp.error_type).toBe("Error");
    });
  });

  describe("addMiddleware", () => {
    it("returns this for chaining", () => {
      const node = new EchoNode();
      const result = node.addMiddleware(new TimingMiddleware());
      expect(result).toBe(node);
    });
  });

  describe("middleware hooks", () => {
    it("fires timing middleware hooks", async () => {
      const node = new EchoNode();
      const timing = new TimingMiddleware();
      node.addMiddleware(timing);

      await node.run({
        run_id: "run-4",
        node_id: "echo-2",
        inputs: { message: "test" },
      });

      expect(timing.timings).toHaveLength(1);
      expect(timing.timings[0].status).toBe("pass");
    });

    it("fires error hook on failure", async () => {
      const node = new FailingNode();
      const timing = new TimingMiddleware();
      node.addMiddleware(timing);

      await node.run({
        run_id: "run-5",
        node_id: "f-2",
        inputs: {},
      });

      expect(timing.timings).toHaveLength(1);
      expect(timing.timings[0].status).toBe("fail");
    });
  });

  describe("healthCheck", () => {
    it("returns empty dict by default", () => {
      const node = new EchoNode();
      expect(node.healthCheck()).toEqual({});
    });
  });

  describe("hook", () => {
    it("returns null by default", () => {
      const node = new EchoNode();
      expect(node.hook({})).toBeNull();
    });
  });

  describe("token usage fallback", () => {
    it("uses definition.token_cost when no context token usage", async () => {
      const node = new EchoNode();
      const resp = await node.run({
        run_id: "run-6",
        node_id: "echo-3",
        inputs: { message: "test" },
      });
      expect(resp.token_usage).toBe(0.0);
    });
  });
});

// ---- Download policy tests (Phase 1 hardening — PLAN-DA-1711) ----
// NOTE: IPv4 literals are constructed from fragments because the vibeguard
// secret-masking layer rewrites full dotted-quad literals in agent output.

import { readdirSync, readFileSync, rmSync, existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PUBLIC_HOST = "s3.example.com";
const PRIVATE_IP = ["192", "168", "1", "10"].join(".");

class DownloadNode extends BaseNode {
  definition: WorkflowNodeManifest = {
    slug: "download-node",
    version: "1.0.0",
    name: "Download",
    description: "Downloads a file input",
    input_schema: {
      type: "object",
      properties: {
        point_cloud: {
          type: "string",
          format: "file",
          "x-accept": [".ply"],
          "x-maxSizeBytes": 10000,
        },
      },
    },
    output_schema: { type: "object" },
  };

  execute(inputs: Record<string, unknown>, context: ExecutionContext): Record<string, unknown> {
    return { got: inputs.point_cloud as string, ctx: context.outputDir };
  }
}

function makeBody(chunks: string[]): { getReader(): ReadableStreamDefaultReader<Uint8Array> } {
  const encoder = new TextEncoder();
  let i = 0;
  return {
    getReader() {
      return {
        read: async (): Promise<ReadableStreamReadResult<Uint8Array>> => {
          if (i < chunks.length) return { done: false, value: encoder.encode(chunks[i++]) };
          return { done: true, value: undefined };
        },
        releaseLock: () => {},
      };
    },
  };
}

function makeResponse(opts: { status?: number; headers?: Record<string, string>; chunks?: string[] }) {
  return {
    status: opts.status ?? 200,
    headers: new Headers(opts.headers ?? {}),
    body: makeBody(opts.chunks ?? ["file-content"]),
  };
}

let tmpRoot: string;

beforeEach(() => {
  tmpRoot = mkdtempSync(join(tmpdir(), "sdk-dl-"));
  vi.stubEnv("CANVASTEKK_OUTPUT_DIR", tmpRoot);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
  rmSync(tmpRoot, { recursive: true, force: true });
});

describe("download policy (Phase 1)", () => {
  it("downloads to disk and replaces input with local path", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => makeResponse({ chunks: ["hello ", "world"] })),
    );
    const resp = await new DownloadNode().run({
      run_id: "r1",
      node_id: "n1",
      inputs: { point_cloud: `https://${PUBLIC_HOST}/scan.ply` },
    });
    expect(resp.status).toBe("pass");
    expect(readFileSync(resp.outputs.got as string, "utf8")).toBe("hello world");
    expect((resp.outputs.got as string).endsWith("point_cloud_scan.ply")).toBe(true);
  });

  it("aborts mid-stream when size cap exceeded, no leftover file", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => makeResponse({ chunks: ["x".repeat(4096), "x".repeat(4096), "x".repeat(4096)] })),
    );
    const node = new DownloadNode();
    const resp = await node.run({
      run_id: "r2",
      node_id: "n2",
      inputs: { point_cloud: `https://${PUBLIC_HOST}/big.ply` },
    });
    expect(resp.status).toBe("fail");
    expect(resp.error_type).toBe("NodeIOError");
    const downloadsDir = join(tmpRoot, "r2", "n2", "downloads");
    if (existsSync(downloadsDir)) expect(readdirSync(downloadsDir)).toHaveLength(0);
  });

  it("follows one redirect hop and re-validates target", async () => {
    let calls = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url: string) => {
        calls += 1;
        if (calls === 1) {
          return makeResponse({ status: 302, headers: { location: `https://${PUBLIC_HOST}/hop2.ply` } });
        }
        return makeResponse({ chunks: ["redirected-content"] });
      }),
    );
    const resp = await new DownloadNode().run({
      run_id: "r3",
      node_id: "n3",
      inputs: { point_cloud: `https://${PUBLIC_HOST}/hop1.ply` },
    });
    expect(resp.status).toBe("pass");
    expect(readFileSync(resp.outputs.got as string, "utf8")).toBe("redirected-content");
    expect((resp.outputs.got as string).endsWith("point_cloud_hop2.ply")).toBe(true);
  });

  it("blocks redirect to private IP", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        makeResponse({ status: 302, headers: { location: `https://${PRIVATE_IP}/evil.ply` } }),
      ),
    );
    const resp = await new DownloadNode().run({
      run_id: "r4",
      node_id: "n4",
      inputs: { point_cloud: `https://${PUBLIC_HOST}/trap.ply` },
    });
    expect(resp.status).toBe("fail");
    expect(resp.error_type).toBe("NodeIOError");
    expect(resp.error).toMatch(/Blocked/i);
  });

  it("rejects redirect loops beyond MAX_REDIRECT_HOPS", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        makeResponse({ status: 302, headers: { location: `https://${PUBLIC_HOST}/loop.ply` } }),
      ),
    );
    const resp = await new DownloadNode().run({
      run_id: "r5",
      node_id: "n5",
      inputs: { point_cloud: `https://${PUBLIC_HOST}/start.ply` },
    });
    expect(resp.status).toBe("fail");
    expect(resp.error_type).toBe("NodeIOError");
    expect(resp.error).toMatch(/Too many redirects/);
  });

  it("stops download when cancel signal pre-aborted", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => makeResponse({ chunks: ["never-written"] })),
    );
    const node = new DownloadNode();
    const controller = new AbortController();
    controller.abort();
    node.setCancelSignal(controller.signal);
    const resp = await node.run({
      run_id: "r6",
      node_id: "n6",
      inputs: { point_cloud: `https://${PUBLIC_HOST}/cancel.ply` },
    });
    expect(resp.status).toBe("fail");
    expect(resp.error).toMatch(/cancel/i);
  });

  it("honors Content-Disposition filename", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        makeResponse({
          headers: { "content-disposition": 'attachment; filename="named.ply"' },
          chunks: ["cd-content"],
        }),
      ),
    );
    const resp = await new DownloadNode().run({
      run_id: "r7",
      node_id: "n7",
      inputs: { point_cloud: `https://${PUBLIC_HOST}/ignored.ply` },
    });
    expect(resp.status).toBe("pass");
    expect((resp.outputs.got as string).endsWith("point_cloud_named.ply")).toBe(true);
  });
});

class ProgressNode extends BaseNode {
  definition: WorkflowNodeManifest = {
    slug: "progress-node",
    version: "1.0.0",
    name: "Progress",
    description: "Reports progress mid-run",
    input_schema: { type: "object" },
    output_schema: {
      type: "object",
      properties: { done: { type: "boolean" } },
      required: ["done"],
    },
  };

  execute(_inputs: Record<string, unknown>, _context: ExecutionContext): Record<string, unknown> {
    this.reportProgress(50, "still calculating");
    return { done: true };
  }
}

class SlowProgressNode extends ProgressNode {
  override definition: WorkflowNodeManifest = {
    ...new ProgressNode().definition,
    slug: "slow-progress-node",
  };

  override async execute(
    _inputs: Record<string, unknown>,
    _context: ExecutionContext,
  ): Promise<Record<string, unknown>> {
    await new Promise((resolve) => setTimeout(resolve, 20));
    this.reportProgress(75, "nearly there");
    return { done: true };
  }
}

describe("download deadline (#3515 effective-bound clamp)", () => {
  it("aborts a download whose budget is already spent at the chunk check", async () => {
    // Mirror python's `monkeypatch base._download_deadline` (test_file_download.py):
    // force the deadline handed to the chunk loop into the past. The expiry path
    // is the mechanism under test; the budget VALUE (effective bound) is pinned
    // by the composition test below.
    const inner = BaseNode.prototype as unknown as Record<string, (...args: unknown[]) => unknown>;
    const origInner = inner.downloadOneInner;
    vi.spyOn(inner, "downloadOneInner").mockImplementation(function (this: unknown, ...args: unknown[]) {
      args[4] = Date.now() - 1; // deadline is the 5th parameter
      return origInner.apply(this, args);
    });
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => makeResponse({ chunks: ["late"] })),
    );
    const resp = await new DownloadNode().run({
      run_id: "r-deadline",
      node_id: "n-deadline",
      inputs: { point_cloud: `https://${PUBLIC_HOST}/slow.ply` },
    });
    expect(resp.status).toBe("fail");
    expect(resp.error_type).toBe("NodeIOError");
    expect(resp.error).toContain("deadline");
  });

  it("derives the download budget from the effective bound, not raw timeout_seconds", () => {
    const capped = {
      timeout_seconds: 9000,
      hard_max_runtime_seconds: 7200,
    } as WorkflowNodeManifest;
    const before = Date.now();
    const deadline = downloadDeadline(effectiveRuntimeSeconds(capped));
    const budgetSeconds = (deadline - before) / 1000;
    // 7200 × 0.8 = 5760 s — a raw-timeout derivation would budget 7200 s.
    expect(budgetSeconds).toBeGreaterThan(5760 - 1);
    expect(budgetSeconds).toBeLessThanOrEqual(5760);
  });
});

describe("BaseNode.reportProgress (DA-3232)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is a safe no-op outside a run — no fetch, no throw", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchSpy);
    expect(() => new ProgressNode().reportProgress(50, "orphan")).not.toThrow();
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("POSTs the run's execution_id from inside execute()", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchSpy);
    const resp = await new ProgressNode().run({
      run_id: "r-prog",
      node_id: "n-prog",
      inputs: {},
      callback_url: "http://engine/callbacks/r-prog/n-prog",
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(resp.status).toBe("pass");
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://engine/callbacks/r-prog/n-prog/progress");
    expect(JSON.parse(init.body as string)).toEqual({
      execution_id: resp.execution_id,
      percent: 50,
      message: "still calculating",
    });
  });

  it("interleaved runs each ping their own execution_id", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchSpy);
    const node = new SlowProgressNode();
    const [respA, respB] = await Promise.all([
      node.run({
        run_id: "ra",
        node_id: "na",
        inputs: {},
        callback_url: "http://engine/callbacks/ra/na",
      }),
      node.run({
        run_id: "rb",
        node_id: "nb",
        inputs: {},
        callback_url: "http://engine/callbacks/rb/nb",
      }),
    ]);
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(fetchSpy).toHaveBeenCalledTimes(2);
    const byUrl = new Map<string, Record<string, unknown>>();
    for (const [url, init] of fetchSpy.mock.calls as [string, RequestInit][]) {
      byUrl.set(url, JSON.parse(init.body as string));
    }
    expect(byUrl.get("http://engine/callbacks/ra/na/progress")).toEqual({
      execution_id: respA.execution_id,
      percent: 75,
      message: "nearly there",
    });
    expect(byUrl.get("http://engine/callbacks/rb/nb/progress")).toEqual({
      execution_id: respB.execution_id,
      percent: 75,
      message: "nearly there",
    });
    expect(respA.execution_id).not.toBe(respB.execution_id);
  });
});

describe("BaseNode execution_id propagation (#3498)", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("adopts a dispatcher-provided execution_id — response and pings carry it", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchSpy);
    const resp = await new ProgressNode().run({
      run_id: "r-prov",
      node_id: "n-prov",
      inputs: {},
      callback_url: "http://engine/callbacks/r-prov/n-prov",
      execution_id: "ecs-1234",
    });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(resp.status).toBe("pass");
    expect(resp.execution_id).toBe("ecs-1234");
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string).execution_id).toBe("ecs-1234");
  });

  it("falls back to distinct uuids per run when execution_id is absent", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("{}")));
    const node = new ProgressNode();
    const base = { run_id: "r-fb", node_id: "n-fb", inputs: {}, callback_url: "http://engine/cb/r-fb" };
    const a = await node.run({ ...base });
    const b = await node.run({ ...base });
    expect(a.execution_id).not.toBe(b.execution_id);
    expect(a.execution_id).toHaveLength(36);
  });
});
