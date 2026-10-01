"""
Generic Data Contracts for Node I/O

This module defines standard data formats for communication between nodes.
Nodes should use these contracts to ensure loose coupling and composability.

Design Principles:
1. Generic - Not tied to specific nodes (e.g., "instances" not "segmentation_output")
2. JSON-serializable - Can be saved to files and passed between nodes
3. Self-describing - Include metadata about data source and format version
4. Composable - Any node producing a format can connect to any node consuming it

Usage:
    # In a node that produces instances
    from canvastekk_workflow_sdk.contracts import InstanceSet, Instance

    result = InstanceSet(
        instances=[Instance(class_id=4, class_name="vent", ...)],
        source_file="input.ply",
    )
    result.save_json("/tmp/instances.json")

    # In a node that consumes instances
    instances = InstanceSet.load_json("/tmp/instances.json")
    vents = [i for i in instances.instances if i.class_name == "vent"]
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self

from pydantic import BaseModel, Field, field_validator, model_validator

# =============================================================================
# Contract Version
# =============================================================================

CONTRACT_VERSION = "1.0.0"


# =============================================================================
# Base Contract
# =============================================================================


class BaseContract(BaseModel):
    """Base class for all data contracts."""

    contract_version: str = Field(
        default=CONTRACT_VERSION,
        description="Version of the contract schema",
    )
    source_node: str | None = Field(
        default=None,
        description="Slug of the node that produced this data (for debugging)",
    )
    source_file: str | None = Field(
        default=None,
        description="Original input file this data was derived from",
    )

    def save_json(self, path: str | Path) -> None:
        """Save contract data to JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.model_dump(mode="json"), f, indent=2)

    @classmethod
    def load_json(cls, path: str | Path) -> Self:
        """Load contract data from JSON file.

        Note: Return type is `Self` (not `BaseContract`) so that subclasses
        return their own type. e.g., `InstanceSet.load_json()` returns `InstanceSet`.
        Using `BaseContract` here would cause mypy errors like:
            "BaseContract has no attribute 'instances'"
        when accessing subclass-specific attributes.
        """
        with open(path) as f:
            data = json.load(f)
        return cls.model_validate(data)


# =============================================================================
# Geometry Primitives
# =============================================================================


class Point3D(BaseModel):
    """A 3D point coordinate."""

    x: float = Field(description="X coordinate in mm")
    y: float = Field(description="Y coordinate in mm")
    z: float = Field(description="Z coordinate in mm")

    def to_list(self) -> list[float]:
        """Convert to ``[x, y, z]`` list."""
        return [self.x, self.y, self.z]

    @classmethod
    def from_list(cls, coords: list[float]) -> Point3D:
        """Create a Point3D from a ``[x, y, z]`` list."""
        return cls(x=coords[0], y=coords[1], z=coords[2])


class BoundingBox3D(BaseModel):
    """
    Axis-aligned 3D bounding box.

    Constraints:
        min_point must be <= max_point on each axis
    """

    min_point: Point3D = Field(description="Minimum corner (x, y, z)")
    max_point: Point3D = Field(description="Maximum corner (x, y, z)")

    @model_validator(mode="after")
    def _validate_min_le_max(self) -> BoundingBox3D:
        """Ensure min_point <= max_point on each axis.

        Returns:
            Self for chaining

        Raises:
            ValueError: If any axis has min > max
        """
        for axis in ("x", "y", "z"):
            min_val = getattr(self.min_point, axis)
            max_val = getattr(self.max_point, axis)
            if min_val > max_val:
                raise ValueError(
                    f"BoundingBox3D min_point.{axis} ({min_val}) > max_point.{axis} ({max_val})"
                )
        return self

    @property
    def center(self) -> Point3D:
        """Center point of the bounding box."""
        return Point3D(
            x=(self.min_point.x + self.max_point.x) / 2,
            y=(self.min_point.y + self.max_point.y) / 2,
            z=(self.min_point.z + self.max_point.z) / 2,
        )

    @property
    def size(self) -> Point3D:
        """Size of the bounding box along each axis."""
        return Point3D(
            x=self.max_point.x - self.min_point.x,
            y=self.max_point.y - self.min_point.y,
            z=self.max_point.z - self.min_point.z,
        )


class Plane(BaseModel):
    """A 3D plane defined by point and normal."""

    point: Point3D = Field(description="A point on the plane")
    normal: Point3D = Field(description="Unit normal vector (nx, ny, nz)")
    label: str | None = Field(default=None, description="Optional label (e.g., 'floor', 'ceiling')")


# =============================================================================
# Instance Data (Generic - not tied to segmentation)
# =============================================================================


class Instance(BaseModel):
    """
    A detected object instance in a point cloud.

    This is a generic format that can be produced by:
    - Segmentation nodes (ML-based detection)
    - Manual annotation tools
    - Other detection algorithms

    Consumers should not assume the source - just use the data.

    Constraints:
        instance_id: Must be >= 0
        class_id: Must be >= 0
        point_indices: All values must be >= 0
    """

    instance_id: int = Field(ge=0, description="Unique ID within this instance set")
    class_id: int = Field(ge=0, description="Numeric class identifier")
    class_name: str = Field(description="Human-readable class name")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Detection confidence (1.0 if manually annotated)",
    )
    point_indices: list[int] = Field(description="Indices of points belonging to this instance")
    centroid: Point3D | None = Field(
        default=None,
        description="Centroid of the instance (computed if not provided)",
    )
    bounding_box: BoundingBox3D | None = Field(
        default=None,
        description="Bounding box of the instance",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional instance-specific metadata",
    )

    @field_validator("point_indices")
    @classmethod
    def _validate_indices_non_negative(cls, v: list[int]) -> list[int]:
        """Ensure all point indices are non-negative.

        Args:
            v: List of point indices

        Returns:
            The validated list

        Raises:
            ValueError: If any index is negative
        """
        if any(idx < 0 for idx in v):
            raise ValueError("point_indices must be non-negative integers")
        return v

    @property
    def num_points(self) -> int:
        """Number of points belonging to this instance."""
        return len(self.point_indices)


class InstanceSet(BaseContract):
    """
    A collection of detected instances from a point cloud.

    This is the standard format for passing instance data between nodes.
    Any node that detects/identifies objects should output this format.
    Any node that processes instances should accept this format.

    Constraints:
        point_count: Must be >= 0
    """

    instances: list[Instance] = Field(
        default_factory=list,
        description="List of detected instances",
    )
    class_names: list[str] = Field(
        default_factory=list,
        description="Ordered list of class names (index = class_id)",
    )
    point_count: int = Field(
        default=0,
        ge=0,
        description="Total number of points in the source point cloud",
    )
    semantic_labels: list[int] | None = Field(
        default=None,
        description="Per-point class labels (length = point_count)",
    )
    instance_labels: list[int] | None = Field(
        default=None,
        description="Per-point instance IDs (length = point_count)",
    )

    def get_instances_by_class(self, class_name: str) -> list[Instance]:
        """Return all instances whose ``class_name`` matches."""
        return [i for i in self.instances if i.class_name == class_name]

    def get_instances_by_class_id(self, class_id: int) -> list[Instance]:
        """Return all instances whose ``class_id`` matches."""
        return [i for i in self.instances if i.class_id == class_id]


# =============================================================================
# Measurement Results
# =============================================================================


class Measurement(BaseModel):
    """
    A single measurement result.

    Generic format for any distance, dimension, or calculated value.
    """

    name: str = Field(description="Measurement name (e.g., 'height', 'vent_distance')")
    value: float = Field(description="Measured value")
    unit: str = Field(default="mm", description="Unit of measurement")
    method: str = Field(
        default="unknown",
        description="Method used to obtain measurement",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence in the measurement",
    )
    points: list[Point3D] = Field(
        default_factory=list,
        description="Key points involved in the measurement (for visualization)",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional measurement-specific metadata",
    )


class MeasurementSet(BaseContract):
    """
    A collection of measurements.

    Standard format for nodes that compute measurements.
    """

    measurements: list[Measurement] = Field(
        default_factory=list,
        description="List of measurements",
    )

    def get_measurement(self, name: str) -> Measurement | None:
        """Return the first measurement with the given *name*, or ``None``."""
        for m in self.measurements:
            if m.name == name:
                return m
        return None

    def get_value(self, name: str, default: float | None = None) -> float | None:
        """Return the value of the first measurement with *name*, or *default*."""
        m = self.get_measurement(name)
        return m.value if m else default


# =============================================================================
# Plane Detection Results
# =============================================================================


class PlaneSet(BaseContract):
    """
    A collection of detected planes.

    Standard format for plane detection nodes.
    """

    planes: list[Plane] = Field(
        default_factory=list,
        description="List of detected planes",
    )

    def get_plane_by_label(self, label: str) -> Plane | None:
        """Return the first plane with the given *label*, or ``None``."""
        for p in self.planes:
            if p.label == label:
                return p
        return None


# =============================================================================
# Standard Class Definitions (Reference)
# =============================================================================

# Standard class IDs for BCA inspection
# These are conventions, not enforced by the contracts
STANDARD_CLASSES = {
    0: "floor",
    1: "ceiling",
    2: "wall",
    3: "door",
    4: "vent",
}

STANDARD_CLASS_NAMES = list(STANDARD_CLASSES.values())


# ---------------------------------------------------------------------------
# Check-node output-contract builder (DA-3359)
# ---------------------------------------------------------------------------
# Opt-in module surface for compliance-check nodes. `app.py` / `base.py` never
# import this module (pinned by tests/test_contracts.py::TestImportGraph) —
# nothing here is on the core execution path.

DEFAULT_CHECK_VERDICTS: tuple[str, ...] = ("PASS", "FAIL", "NOT_EVALUABLE")


def build_check_output_schema(
    verdicts: Sequence[str] = DEFAULT_CHECK_VERDICTS,
    result_description: str = "Check result summary.",
    *,
    closed: bool = False,
) -> dict[str, Any]:
    """Build the output schema shared by compliance-check nodes (DA-3359).

    Generalizes the shape the IFC compliance fleet uses (verdict head-line,
    verdict_counts, a nested ``result`` summary) into a reusable builder.

    Args:
        verdicts: The node's verdict vocabulary. Defaults to the
            three-value PASS/FAIL/NOT_EVALUABLE contract.
        result_description: One line naming what ``result`` holds, emitted
            as the ``result`` property description.
        closed: When True, sets ``additionalProperties: false`` on the root
            and on ``result``. The root keeps a nullable ``error`` property
            so the ErrorOutputNode error-append rewrite still validates.

    Returns:
        A JSON Schema dict ready for ``WorkflowNodeManifest(output_schema=...)``.
    """
    vocab = list(verdicts)
    result_properties: dict[str, Any] = {
        "verdict": {"type": "string", "enum": vocab},
    }
    result: dict[str, Any] = {
        "type": "object",
        "description": result_description,
        "properties": result_properties,
        "required": ["verdict"],
    }
    if closed:
        result["additionalProperties"] = False

    root: dict[str, Any] = {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": vocab,
                "description": (
                    "Headline verdict for the subject, emitted verbatim from "
                    "the check."
                ),
                "examples": [vocab[-2] if len(vocab) > 1 else vocab[0]],
            },
            "verdict_counts": {
                "type": "object",
                "additionalProperties": {"type": "integer", "minimum": 0},
                "description": "Count of measured subjects per verdict; absent keys mean zero.",
            },
            "result": result,
            "error": {
                "type": ["object", "null"],
                "description": (
                    "Error detail when the node failed before producing a "
                    "verdict; null (or absent) on a normal run."
                ),
            },
        },
        "required": ["verdict", "result"],
    }
    if closed:
        root["additionalProperties"] = False
    return root


def validate_verdict_fields(payload: dict[str, Any], verdicts: Sequence[str] = DEFAULT_CHECK_VERDICTS) -> None:
    """Validate a check node's output against its verdict vocabulary (DA-3359).

    Raises:
        ValueError: If the head-line verdict or the ``result.verdict`` is
            missing or outside the vocabulary.
    """
    vocab = set(verdicts)
    headline = payload.get("verdict")
    if headline not in vocab:
        raise ValueError(
            f"verdict {headline!r} is not in the check vocabulary {sorted(vocab)}"
        )
    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("check payload must carry a 'result' object")
    result_verdict = result.get("verdict")
    if result_verdict not in vocab:
        raise ValueError(
            f"result.verdict {result_verdict!r} is not in the check vocabulary {sorted(vocab)}"
        )
