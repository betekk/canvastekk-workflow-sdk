/**
 * 3D point with x, y, z coordinates.
 *
 * All fields are readonly.
 */
export interface Point3D {
  readonly x: number;
  readonly y: number;
  readonly z: number;
}

/**
 * Converts a Point3D to a list of coordinates.
 * @param p - Point3D to convert
 * @returns Array of [x, y, z] coordinates
 */
export function point3DToList(p: Point3D): [number, number, number] {
  return [p.x, p.y, p.z];
}

/**
 * Creates a Point3D from an array of coordinates.
 * @param coords - Array of [x, y, z] coordinates
 * @returns Point3D object
 */
export function point3DFromList(coords: number[]): Point3D {
  return { x: coords[0], y: coords[1], z: coords[2] };
}

/**
 * 3D axis-aligned bounding box.
 *
 * All fields are readonly. The min_point must be <= max_point on each axis.
 *
 * Field names match the Python SDK (min_point, max_point).
 */
export interface BoundingBox3D {
  readonly min_point: Point3D;
  readonly max_point: Point3D;
}

/**
 * Calculates the center point of a bounding box.
 * @param box - Bounding box
 * @returns Center point
 */
export function boundingBoxCenter(box: BoundingBox3D): Point3D {
  return {
    x: (box.min_point.x + box.max_point.x) / 2,
    y: (box.min_point.y + box.max_point.y) / 2,
    z: (box.min_point.z + box.max_point.z) / 2,
  };
}

/**
 * Calculates the size of a bounding box.
 * @param box - Bounding box
 * @returns Size as a Point3D
 */
export function boundingBoxSize(box: BoundingBox3D): Point3D {
  return {
    x: box.max_point.x - box.min_point.x,
    y: box.max_point.y - box.min_point.y,
    z: box.max_point.z - box.min_point.z,
  };
}
