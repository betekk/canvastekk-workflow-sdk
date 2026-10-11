import { describe, it, expect } from "vitest";
import {
  NodeExecutionResponseFactory,
  NodeExecutionResponseSchema,
  HealthResponseSchema,
} from "../src/response.js";

describe("NodeExecutionResponseFactory", () => {
  describe("success()", () => {
    it("creates a pass response", () => {
      const resp = NodeExecutionResponseFactory.success("exec-1", { result: "ok" }, 42, 1.5);
      expect(resp).toEqual({
        execution_id: "exec-1",
        status: "pass",
        outputs: { result: "ok" },
        duration_ms: 42,
        token_usage: 1.5,
        error: null,
        error_type: null,
        error_code: null,
        dry_run: false,
      });
    });

    it("defaults duration and token_usage", () => {
      const resp = NodeExecutionResponseFactory.success("exec-1", {});
      expect(resp.duration_ms).toBe(0);
      expect(resp.token_usage).toBe(0.0);
    });
  });

  describe("failure()", () => {
    it("creates a fail response", () => {
      const resp = NodeExecutionResponseFactory.failure(
        "exec-1",
        "timed out",
        "NodeTimeoutError",
        30000,
        "TIMEOUT",
      );
      expect(resp).toEqual({
        execution_id: "exec-1",
        status: "fail",
        outputs: null,
        error: "timed out",
        error_type: "NodeTimeoutError",
        duration_ms: 30000,
        error_code: "TIMEOUT",
        token_usage: 0.0,
        dry_run: false,
      });
    });

    it("defaults optional fields", () => {
      const resp = NodeExecutionResponseFactory.failure("exec-1", "error");
      expect(resp.error_type).toBeNull();
      expect(resp.duration_ms).toBe(0);
      expect(resp.error_code).toBeNull();
    });
  });
});

describe("NodeExecutionResponseSchema", () => {
  it("validates a success response", () => {
    const resp = NodeExecutionResponseSchema.parse(
      NodeExecutionResponseFactory.success("exec-1", { x: 1 }),
    );
    expect(resp.status).toBe("pass");
  });

  it("rejects invalid status", () => {
    expect(() =>
      NodeExecutionResponseSchema.parse({
        execution_id: "exec-1",
        status: "pending",
      }),
    ).toThrow();
  });
});

describe("HealthResponseSchema", () => {
  it("parses a healthy response", () => {
    const resp = HealthResponseSchema.parse({
      status: "healthy",
      node_id: "echo-v1.0.0",
      version: "1.0.0",
      checks: {},
    });
    expect(resp.status).toBe("healthy");
  });

  it("accepts degraded status", () => {
    const resp = HealthResponseSchema.parse({
      status: "degraded",
      node_id: "node-v1",
      version: "1.0.0",
      checks: { db: true, cache: false },
    });
    expect(resp.status).toBe("degraded");
    expect(resp.checks).toEqual({ db: true, cache: false });
  });

  it("rejects invalid status", () => {
    expect(() =>
      HealthResponseSchema.parse({
        status: "ok",
        node_id: "node-v1",
        version: "1.0.0",
      }),
    ).toThrow();
  });
});
