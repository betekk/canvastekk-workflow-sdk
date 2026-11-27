import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import * as sdk from "../src/index.js";
import { MODEL_CHECK_FLOOR_GROUP_TEST_VECTORS } from "../src/model-check-floor-group-vectors.js";

const REPO = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const CANONICAL = join(REPO, "schemas", "result-body", "model_check.check", "vectors", "floor-groups.json");

type Storey = { ref: string; name: string; elevation_mm: number };
type Point = number[];
type Primitive = {
  primitive_id: string;
  kind?: string;
  geometry?: { points_model_mm?: Point[] };
};
type Measurement = {
  subject_id: string;
  spatial_context?: {
    anchor_z_mm?: number;
    storey_below?: { ref: string };
    floor_surface?: { elevation_mm?: number };
  };
  viewer_representation?: { primitives?: Primitive[] };
};
type VectorCase = {
  name: string;
  spatial_reference: { storeys: Storey[] };
  measurements: Measurement[];
  expected: unknown;
};
type Group = {
  key: string;
  storey_ref: string | null;
  name: string;
  elevation_mm: number;
  subject_ids: string[];
};

const paths = (measurement: Measurement): Primitive[] =>
  (measurement.viewer_representation?.primitives ?? []).filter(
    (primitive) => primitive.kind === "path_polyline" && (primitive.geometry?.points_model_mm?.length ?? 0) >= 2,
  );

function anchor(measurement: Measurement): number | undefined {
  if (measurement.spatial_context?.anchor_z_mm !== undefined) return measurement.spatial_context.anchor_z_mm;
  const zValues = (measurement.viewer_representation?.primitives ?? []).flatMap((primitive) =>
    (primitive.geometry?.points_model_mm ?? []).map((point) => point[2]),
  );
  return zValues.length ? Math.min(...zValues) : undefined;
}

function clipPath(points: Point[], low: number, high: number): Point[] {
  const clipped: Point[] = [];
  const add = (point: Point) => {
    const previous = clipped.at(-1);
    if (!previous || previous.some((value, index) => value !== point[index])) clipped.push(point);
  };
  for (let index = 0; index + 1 < points.length; index += 1) {
    const first = points[index];
    const second = points[index + 1];
    const [z0, z1] = [first[2], second[2]];
    if (z0 === z1) {
      if (z0 >= low && z0 <= high) {
        add(first);
        add(second);
      }
      continue;
    }
    const enter = (low - z0) / (z1 - z0);
    const leave = (high - z0) / (z1 - z0);
    const start = Math.max(0, Math.min(enter, leave));
    const end = Math.min(1, Math.max(enter, leave));
    if (start > end) continue;
    for (const ratio of start === end ? [start] : [start, end]) {
      add(first.map((value, axis) => Number((value + (second[axis] - value) * ratio).toFixed(9))));
    }
  }
  return clipped;
}

function referenceGroups(testCase: VectorCase, fallbackGapMm: number) {
  const storeys = [...testCase.spatial_reference.storeys].sort((a, b) => a.elevation_mm - b.elevation_mm);
  const byRef = new Map(storeys.map((storey) => [storey.ref, storey]));
  const degenerate = new Set(storeys.map((storey) => storey.elevation_mm)).size <= 1;
  const groups = new Map<string, Group>();
  const homes = new Map<string, string>();
  const unplaced: string[] = [];
  const put = (key: string, storey: Storey | null, elevation: number, subject: string) => {
    if (!groups.has(key)) {
      groups.set(key, {
        key,
        storey_ref: storey?.ref ?? null,
        name: storey?.name ?? `Floor ${elevation} mm`,
        elevation_mm: elevation,
        subject_ids: [],
      });
    }
    groups.get(key)!.subject_ids.push(subject);
    homes.set(subject, key);
  };

  if (degenerate) {
    const placed: { elevation: number; subject: string }[] = [];
    for (const measurement of testCase.measurements) {
      const elevation = measurement.spatial_context?.floor_surface?.elevation_mm;
      if (elevation === undefined) unplaced.push(measurement.subject_id);
      else placed.push({ elevation, subject: measurement.subject_id });
    }
    placed.sort((a, b) => a.elevation - b.elevation);
    let previous: number | undefined;
    let key = "";
    for (const { elevation, subject } of placed) {
      if (previous === undefined || elevation - previous > fallbackGapMm) key = `floor:${elevation}`;
      put(key, null, groups.get(key)?.elevation_mm ?? elevation, subject);
      previous = elevation;
    }
  } else {
    for (const measurement of testCase.measurements) {
      const subject = measurement.subject_id;
      const context = measurement.spatial_context;
      const position = anchor(measurement);
      let storey = context?.storey_below ? byRef.get(context.storey_below.ref) : undefined;
      if (!storey && position !== undefined) {
        storey = storeys.filter((entry) => entry.elevation_mm <= position).at(-1);
      }
      if (!storey) {
        unplaced.push(subject);
        continue;
      }
      const surface = context?.floor_surface?.elevation_mm;
      put(`storey:${storey.ref}`, storey, surface ?? storey.elevation_mm, subject);
    }
  }

  const clips: {
    group_key: string;
    primitive_id: string;
    points_model_mm: Point[];
    continuation_label: string | null;
  }[] = [];
  if (!degenerate) {
    for (const measurement of testCase.measurements) {
      const home = homes.get(measurement.subject_id);
      if (!home) continue;
      const homeStorey = byRef.get(home.slice("storey:".length))!;
      for (const path of paths(measurement)) {
        const points = path.geometry!.points_model_mm!;
        const pathClips: { storey: Storey; clipped: Point[] }[] = [];
        storeys.forEach((storey, index) => {
          const low = storey.elevation_mm;
          const high = index + 1 < storeys.length
            ? storeys[index + 1].elevation_mm
            : Math.max(low, ...points.map((point) => point[2]));
          const clipped = clipPath(points, low, high);
          if (clipped.length >= 2) pathClips.push({ storey, clipped });
        });
        if (pathClips.length < 2) continue;
        for (const { storey, clipped } of pathClips) {
          clips.push({
            group_key: `storey:${storey.ref}`,
            primitive_id: path.primitive_id,
            points_model_mm: clipped,
            continuation_label: storey.ref === homeStorey.ref ? null : `Continues from ${homeStorey.name}`,
          });
        }
      }
    }
  }
  return { groups: [...groups.values()], unplaced_subject_ids: unplaced, clips };
}

const vectors = MODEL_CHECK_FLOOR_GROUP_TEST_VECTORS as unknown as {
  fallback_gap_mm: number;
  cases: VectorCase[];
};

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

  it("passes every published vector through the TypeScript reference grouping", () => {
    for (const testCase of vectors.cases) {
      expect(referenceGroups(testCase, vectors.fallback_gap_mm), testCase.name).toEqual(testCase.expected);
    }
  });
});
