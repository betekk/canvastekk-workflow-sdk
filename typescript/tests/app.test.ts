import { describe, it, expect } from "vitest";
import request from "supertest";
import { createNodeApp } from "../src/app.js";
import { writeFileSync } from "node:fs";
import { BaseNode } from "../src/base-node.js";
import type { WorkflowNodeManifest } from "../src/definition.js";
import type { ExecutionContext } from "../src/context.js";
import { NodeAuth } from "../src/auth.js";

class TestNode extends BaseNode {
  definition: WorkflowNodeManifest = {
    slug: "test-node",
    version: "1.0.0",
    name: "Test Node",
    description: "A test node",
    input_schema: {
      type: "object",
      properties: { message: { type: "string" } },
    },
    output_schema: {
      type: "object",
      properties: { result: { type: "string" } },
    },
  };

  execute(inputs: Record<string, unknown>, _context: ExecutionContext): Record<string, unknown> {
    return { result: `echo: ${inputs.message ?? ""}` };
  }
}

class HealthCheckNode extends BaseNode {
  definition: WorkflowNodeManifest = {
    slug: "health-node",
    version: "2.0.0",
    name: "Health Node",
    description: "Node with health checks",
    input_schema: { type: "object" },
    output_schema: { type: "object" },
  };

  execute(): Record<string, unknown> {
    return {};
  }

  healthCheck(): Record<string, boolean> {
    return { db: true, cache: false };
  }
}

describe("Express endpoints", () => {
  const node = new TestNode();
  const app = createNodeApp(node);

  describe("POST /execute", () => {
    it("executes successfully", async () => {
      const resp = await request(app)
        .post("/execute")
        .send({ run_id: "run-1", node_id: "test-1", inputs: { message: "hello" } });

      expect(resp.status).toBe(200);
      expect(resp.body.status).toBe("pass");
      expect(resp.body.outputs.result).toBe("echo: hello");
      expect(resp.body.execution_id).toBeDefined();
      expect(resp.body.duration_ms).toBeGreaterThanOrEqual(0);
    });

    it("returns 400 for missing required fields", async () => {
      const resp = await request(app)
        .post("/execute")
        .send({});

      expect(resp.status).toBe(400);
      expect(resp.body.detail).toBeDefined();
    });
  });

  describe("GET /health", () => {
    it("returns healthy when no checks", async () => {
      const resp = await request(app).get("/health");
      expect(resp.status).toBe(200);
      expect(resp.body.status).toBe("healthy");
      expect(resp.body.node_id).toBe("test-node-v1.0.0");
      expect(resp.body.version).toBe("1.0.0");
    });

    it("returns degraded when some checks fail", async () => {
      const healthNode = new HealthCheckNode();
      const healthApp = createNodeApp(healthNode);
      const resp = await request(healthApp).get("/health");
      expect(resp.body.status).toBe("degraded");
      expect(resp.body.checks).toEqual({ db: true, cache: false });
    });
  });

  describe("GET /manifest", () => {
    it("returns node definition with sdk_version and mode", async () => {
      const resp = await request(app).get("/manifest");
      expect(resp.status).toBe(200);
      expect(resp.body.slug).toBe("test-node");
      expect(resp.body.version).toBe("1.0.0");
      expect(resp.body.sdk_version).toBeDefined();
      expect(resp.body.mode).toBeDefined();
    });
  });

  describe("POST /hook", () => {
    it("returns 501 when not implemented", async () => {
      const resp = await request(app)
        .post("/hook")
        .send({ event: "test" });

      expect(resp.status).toBe(501);
      expect(resp.body.detail).toContain("not implemented");
    });
  });

  describe("GET /metrics", () => {
    it("returns metrics summary", async () => {
      const resp = await request(app).get("/metrics");
      expect(resp.status).toBe(200);
      expect(resp.body.total_executions).toBeDefined();
    });
  });

  describe("GET /live", () => {
    it("returns alive", async () => {
      const resp = await request(app).get("/live");
      expect(resp.status).toBe(200);
      expect(resp.body.status).toBe("alive");
    });
  });

  describe("GET /ready", () => {
    it("returns ready when checks pass", async () => {
      const resp = await request(app).get("/ready");
      expect(resp.status).toBe(200);
      expect(resp.body.status).toBe("ready");
    });

    it("returns 503 when checks fail", async () => {
      const healthNode = new HealthCheckNode();
      const healthApp = createNodeApp(healthNode);
      const resp = await request(healthApp).get("/ready");
      expect(resp.status).toBe(503);
      expect(resp.body.status).toBe("not_ready");
    });
  });
});

describe("X-SDK-Version header", () => {
  it("is present on all responses", async () => {
    const node = new TestNode();
    const app = createNodeApp(node);
    const resp = await request(app).get("/health");
    expect(resp.headers["x-sdk-version"]).toBeDefined();
  });
});

describe("Auth middleware", () => {
  it("rejects requests without API key", async () => {
    const node = new TestNode();
    process.env.CANVASTEKK_API_KEY = "test-secret-key";
    delete process.env.CANVASTEKK_DEV_MODE;
    const auth = NodeAuth.apiKey();
    const app = createNodeApp(node, { dependencies: [auth] });

    const resp = await request(app)
      .get("/health");

    expect(resp.status).toBe(401);
    delete process.env.CANVASTEKK_API_KEY;
  });

  it("accepts requests with valid API key", async () => {
    const node = new TestNode();
    process.env.CANVASTEKK_API_KEY = "test-secret-key";
    delete process.env.CANVASTEKK_DEV_MODE;
    const auth = NodeAuth.apiKey();
    const app = createNodeApp(node, { dependencies: [auth] });

    const resp = await request(app)
      .get("/health")
      .set("X-API-Key", "test-secret-key");

    expect(resp.status).toBe(200);
    delete process.env.CANVASTEKK_API_KEY;
  });

  it("accepts the rotation NEXT key alongside the current key", async () => {
    const node = new TestNode();
    process.env.CANVASTEKK_API_KEY = "current-key";
    process.env.CANVASTEKK_API_KEY_NEXT = "new-key";
    delete process.env.CANVASTEKK_DEV_MODE;
    const auth = NodeAuth.apiKey();
    const app = createNodeApp(node, { dependencies: [auth] });

    const resp = await request(app)
      .get("/health")
      .set("X-API-Key", "new-key");

    expect(resp.status).toBe(200);
    delete process.env.CANVASTEKK_API_KEY;
    delete process.env.CANVASTEKK_API_KEY_NEXT;
  });

  it("ignores an empty NEXT key", async () => {
    const node = new TestNode();
    process.env.CANVASTEKK_API_KEY = "current-key";
    process.env.CANVASTEKK_API_KEY_NEXT = "";
    delete process.env.CANVASTEKK_DEV_MODE;
    const auth = NodeAuth.apiKey();
    const app = createNodeApp(node, { dependencies: [auth] });

    const resp = await request(app)
      .get("/health")
      .set("X-API-Key", "current-key");

    expect(resp.status).toBe(200);
    delete process.env.CANVASTEKK_API_KEY;
    delete process.env.CANVASTEKK_API_KEY_NEXT;
  });

  it("bypasses auth in dev mode", async () => {
    const node = new TestNode();
    process.env.CANVASTEKK_API_KEY = "test-secret-key";
    process.env.CANVASTEKK_DEV_MODE = "true";
    const auth = NodeAuth.apiKey();
    const app = createNodeApp(node, { dependencies: [auth] });

    const resp = await request(app)
      .get("/health");

    expect(resp.status).toBe(200);
    delete process.env.CANVASTEKK_API_KEY;
    delete process.env.CANVASTEKK_DEV_MODE;
  });
});

describe("POST /execute upload failure (DA-1711 parity)", () => {
  class FileOutputNode extends BaseNode {
    definition: WorkflowNodeManifest = {
      slug: "file-out-node",
      version: "1.0.0",
      name: "File Out",
      description: "Produces a file output",
      input_schema: { type: "object" },
      output_schema: {
        type: "object",
        properties: { out_file: { type: "string", format: "file" } },
      },
    };

    execute(_inputs: Record<string, unknown>, context: ExecutionContext): Record<string, unknown> {
      const p = context.outputPath("result.txt");
      writeFileSync(p, "data");
      return { out_file: p };
    }
  }

  it("fails execution with UPLOAD_FAILED when upload PUT fails", async () => {
    const node = new FileOutputNode();
    const app = createNodeApp(node);
    const server = app.listen(0);
    const port = (server.address() as { port: number }).port;

    const originalFetch = globalThis.fetch;
    // Only the upload PUT fails; other requests (the test's own POST to
    // /execute) pass through to the real fetch.
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === "PUT") {
        return new Response("boom", { status: 500 });
      }
      return originalFetch(input as RequestInfo, init);
    }) as typeof fetch;

    try {
      const resp = await fetch(`http://127.0.0.1:${port}/execute`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          run_id: "r1",
          node_id: "n1",
          inputs: {},
          output_upload_url: { out_file: "https://s3.example.com/put" },
        }),
      });
      const data = (await resp.json()) as { status: string; error_code?: string };
      expect(data.status).toBe("fail");
      expect(data.error_code).toBe("UPLOAD_FAILED");
    } finally {
      globalThis.fetch = originalFetch;
      server.close();
    }
  });
});

describe("GET /manifest null-key stripping (DA-1955)", () => {
  it("omits null optional keys instead of leaking explicit nulls", async () => {
    class NullOptionalsNode extends BaseNode {
      definition: WorkflowNodeManifest = {
        slug: "null-opt-node",
        version: "1.0.0",
        name: "Null Optionals",
        description: "Definition carrying explicit null optionals",
        input_schema: { type: "object" },
        output_schema: { type: "object" },
        deprecation: null,
        minimum_sdk_version: null,
        maximum_sdk_version: null,
        docs_url: null,
        changelog_url: null,
      } as unknown as WorkflowNodeManifest;

      execute(): Record<string, unknown> {
        return {};
      }
    }
    const app = createNodeApp(new NullOptionalsNode());
    const resp = await request(app).get("/manifest");
    expect(resp.status).toBe(200);
    expect(resp.body).not.toHaveProperty("deprecation");
    expect(resp.body).not.toHaveProperty("minimum_sdk_version");
    expect(resp.body).not.toHaveProperty("maximum_sdk_version");
    expect(resp.body).not.toHaveProperty("docs_url");
    expect(resp.body).not.toHaveProperty("changelog_url");
    expect(resp.body.slug).toBe("null-opt-node");
  });
});

describe("auth middleware detection (DA-1955 review fix)", () => {
  it("tags NodeAuth middleware with the detection marker", async () => {
    const { CANVASTEKK_AUTH_MARKER } = await import("../src/auth.js");
    const mw = NodeAuth.apiKey() as unknown as Record<string, unknown>;
    expect(mw[CANVASTEKK_AUTH_MARKER]).toBe(true);
  });

  it("plain middleware is not tagged as auth", () => {
    const plain = (req: unknown, res: unknown, next: () => void) => next();
    expect((plain as unknown as Record<string, unknown>)["_canvastekkAuth"]).toBeUndefined();
  });
});

describe("manifest code_digest (DA-2603)", () => {
  it("serves a 64-hex digest of the handler module source (this test file)", async () => {
    const { createHash } = await import("node:crypto");
    const { readFileSync } = await import("node:fs");
    const node = new (class extends BaseNode {
      definition = {
        slug: "digest-node",
        version: "1.0.0",
        name: "Digest",
        description: "digest probe",
        input_schema: { type: "object" },
        output_schema: { type: "object" },
        role: "operation",
      } as unknown as WorkflowNodeManifest;
      async execute(_inputs: Record<string, unknown>) {
        return {};
      }
    })();
    const app = createNodeApp(node);
    const res = await request(app).get("/manifest");
    expect(res.status).toBe(200);
    const digest = res.body.code_digest as string;
    expect(digest).toMatch(/^[0-9a-f]{64}$/);
    const testFile = new URL(import.meta.url).pathname;
    expect(digest).toBe(createHash("sha256").update(readFileSync(testFile)).digest("hex"));
  });
});
