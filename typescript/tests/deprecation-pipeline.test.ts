import { describe, it, expect, vi, beforeEach } from "vitest";

const { warnSpy } = vi.hoisted(() => ({ warnSpy: vi.fn() }));

vi.mock("../src/logging.js", () => ({
  createLogger: vi.fn(() => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: warnSpy,
    error: vi.fn(),
  })),
  getNodeLogger: vi.fn(() => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: warnSpy,
    error: vi.fn(),
  })),
}));

import { BaseNode } from "../src/base-node.js";
import { WorkflowNodeManifestSchema } from "../src/definition.js";
import { buildRegistryPayload } from "../src/registry.js";
import type { WorkflowNodeManifest, DeprecationInfo } from "../src/definition.js";

const fullDeprecation: DeprecationInfo = {
  deprecated_at: "2026-09-03",
  sunset_date: "2027-01-01",
  replacement_slug: "echo-v2",
  migration_url: "https://example.com/migrate",
  notice: "use echo-v2",
};

const baseManifest = (deprecation?: DeprecationInfo): WorkflowNodeManifest => ({
  slug: "echo",
  version: "1.0.0",
  name: "Echo",
  description: "Returns input",
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
  ...(deprecation !== undefined ? { deprecation } : {}),
});

function makeNode(deprecation?: DeprecationInfo): BaseNode {
  class TestNode extends BaseNode {
    definition: WorkflowNodeManifest = baseManifest(deprecation);

    execute(inputs: Record<string, unknown>): Record<string, unknown> {
      return { message: inputs.message as string };
    }
  }
  return new TestNode();
}

describe("deprecation pipeline (DA-2312, parity with Python v0.25.0)", () => {
  beforeEach(() => {
    warnSpy.mockClear();
  });

  describe("registry payload emission", () => {
    it("emits the full 5-key dump when deprecation is set", () => {
      const payload = buildRegistryPayload(baseManifest(fullDeprecation));
      expect(payload.deprecation).toEqual({
        deprecated_at: "2026-09-03",
        sunset_date: "2027-01-01",
        replacement_slug: "echo-v2",
        migration_url: "https://example.com/migrate",
        notice: "use echo-v2",
      });
    });

    it("omits deprecation when null", () => {
      const payload = buildRegistryPayload(baseManifest());
      expect(payload).not.toHaveProperty("deprecation");
    });
  });

  describe("DeprecationInfo validation", () => {
    it("rejects sunset_date before deprecated_at", () => {
      expect(() =>
        WorkflowNodeManifestSchema.parse(
          baseManifest({
            ...fullDeprecation,
            deprecated_at: "2026-09-03",
            sunset_date: "2026-01-01",
          }),
        ),
      ).toThrow(/sunset_date .* is before deprecated_at/);
    });

    it("accepts sunset_date equal to deprecated_at (boundary)", () => {
      const parsed = WorkflowNodeManifestSchema.parse(
        baseManifest({ ...fullDeprecation, sunset_date: "2026-09-03" }),
      );
      expect(parsed.deprecation?.sunset_date).toBe("2026-09-03");
    });

    it("accepts null dates", () => {
      const parsed = WorkflowNodeManifestSchema.parse(
        baseManifest({ ...fullDeprecation, sunset_date: null }),
      );
      expect(parsed.deprecation?.sunset_date).toBeNull();
    });

    it("rejects non-ISO date formats (strict YYYY-MM-DD)", () => {
      expect(() =>
        WorkflowNodeManifestSchema.parse(
          baseManifest({
            ...fullDeprecation,
            deprecated_at: "2026-09-03",
            sunset_date: "2027-1-1",
          }),
        ),
      ).toThrow();
    });
  });

  describe("runtime sunset lifecycle", () => {
    it("refuses to run after sunset_date has passed", async () => {
      const node = makeNode({
        ...fullDeprecation,
        deprecated_at: "2020-01-01",
        sunset_date: "2020-06-01",
      });
      const resp = await node.run({
        run_id: "run-1",
        node_id: "echo-1",
        inputs: { message: "hi" },
      });
      expect(resp.status).toBe("fail");
      expect(resp.error).toContain("was sunset");
      expect(resp.error).toContain("echo-v2");
      expect(warnSpy).not.toHaveBeenCalled();
    });

    it("warns but runs while deprecated and not sunset", async () => {
      const node = makeNode({
        ...fullDeprecation,
        deprecated_at: "2026-01-01",
        sunset_date: null,
      });
      const resp = await node.run({
        run_id: "run-2",
        node_id: "echo-2",
        inputs: { message: "hi" },
      });
      expect(resp.status).toBe("pass");
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining("deprecated"),
      );
      expect(warnSpy).toHaveBeenCalledWith(
        expect.stringContaining("echo-v2"),
      );
    });

    it("still runs on the sunset day itself (day-inclusive boundary)", async () => {
      vi.useFakeTimers();
      vi.setSystemTime(new Date("2026-09-03T12:00:00Z"));
      try {
        const node = makeNode({
          ...fullDeprecation,
          deprecated_at: "2026-01-01",
          sunset_date: "2026-09-03",
        });
        const resp = await node.run({
          run_id: "run-4",
          node_id: "echo-4",
          inputs: { message: "hi" },
        });
        expect(resp.status).toBe("pass");
        expect(warnSpy).toHaveBeenCalled();
      } finally {
        vi.useRealTimers();
      }
    });

    it("does nothing when deprecation is unset", async () => {
      const node = makeNode();
      const resp = await node.run({
        run_id: "run-3",
        node_id: "echo-3",
        inputs: { message: "hi" },
      });
      expect(resp.status).toBe("pass");
      expect(warnSpy).not.toHaveBeenCalled();
    });
  });
});
