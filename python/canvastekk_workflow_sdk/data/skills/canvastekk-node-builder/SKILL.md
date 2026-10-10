---
name: canvastekk-node-builder
description: Create CanvasTEKK workflow nodes with correct SDK patterns, schemas, file I/O, Dockerfiles, and tests. Covers BaseNode, WorkflowNodeManifest, ExecutionContext, contracts, and the complete node creation workflow from analysis to CLI validation. File inputs are auto-downloaded by the SDK before execute().
---

## What I do

I guide the complete creation of CanvasTEKK Workflow Engine nodes using the Python SDK (`canvastekk-workflow-sdk`). I provide:

- Complete SDK API reference embedded as working knowledge (no doc lookups needed)
- A 7-step node creation workflow from requirements analysis to CLI validation
- Code templates for all required files (handler.py, Dockerfile, pyproject.toml, tests)
- JSON Schema patterns for input/output definitions including file fields
- File I/O patterns (presigned URL downloads, validate_file_input, output_path)
- Data contract patterns (InstanceSet, MeasurementSet, PlaneSet)
- A validation checklist and catalog of common mistakes to avoid

## When to use me

Load this skill when a user asks to:

- "Create a workflow node that does X"
- "Build a CanvasTEKK node for Y"
- "Scaffold a new node with BaseNode"
- "Add a node that processes point clouds / measures distances / converts formats"
- "Set up a CanvasTEKK node project with Dockerfile and tests"
- "Help me define input_schema and output_schema for a node"
- Any task involving CanvasTEKK workflow node creation or SDK usage

For domain-specific code examples (point cloud segmentation patterns, measurement patterns, inference with model loading, auth, middleware, webhooks), also load the `canvastekk-node-patterns` skill after this one.

## SDK API Reference

### Imports

```python
from canvastekk_workflow_sdk import (
    BaseNode,
    WorkflowNodeManifest,
    ExecutionContext,
    WorkflowNodeStyles,
    RetryConfig,
    NodeAuth,
    NodeExecutionRequest,
    NodeExecutionResponse,
    HealthResponse,
    # Contracts
    Point3D,
    BoundingBox3D,
    Plane,
    PlaneSet,
    Instance,
    InstanceSet,
    Measurement,
    MeasurementSet,
    # Exceptions
    NodeExecutionError,
    NodeValidationError,
    NodeTimeoutError,
    NodeIOError,
    NodeConfigurationError,
    NodeOutputValidationError,
    # Utilities
    export_definition,
    register_node,
    create_multi_node_app,
    get_node_logger,
    configure_logging,
)
```

### BaseNode (Required Base Class)

All nodes must subclass `BaseNode`, define a class-level `definition` attribute, and implement `execute()`.

```python
from canvastekk_workflow_sdk import BaseNode, WorkflowNodeManifest, ExecutionContext

class MyNode(BaseNode):
    definition = WorkflowNodeManifest(...)  # Class-level attribute (NOT inside __init__)

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        """Required: Implement business logic. Return a dict matching output_schema."""
        return {"result": "..."}

    # Optional overrides:
    def health_check(self) -> dict[str, bool]:
        """Override to add custom health checks (e.g., model_loaded, gpu_available)."""
        return {}

    def hook(self, payload: dict) -> dict | None:
        """Override for webhook/callback handling. Default returns None (501)."""
        return None

    async def on_startup(self) -> None:
        """Override for initialization (load models, warm caches). Called once at startup."""

    async def on_shutdown(self) -> None:
        """Override for cleanup (close connections, release resources). Called once at shutdown."""
```

**App creation** (required at module level in handler.py):

```python
app = MyNode().create_app()

# With authentication:
from fastapi import Depends
from canvastekk_workflow_sdk import NodeAuth
auth = NodeAuth.api_key()
app = MyNode().create_app(dependencies=[Depends(auth)])

# With middleware chaining:
node = MyNode()
node.add_middleware(MyMiddleware())
app = node.create_app()
```

### WorkflowNodeManifest (Required)

```python
from canvastekk_workflow_sdk import WorkflowNodeManifest, RetryConfig, WorkflowNodeStyles

definition = WorkflowNodeManifest(
    # === REQUIRED ===
    slug="segment",                    # Slug for routing (lowercase, hyphens)
    version="1.0.0",                   # Semantic version
    name="Point Cloud Segmentation",  # Human-readable title
    description="Segments a point cloud into instances",  # What this node does
    input_schema={...},                # JSON Schema (Draft 7)
    output_schema={...},               # JSON Schema (Draft 7)

    # === OPTIONAL (with defaults shown) ===
    category="utility",                # "transform" | "inference" | "utility" | "control-flow"
    timeout_seconds=30,                # Max execution time in seconds (min: 1)
    token_cost=0.0,                    # Cost per execution (float >= 0)
    default_retry=RetryConfig(),       # See RetryConfig below
    styles=None,                       # See WorkflowNodeStyles below
)
```

#### RetryConfig

```python
RetryConfig(
    max_attempts=1,           # Total attempts (1 = no retry, 3 = 1 initial + 2 retries)
    initial_delay_ms=1000,    # Delay before first retry (ms)
    backoff_multiplier=2.0,   # Exponential backoff multiplier (>= 1.0)
    max_delay_ms=30000,       # Maximum delay between retries (ms)
)
```

#### WorkflowNodeStyles and ColorPreset

```python
WorkflowNodeStyles(
    icon="Brain",       # Any Lucide icon name in PascalCase (1500+ icons). See https://lucide.dev/icons
    color="emerald",    # ColorPreset value (see below)
)

# ColorPreset options:
# Standard:  purple, red, gray, cyan, emerald, orange, amber, sky, violet,
#            teal, indigo, slate, blue, green, pink, yellow, rose, lime, fuchsia
# Light:     emerald-light, indigo-light, slate-light
# Dark:      red-dark, sky-dark, teal-dark, emerald-dark
```

#### WorkflowNodeManifest Properties and Methods

```python
definition.file_input_fields    # list[str] — field names with format: "file" in input_schema
definition.file_output_fields   # list[str] — field names with format: "file" in output_schema
definition.has_file_inputs      # bool — True if any file input fields exist
definition.validate_file_input(field_name, file_path)  # Validate downloaded file against x-* extensions
definition.to_dict()            # Serialize to dict for JSON
```

### ExecutionContext

Provided to `execute()` — contains run context, output directory, logger, and progress reporting.

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    # === Identifiers ===
    context.run_id          # str — Workflow run identifier (e.g., "run-abc123")
    context.node_id         # str — Node instance ID in workflow (e.g., "segment-1")

    # === File Output ===
    context.output_dir                     # Path — Auto-created temp dir (/tmp/{run_id}/{node_id}/)
    context.output_path("result.json")     # Path — Get path for output file in output_dir

    # === Logging ===
    context.logger          # logging.Logger — Pre-configured with context (run_id, node_id)
    context.logger.info("Processing started")
    context.logger.info("File downloaded", extra={"file_size_bytes": len(data)})

    # === Progress (0.0 to 1.0) ===
    context.report_progress(0.5, "Halfway done")

    # === Token Usage (for LLM nodes) ===
    context.record_token_usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    context.token_usage     # dict — {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    return {}
```

### NodeExecutionRequest (inbound payload)

The engine sends this to POST /execute:

```python
NodeExecutionRequest(
    run_id="workflow-run-abc123",       # Required
    node_id="node-instance-456",        # Required
    inputs={"field": "value"},          # Validated against input_schema
    callback_url=None,                  # Optional: for async execution
    output_upload_url=None,             # Optional: {"field_name": "<UploadSession descriptor>"}
)
```

### Exception Types

```python
from canvastekk_workflow_sdk.exceptions import (
    NodeExecutionError,          # Generic: error_code="EXECUTION_ERROR", HTTP 500
    NodeValidationError,         # Input validation: error_code="VALIDATION_ERROR", HTTP 422
    NodeTimeoutError,            # Timeout: error_code="TIMEOUT", HTTP 408
    NodeIOError,                 # File I/O: error_code="IO_ERROR", HTTP 500
    NodeConfigurationError,      # Bad config: error_code="CONFIGURATION_ERROR", HTTP 500
    NodeOutputValidationError,   # Output validation: error_code="OUTPUT_VALIDATION_ERROR", HTTP 422
)

# Usage in execute():
raise NodeIOError("File not found", path=str(file_path))
raise NodeExecutionError("Model inference failed", error_code="MODEL_ERROR")
raise NodeTimeoutError(timeout_seconds=60)
```

### Data Contracts

Standard data formats for passing structured data between nodes. All contracts extend `BaseContract` which provides `save_json()` and `load_json()`.

```python
from canvastekk_workflow_sdk.contracts import (
    Point3D,              # x, y, z coordinates (mm)
    BoundingBox3D,        # min_point, max_point + center, size properties
    Plane,                # point, normal, optional label
    PlaneSet,             # Collection of planes + get_plane_by_label()
    Instance,             # instance_id, class_id, class_name, confidence, point_indices, centroid, bounding_box
    InstanceSet,          # Collection of instances + get_instances_by_class/id()
    Measurement,          # name, value, unit, method, confidence, points
    MeasurementSet,       # Collection of measurements + get_measurement/value()
)
```

### Authentication (Optional)

```python
from canvastekk_workflow_sdk.auth import NodeAuth
from fastapi import Depends

# Layer 1: API Key (simplest)
auth = NodeAuth.api_key()  # Reads CANVASTEKK_API_KEY env var

# Layer 2: JWT (HMAC-SHA256) — requires PyJWT
auth = NodeAuth.jwt()  # Reads CANVASTEKK_JWT_SECRET env var

# Layer 3: Keycloak (enterprise) — requires PyJWT + cryptography
auth = NodeAuth.keycloak()  # Reads CANVASTEKK_KEYCLOAK_* env vars

# Apply to app:
app = MyNode().create_app(dependencies=[Depends(auth)])
```

### Auto-Generated Endpoints

`create_app()` creates these endpoints automatically:

| Endpoint  | Method | Purpose |
|-----------|--------|---------|
| `/execute` | POST | Run node business logic |
| `/health` | GET | Health status (calls health_check()) |
| `/manifest` | GET | Node self-description + sdk_version + mode |
| `/hook` | POST | Webhook handler (501 if not overridden) |
| `/metrics` | GET | Execution statistics |
| `/live` | GET | Liveness probe (Kubernetes) |
| `/ready` | GET | Readiness probe (Kubernetes) |

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CANVASTEKK_NODE_ENV` | `dev` | `dev`/`uat`/`production` — appears in /manifest `mode` field |
| `CANVASTEKK_LOG_LEVEL` | `INFO` | Log level |
| `CANVASTEKK_LOG_FORMAT` | `json` | `json` (CloudWatch/ELK) or `text` (human-readable) |
| `CANVASTEKK_OUTPUT_DIR` | `/tmp` | Base directory for output files |
| `CANVASTEKK_DEV_MODE` | — | Bypass all auth. NEVER in production |
| `CANVASTEKK_API_KEY` | — | Shared secret for API key auth |
| `CANVASTEKK_JWT_SECRET` | — | Signing secret for JWT auth |
| `CANVASTEKK_KEYCLOAK_*` | — | Keycloak configuration |

### Package Installation

```bash
pip install canvastekk-workflow-sdk --index-url https://USERNAME:TOKEN@pypi.pkg.github.com/betekk/
```

Optional extras: `canvastekk-workflow-sdk[jwt]`, `canvastekk-workflow-sdk[keycloak]`, or `canvastekk-workflow-sdk[serve]` (bundles uvicorn for container serving — since SDK 0.41 the base install no longer includes uvicorn)

---

## Node Creation Workflow

### Step 1: Analyze the Request

Before writing any code, determine:

1. **Node purpose**: What does it do? (segmentation, measurement, format conversion, inference, filtering, etc.)
2. **Input types**: What data does it accept? (point cloud files, JSON contracts, text parameters, numbers)
3. **Output types**: What does it produce? (files, JSON data, contracts, metrics)
4. **Category**: `transform` (data conversion), `inference` (ML/AI), `utility` (general), `control-flow` (orchestrator-level)
5. **File I/O needed**: Does it receive file inputs (auto-downloaded by SDK)? Does it write output files?
6. **Contracts needed**: Will it produce or consume InstanceSet, MeasurementSet, PlaneSet?
7. **Special needs**: Model loading at startup? GPU access? Authentication? Custom health checks?
8. **Timeout**: How long might execution take? (default: 30s, increase for heavy computation)

### Step 2: Design Schemas

Create `input_schema` and `output_schema` as JSON Schema (Draft 7).

**Schema rules:**
- File fields: `"type": "string", "format": "file"` (NEVER `"format": "binary"`, NEVER `"type": "object"`)
- Always add `"x-accept": [".ext1", ".ext2"]` for file inputs (allowed extensions)
- Always add `"x-maxSizeBytes": N` for file inputs (maximum file size)
- Mark required fields in `"required": ["field1", "field2"]`
- Use `"description"` on every property for frontend documentation

**Simple inputs schema:**

```python
input_schema={
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "Input text to process"},
        "confidence": {"type": "number", "default": 0.5, "minimum": 0, "maximum": 1},
    },
    "required": ["text"],
}
```

**File input schema:**

```python
input_schema={
    "type": "object",
    "properties": {
        "point_cloud": {
            "type": "string",
            "format": "file",
            "description": "Point cloud file to process",
            "x-accept": [".ply", ".pcd"],
            "x-maxSizeBytes": 104857600,  # 100 MB
        },
        "confidence_threshold": {
            "type": "number",
            "default": 0.5,
            "minimum": 0.0,
            "maximum": 1.0,
            "description": "Minimum confidence threshold",
        },
    },
    "required": ["point_cloud"],
}
```

**File output schema:**

```python
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
}
```

### Step 3: Generate handler.py

Follow this structure exactly:

```python
"""{{Title}} Node — {{one-line description}}."""

from pathlib import Path

from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest

definition = WorkflowNodeManifest(
    slug="{{name}}",
    version="{{version}}",
    name="{{title}}",
    description="{{description}}",
    input_schema={...},  # From Step 2
    output_schema={...},  # From Step 2
    category="{{category}}",
    timeout_seconds={{timeout}},
)


class {{ClassName}}(BaseNode):
    definition = definition

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        # Report progress at key stages
        context.report_progress(0.1, "Starting {{title}}")

        # === FILE INPUT PATTERN ===
        # File inputs are auto-downloaded by SDK to context.downloads_dir
        # Use local file paths directly (SDK already validated against x-accept/x-maxSizeBytes):
        # local_path = Path(inputs["file_field"])  # SDK provides local path

        # === BUSINESS LOGIC ===
        # Process inputs here

        # === FILE OUTPUT PATTERN ===
        # If node produces files, write to output_path:
        # output_path = context.output_path("result.ext")
        # output_path.write_bytes(data)
        # Return the path as a string:
        # return {"file_field": str(output_path), "other_field": value}

        context.report_progress(1.0, "Complete")
        return {}


app = {{ClassName}}().create_app()
```

**Critical: `definition` must be a module-level variable AND a class attribute.** The module-level variable enables CLI validation (`python -m canvastekk_workflow_sdk validate handler:definition`). The class attribute is required by `BaseNode.__init_subclass__`.

### Step 4: Generate Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install SDK from GitHub Packages
COPY pyproject.toml ./
RUN pip install "canvastekk-workflow-sdk>=0.5.2" uvicorn \
    --index-url https://betekk:${SDK_PAT}@pypi.pkg.github.com/betekk/

# Copy node code
COPY handler.py .

EXPOSE 8001

CMD ["uvicorn", "handler:app", "--host", "0.0.0.0", "--port", "8001"]
```

**If the node has extra dependencies:**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install all dependencies
COPY pyproject.toml ./
RUN pip install . \
    --index-url https://betekk:${SDK_PAT}@pypi.pkg.github.com/betekk/ \
    --extra-index-url https://pypi.org/simple/

COPY handler.py .

EXPOSE 8001

CMD ["uvicorn", "handler:app", "--host", "0.0.0.0", "--port", "8001"]
```

### Step 5: Generate pyproject.toml

```toml
[project]
name = "{{name}}-node"
version = "{{version}}"
description = "{{description}}"
requires-python = ">=3.12"
dependencies = [
    "canvastekk-workflow-sdk>=0.5.2",
    "uvicorn>=0.54",
]

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
```

**If extra dependencies are needed:**

```toml
dependencies = [
    "canvastekk-workflow-sdk>=0.5.2",
    "uvicorn>=0.54",
    "numpy>=1.26",
    "open3d>=0.18",
]
```

### Step 6: Generate Tests

Create `tests/test_handler.py` following this template:

```python
"""Tests for {{ClassName}}."""

from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from canvastekk_workflow_sdk import NodeExecutionRequest

from handler import {{ClassName}}, app, definition


class Test{{ClassName}}Unit:
    """Unit tests for node business logic."""

    def test_definition_fields(self):
        """Verify WorkflowNodeManifest has all required fields."""
        assert definition.id == "{{name}}-v{{version}}"
        assert definition.slug == "{{name}}"
        assert definition.version == "{{version}}"
        assert definition.input_schema
        assert definition.output_schema

    def test_definition_file_fields(self):
        """Verify file field declarations match expectations."""
        # Adjust based on actual file fields
        expected_inputs = ["..."]   # e.g., ["point_cloud"]
        expected_outputs = ["..."]  # e.g., ["instances"]
        assert definition.file_input_fields == expected_inputs
        assert definition.file_output_fields == expected_outputs

    def test_definition_schema_format(self):
        """Verify file fields use format: 'file' and type: 'string'."""
        for field_name in definition.file_input_fields:
            schema = definition.input_schema["properties"][field_name]
            assert schema["format"] == "file"
            assert schema["type"] == "string"

    def test_execute_returns_expected_output(self):
        """Test execute() with valid inputs returns correct structure."""
        # Mock external dependencies (file downloads, model inference, etc.)
        node = {{ClassName}}()
        request = NodeExecutionRequest(
            run_id="test-run",
            node_id="test-node",
            inputs={"...": "..."},  # Provide valid test inputs
        )
        response = node.run(request)

        assert response.status == "pass"
        assert response.outputs is not None
        # Assert specific output fields
        # assert "result" in response.outputs


class Test{{ClassName}}API:
    """Integration tests for HTTP endpoints."""

    client = TestClient(app)

    def test_health(self):
        resp = self.client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["node_id"] == "{{name}}-v{{version}}"

    def test_manifest(self):
        resp = self.client.get("/manifest")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "{{name}}"
        assert "input_schema" in data
        assert "output_schema" in data
        assert "sdk_version" in data

    def test_liveness(self):
        resp = self.client.get("/live")
        assert resp.status_code == 200
        assert resp.json()["status"] == "alive"

    def test_readiness(self):
        resp = self.client.get("/ready")
        assert resp.status_code == 200

    def test_execute_endpoint(self):
        """Test POST /execute with valid inputs."""
        # Mock file downloads if needed
        resp = self.client.post(
            "/execute",
            json={
                "run_id": "test-run",
                "node_id": "test-node",
                "inputs": {"...": "..."},  # Provide valid test inputs
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "pass"
        assert "outputs" in data
```

### Step 7: Validate

Run the CLI validator to verify the definition:

```bash
# Basic validation (human-readable)
python -m canvastekk_workflow_sdk validate handler:definition

# JSON output (for CI)
python -m canvastekk_workflow_sdk validate handler:definition --json
```

The validator checks:
- File fields use `format: "file"` (rejects `format: "binary"`)
- File fields have `type: "string"` (rejects `type: "object"` or `"array"`)
- Warns on file fields missing `x-accept` or `x-maxSizeBytes`
- Exit code: 0 = valid, 1 = errors

Also run the test suite:

```bash
pytest tests/ -v
```

---

## File I/O Detailed Guide

### How File Inputs Work

1. The workflow engine sends a presigned GET URL as the field value
2. The SDK downloads the file to `context.downloads_dir` before calling `execute()`
3. The SDK validates the downloaded file against `x-accept` and `x-maxSizeBytes` constraints
4. The node receives a local file path in `inputs` (not the URL)
5. The node processes the file

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    # 1. Get the local file path from inputs (SDK already downloaded)
    local_path = Path(inputs["point_cloud"])  # SDK provides local path

    # 2. Process the file (SDK already validated constraints)
    # ... your logic here ...
```

**Note:** Manual download with `httpx.stream()` is only needed for non-file URLs or opt-out scenarios.

### How File Outputs Work

1. Write output files to `context.output_path("filename.ext")`
2. Return the file path as a string in the outputs dict
3. The SDK uploads the file automatically after successful execution — the engine provides the upload target, which is a multipart `UploadSession` descriptor; since SDK 0.36.0 a legacy presigned PUT URL string is rejected with `NodeIOError` (DA-3340)

**Upload targets: `UploadSession`** (`canvastekk_workflow_sdk.uploads.UploadTarget`)

The engine mints the target; your node never constructs one and must pass it through untouched:

- `UploadSession` (multipart, DA-2885/2886): engine-minted descriptor (`session_token`, `initiate_url`, `complete_url`, `abort_url`, `status_url`, TTL-bound). The SDK redeems it lazily — POSTs size to `initiate_url`, PUTs parts in bounded parallel batches, finalizes via `complete_url`; resume via `status_url` (machinery in `multipart.py`).
- Legacy presigned-PUT string: removed in SDK 0.36.0 — reaching the SDK it raises `NodeIOError` ("engine sent deprecated presigned target — upgrade the engine"). There is no warning to silence and no fallback; the fix is upgrading the engine (DA-3338), not node changes.

Rules: never assume the target is a string (no slicing, concatenation, or `.startswith("http")` checks); never persist or pre-fetch URLs; return the output path and let the SDK upload.

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    # Write output file
    output_path = context.output_path("result.json")
    output_path.write_text('{"data": "..."}')

    # Return the path as a string — the SDK handles the upload
    return {"output_file": str(output_path)}
```

### Contract File I/O

```python
from canvastekk_workflow_sdk.contracts import InstanceSet

# Save contract to output
instance_set = InstanceSet(instances=[...], class_names=[...], point_count=10000)
output_path = context.output_path("instances.json")
instance_set.save_json(output_path)

# Load contract from downloaded file
instance_set = InstanceSet.load_json(local_path)
```

---

## Validation Checklist

Before considering a node complete, verify ALL of these:

### handler.py Structure
- [ ] `definition` is a module-level variable (for CLI validation)
- [ ] `definition` is also a class attribute on the BaseNode subclass
- [ ] `app = ClassName().create_app()` exists at module level
- [ ] `execute(self, inputs: dict, context: ExecutionContext) -> dict` is implemented
- [ ] Docstring describes the node's purpose

### WorkflowNodeManifest
- [ ] `id` follows `{name}-v{version}` format (e.g., `segment-v1.0.0`)
- [ ] `name` is a lowercase slug with hyphens (e.g., `point-cloud-segment`)
- [ ] `version` is semver (e.g., `1.0.0`)
- [ ] `title` is human-readable (e.g., `Point Cloud Segmentation`)
- [ ] `description` explains what the node does
- [ ] `category` is one of: `transform`, `inference`, `utility`, `control-flow`
- [ ] `timeout_seconds` is appropriate for the workload

### Schemas
- [ ] All file fields use `"format": "file"` (NEVER `"format": "binary"`)
- [ ] All file fields have `"type": "string"` (NEVER `"object"` or `"array"`)
- [ ] File inputs include `"x-accept": [".ext1", ".ext2"]`
- [ ] File inputs include `"x-maxSizeBytes": N`
- [ ] All properties have `"description"` fields
- [ ] Required fields are listed in `"required": [...]`

### File I/O
- [ ] File input values are used as local paths (SDK auto-downloaded and validated)
- [ ] Output files use `context.output_path(filename)` (never hardcoded paths)
- [ ] Output file paths returned as `str(output_path)` in outputs dict

### Dockerfile
- [ ] Based on `python:3.12-slim`
- [ ] Installs SDK from GitHub Packages: `pip install canvastekk-workflow-sdk --index-url https://USERNAME:TOKEN@pypi.pkg.github.com/betekk/` (requires PAT)
- [ ] Uses `uvicorn handler:app --host 0.0.0.0 --port 8001`
- [ ] Exposes port 8001

### pyproject.toml
- [ ] Lists `canvastekk-workflow-sdk>=0.5.2` as dependency
- [ ] `requires-python = ">=3.12"`

### Tests
- [ ] Unit tests using `node.run(request)` with `NodeExecutionRequest`
- [ ] API tests using `TestClient(app)` for `/health`, `/manifest`, `/execute`
- [ ] External dependencies (file downloads, model inference) are mocked

### CLI Validation
- [ ] `python -m canvastekk_workflow_sdk validate handler:definition` passes

---

## Common Mistakes to Avoid

| Mistake | Fix |
|---------|-----|
| `format: "binary"` in schema | Use `format: "file"` — binary is rejected by model_validator |
| `type: "object"` on file field | Use `type: "string"` — the value is a presigned URL string |
| Hardcoding `/tmp/` output paths | Use `context.output_path(filename)` — SDK auto-creates and uploads |
| Using `urllib` for downloads | Use `httpx` (SDK dependency, supports streaming/timeout/redirects) |
| Calling `validate_file_input()` on auto-downloaded files | Auto-called by the SDK after download. Only call it yourself for manually downloaded files |
| Definition inside `__init__()` | Must be a class-level attribute for `__init_subclass__` validation |
| Missing `app = Node().create_app()` | Required at module level for uvicorn: `handler:app` |
| Loading a large downloaded file fully into memory | Chunk-read the local path (`open(path, "rb")` iteration) — `httpx.stream()` + `iter_bytes()` only for manual URL downloads |
| Missing `x-maxSizeBytes` | Add size limits to prevent OOM on unexpected large inputs |
| Using `self.definition` vs module `definition` | Module-level `definition` enables CLI validation; `self.definition` accesses it in execute() |
| Not setting `follow_redirects=True` | Presigned URLs may redirect; always pass `follow_redirects=True` to httpx |
| Forgetting `.create_app()` dependencies | If using auth: `create_app(dependencies=[Depends(auth)])` |

## Node Project Structure

```
my_node/
├── handler.py          # WorkflowNodeManifest + BaseNode subclass + app = Node().create_app()
├── Dockerfile          # python:3.12-slim, SDK from GitHub Packages, uvicorn
├── pyproject.toml      # Dependencies including canvastekk-workflow-sdk
├── README.md           # Optional: node-specific documentation
└── tests/
    ├── __init__.py
    └── test_handler.py # Unit tests (node.run) + API tests (TestClient)
```
