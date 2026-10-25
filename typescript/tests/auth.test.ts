import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { NODE_TOKEN_PREFIX, isNodeToken } from "../src/node-token.js";
import { NodeAuth } from "../src/auth.js";
import type { AuthRequest, AuthMiddleware } from "../src/auth.js";

function makeReq(key?: string): AuthRequest {
  const headers: Record<string, string> = {};
  if (key !== undefined) headers["x-api-key"] = key;
  return { headers };
}

interface RunResult {
  statusCode: number;
  body: unknown;
}

/**
 * Runs middleware to completion — settles when next() fires OR when a
 * status+json response is written (a 401/503 path never calls next()).
 */
async function run(middleware: AuthMiddleware, req: AuthRequest): Promise<RunResult> {
  const result: RunResult = { statusCode: 0, body: undefined };
  await new Promise<void>((resolve) => {
    let settled = false;
    const done = () => {
      if (!settled) {
        settled = true;
        resolve();
      }
    };
    const res = {
      status(code: number) {
        return {
          json(payload: unknown) {
            result.statusCode = code;
            result.body = payload;
            done();
            return undefined;
          },
        };
      },
    };
    middleware(req, res, done);
  });
  return result;
}

const VALID_TOKEN = `${NODE_TOKEN_PREFIX}cGF5bG9hZA.c2lnbmF0dXJl`;

describe("isNodeToken", () => {
  it("accepts prefix + two non-empty segments", () => {
    expect(isNodeToken(VALID_TOKEN)).toBe(true);
  });

  it("rejects plain keys, empty strings, and bare prefixes", () => {
    expect(isNodeToken("legacy-static-key")).toBe(false);
    expect(isNodeToken("")).toBe(false);
    expect(isNodeToken(NODE_TOKEN_PREFIX)).toBe(false);
  });

  it("rejects wrong segment counts", () => {
    expect(isNodeToken(`${NODE_TOKEN_PREFIX}a.b.c`)).toBe(false);
    expect(isNodeToken(`${NODE_TOKEN_PREFIX}onlyone`)).toBe(false);
  });
});

describe("NodeAuth.central", () => {
  const VALID_BODY = {
    valid: true,
    run_id: "run-7",
    node_id: "node-a",
    exp: 9_999_999_999,
  };
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    delete process.env.CANVASTEKK_DEV_MODE;
    delete process.env.CANVASTEKK_API_KEY;
    delete process.env.CANVASTEKK_API_KEY_NEXT;
    process.env.CWE_API_BASE_URL = "http://engine.example";
    fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    delete process.env.CWE_API_BASE_URL;
  });

  it("accepts a valid token and caches the verdict", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify(VALID_BODY), { status: 200 }),
    );
    const middleware = NodeAuth.central();
    const first = await run(middleware, makeReq(VALID_TOKEN));
    const second = await run(middleware, makeReq(VALID_TOKEN));
    expect(first.statusCode).toBe(0);
    expect(second.statusCode).toBe(0);
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls[0][0]).toBe("http://engine.example/api/nodes/verify-token");
  });

  it("rejects a definitive invalid verdict with 401 (cached)", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ valid: false }), { status: 200 }),
    );
    const middleware = NodeAuth.central();
    const first = await run(middleware, makeReq(VALID_TOKEN));
    const second = await run(middleware, makeReq(VALID_TOKEN));
    expect(first.statusCode).toBe(401);
    expect(second.statusCode).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("fails closed with 503 when the verify endpoint is unreachable (not cached)", async () => {
    fetchMock.mockRejectedValueOnce(new Error("network down"));
    fetchMock.mockResolvedValueOnce(
      new Response(JSON.stringify(VALID_BODY), { status: 200 }),
    );
    const middleware = NodeAuth.central();
    const first = await run(middleware, makeReq(VALID_TOKEN));
    const second = await run(middleware, makeReq(VALID_TOKEN));
    expect(first.statusCode).toBe(503);
    expect(second.statusCode).toBe(0);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("answers 503 on malformed verify responses", async () => {
    fetchMock.mockResolvedValue(new Response("<not-json>", { status: 200 }));
    const middleware = NodeAuth.central();
    const res = await run(middleware, makeReq(VALID_TOKEN));
    expect(res.statusCode).toBe(503);
  });

  it("answers 401 when no engine URL is configured and no legacy key matches", async () => {
    delete process.env.CWE_API_BASE_URL;
    const middleware = NodeAuth.central();
    const res = await run(middleware, makeReq(VALID_TOKEN));
    expect(res.statusCode).toBe(401);
    expect((res.body as { detail: string }).detail).toBe("Authentication not configured");
  });

  it("answers 401 when the header is missing", async () => {
    const middleware = NodeAuth.central();
    const res = await run(middleware, makeReq());
    expect(res.statusCode).toBe(401);
  });

  it("accepts the legacy static key during dual-accept (incl. _NEXT rotation)", async () => {
    process.env.CANVASTEKK_API_KEY = "legacy-secret";
    const middleware = NodeAuth.central();
    const res = await run(middleware, makeReq("legacy-secret"));
    expect(res.statusCode).toBe(0);
    expect(fetchMock).not.toHaveBeenCalled();

    delete process.env.CANVASTEKK_API_KEY;
    process.env.CANVASTEKK_API_KEY_NEXT = "rotating-secret";
    const resNext = await run(middleware, makeReq("rotating-secret"));
    expect(resNext.statusCode).toBe(0);
  });

  it("legacy leg inert when env unset — token path proceeds", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ valid: false }), { status: 200 }),
    );
    const middleware = NodeAuth.central();
    const res = await run(middleware, makeReq("legacy-secret"));
    expect(res.statusCode).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("dev mode bypasses everything", async () => {
    process.env.CANVASTEKK_DEV_MODE = "true";
    const middleware = NodeAuth.central();
    const res = await run(middleware, makeReq("anything"));
    expect(res.statusCode).toBe(0);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("central-only mode disables the legacy leg entirely", async () => {
    process.env.CANVASTEKK_API_KEY = "legacy-secret";
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ valid: false }), { status: 200 }),
    );
    const middleware = NodeAuth.central({ legacyKeyEnvVar: null });
    const res = await run(middleware, makeReq("legacy-secret"));
    expect(res.statusCode).toBe(401);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("NodeAuth.apiKey (regression)", () => {
  beforeEach(() => {
    delete process.env.CANVASTEKK_DEV_MODE;
    process.env.CANVASTEKK_API_KEY = "static-key";
  });

  afterEach(() => {
    delete process.env.CANVASTEKK_API_KEY;
  });

  it("still accepts the configured static key", async () => {
    const middleware = NodeAuth.apiKey();
    const res = await run(middleware, makeReq("static-key"));
    expect(res.statusCode).toBe(0);
  });

  it("still rejects a wrong key with 401", async () => {
    const middleware = NodeAuth.apiKey();
    const res = await run(middleware, makeReq("wrong"));
    expect(res.statusCode).toBe(401);
  });
});
