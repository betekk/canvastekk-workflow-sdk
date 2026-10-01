/**
 * CanvasTEKK contract types and utilities for point cloud data.
 * Exports standard contract schemas for Point3D, BoundingBox, Instance, Measurement, and Plane.
 */
export { CONTRACT_VERSION, saveJson, loadJson } from "./base.js";
export type { BaseContractData } from "./base.js";
export {
  point3DToList,
  point3DFromList,
  boundingBoxCenter,
  boundingBoxSize,
} from "./point3d.js";
export type { Point3D, BoundingBox3D } from "./point3d.js";
export {
  instanceNumPoints,
  getInstancesByClass,
  getInstancesByClassId,
} from "./instance.js";
export type { Instance, InstanceSetData } from "./instance.js";
export {
  getMeasurement,
  getValue,
} from "./measurement.js";
export type { Measurement, MeasurementSetData } from "./measurement.js";
export { getPlaneByLabel } from "./plane.js";
export type { Plane, PlaneSetData } from "./plane.js";

/** Standard semantic class mappings. */
export const STANDARD_CLASSES: Record<number, string> = {
  0: "floor",
  1: "ceiling",
  2: "wall",
  3: "door",
  4: "vent",
};

export const STANDARD_CLASS_NAMES = Object.values(STANDARD_CLASSES);

export { buildCheckOutputSchema, validateVerdictFields, DEFAULT_CHECK_VERDICTS } from "./check-output.js";
export type { CheckOutputOptions } from "./check-output.js";
