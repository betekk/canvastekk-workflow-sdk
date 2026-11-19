import type { Point3D } from "./point3d.js";

/**
 * Plane defined by a point and normal vector.
 */
export interface Plane {
  point: Point3D;
  normal: Point3D;
  label?: string | null;
}

/**
 * Data for a set of planes.
 */
export interface PlaneSetData {
  contract_version: string;
  source_node?: string | null;
  source_file?: string | null;
  planes: Plane[];
}

/**
 * Gets a plane by label.
 * @param set - Plane set
 * @param label - Plane label
 * @returns Plane or undefined
 */
export function getPlaneByLabel(set: PlaneSetData, label: string): Plane | undefined {
  return set.planes.find((p) => p.label === label);
}
