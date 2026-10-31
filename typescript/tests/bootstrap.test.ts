import { describe, it, expect } from "vitest";
import request from "supertest";
import express from "express";
import { createAuthedApp, mountNode } from "../src/bootstrap.js";
import { BaseNode } from "../src/base-node.js";
import type { WorkflowNodeManifest } from "../src/definition.js";
import type { ExecutionContext } from "../src/context.js";

class TestNode extends BaseNode {
  definition: WorkflowNodeManifest = {
    slug: "bootstrap-test-node",
    version: "1.0.0",
    name: "Bootstrap Test Node",
    description: "Parity test node",
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

describe("createAuthedApp", () => {
  it("fails closed central-only by default (legacy key INERT)", async () => {
    process.env.BOOTSTRAP_TEST_KEY = "static-key-1";
    delete process.env.CWE_API_BASE_URL;
    const app = createAuthedApp(new TestNode());
    const res = await request(app)
      .post("/execute")
      .set("X-API-Key", "static-key-1")
      .send({ run_id: "r1", node_id: "n1", inputs: { message: "hi" } });
    // No CWE_API_BASE_URL -> verify unconfigured; legacy leg is INERT (legacyKeyEnvVar=null).
    expect([401, 503]).toContain(res.status);
  });

  it("keeps the legacy static-key leg live when legacyKeyEnvVar is set", async () => {
    process.env.BOOTSTRAP_TEST_KEY = "static-key-1";
    delete process.env.CWE_API_BASE_URL;
    const app = createAuthedApp(new TestNode(), { legacyKeyEnvVar: "BOOTSTRAP_TEST_KEY" });
    const res = await request(app)
      .post("/execute")
      .set("X-API-Key", "static-key-1")
      .send({ run_id: "r1", node_id: "n1", inputs: { message: "hi" } });
    expect(res.status).toBe(200);
  });

  it("APPENDS auth to caller-supplied dependencies (never drops them)", async () => {
    process.env.BOOTSTRAP_TEST_KEY = "static-key-1";
    delete process.env.CWE_API_BASE_URL;
    const seen: string[] = [];
    const app = createAuthedApp(new TestNode(), {
      legacyKeyEnvVar: "BOOTSTRAP_TEST_KEY",
      dependencies: [
        (_req, _res, next) => {
          seen.push("caller-dep");
          next();
        },
      ],
    });
    const res = await request(app)
      .post("/execute")
      .set("X-API-Key", "static-key-1")
      .send({ run_id: "r1", node_id: "n1", inputs: { message: "hi" } });
    expect(res.status).toBe(200);
    expect(seen).toEqual(["caller-dep"]); // caller middleware ran alongside auth
  });

  it("rejects extraRoutes (mounted without the auth middleware)", () => {
    expect(() => createAuthedApp(new TestNode(), { extraRoutes: [express.Router()] })).toThrow(
      /extraRoutes/,
    );
  });
});

describe("mountNode", () => {
  it("dual-purpose: root routes open, node sub-app behind central auth", async () => {
    process.env.BOOTSTRAP_TEST_KEY = "static-key-1";
    delete process.env.CWE_API_BASE_URL;
    const root = express();
    root.get("/ping", (_req, res) => {
      res.json({ ping: "pong" });
    });
    mountNode(root, new TestNode(), { legacyKeyEnvVar: "BOOTSTRAP_TEST_KEY" });

    expect((await request(root).get("/ping")).status).toBe(200);

    const denied = await request(root)
      .post("/node/execute")
      .send({ run_id: "r1", node_id: "n1", inputs: {} });
    expect(denied.status).toBe(401);

    const ok = await request(root)
      .post("/node/execute")
      .set("X-API-Key", "static-key-1")
      .send({ run_id: "r1", node_id: "n1", inputs: { message: "hi" } });
    expect(ok.status).toBe(200);
  });

  it("honors a custom prefix", async () => {
    process.env.BOOTSTRAP_TEST_KEY = "static-key-1";
    const root = express();
    mountNode(root, new TestNode(), { prefix: "/cw", legacyKeyEnvVar: "BOOTSTRAP_TEST_KEY" });
    const ok = await request(root)
      .post("/cw/execute")
      .set("X-API-Key", "static-key-1")
      .send({ run_id: "r1", node_id: "n1", inputs: { message: "hi" } });
    expect(ok.status).toBe(200);
  });
});
