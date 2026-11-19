import { describe, it, expect } from "vitest";
import {
  point3DToList,
  point3DFromList,
  boundingBoxCenter,
  boundingBoxSize,
} from "../src/node-io-data-contracts/point3d.js";
import type { BoundingBox3D } from "../src/node-io-data-contracts/point3d.js";
import {
  instanceNumPoints,
  getInstancesByClass,
  getInstancesByClassId,
} from "../src/node-io-data-contracts/instance.js";
import type { Instance, InstanceSetData } from "../src/node-io-data-contracts/instance.js";
import { getMeasurement, getValue } from "../src/node-io-data-contracts/measurement.js";
import type { MeasurementSetData } from "../src/node-io-data-contracts/measurement.js";
import { getPlaneByLabel } from "../src/node-io-data-contracts/plane.js";
import type { PlaneSetData } from "../src/node-io-data-contracts/plane.js";
import { saveJson, loadJson } from "../src/node-io-data-contracts/base.js";
import { STANDARD_CLASSES, STANDARD_CLASS_NAMES } from "../src/node-io-data-contracts/index.js";

describe("Point3D", () => {
  it("toList returns [x, y, z]", () => {
    expect(point3DToList({ x: 1, y: 2, z: 3 })).toEqual([1, 2, 3]);
  });

  it("fromList creates Point3D", () => {
    expect(point3DFromList([4, 5, 6])).toEqual({ x: 4, y: 5, z: 6 });
  });
});

describe("BoundingBox3D", () => {
  const box: BoundingBox3D = {
    min_point: { x: 0, y: 0, z: 0 },
    max_point: { x: 10, y: 20, z: 30 },
  };

  it("computes center", () => {
    const c = boundingBoxCenter(box);
    expect(c).toEqual({ x: 5, y: 10, z: 15 });
  });

  it("computes size", () => {
    const s = boundingBoxSize(box);
    expect(s).toEqual({ x: 10, y: 20, z: 30 });
  });
});

describe("Instance", () => {
  const inst: Instance = {
    instance_id: 1,
    class_id: 4,
    class_name: "vent",
    confidence: 0.95,
    point_indices: [0, 1, 2, 3, 4],
    metadata: {},
  };

  it("numPoints returns point_indices length", () => {
    expect(instanceNumPoints(inst)).toBe(5);
  });
});

describe("InstanceSet helpers", () => {
  const set: InstanceSetData = {
    contract_version: "1.0.0",
    instances: [
      { instance_id: 1, class_id: 4, class_name: "vent", confidence: 0.9, point_indices: [0, 1], metadata: {} },
      { instance_id: 2, class_id: 2, class_name: "wall", confidence: 0.8, point_indices: [2, 3], metadata: {} },
      { instance_id: 3, class_id: 4, class_name: "vent", confidence: 0.7, point_indices: [4], metadata: {} },
    ],
    class_names: ["floor", "ceiling", "wall", "door", "vent"],
    point_count: 5,
  };

  it("getInstancesByClass filters correctly", () => {
    const vents = getInstancesByClass(set, "vent");
    expect(vents).toHaveLength(2);
    expect(vents[0].instance_id).toBe(1);
    expect(vents[1].instance_id).toBe(3);
  });

  it("getInstancesByClassId filters correctly", () => {
    const items = getInstancesByClassId(set, 2);
    expect(items).toHaveLength(1);
    expect(items[0].class_name).toBe("wall");
  });
});

describe("MeasurementSet helpers", () => {
  const set: MeasurementSetData = {
    contract_version: "1.0.0",
    measurements: [
      { name: "height", value: 2500, unit: "mm", method: "plane", confidence: 0.9, points: [], metadata: {} },
      { name: "width", value: 3000, unit: "mm", method: "plane", confidence: 0.85, points: [], metadata: {} },
    ],
  };

  it("getMeasurement returns matching measurement", () => {
    const m = getMeasurement(set, "height");
    expect(m?.value).toBe(2500);
  });

  it("getMeasurement returns undefined for missing", () => {
    expect(getMeasurement(set, "depth")).toBeUndefined();
  });

  it("getValue returns value or default", () => {
    expect(getValue(set, "width")).toBe(3000);
    expect(getValue(set, "depth", 0)).toBe(0);
    expect(getValue(set, "depth")).toBeUndefined();
  });
});

describe("PlaneSet helpers", () => {
  const set: PlaneSetData = {
    contract_version: "1.0.0",
    planes: [
      { point: { x: 0, y: 0, z: 0 }, normal: { x: 0, y: 1, z: 0 }, label: "floor" },
      { point: { x: 0, y: 5, z: 0 }, normal: { x: 0, y: -1, z: 0 }, label: "ceiling" },
    ],
  };

  it("getPlaneByLabel returns matching plane", () => {
    const p = getPlaneByLabel(set, "floor");
    expect(p?.label).toBe("floor");
  });

  it("getPlaneByLabel returns undefined for missing", () => {
    expect(getPlaneByLabel(set, "roof")).toBeUndefined();
  });
});

describe("BaseContract saveJson/loadJson round-trip", () => {
  it("round-trips data correctly", () => {
    const data = { contract_version: "1.0.0", instances: [], class_names: [], point_count: 0 };
    const path = "/tmp/sdk-test-contract.json";
    saveJson(data, path);
    const loaded = loadJson(path);
    expect(loaded).toEqual(data);
  });
});

describe("STANDARD_CLASSES", () => {
  it("has correct mapping", () => {
    expect(STANDARD_CLASSES[0]).toBe("floor");
    expect(STANDARD_CLASSES[4]).toBe("vent");
  });

  it("STANDARD_CLASS_NAMES is values array", () => {
    expect(STANDARD_CLASS_NAMES).toEqual(["floor", "ceiling", "wall", "door", "vent"]);
  });
});
