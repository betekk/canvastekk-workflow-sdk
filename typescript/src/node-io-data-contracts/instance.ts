import type { Point3D, BoundingBox3D } from "./point3d.js";

/**
 * Instance in a point cloud with classification and spatial info.
 *
 * Field names match the Python SDK for cross-language wire-format compatibility.
 *
 * All fields are readonly. ID fields (instance_id, class_id) must be non-negative.
 */
export interface Instance {
  readonly instance_id: number;
  readonly class_id: number;
  readonly class_name: string;
  readonly confidence: number;
  readonly point_indices: number[];
  readonly centroid?: Point3D | null;
  readonly bounding_box?: BoundingBox3D | null;
  readonly metadata: Record<string, unknown>;
}

/**
 * Gets the number of points in an instance.
 * @param inst - Instance
 * @returns Point count
 */
export function instanceNumPoints(inst: Instance): number {
  return inst.point_indices.length;
}

/**
 * Data for a set of instances.
 *
 * All fields are readonly. The point_count field must be non-negative.
 */
export interface InstanceSetData {
  readonly contract_version: string;
  readonly source_node?: string | null;
  readonly source_file?: string | null;
  readonly instances: Instance[];
  readonly class_names: string[];
  readonly point_count: number;
  readonly semantic_labels?: number[] | null;
  readonly instance_labels?: number[] | null;
}

/**
 * Gets all instances of a specific class.
 * @param set - Instance set
 * @param className - Class name to filter by
 * @returns Array of matching instances
 */
export function getInstancesByClass(set: InstanceSetData, className: string): Instance[] {
  return set.instances.filter((i) => i.class_name === className);
}

/**
 * Gets all instances of a specific class ID.
 * @param set - Instance set
 * @param classId - Class ID to filter by
 * @returns Array of matching instances
 */
export function getInstancesByClassId(set: InstanceSetData, classId: number): Instance[] {
  return set.instances.filter((i) => i.class_id === classId);
}
