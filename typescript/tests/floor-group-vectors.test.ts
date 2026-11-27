import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import * as sdk from "../src/index.js";
import { MODEL_CHECK_FLOOR_GROUP_TEST_VECTORS } from "../src/model-check-floor-group-vectors.js";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CANONICAL = join(REPO, "schemas", "result-body", "model_check.check", "vectors", "floor-groups.json");

describe("Model Checker floor-group vectors", () => {
  it("are exported from the package root and match the canonical JSON", () => {
    const canonical = JSON.parse(readFileSync(CANONICAL, "utf8"));
    expect(MODEL_CHECK_FLOOR_GROUP_TEST_VECTORS).toEqual(canonical);
    expect(sdk.MODEL_CHECK_FLOOR_GROUP_TEST_VECTORS).toBe(MODEL_CHECK_FLOOR_GROUP_TEST_VECTORS);
    expect(canonical.cases.map((entry: { name: string }) => entry.name)).toEqual([
      "single_floor_mixed_heights",
      "two_floors_same_check",
      "degenerate_storeys_floor_surface_fallback",
      "unplaced_row_and_usable_z_fallback",
      "cross_floor_path",
    ]);
  });
});
