import { describe, expect, it } from "vitest";
import {
  buildCheckOutputSchema,
  validateVerdictFields,
} from "../src/contracts/check-output.js";

describe("buildCheckOutputSchema (DA-3359)", () => {
  it("defaults to the three-value vocab and an open schema", () => {
    const schema = buildCheckOutputSchema();
    const props = schema.properties as Record<string, Record<string, unknown>>;
    const result = props.result as Record<string, unknown>;
    expect((props.verdict.enum as string[])).toEqual(["PASS", "FAIL", "NOT_EVALUABLE"]);
    expect((result.required as string[])).toEqual(["verdict"]);
    expect(schema.additionalProperties).toBeUndefined();
  });

  it("accepts a custom vocab and result description", () => {
    const schema = buildCheckOutputSchema(["CLEAR", "VIOLATION"], "Seam check.");
    const props = schema.properties as Record<string, Record<string, unknown>>;
    const result = props.result as Record<string, unknown>;
    expect((props.verdict.enum as string[])).toEqual(["CLEAR", "VIOLATION"]);
    expect(result.description).toBe("Seam check.");
  });

  it("closed flag closes both levels and keeps the error property", () => {
    const schema = buildCheckOutputSchema(undefined, undefined, { closed: true });
    expect(schema.additionalProperties).toBe(false);
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect((props.result as Record<string, unknown>).additionalProperties).toBe(false);
    expect(schema.properties).toHaveProperty("error");
  });

  it("closed schema still validates the ErrorOutputNode error append", () => {
    // minimal JSON-Schema validation without a dependency: structural check
    const schema = buildCheckOutputSchema(undefined, undefined, { closed: true });
    const props = schema.properties as Record<string, Record<string, unknown>>;
    expect(props.error.type).toContain("object");
    const payload = { verdict: "FAIL", result: { verdict: "FAIL" }, error: { message: "boom" } };
    // every top-level payload key must be declared (closed contract)
    for (const key of Object.keys(payload)) {
      expect(props).toHaveProperty(key);
    }
  });
});

describe("validateVerdictFields (DA-3359)", () => {
  it("accepts a valid payload", () => {
    expect(() =>
      validateVerdictFields({ verdict: "PASS", result: { verdict: "PASS" } }),
    ).not.toThrow();
  });

  it("rejects an off-vocab headline", () => {
    expect(() =>
      validateVerdictFields({ verdict: "SKIP", result: { verdict: "PASS" } }),
    ).toThrow(/verdict/);
  });

  it("rejects a missing result", () => {
    expect(() => validateVerdictFields({ verdict: "PASS" })).toThrow(/result/);
  });

  it("rejects an off-vocab result verdict", () => {
    expect(() =>
      validateVerdictFields({ verdict: "PASS", result: { verdict: "MAYBE" } }),
    ).toThrow(/result\.verdict/);
  });
});
