import { describe, it, expect } from "vitest";
import { LoggingMiddleware, TimingMiddleware, SDKVersionMiddleware } from "../src/middleware.js";
import { ExecutionContext } from "../src/context.js";

function makeContext(): ExecutionContext {
  return new ExecutionContext({ outputDir: "/tmp/mw-test", run_id: "run-1", node_id: "node-1" });
}

describe("LoggingMiddleware", () => {
  it("onBeforeExecute returns inputs unchanged", () => {
    const mw = new LoggingMiddleware();
    const ctx = makeContext();
    const inputs = { message: "hello" };
    const result = mw.onBeforeExecute(inputs, ctx);
    expect(result).toEqual(inputs);
  });

  it("onAfterExecute does not throw", () => {
    const mw = new LoggingMiddleware();
    const ctx = makeContext();
    expect(() => mw.onAfterExecute({}, {}, ctx, 100)).not.toThrow();
  });

  it("onError does not throw", () => {
    const mw = new LoggingMiddleware();
    const ctx = makeContext();
    expect(() => mw.onError({}, new Error("test"), ctx, 50)).not.toThrow();
  });
});

describe("TimingMiddleware", () => {
  it("records pass timing", () => {
    const mw = new TimingMiddleware();
    const ctx = makeContext();
    mw.onAfterExecute({}, { result: "ok" }, ctx, 42);
    expect(mw.timings).toHaveLength(1);
    expect(mw.timings[0].status).toBe("pass");
    expect(mw.timings[0].duration_ms).toBe(42);
  });

  it("records fail timing", () => {
    const mw = new TimingMiddleware();
    const ctx = makeContext();
    mw.onError({}, new Error("fail"), ctx, 100);
    expect(mw.timings).toHaveLength(1);
    expect(mw.timings[0].status).toBe("fail");
    expect(mw.timings[0].error_type).toBe("Error");
  });

  it("accumulates multiple timings", () => {
    const mw = new TimingMiddleware();
    const ctx = makeContext();
    mw.onAfterExecute({}, {}, ctx, 10);
    mw.onAfterExecute({}, {}, ctx, 20);
    mw.onError({}, new Error("x"), ctx, 30);
    expect(mw.timings).toHaveLength(3);
  });

  it("onBeforeExecute passes through inputs", () => {
    const mw = new TimingMiddleware();
    const ctx = makeContext();
    const inputs = { x: 1 };
    expect(mw.onBeforeExecute(inputs, ctx)).toEqual(inputs);
  });
});

describe("SDKVersionMiddleware", () => {
  it("sets X-SDK-Version header", () => {
    const mw = new SDKVersionMiddleware("0.13.0");
    const handler = mw.handler();
    const res = {
      setHeader: vi.fn(),
    };
    handler({}, res as unknown as { setHeader: (k: string, v: string) => void }, vi.fn());
    expect(res.setHeader).toHaveBeenCalledWith("X-SDK-Version", "0.13.0");
  });
});

describe("node slug header (DA-3359)", () => {
  it("stamps X-Canvastekk-Node-Slug when provided", () => {
    const mw = new SDKVersionMiddleware("0.37.0", "echo-lambda");
    const headers: Record<string, string> = {};
    mw.handler()({} as never, { setHeader: (k: string, v: string) => { headers[k] = v; } }, () => {});
    expect(headers["X-SDK-Version"]).toBe("0.37.0");
    expect(headers["X-Canvastekk-Node-Slug"]).toBe("echo-lambda");
  });

  it("omits the slug header when absent", () => {
    const mw = new SDKVersionMiddleware("0.37.0");
    const headers: Record<string, string> = {};
    mw.handler()({} as never, { setHeader: (k: string, v: string) => { headers[k] = v; } }, () => {});
    expect(headers["X-SDK-Version"]).toBe("0.37.0");
    expect(headers).not.toHaveProperty("X-Canvastekk-Node-Slug");
  });
});
