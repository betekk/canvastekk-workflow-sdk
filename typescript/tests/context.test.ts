import { describe, it, expect, afterEach, vi } from "vitest";
import { existsSync, rmSync } from "node:fs";
import { join } from "node:path";
import { ExecutionContext } from "../src/context.js";

describe("ExecutionContext", () => {
  const testDir = "/tmp/sdk-test-context";

  afterEach(() => {
    if (existsSync(testDir)) {
      rmSync(testDir, { recursive: true, force: true });
    }
  });

  it("creates output directory on construction", () => {
    const ctx = new ExecutionContext({ outputDir: join(testDir, "run-1/node-1") });
    expect(existsSync(ctx.outputDir)).toBe(true);
  });

  it("uses CANVASTEKK_OUTPUT_DIR env var", () => {
    process.env.CANVASTEKK_OUTPUT_DIR = testDir;
    const ctx = new ExecutionContext({ runId: "run-1", nodeId: "node-1" });
    expect(ctx.outputDir).toBe(join(testDir, "run-1", "node-1"));
    delete process.env.CANVASTEKK_OUTPUT_DIR;
  });

  it("defaults to /tmp when no env var", () => {
    delete process.env.CANVASTEKK_OUTPUT_DIR;
    const ctx = new ExecutionContext({ runId: "r", nodeId: "n" });
    expect(ctx.outputDir).toContain("/tmp/");
    expect(ctx.outputDir).toContain("r");
    expect(ctx.outputDir).toContain("n");
  });

  it("extracts runId from request", () => {
    const ctx = new ExecutionContext({
      request: { run_id: "run-abc", node_id: "node-1", inputs: {} },
    });
    expect(ctx.runId).toBe("run-abc");
  });

  it("extracts nodeId from request", () => {
    const ctx = new ExecutionContext({
      request: { run_id: "run-abc", node_id: "node-1", inputs: {} },
    });
    expect(ctx.nodeId).toBe("node-1");
  });

  it("returns outputPath with filename", () => {
    const ctx = new ExecutionContext({ outputDir: join(testDir, "run-1/node-1") });
    expect(ctx.outputPath("result.json")).toBe(join(testDir, "run-1/node-1/result.json"));
  });

  it("lazily creates downloadsDir", () => {
    const ctx = new ExecutionContext({ outputDir: join(testDir, "run-2/node-2") });
    expect(existsSync(join(testDir, "run-2/node-2/downloads"))).toBe(false);
    const dlDir = ctx.downloadsDir;
    expect(existsSync(dlDir)).toBe(true);
    expect(dlDir).toContain("downloads");
  });

  it("tracks metadata", () => {
    const ctx = new ExecutionContext({ outputDir: join(testDir, "run-3/node-3") });
    ctx.metadata["key"] = "value";
    expect(ctx.metadata["key"]).toBe("value");
  });

  it("records token usage", () => {
    const ctx = new ExecutionContext({ outputDir: join(testDir, "run-4/node-4") });
    ctx.recordTokenUsage({ promptTokens: 10, completionTokens: 5, totalTokens: 15 });
    expect(ctx.tokenUsage).toEqual({
      prompt_tokens: 10,
      completion_tokens: 5,
      total_tokens: 15,
    });
  });

  it("token_usage returns a copy", () => {
    const ctx = new ExecutionContext({ outputDir: join(testDir, "run-5/node-5") });
    ctx.recordTokenUsage({ totalTokens: 100 });
    const usage = ctx.tokenUsage;
    usage.total_tokens = 999;
    expect(ctx.tokenUsage.total_tokens).toBe(100);
  });

  it("reportProgress does not throw", () => {
    const ctx = new ExecutionContext({ outputDir: join(testDir, "run-6/node-6") });
    expect(() => ctx.reportProgress(0.5, "halfway")).not.toThrow();
  });

  it("executionId defaults to null and accepts an explicit value", () => {
    const ctxA = new ExecutionContext({ outputDir: join(testDir, "run-7/node-7") });
    expect(ctxA.executionId).toBeNull();
    const ctxB = new ExecutionContext({ executionId: "exec-123" });
    expect(ctxB.executionId).toBe("exec-123");
  });
});

describe("ExecutionContext progress ping (DA-3232)", () => {
  const testDir = "/tmp/sdk-test-context-ping";
  const baseRequest = {
    run_id: "run-abc",
    node_id: "node-1",
    inputs: {},
  };

  const flush = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

  afterEach(() => {
    vi.unstubAllGlobals();
    if (existsSync(testDir)) rmSync(testDir, { recursive: true, force: true });
  });

  it("no-op without callback_url — fetch never called", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchSpy);
    const ctx = new ExecutionContext({
      request: { ...baseRequest, callback_url: null },
      executionId: "exec-1",
      outputDir: join(testDir, "n1"),
    });
    expect(() => ctx.reportProgress(0.5, "halfway")).not.toThrow();
    await flush();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("no-op without execution_id even when callback_url present", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchSpy);
    const ctx = new ExecutionContext({
      request: { ...baseRequest, callback_url: "http://engine/callbacks/run-abc/node-1" },
      outputDir: join(testDir, "n2"),
    });
    expect(() => ctx.reportProgress(0.5)).not.toThrow();
    await flush();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("happy path — POSTs execution_id, percent and message to callback_url/progress", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchSpy);
    const ctx = new ExecutionContext({
      request: { ...baseRequest, callback_url: "http://engine/callbacks/run-abc/node-1" },
      executionId: "exec-42",
      outputDir: join(testDir, "n3"),
    });
    ctx.reportProgress(0.5, "halfway");
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://engine/callbacks/run-abc/node-1/progress");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      execution_id: "exec-42",
      percent: 50,
      message: "halfway",
    });
  });

  it("omits message key when message is empty", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchSpy);
    const ctx = new ExecutionContext({
      request: { ...baseRequest, callback_url: "http://engine/cb" },
      executionId: "exec-43",
      outputDir: join(testDir, "n4"),
    });
    ctx.reportProgress(0.25);
    await flush();
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      execution_id: "exec-43",
      percent: 25,
    });
  });

  it("clamps percent above 100 and truncates message to the payload cap", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchSpy);
    const ctx = new ExecutionContext({
      request: { ...baseRequest, callback_url: "http://engine/cb" },
      executionId: "exec-44",
      outputDir: join(testDir, "n5"),
    });
    ctx.reportProgress(1.5, "x".repeat(1500));
    await flush();
    const [, init] = fetchSpy.mock.calls[0] as [string, RequestInit];
    const body = JSON.parse(init.body as string);
    expect(body.percent).toBe(100);
    expect((body.message as string).length).toBe(1000);
  });

  it("normalizes a trailing slash on callback_url", async () => {
    const fetchSpy = vi.fn(async () => new Response("{}"));
    vi.stubGlobal("fetch", fetchSpy);
    const ctx = new ExecutionContext({
      request: { ...baseRequest, callback_url: "http://engine/cb/" },
      executionId: "exec-46",
      outputDir: join(testDir, "n7"),
    });
    ctx.reportProgress(1);
    await flush();
    const [url] = fetchSpy.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://engine/cb/progress");
  });

  it("swallows transport errors — never throws, never unhandled", async () => {
    const warnings: string[] = [];
    const fetchSpy = vi.fn(async () => {
      throw new Error("engine unreachable");
    });
    vi.stubGlobal("fetch", fetchSpy);
    const ctx = new ExecutionContext({
      request: { ...baseRequest, callback_url: "http://engine/cb" },
      executionId: "exec-45",
      outputDir: join(testDir, "n6"),
    });
    // Reach into the private logger to observe the warn swallow.
    (ctx as unknown as { _logger: { info: (m: string) => void; warn: (m: string) => void } })._logger = {
      info: () => {},
      warn: (m: string) => warnings.push(m),
    };
    expect(() => ctx.reportProgress(0.5, "msg")).not.toThrow();
    await flush();
    await flush();
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(warnings.length).toBe(1);
    expect(warnings[0]).toContain("Progress ping failed");
  });
});
