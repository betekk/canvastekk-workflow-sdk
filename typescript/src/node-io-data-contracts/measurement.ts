import type { Point3D } from "./point3d.js";

/**
 * Measurement with spatial reference.
 */
export interface Measurement {
  name: string;
  value: number;
  unit: string;
  method: string;
  confidence: number;
  points: Point3D[];
  metadata: Record<string, unknown>;
}

/**
 * Data for a set of measurements.
 */
export interface MeasurementSetData {
  contract_version: string;
  source_node?: string | null;
  source_file?: string | null;
  measurements: Measurement[];
}

/**
 * Gets a measurement by name.
 * @param set - Measurement set
 * @param name - Measurement name
 * @returns Measurement or undefined
 */
export function getMeasurement(set: MeasurementSetData, name: string): Measurement | undefined {
  return set.measurements.find((m) => m.name === name);
}

/**
 * Gets a measurement value by name.
 * @param set - Measurement set
 * @param name - Measurement name
 * @param defaultValue - Default value if not found
 * @returns Measurement value or default
 */
export function getValue(set: MeasurementSetData, name: string, defaultValue?: number): number | undefined {
  const m = getMeasurement(set, name);
  return m ? m.value : defaultValue;
}
