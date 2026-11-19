import { describe, it, expect, vi, afterEach } from "vitest";
import request from "supertest";
import { createNodeApp } from "../src/app.js";
import { BaseNode } from "../src/base-node.js";
import type { WorkflowNodeManifest } from "../src/definition.js";
import type { ExecutionContext } from "../src/context.js";
import {
  NODE_PROTOCOL_HEADER,
  NODE_PROTOCOL_VERSION,
  outcomeForProtocol,
  readOutcome,
  requestedProtocol,
} from "../src/protocol.js";
import { parseNodeExecutionStatus } from "../src/response.js";
import { NodeValidationError } from "../src/exceptions.js";
import { HttpExecutor } from "../src/workflow/executor.js";

const manifest = (slug: string): WorkflowNodeManifest => ({
  slug,
  version: "1.0.0",
  name: slug,
  description: slug,
  input_schema: { type: "object" },
  output_schema: { type: "object" },
});

class EchoNode extends BaseNode {
  definition = manifest("echo");
  execute(inputs: Record<string, unknown>, _ctx: ExecutionContext): Record<string, unknown> {
    return { message: inputs.message };
  }
}

class FailingNode extends BaseNode {
  definition = manifest("failing");
  execute(): Record<string, unknown> {
    throw new Error("Intentional failure");
  }
}

const body = { run_id: "r", node_id: "n", inputs: { message: "hi" } };

describe("node protocol 2 (engine#1300)", () => {
  it.each([
    [undefined, 1],
    ["1", 1],
    ["2", 2],
    [" 2 ", 2],
    ["3", NODE_PROTOCOL_VERSION],
    ["0", 1],
    ["two", 1],
    ["", 1],
  ])("requestedProtocol(%j) = %d", (header, protocol) => {
    expect(requestedProtocol(header)).toBe(protocol);
  });

  it("translates outcomes only under protocol 2", () => {
    expect(["pass", "fail", "pending"].map((s) => outcomeForProtocol(s, 2))).toEqual(["SUCCEEDED", "FAILED", "ACCEPTED"]);
    expect(["pass", "fail", "pending"].map((s) => outcomeForProtocol(s, 1))).toEqual(["pass", "fail", "pending"]);
  });

  it("reads outcomes in either protocol", () => {
    expect(["pass", "SUCCEEDED", "succeeded", "FAILED", "ACCEPTED"].map(readOutcome)).toEqual([
      "pass",
      "pass",
      "pass",
      "fail",
      "pending",
    ]);
    expect(readOutcome("skipped")).toBeNull();
    expect(readOutcome(undefined)).toBeNull();
  });

  it("answers protocol-2 words only when asked", async () => {
    const app = createNodeApp(new EchoNode());
    const old = await request(app).post("/execute").send(body);
    const next = await request(app).post("/execute").set(NODE_PROTOCOL_HEADER, "2").send(body);
    expect(old.body.status).toBe("pass");
    expect(next.body.status).toBe("SUCCEEDED");
    expect(next.body.outputs).toEqual(old.body.outputs);
  });

  it("a failing node answers FAILED under protocol 2", async () => {
    const app = createNodeApp(new FailingNode());
    expect((await request(app).post("/execute").send(body)).body.status).toBe("fail");
    expect((await request(app).post("/execute").set(NODE_PROTOCOL_HEADER, "2").send(body)).body.status).toBe("FAILED");
  });

  it("strict parser reads exact protocol-2 results only", () => {
    expect(parseNodeExecutionStatus("SUCCEEDED")).toBe("pass");
    expect(parseNodeExecutionStatus("FAILED")).toBe("fail");
    for (const bad of ["ACCEPTED", "succeeded", "Failed"]) {
      expect(() => parseNodeExecutionStatus(bad)).toThrow(NodeValidationError);
    }
  });

  describe("HttpExecutor", () => {
    afterEach(() => vi.unstubAllGlobals());

    it.each([
      ["SUCCEEDED", true],
      ["pass", true],
      ["FAILED", false],
    ])("sends the header and reads %s", async (status, succeeds) => {
      const fetchMock = vi.fn(async () =>
        new Response(JSON.stringify({ execution_id: "e", status, outputs: { x: 1 }, error: "boom" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
      vi.stubGlobal("fetch", fetchMock);
      const executor = new HttpExecutor().registerUrl("echo", "http://node.example");
      const ctx = { runId: "r", nodeId: "n" } as unknown as ExecutionContext;

      if (succeeds) {
        await expect(executor.execute("echo", {}, ctx)).resolves.toEqual({ x: 1 });
      } else {
        await expect(executor.execute("echo", {}, ctx)).rejects.toThrow(/boom/);
      }
      const init = (fetchMock.mock.calls[0] as unknown as [string, RequestInit])[1];
      expect((init.headers as Record<string, string>)[NODE_PROTOCOL_HEADER]).toBe("2");
    });
  });
});
