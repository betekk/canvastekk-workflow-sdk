---
name: canvastekk-node-patterns
description: Domain-specific patterns and code examples for CanvasTEKK workflow nodes — point cloud processing, segmentation, measurement, plane detection, inference with model loading, authentication, middleware, multi-node apps, webhook hooks, and contract serialization.
---

## What I do

I provide ready-to-use code patterns for specific CanvasTEKK node types and advanced features:

- Point cloud processing and segmentation node patterns
- Measurement computation and plane detection node patterns
- Model inference with startup loading and GPU health checks
- Data contract production and consumption (InstanceSet, MeasurementSet, PlaneSet)
- Authentication integration (API Key, JWT, Keycloak)
- Middleware for audit logging and timing
- Multi-node applications with shared routing
- Webhook/callback handling for async operations
- Format conversion and simple transform patterns
- Testing patterns for file I/O mocking

## When to use me

Load this skill when:
- You need a specific code pattern for a CanvasTEKK node type (point cloud, measurement, inference, etc.)
- A user asks "how do I use InstanceSet/MeasurementSet/PlaneSet in a node?"
- You need to add authentication, middleware, or webhooks to an existing node
- You want example code for testing file I/O with mocked presigned URLs
- The `canvastekk-node-builder` skill has been loaded and you need domain-specific patterns

This skill complements `canvastekk-node-builder` — load both when creating a node from scratch.

---

## Pattern 1: Point Cloud Segmentation Node

Full example of an inference node that downloads a point cloud, runs segmentation, and produces an InstanceSet.

```python
"""Point Cloud Segmentation Node — segments a point cloud into detected instances."""

from pathlib import Path

import httpx
from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest, WorkflowNodeStyles
from canvastekk_workflow_sdk.contracts import (
    BoundingBox3D,
    Instance,
    InstanceSet,
    Point3D,
)
from canvastekk_workflow_sdk.exceptions import NodeExecutionError

definition = WorkflowNodeManifest(
    slug="segment",
    version="1.0.0",
    name="Point Cloud Segmentation",
    description="Segments a point cloud file into detected object instances",
    input_schema={
        "type": "object",
        "properties": {
            "point_cloud": {
                "type": "string",
                "format": "file",
                "description": "Point cloud file to segment",
                "x-accept": [".ply", ".pcd"],
                "x-maxSizeBytes": 104857600,  # 100 MB
            },
            "confidence_threshold": {
                "type": "number",
                "default": 0.5,
                "minimum": 0.0,
                "maximum": 1.0,
                "description": "Minimum confidence for instance detection",
            },
        },
        "required": ["point_cloud"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "instances": {
                "type": "string",
                "format": "file",
                "description": "InstanceSet JSON with detected objects",
            },
            "instance_count": {
                "type": "integer",
                "description": "Number of detected instances",
            },
        },
    },
    category="inference",
    timeout_seconds=120,
    styles=WorkflowNodeStyles(icon="Brain", color="purple"),
)


class SegmentNode(BaseNode):
    definition = definition

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        # File inputs are auto-downloaded by SDK before execute()
        local_path = Path(inputs["point_cloud"])  # SDK provides local path
        threshold = inputs.get("confidence_threshold", 0.5)

        # Process input file (SDK already validated against x-accept/x-maxSizeBytes)
        context.report_progress(0.1, "Processing point cloud")

        # Process point cloud (replace with actual ML inference)
        context.report_progress(0.3, "Running segmentation")
        try:
            instances = self._run_segmentation(local_path, threshold)
        except Exception as e:
            raise NodeExecutionError(f"Segmentation failed: {e}", error_code="MODEL_ERROR") from e

        # Build InstanceSet contract
        context.report_progress(0.8, "Saving results")
        instance_set = InstanceSet(
            instances=instances,
            class_names=["floor", "ceiling", "wall", "door", "vent"],
            point_count=len(instances) * 1000,  # Placeholder
            source_node="segment",
            source_file=local_path.name,
        )

        # Write output file
        output_path = context.output_path("instances.json")
        instance_set.save_json(output_path)

        context.report_progress(1.0, "Segmentation complete")
        return {
            "instances": str(output_path),
            "instance_count": len(instances),
        }

    def _run_segmentation(self, file_path: Path, threshold: float) -> list[Instance]:
        """Run segmentation model on point cloud. Replace with actual model."""
        # Placeholder: return sample instances
        return [
            Instance(
                instance_id=1,
                class_id=0,
                class_name="floor",
                confidence=0.98,
                point_indices=[0, 1, 2, 3, 4],
                centroid=Point3D(x=500.0, y=300.0, z=0.0),
                bounding_box=BoundingBox3D(
                    min_point=Point3D(x=0.0, y=0.0, z=0.0),
                    max_point=Point3D(x=1000.0, y=600.0, z=5.0),
                ),
            ),
        ]

    @staticmethod
    def _download(url: str, dest: Path) -> None:
        """Download helper for non-file URLs only (e.g., external APIs)."""
        with httpx.stream("GET", url, timeout=30.0, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)


app = SegmentNode().create_app()
```

## Pattern 2: Measurement Node

Consumes an InstanceSet and computes measurements (heights, widths, distances).

```python
"""Measurement Node — computes dimensions from detected instances."""

from pathlib import Path

import httpx
from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest, WorkflowNodeStyles
from canvastekk_workflow_sdk.contracts import (
    InstanceSet,
    Measurement,
    MeasurementSet,
    Point3D,
)
from canvastekk_workflow_sdk.exceptions import NodeIOError

definition = WorkflowNodeManifest(
    slug="measure",
    version="1.0.0",
    name="Measurement",
    description="Computes dimensional measurements from detected instances",
    input_schema={
        "type": "object",
        "properties": {
            "instances": {
                "type": "string",
                "format": "file",
                "description": "InstanceSet JSON from segmentation node",
                "x-accept": [".json"],
                "x-maxSizeBytes": 10485760,  # 10 MB
            },
        },
        "required": ["instances"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "measurements": {
                "type": "string",
                "format": "file",
                "description": "MeasurementSet JSON with computed values",
            },
            "measurement_count": {
                "type": "integer",
                "description": "Number of measurements computed",
            },
        },
    },
    category="transform",
    timeout_seconds=60,
    styles=WorkflowNodeStyles(icon="Ruler", color="cyan"),
)


class MeasureNode(BaseNode):
    definition = definition

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        # File inputs are auto-downloaded by SDK before execute()
        local_path = Path(inputs["instances"])

        # Parse InstanceSet (SDK already validated against x-accept/x-maxSizeBytes)
        context.report_progress(0.1, "Loading instances")

        try:
            instance_set = InstanceSet.load_json(local_path)
        except Exception as e:
            raise NodeIOError(f"Failed to parse InstanceSet: {e}", path=str(local_path)) from e

        # Compute measurements
        context.report_progress(0.5, "Computing measurements")
        measurements = []
        for inst in instance_set.instances:
            if inst.bounding_box:
                size = inst.bounding_box.size
                measurements.append(
                    Measurement(
                        name=f"{inst.class_name}_height",
                        value=size.z,
                        unit="mm",
                        method="bounding_box",
                        confidence=inst.confidence,
                        points=[inst.bounding_box.min_point, inst.bounding_box.max_point],
                    )
                )
                measurements.append(
                    Measurement(
                        name=f"{inst.class_name}_width",
                        value=size.x,
                        unit="mm",
                        method="bounding_box",
                    )
                )

        # Build and save MeasurementSet
        context.report_progress(0.8, "Saving measurements")
        result = MeasurementSet(
            measurements=measurements,
            source_node="measure",
            source_file=local_path.name,
        )
        output_path = context.output_path("measurements.json")
        result.save_json(output_path)

        context.report_progress(1.0, "Complete")
        return {
            "measurements": str(output_path),
            "measurement_count": len(measurements),
        }

    @staticmethod
    def _download(url: str, dest: Path) -> None:
        """Download helper for non-file URLs only (e.g., external APIs)."""
        with httpx.stream("GET", url, timeout=30.0, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)


app = MeasureNode().create_app()
```

## Pattern 3: Plane Detection Node

Detects planes in a point cloud and produces a PlaneSet.

```python
"""Plane Detection Node — detects planar surfaces in a point cloud."""

from pathlib import Path

import httpx
from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest, WorkflowNodeStyles
from canvastekk_workflow_sdk.contracts import Plane, PlaneSet, Point3D

definition = WorkflowNodeManifest(
    slug="plane-detect",
    version="1.0.0",
    name="Plane Detection",
    description="Detects planar surfaces (floor, ceiling, walls) in a point cloud",
    input_schema={
        "type": "object",
        "properties": {
            "point_cloud": {
                "type": "string",
                "format": "file",
                "description": "Point cloud file",
                "x-accept": [".ply", ".pcd"],
                "x-maxSizeBytes": 104857600,
            },
        },
        "required": ["point_cloud"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "planes": {
                "type": "string",
                "format": "file",
                "description": "PlaneSet JSON with detected planes",
            },
            "plane_count": {
                "type": "integer",
                "description": "Number of planes detected",
            },
        },
    },
    category="inference",
    timeout_seconds=90,
    styles=WorkflowNodeStyles(icon="Layers", color="indigo"),
)


class PlaneDetectNode(BaseNode):
    definition = definition

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        # File inputs are auto-downloaded by SDK before execute()
        local_path = Path(inputs["point_cloud"])
        context.report_progress(0.1, "Processing point cloud")  # SDK already validated

        context.report_progress(0.4, "Detecting planes")
        planes = self._detect_planes(local_path)

        plane_set = PlaneSet(
            planes=planes,
            source_node="plane-detect",
        )
        output_path = context.output_path("planes.json")
        plane_set.save_json(output_path)

        context.report_progress(1.0, "Complete")
        return {
            "planes": str(output_path),
            "plane_count": len(planes),
        }

    def _detect_planes(self, file_path: Path) -> list[Plane]:
        """Replace with actual RANSAC or ML-based plane detection."""
        return [
            Plane(point=Point3D(x=0, y=0, z=0), normal=Point3D(x=0, y=0, z=1), label="floor"),
            Plane(point=Point3D(x=0, y=0, z=2800), normal=Point3D(x=0, y=0, z=-1), label="ceiling"),
        ]

    @staticmethod
    def _download(url: str, dest: Path) -> None:
        """Download helper for non-file URLs only (e.g., external APIs)."""
        with httpx.stream("GET", url, timeout=30.0, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)


app = PlaneDetectNode().create_app()
```

## Pattern 4: Model Inference with Startup/Shutdown

Loads a model at startup, checks GPU health, and runs inference in execute().

```python
"""Inference Node — loads model at startup and runs inference per request."""

from pathlib import Path

import httpx
from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest, WorkflowNodeStyles
from canvastekk_workflow_sdk.exceptions import NodeConfigurationError, NodeExecutionError

definition = WorkflowNodeManifest(
    slug="infer",
    version="1.0.0",
    name="Model Inference",
    description="Runs ML model inference on input data",
    input_schema={
        "type": "object",
        "properties": {
            "input_data": {
                "type": "string",
                "format": "file",
                "description": "Input data file",
                "x-accept": [".ply", ".npy", ".json"],
                "x-maxSizeBytes": 52428800,  # 50 MB
            },
        },
        "required": ["input_data"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "predictions": {
                "type": "string",
                "format": "file",
                "description": "Prediction results JSON",
            },
        },
    },
    category="inference",
    timeout_seconds=120,
    token_cost=1.0,
    styles=WorkflowNodeStyles(icon="Cpu", color="emerald"),
)


class InferenceNode(BaseNode):
    definition = definition

    def __init__(self):
        super().__init__()
        self.model = None

    async def on_startup(self) -> None:
        """Load model into memory at server startup."""
        self.model = self._load_model()

    async def on_shutdown(self) -> None:
        """Release model and GPU memory."""
        if self.model is not None:
            del self.model
            self.model = None

    def health_check(self) -> dict[str, bool]:
        """Check if model is loaded and GPU is available."""
        return {
            "model_loaded": self.model is not None,
            "gpu_available": self._check_gpu(),
        }

    def _check_gpu(self) -> bool:
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _load_model(self):
        """Load your model here. Replace with actual model loading."""
        # import torch
        # return torch.load("model.pt")
        return "dummy_model"

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        if self.model is None:
            raise NodeConfigurationError("Model not loaded — startup may have failed")

        # File inputs are auto-downloaded by SDK before execute()
        local_path = Path(inputs["input_data"])
        context.report_progress(0.1, "Processing input data")  # SDK already validated

        context.report_progress(0.3, "Running inference")
        try:
            result = self._run_inference(local_path)
        except Exception as e:
            raise NodeExecutionError(f"Inference failed: {e}", error_code="MODEL_ERROR") from e

        context.report_progress(0.9, "Saving predictions")
        output_path = context.output_path("predictions.json")
        output_path.write_text(result)

        context.report_progress(1.0, "Complete")
        return {"predictions": str(output_path)}

    def _run_inference(self, file_path: Path) -> str:
        """Replace with actual model inference."""
        import json
        return json.dumps({"status": "ok", "predictions": []})

    @staticmethod
    def _download(url: str, dest: Path) -> None:
        """Download helper for non-file URLs only (e.g., external APIs)."""
        with httpx.stream("GET", url, timeout=30.0, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)


app = InferenceNode().create_app()
```

## Pattern 5: Simple Transform (No File I/O)

A pure data transform node with no file uploads/downloads.

```python
"""Uppercase Node — converts text to uppercase (no file I/O)."""

from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest

definition = WorkflowNodeManifest(
    slug="uppercase",
    version="1.0.0",
    name="Uppercase",
    description="Converts input text to uppercase",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to convert"},
        },
        "required": ["text"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "result": {"type": "string", "description": "Uppercased text"},
        },
    },
    category="utility",
)


class UppercaseNode(BaseNode):
    definition = definition

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        context.report_progress(0.5, "Processing text")
        return {"result": inputs["text"].upper()}


app = UppercaseNode().create_app()
```

## Pattern 6: Node with Authentication

```python
from canvastekk_workflow_sdk.auth import NodeAuth
from fastapi import Depends

# Choose one auth layer:

# Layer 1: API Key (simplest)
auth = NodeAuth.api_key()  # Reads CANVASTEKK_API_KEY env var

# Layer 2: JWT (HMAC-SHA256)
auth = NodeAuth.jwt()  # Reads CANVASTEKK_JWT_SECRET env var

# Layer 3: Keycloak (enterprise)
auth = NodeAuth.keycloak()  # Reads CANVASTEKK_KEYCLOAK_* env vars

# Apply:
app = MyNode().create_app(dependencies=[Depends(auth)])
```

During development, set `CANVASTEKK_DEV_MODE=true` to bypass auth.

## Pattern 7: Custom Middleware

```python
from typing import Any
from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest
from canvastekk_workflow_sdk.middleware import NodeMiddleware


class AuditMiddleware:
    """Logs execution details for auditing purposes."""

    def on_before_execute(
        self, inputs: dict[str, Any], context: ExecutionContext
    ) -> dict[str, Any]:
        context.logger.info(
            "Audit: execution started",
            extra={"run_id": context.run_id, "node_id": context.node_id, "input_count": len(inputs)},
        )
        return inputs

    def on_after_execute(
        self,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        context.logger.info(
            "Audit: execution completed",
            extra={"run_id": context.run_id, "duration_ms": duration_ms, "output_count": len(outputs)},
        )

    def on_error(
        self,
        inputs: dict[str, Any],
        error: Exception,
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        context.logger.error(
            f"Audit: execution failed: {error}",
            extra={"run_id": context.run_id, "error_type": type(error).__name__},
        )


# Register with chaining:
node = MyNode()
node.add_middleware(AuditMiddleware())
app = node.create_app()
```

## Pattern 8: Webhook/Callback Handling

```python
class AsyncTaskNode(BaseNode):
    definition = WorkflowNodeManifest(...)

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        """Start a long-running task and return immediately."""
        task_id = self._start_task(inputs)
        return {"task_id": task_id, "status": "processing"}

    def hook(self, payload: dict) -> dict | None:
        """Handle callback when async task completes."""
        task_id = payload.get("task_id")
        result = payload.get("result")

        if task_id and result:
            return {"task_id": task_id, "status": "completed", "result": result}

        return None  # Returns 501 Not Implemented
```

## Pattern 9: Multi-Node Application

Host multiple nodes under one server:

```python
from canvastekk_workflow_sdk import create_multi_node_app

# Each node gets its own URL prefix:
# POST /segment/execute, GET /segment/health, ...
# POST /measure/execute, GET /measure/health, ...
app = create_multi_node_app({
    "segment": SegmentNode(),
    "measure": MeasureNode(),
})
```

## Pattern 10: Format Conversion Node

Converts between file formats (e.g., PLY to XYZ):

```python
"""Format Converter Node — converts point cloud file formats."""

from pathlib import Path

import httpx
from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest, WorkflowNodeStyles

definition = WorkflowNodeManifest(
    slug="convert",
    version="1.0.0",
    name="Format Converter",
    description="Converts point cloud files between formats (PLY, PCD, XYZ)",
    input_schema={
        "type": "object",
        "properties": {
            "input_file": {
                "type": "string",
                "format": "file",
                "description": "Input point cloud file",
                "x-accept": [".ply", ".pcd"],
                "x-maxSizeBytes": 52428800,  # 50 MB
            },
            "output_format": {
                "type": "string",
                "enum": ["xyz", "csv"],
                "default": "xyz",
                "description": "Target output format",
            },
        },
        "required": ["input_file"],
    },
    output_schema={
        "type": "object",
        "properties": {
            "converted": {
                "type": "string",
                "format": "file",
                "description": "Converted output file",
            },
            "point_count": {
                "type": "integer",
                "description": "Number of points in output",
            },
        },
    },
    category="transform",
    timeout_seconds=60,
    styles=WorkflowNodeStyles(icon="FileOutput", color="amber"),
)


class ConvertNode(BaseNode):
    definition = definition

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        # File inputs are auto-downloaded by SDK before execute()
        input_path = Path(inputs["input_file"])
        output_format = inputs.get("output_format", "xyz")

        context.report_progress(0.1, "Converting format")  # SDK already validated

        context.report_progress(0.5, f"Converting to {output_format}")
        output_path = context.output_path(f"output.{output_format}")
        point_count = self._convert(input_path, output_path, output_format)

        context.report_progress(1.0, "Conversion complete")
        return {
            "converted": str(output_path),
            "point_count": point_count,
        }

    def _convert(self, input_path: Path, output_path: Path, fmt: str) -> int:
        """Convert point cloud format. Replace with actual conversion logic."""
        # Placeholder: read input, write output
        data = input_path.read_bytes()
        output_path.write_bytes(data)
        return 1000  # placeholder point count

    @staticmethod
    def _download(url: str, dest: Path) -> None:
        """Download helper for non-file URLs only (e.g., external APIs)."""
        with httpx.stream("GET", url, timeout=30.0, follow_redirects=True) as resp:
            resp.raise_for_status()
            with open(dest, "wb") as f:
                for chunk in resp.iter_bytes(chunk_size=65536):
                    f.write(chunk)


app = ConvertNode().create_app()
```

---

## Testing Patterns

### Testing File Download with Mocked httpx

```python
from pathlib import Path
from unittest.mock import patch

from canvastekk_workflow_sdk import NodeExecutionRequest


def make_mock_stream_response(content: bytes):
    """Create a mock httpx.stream response for testing file downloads."""

    class MockResponse:
        def raise_for_status(self):
            pass

        def iter_bytes(self, chunk_size):
            yield content

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    return MockResponse()


@patch("handler.httpx.stream")
def test_execute_downloads_and_processes(mock_stream, tmp_path):
    mock_stream.return_value = make_mock_stream_response(b"fake point cloud data")

    node = MyNode()
    request = NodeExecutionRequest(
        run_id="test-run",
        node_id="test-node",
        inputs={"point_cloud": "https://example.com/test.ply"},
    )
    response = node.run(request)

    assert response.status == "pass"
    assert response.outputs is not None
```

### Testing Contract Serialization

```python
from canvastekk_workflow_sdk.contracts import InstanceSet, Instance, Point3D, MeasurementSet, Measurement


def test_instance_set_roundtrip(tmp_path):
    """Test InstanceSet save/load roundtrip."""
    original = InstanceSet(
        instances=[
            Instance(
                instance_id=1,
                class_id=0,
                class_name="floor",
                confidence=0.95,
                point_indices=[0, 1, 2],
                centroid=Point3D(x=1.0, y=2.0, z=3.0),
            ),
        ],
        class_names=["floor"],
        point_count=1000,
        source_node="test",
    )

    path = tmp_path / "instances.json"
    original.save_json(path)
    loaded = InstanceSet.load_json(path)

    assert len(loaded.instances) == 1
    assert loaded.instances[0].class_name == "floor"
    assert loaded.point_count == 1000


def test_measurement_set_helpers():
    """Test MeasurementSet lookup helpers."""
    ms = MeasurementSet(
        measurements=[
            Measurement(name="height", value=2800.0, unit="mm"),
            Measurement(name="width", value=5000.0, unit="mm"),
        ],
    )

    assert ms.get_value("height") == 2800.0
    assert ms.get_value("nonexistent", default=0.0) == 0.0
    assert ms.get_measurement("width").value == 5000.0
```

### Testing API Endpoints with TestClient

```python
from fastapi.testclient import TestClient
from handler import app

client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"


def test_manifest_contains_sdk_version():
    resp = client.get("/manifest")
    data = resp.json()
    assert "sdk_version" in data
    assert "mode" in data


def test_execute_with_mocked_download():
    """Test the full HTTP stack with mocked file download."""
    from unittest.mock import patch

    with patch("handler.httpx.stream") as mock_stream:
        # Set up mock
        mock_stream.return_value = make_mock_stream_response(b"test data")

        resp = client.post(
            "/execute",
            json={
                "run_id": "run-1",
                "node_id": "node-1",
                "inputs": {"point_cloud": "https://example.com/test.ply"},
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "pass"
```

---

## Quick Reference: Contract Fields

### Instance

| Field          | Type              | Required | Description                        |
| -------------- | ----------------- | -------- | ---------------------------------- |
| instance_id    | int               | Yes      | Unique ID within instance set      |
| class_id       | int               | Yes      | Numeric class identifier           |
| class_name     | str               | Yes      | Human-readable class name          |
| confidence     | float             | No       | Detection confidence (0.0-1.0)     |
| point_indices  | list[int]         | Yes      | Indices of points in instance      |
| centroid       | Point3D or None   | No       | Centroid of instance               |
| bounding_box   | BoundingBox3D or None | No   | Bounding box of instance           |
| metadata       | dict              | No       | Additional instance metadata       |

### Measurement

| Field       | Type           | Required | Description                         |
| ----------- | -------------- | -------- | ----------------------------------- |
| name        | str            | Yes      | Measurement name (e.g., "height")   |
| value       | float          | Yes      | Measured value                      |
| unit        | str            | No       | Unit (default: "mm")               |
| method      | str            | No       | Method used (default: "unknown")    |
| confidence  | float          | No       | Confidence (0.0-1.0)               |
| points      | list[Point3D]  | No       | Key points for visualization        |
| metadata    | dict           | No       | Additional metadata                 |

### Plane

| Field  | Type          | Required | Description                       |
| ------ | ------------- | -------- | --------------------------------- |
| point  | Point3D       | Yes      | A point on the plane              |
| normal | Point3D       | Yes      | Unit normal vector                |
| label  | str or None   | No       | Optional label (e.g., "floor")    |

## File-input download facts: `context.metadata`

File inputs marked `"format": "file"` are auto-downloaded by the SDK before
`execute()` — your handler receives a local path. After download+validation,
the SDK records facts per field in `context.metadata` (see `base.py`):

```python
context.metadata[field_name] = {
    "original_url": value,       # the input URL string
    "local_path": str(local_path),
    "size_bytes": file_size,
}
```

Read these in `execute()` for audit trails or size-based branching. Manual
`httpx.stream()` downloads are for non-file URLs or opt-out scenarios only.

## Upload target: `UploadSession`

Output upload targets come from the engine and are a multipart `UploadSession`
descriptor. Since SDK 0.36.0 (DA-3340) a legacy presigned PUT URL string is
rejected with `NodeIOError` ("engine sent deprecated presigned target —
upgrade the engine") — the fix is upgrading the engine, not node changes.
Your node never constructs one:

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    out = context.output_path("result.parquet")
    # ... write the file ...
    return {"output_file": str(out)}   # SDK uploads via the engine's session
```

Rules: pass targets through untouched — no string slicing, concatenation, or
`startswith("http")` checks; no URL prefetch or persistence. The SDK
redeems `UploadSession` lazily (initiate → parallel part PUTs → complete,
resume via status; see `uploads.py` / `multipart.py`).
