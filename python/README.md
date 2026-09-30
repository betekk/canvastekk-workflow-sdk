# CanvasTEKK Workflow SDK — Python

> Part of [canvastekk-workflow-sdk](../) monorepo

Node SDK for CanvasTEKK Workflow Engine. Handles HTTP endpoint boilerplate so node authors can focus on business logic.

## Installation

### From GitHub Packages (requires PAT)

> GitHub Packages PyPI requires a PAT with `read:packages` scope. See the [root README](../README.md#python) for setup instructions.

```bash
pip install canvastekk-workflow-sdk \
  --index-url https://USERNAME:TOKEN@pypi.pkg.github.com/nus-cee/
```

### From GitHub Releases (no auth)

```bash
# Download the .whl from https://github.com/nus-cee/canvastekk-workflow-sdk/releases
pip install canvastekk_workflow_sdk-VERSION-py3-none-any.whl
```

### For Development

All commands run from this `python/` directory. The `.venv` lives here too.

```bash
cd python/
python3.12 -m venv .venv
source .venv/bin/activate
pip install poetry
poetry install
```

### Linting & Testing

```bash
# Lint
poetry run ruff check canvastekk_workflow_sdk/ tests/

# Test
poetry run pytest -v

# Test with coverage report
poetry run pytest --cov=canvastekk_workflow_sdk --cov-report=term-missing
```

### Runtime Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Python | ^3.12 | Runtime |
| FastAPI | ^0.135 | HTTP framework |
| Pydantic | ^2.12 | Data validation |
| Uvicorn | ^0.43 | ASGI server |
| httpx | ^0.28 | HTTP client (auto-download pipeline, registry, uploads) |

### Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| pytest | ^9.0 | Test runner |
| pytest-asyncio | ^1.3 | Async test support |
| pytest-cov | ^7.1 | Coverage reporting |
| ruff | ^0.15 | Linter & formatter |

---

## Creating Your First Node

### Step 1: Install the SDK

```bash
# From GitHub Packages (requires PAT with read:packages scope)
pip install canvastekk-workflow-sdk \
  --index-url https://USERNAME:TOKEN@pypi.pkg.github.com/nus-cee/

# Or from GitHub Releases (no auth — download the .whl first)
# https://github.com/nus-cee/canvastekk-workflow-sdk/releases
pip install canvastekk_workflow_sdk-VERSION-py3-none-any.whl
```

Or for local development, see the [For Development](#for-development) section above.

### Step 2: Define Your Node

Create a file (e.g. `handler.py`) and subclass `BaseNode`:

```python
# handler.py
from canvastekk_workflow_sdk import BaseNode, WorkflowNodeManifest, ExecutionContext


class UppercaseNode(BaseNode):
    definition = WorkflowNodeManifest(
        slug="uppercase",
        version="1.0.0",
        name="Uppercase",
        description="Converts text to uppercase",
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
        },
        output_schema={
            "type": "object",
            "properties": {"result": {"type": "string"}},
        },
    )

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        context.report_progress(0.5, "Processing text")
        return {"result": inputs["text"].upper()}


app = UppercaseNode().create_app()
```

The four requirements:

1. **Subclass `BaseNode`** — inherit from `canvastekk_workflow_sdk.BaseNode`
2. **Define `definition`** — a `WorkflowNodeManifest` with all required fields (`slug`, `version`, `name`, `description`, `input_schema`, `output_schema`). Note: `id` is auto-derived from `slug` + `version` and must NOT be provided manually.
3. **Implement `execute(inputs, context)`** — return a dict matching your `output_schema`
4. **Call `.create_app()`** — get a ready-to-run FastAPI application

### Step 3: Run It

```bash
# Development
uvicorn handler:app --reload --port 8001

# Production
uvicorn handler:app --host 0.0.0.0 --port 8001 --workers 4
```

### Step 4: Test the Endpoints

```bash
# Health check
curl http://localhost:8001/health
# {"status":"healthy","node_id":"uppercase-v1.0.0","version":"1.0.0","checks":{}}

# Node manifest
curl http://localhost:8001/manifest
# {"id":"uppercase-v1.0.0","name":"uppercase","version":"1.0.0","sdk_version":"0.9.0","mode":"dev",...}

# Execute the node
curl -X POST http://localhost:8001/execute \
  -H "Content-Type: application/json" \
  -d '{"run_id":"run-1","node_id":"node-1","inputs":{"text":"hello world"}}'
# {"execution_id":"...","status":"pass","outputs":{"result":"HELLO WORLD"},...}

# Metrics
curl http://localhost:8001/metrics
# {"total_executions":1,"pass_count":1,"fail_count":0,...}
```

---

## FastAPI Endpoint Deep Dive

### How It Works

When you call `node.create_app()`, the SDK creates a FastAPI application with these endpoints:

| Endpoint | Method | Handler | Purpose |
|----------|--------|---------|---------|
| `/execute` | POST | `node.run(request)` | Execute the node's business logic |
| `/health` | GET | `node.health_check()` | Health status |
| `/manifest` | GET | `node.definition.to_dict()` | Node self-description |
| `/hook` | POST | `node.hook(payload)` | Webhook/callback handler |
| `/metrics` | GET | `node._metrics_collector.get_summary()` | Execution metrics |

### Request/Response Lifecycle

When `POST /execute` receives a request:

```
NodeExecutionRequest
        |
        v
  Input Validation  ──(fail)──>  NodeExecutionResponse(status="fail", error_code="VALIDATION_ERROR")
        |
     (pass)
        v
  ExecutionContext created
        |
        v
  Middleware: on_before_execute(inputs, context)
        |
        v
  node.execute(inputs, context)  ──(exception)──>  Middleware: on_error(...)
        |                                            |
     (returns)                                    NodeExecutionResponse(status="fail")
        v
  Middleware: on_after_execute(inputs, outputs, context, duration_ms)
        |
        v
  NodeExecutionResponse(status="pass", outputs=...)
```

### NodeExecutionRequest

The payload sent to `POST /execute`:

```json
{
  "run_id": "workflow-run-abc123",
  "node_id": "node-instance-456",
  "inputs": { "text": "hello" },
  "callback_url": "https://orchestrator.example.com/callback",
  "output_upload_url": {
    "result_path": "https://s3.amazonaws.com/bucket/file?signature=..."
  }
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `run_id` | `str` | Yes | Workflow run identifier |
| `node_id` | `str` | Yes | Node instance ID in the workflow |
| `inputs` | `dict` | No | Input values (validated against `input_schema`) |
| `callback_url` | `str` | No | URL to POST result to (for async execution) |
| `output_upload_url` | `dict[str, str \| dict]` | No | Mapping of output field name to an upload target: pre-signed S3 PUT URL string (legacy, deprecated) or multipart upload-session descriptor (see [Output Upload](#output-upload)) |
| `account_id` | `int \| None` | No | Active account ID — **engine-controlled**: the SDK sets it exclusively from the `X-Account-Id` request header; any body-supplied value is stripped. Bounds: 1…2⁶³−1 |

### X-Account-Id header (v0.24.0+)

When the workflow engine invokes `POST /execute`, it forwards the run's active
account as the `X-Account-Id` header (`canvastekk-workflow-engine`
`fastapi_app/temporal/activities.py`). The SDK captures it and surfaces it as
`context.account_id`:

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    account_id = context.account_id  # int | None
```

Semantics:

- **Routing identity, not a credential.** It tells your node which account the
  run belongs to (e.g. which `X-Account-Id` header to forward when calling
  account-gated CDS endpoints). Endpoint access is still gated by node auth.
- **Header-only source.** A body-supplied `account_id` is stripped before
  validation — nodes always see the engine-asserted value, never a
  caller-forged one.
- **`None` when absent.** Local runs (`WorkflowRunner`, direct `BaseNode.run()`
  in tests) and engines that don't send the header get `None`. Nodes should
  treat `None` as "no account context" and keep working (or fail with a clear
  error if the account is required).
- **Strict parsing.** Blank/whitespace-only headers are treated as absent;
  non-numeric, negative, zero, or int64-overflowing values fail the request
  with HTTP 400.

Unit-test pattern — construct the request directly, no header plumbing needed:

```python
req = NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}, account_id=7)
ctx = ExecutionContext(req)
assert ctx.account_id == 7
```

### NodeExecutionResponse

The response from `POST /execute`:

```json
{
  "execution_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pass",
  "outputs": { "result": "HELLO" },
  "token_usage": 0.0,
  "duration_ms": 12,
  "error": null,
  "error_type": null,
  "error_code": null
}
```

On failure:

```json
{
  "execution_id": "...",
  "status": "fail",
  "outputs": null,
  "token_usage": 0.0,
  "duration_ms": 5,
  "error": "Intentional failure for testing",
  "error_type": "ValueError",
  "error_code": null
}
```

### Error Types and HTTP Status Codes

The SDK provides structured exceptions. When raised inside `execute()`, they produce specific error codes in the response:

| Exception | Error Code | HTTP Status (when unhandled) | When to Use |
|-----------|-----------|------------------------------|-------------|
| `NodeExecutionError` | `EXECUTION_ERROR` | 500 | Generic execution failure |
| `NodeValidationError` | `VALIDATION_ERROR` | 422 | Input validation failure |
| `NodeTimeoutError` | `TIMEOUT` | 408 | Execution exceeded time limit |
| `NodeIOError` | `IO_ERROR` | 500 | File read/write failure |
| `NodeConfigurationError` | `CONFIGURATION_ERROR` | 500 | Invalid node configuration |
| `WorkflowValidationError` | `WORKFLOW_VALIDATION_ERROR` | 422 | Workflow spec validation failure (cycle, orphan, missing START/END) |
| `WorkflowExecutionError` | `WORKFLOW_EXECUTION_ERROR` | 500 | Local workflow execution failure |

Note: When raised inside `execute()`, the SDK catches them and returns `status: "fail"` with HTTP 200. The structured error codes appear in the `error_code` field. When exceptions escape to the FastAPI exception handler, they produce the HTTP status codes above.

Usage example:

```python
from canvastekk_workflow_sdk import BaseNode, WorkflowNodeManifest, ExecutionContext
from canvastekk_workflow_sdk.exceptions import NodeIOError, NodeExecutionError


class FileProcessorNode(BaseNode):
    definition = WorkflowNodeManifest(
        slug="file-proc",
        version="1.0.0",
        name="File Processor",
        description="Processes a file",
        input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
        output_schema={"type": "object", "properties": {"line_count": {"type": "integer"}}},
    )

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        from pathlib import Path

        file_path = Path(inputs.get("path", ""))
        if not file_path.exists():
            raise NodeIOError(f"File not found: {file_path}", path=str(file_path))

        content = file_path.read_text()
        return {"line_count": len(content.splitlines())}


app = FileProcessorNode().create_app()
```

---

## File Handling Guide

### Declaring File Inputs

Mark input fields as files using `"format": "file"` in `input_schema`. Use `x-accept` and `x-maxSizeBytes` extensions to specify accepted file types and size limits:

```python
definition = WorkflowNodeManifest(
    slug="segment",
    version="1.0.0",
    name="Segment",
    description="Segments a point cloud",
    input_schema={
        "type": "object",
        "properties": {
            "point_cloud": {
                "type": "string",
                "format": "file",
                "description": "Point cloud file",
                "x-accept": [".ply", ".pcd"],
                "x-maxSizeBytes": 52428800,  # 50 MB
            },
            "confidence": {"type": "number", "default": 0.5},
        },
    },
    output_schema={
        "type": "object",
        "properties": {
            "instances": {"type": "string"},
        },
    },
)
```

When the SDK detects `format: "file"`, the field becomes a file input (`definition.file_input_fields` returns `["point_cloud"]`).

### How File Inputs Work

When the workflow engine executes your node, file input values are presigned GET URLs (strings). The SDK **automatically downloads** them to `context.downloads_dir` before calling `execute()`:

- URL inputs (`https://` or `http://`) are downloaded to a local file
- Local path inputs are passed through unchanged
- Downloaded files are auto-validated against `x-accept` and `x-maxSizeBytes`
- Download metadata is available via `context.metadata[field_name]`

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    # inputs["point_cloud"] is now a LOCAL FILE PATH (auto-downloaded by SDK)
    cloud_path = Path(inputs["point_cloud"])
    cloud_data = cloud_path.read_bytes()

    confidence = inputs.get("confidence", 0.5)

    # Check download metadata if needed
    meta = context.metadata.get("point_cloud", {})

    # ... process the point cloud ...
    return {"instances": "42 objects found"}
```

> **Note:** You no longer need to manually download with `httpx` or call `validate_file_input()` for standard file inputs — the SDK handles this automatically. Manual download is only needed for non-file URLs or opt-out scenarios.

### Runtime Validation

The SDK **automatically validates** downloaded file inputs against the constraints defined in `x-accept` and `x-maxSizeBytes`. This happens before `execute()` is called, so you can trust that file inputs are valid.

If you need to validate additional files (e.g., files you generate or download manually), use:

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    # Auto-validated inputs are guaranteed to pass constraints
    cloud_path = Path(inputs["point_cloud"])

    # Validate additional files manually if needed
    extra_file = context.output_path("extra.dat")
    self.definition.validate_file_input("point_cloud", extra_file)

    # ...
```

### Writing Output Files

Use `context.output_path(filename)` for output files:

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    # Write output to the context's output directory
    output_file = context.output_path("result.json")
    output_file.write_text('{"status": "done"}')

    return {"result_path": str(output_file)}
```

`context.output_dir` is created automatically at `/tmp/{run_id}/{node_id}`.

#### v0.22+ security & behavior changes

- **SSRF policy**: file-input URLs must be `https://` (production); loopback/private/link-local/metadata/CGNAT IPs are blocked, re-validated per redirect hop. Escape hatches: `CANVASTEKK_URL_ALLOWLIST` (trusted host suffixes), `CANVASTEKK_DEV_MODE` (dev only — also lifts auth).
- **Mid-stream size caps**: `x-maxSizeBytes` aborts downloads as soon as exceeded; undeclared fields fall back to `CANVASTEKK_MAX_DOWNLOAD_BYTES` (default 10 GiB).
- **Download deadlines**: derived from `timeout_seconds`; timed-out requests cancel in-flight downloads cooperatively (`context.cancel_event`).
- **Upload failures fail the execution** (`error_code: "UPLOAD_FAILED"`) instead of silently passing.
- **Body limits & validation**: request bodies are capped (50 MB default, `CANVASTEKK_MAX_BODY_BYTES`); `run_id`/`node_id` must be slug-safe (no `..`); `context.output_path()` rejects path traversal.
- **Auth posture**: startup logs warn loudly when no auth is configured or dev-mode is active.
- **Local `WorkflowRunner` (BREAKING)**: each node now gets `run_output_dir/<node_id>/` for outputs/downloads (previously all nodes shared the run root). Inter-node file hand-off via absolute-path strings is unchanged; code globbing the run root must adapt. Seeded `run(spec, inputs={...})` START inputs now merge with (not clobber) static start inputs, and mis-wired edges fail one node instead of crashing the run.

### Output Upload

The engine provides upload targets via the `output_upload_url` field in the request. The SDK uploads file outputs automatically after successful execution. The target is a **multipart upload-session descriptor** — the only target since SDK 0.36.0 (DA-3340): the SDK lazily redeems the session token, PUTs parts in bounded parallel batches with per-part `Content-MD5`, retries per part, resumes from server-side upload status after a failure, and aborts cleanly. No size ceiling beyond the engine's own part policy; node code needs **zero changes** (the router, not the developer, performs uploads). A legacy presigned-PUT string reaching the SDK raises `NodeIOError` ("engine sent deprecated presigned target — upgrade the engine") — there is no fallback; the fix is upgrading the engine (DA-3338/DA-2887).

Session descriptor wire contract (snake_case, matching the execute wire):

```json
{
  "kind": "multipart-upload-session",
  "session_token": "<opaque, TTL-bound>",
  "initiate_url": "POST {size, content_type} -> {upload_id, part_size, part_urls: [...]}",
  "complete_url": "POST {upload_id, parts: [{part_number, etag}]} -> 200",
  "abort_url": "POST {upload_id} (best-effort)",
  "status_url": "GET -> {upload_id, uploaded_parts: [...]}",
  "expires_at": "<ISO-8601, informational>"
}
```

Failure semantics are unchanged from DA-1711: a terminal upload failure produces `fail`/`UPLOAD_FAILED` at the router layer (outside `ErrorOutputNode`).

```python
definition = WorkflowNodeManifest(
    slug="converter",
    version="1.0.0",
    name="Converter",
    description="Converts file format",
    input_schema={
        "type": "object",
        "properties": {
            "input_file": {"type": "string", "format": "file"},
        },
    },
    output_schema={
        "type": "object",
        "properties": {
            "converted": {"type": "string", "format": "file"},
            "metadata": {"type": "object"},
        },
    },
)
```

Client request:

```json
{
  "run_id": "run-1",
  "node_id": "node-1",
  "inputs": {
    "input_file": "https://s3.amazonaws.com/bucket/input.ply?X-Amz-Signature=..."
  },
  "output_upload_url": {
    "converted": "https://s3.amazonaws.com/bucket/result.ply?X-Amz-Signature=..."
  }
}
```

After successful execution, the SDK uploads the file at `outputs["converted"]` to the pre-signed PUT URL. If execution fails (`status: "fail"`), the upload is skipped.

### Complete Example

```python
from canvastekk_workflow_sdk import BaseNode, WorkflowNodeManifest, ExecutionContext
from pathlib import Path


class PointCloudSegmenter(BaseNode):
    definition = WorkflowNodeManifest(
        slug="segment",
        version="1.0.0",
        name="Segment",
        description="Segments a point cloud",
        input_schema={
            "type": "object",
            "properties": {
                "point_cloud": {
                    "type": "string",
                    "format": "file",
                    "description": "Point cloud file",
                    "x-accept": [".ply", ".pcd"],
                    "x-maxSizeBytes": 52428800,
                },
                "confidence": {"type": "number", "default": 0.5},
            },
        },
        output_schema={
            "type": "object",
            "properties": {
                "instances": {"type": "string", "format": "file"},
                "count": {"type": "integer"},
            },
        },
    )

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        # File inputs are auto-downloaded to local paths by the SDK
        cloud_path = Path(inputs["point_cloud"])
        cloud_data = cloud_path.read_bytes()

        # Process the point cloud
        confidence = inputs.get("confidence", 0.5)
        result_data = b"Processed point cloud data..."

        # Write output file
        output_file = context.output_path("instances.ply")
        output_file.write_bytes(result_data)

        return {
            "instances": str(output_file),
            "count": 42,
        }


app = PointCloudSegmenter().create_app()
```

### Testing with Presigned URLs

```bash
curl -X POST http://localhost:8001/execute \
  -H "Content-Type: application/json" \
  -d '{
    "run_id": "run-1",
    "node_id": "node-1",
    "inputs": {
      "point_cloud": "https://s3.amazonaws.com/bucket/scan.ply?X-Amz-Signature=...",
      "confidence": 0.8
    }
  }'
```

---

## Template Variable Substitution

The workflow engine automatically resolves `{{variable}}` placeholders in string node inputs after edge resolution. Your `execute()` method receives fully resolved strings — you do not handle `{{}}` syntax in your node code.

### Syntax

| Pattern | Behavior |
|---------|----------|
| `{{variable}}` | Replaced with `str(inputs["variable"])` |
| `{variable}` | Literal — single braces are not substituted |
| `{{unknown_key}}` | Left as-is if key not in inputs (logged at DEBUG) |

Rules:
- Only `{{double_braces}}` trigger substitution
- Single-pass — no recursive resolution
- Non-string values pass through unchanged
- Requires engine version with [DA-1037](https://betekk.atlassian.net/browse/DA-1037)

### Example

Workflow defines inputs with templates:

```json
{
  "folder_path": "{{report_id}}/runs/{{run_id}}/output/zip/",
  "report_id": 13,
  "run_id": "a1b2c3d4-..."
}
```

Node receives resolved values:

```json
{
  "folder_path": "13/runs/a1b2c3d4-.../output/zip/",
  "report_id": 13,
  "run_id": "a1b2c3d4-..."
}
```

### Input Schema Constraints

`input_schema` constraints (`pattern`, `format`, etc.) validate against the **resolved** value, not the template syntax. Design constraints to match the expected resolved output.

### Security

Single-pass substitution prevents recursive injection. Node authors should still validate resolved values before using them in file paths, URLs, or shell commands.

For the full guide including common variables, design considerations, and conflict avoidance, see [EXTERNAL-AUTHOR-GUIDE: Template Variable Substitution](../docs/EXTERNAL-AUTHOR-GUIDE.md#template-variable-substitution).

---

## Deploying a Node

### Uvicorn (Production)

```bash
# Single worker (development)
uvicorn handler:app --host 0.0.0.0 --port 8001

# Multiple workers (production)
uvicorn handler:app --host 0.0.0.0 --port 8001 --workers 4

# With SSL
uvicorn handler:app --host 0.0.0.0 --port 8443 --ssl-keyfile=key.pem --ssl-certfile=cert.pem

# With timeout and access log
uvicorn handler:app --host 0.0.0.0 --port 8001 --timeout-keep-alive 30 --access-log
```

### Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN pip install poetry && \
    poetry config virtualenvs.create false && \
    poetry install --without dev --no-interaction --no-ansi

COPY handler.py .

EXPOSE 8001

CMD ["uvicorn", "handler:app", "--host", "0.0.0.0", "--port", "8001"]
```

Build and run:

```bash
docker build -t my-node .
docker run -p 8001:8001 my-node
```

### Docker Compose

```yaml
services:
  my-node:
    build: .
    ports:
      - "8001:8001"
    environment:
      - LOG_LEVEL=info
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8001/health"]
      interval: 30s
      timeout: 10s
      retries: 3
```

---

## Testing Your Node

### Unit Testing with `node.run()`

Test business logic directly without HTTP:

```python
# tests/test_my_node.py
from my_node import MyNode
from canvastekk_workflow_sdk import NodeExecutionRequest


def test_execute_returns_uppercase():
    node = MyNode()
    request = NodeExecutionRequest(
        run_id="test-run",
        node_id="test-node",
        inputs={"text": "hello"},
    )
    response = node.run(request)

    assert response.status == "pass"
    assert response.outputs == {"result": "HELLO"}
    assert response.duration_ms >= 0


def test_execute_failure_returns_fail_status():
    node = MyNode()
    request = NodeExecutionRequest(
        run_id="test-run",
        node_id="test-node",
        inputs={},  # missing required "text"
    )
    response = node.run(request)

    assert response.status == "fail"
    assert response.error_type == "NodeValidationError"
    assert response.error_code == "VALIDATION_ERROR"
```

### Integration Testing with FastAPI TestClient

Test the full HTTP stack including multipart uploads:

```python
# tests/test_my_node_api.py
from fastapi.testclient import TestClient
from my_node import app


client = TestClient(app)


def test_execute_endpoint():
    response = client.post(
        "/execute",
        json={
            "run_id": "test-run",
            "node_id": "test-node",
            "inputs": {"text": "hello"},
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pass"
    assert data["outputs"]["result"] == "HELLO"


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["node_id"] == "my-node-v1.0.0"


def test_manifest_endpoint():
    response = client.get("/manifest")
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "my-node"
    assert "input_schema" in data


def test_metrics_endpoint():
    # Execute first to generate metrics
    client.post("/execute", json={
        "run_id": "r1", "node_id": "n1", "inputs": {"text": "test"},
    })

    response = client.get("/metrics")
    assert response.status_code == 200
    data = response.json()
    assert data["total_executions"] >= 1


def test_presigned_url_file_input():
    # Create a local test file
    test_file = tmp_path / "scan.ply"
    test_file.write_bytes(b"test point cloud data")

    response = client.post(
        "/execute",
        json={
            "run_id": "test-run",
            "node_id": "test-node",
            "inputs": {
                "point_cloud": str(test_file),  # Local path passes through
                "confidence": 0.8,
            },
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "pass"
```

### Running Tests

```bash
# From python/ directory
poetry run pytest

# With verbose output
poetry run pytest -v

# Specific test file
poetry run pytest tests/test_my_node.py
```

---

## SDK Components

### WorkflowNodeManifest

Defines what a node is. Maps to the engine's **registry-level node type** (`WorkflowNodeManifest` in engine terminology). This is distinct from `WorkflowDefinitionNode`, which the engine uses for node instances within a workflow definition.

**Required fields:** `slug`, `version`, `name`, `description`, `input_schema`, `output_schema`. Note: `id` is auto-derived from `slug` + `version` and must NOT be provided manually.

**Versioning:** The `version` field is a semantic version string (e.g., `"1.0.0"`) validated against the X.Y.Z pattern. The engine uses this version directly and enforces immutability: re-registering with the same version and changed data is rejected. Bump the version for any schema or metadata changes.

```python
from canvastekk_workflow_sdk import WorkflowNodeManifest, RetryConfig, WorkflowNodeStyles
from canvastekk_workflow_sdk.definition import ColorPreset

definition = WorkflowNodeManifest(
    slug="my-node",
    version="1.0.0",
    name="My Node",
    description="Does something useful",
    input_schema={
        "type": "object",
        "properties": {"input": {"type": "string"}},
    },
    output_schema={
        "type": "object",
        "properties": {"output": {"type": "string"}},
    },
    token_cost=0.5,
    default_retry=RetryConfig(max_attempts=3, initial_delay_ms=1000),
    category="inference",
    timeout_seconds=60,
    styles=WorkflowNodeStyles(icon="Brain", color="emerald"),
)
```

Optional fields with defaults:

| Field | Default | Description |
|-------|---------|-------------|
| `token_cost` | 0.0 | Cost per execution |
| `default_retry` | `RetryConfig(1 attempt)` | Retry policy |
| `category` | `"utility"` | Node category (`transform`, `inference`, `utility`, `control-flow`) |
| `timeout_seconds` | 30 | Max execution time |
| `role` | `WorkflowNodeRole.OPERATION` | Node role (`start`, `end`, `error_gate`, `operation`) |
| `styles` | `None` | Icon/color for UI |
| `deprecation` | `None` | Optional `DeprecationInfo` — advisory migration signal (RFC 9745/8594). Omitted from serialization when `None`. Distinct from the registry's `node_status`; a deprecated node stays `active` until retired. |

### DeprecationInfo

Mark a node deprecated so workflow-definition authors get a migration signal.
`deprecation` is **additive metadata** — setting it does not change the node's
behavior and does not require a `major` version bump (a `patch`/`minor` bump is
sufficient, since engine version-immutability only rejects *changed data* on
the same version — adding the field on a new version is a normal registration).

```python
from canvastekk_workflow_sdk import DeprecationInfo, WorkflowNodeManifest
from datetime import date

definition = WorkflowNodeManifest(
    slug="floor-flatness-assessment",
    version="1.4.2",
    # ...required fields...
    deprecation=DeprecationInfo(
        deprecated_at=date(2026, 8, 1),          # RFC 9745 — when deprecation took effect
        sunset_date=date(2027, 1, 1),            # RFC 8594 — planned removal date
        replacement_slug="floor-flatness-per-check-assessment",
        migration_url="https://docs.example.com/ff-migration",
        notice="Use floor-flatness-per-check-assessment for per-check-type outputs.",
    ),
)
```

| Field | Default | Description |
|-------|---------|-------------|
| `deprecated_at` | `None` | Date deprecation took effect (RFC 9745) |
| `sunset_date` | `None` | Planned removal date (RFC 8594); `None` = no firm date |
| `replacement_slug` | `None` | Slug of the replacement node |
| `migration_url` | `None` | URL to migration docs (RFC 9745 §3 / RFC 8594 §6) |
| `notice` | *(required)* | Human-readable notice shown to workflow-def authors |

### ExecutionContext

Provided to `execute()` method:

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    # Identifiers
    context.run_id    # "workflow-run-abc123"
    context.node_id   # "node-instance-456"

    # File outputs
    context.output_dir                 # Path("/tmp/run-abc123/node-456")
    output_file = context.output_path("result.json")  # Path("/tmp/run-abc123/node-456/result.json")

    # Logging
    context.logger.info("Processing started")

    # Progress reporting (0.0 - 1.0)
    context.report_progress(0.5, "Halfway done")

    # Token usage (for LLM nodes)
    context.record_token_usage(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    context.token_usage  # {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150}

    return {}
```

### Data Contracts

Standard data formats for passing structured data between nodes:

#### InstanceSet — Detected Objects

Field constraints enforced at construction time:
- `instance_id`, `class_id`: `ge=0` (non-negative)
- `point_indices`: all values must be non-negative
- `point_count`: `ge=0`
- `BoundingBox3D`: `min_point <= max_point` on each axis (x, y, z)

```python
from canvastekk_workflow_sdk.contracts import InstanceSet, Instance, BoundingBox3D, Point3D

# Producing instances
instance_set = InstanceSet(
    instances=[
        Instance(
            instance_id=1,
            class_id=4,
            class_name="vent",
            confidence=0.95,
            point_indices=[0, 1, 2, 3],
            centroid=Point3D(x=100.0, y=200.0, z=50.0),
            bounding_box=BoundingBox3D(
                min_point=Point3D(x=80.0, y=180.0, z=30.0),
                max_point=Point3D(x=120.0, y=220.0, z=70.0),
            ),
        ),
    ],
    class_names=["floor", "ceiling", "wall", "door", "vent"],
    point_count=10000,
    source_node="segment",
    source_file="scan.ply",
)

# Save to file
instance_set.save_json("/tmp/instances.json")

# Consuming instances in another node
instances = InstanceSet.load_json(inputs["instances_path"])
vents = instances.get_instances_by_class("vent")
for vent in vents:
    print(f"Vent {vent.instance_id}: {vent.num_points} points, confidence={vent.confidence}")
```

#### MeasurementSet — Measurements

```python
from canvastekk_workflow_sdk.contracts import MeasurementSet, Measurement, Point3D

measurements = MeasurementSet(
    measurements=[
        Measurement(
            name="ceiling_height",
            value=2800.0,
            unit="mm",
            method="plane_to_plane",
            confidence=0.98,
            points=[Point3D(x=0, y=0, z=0), Point3D(x=0, y=0, z=2800)],
        ),
        Measurement(
            name="vent_width",
            value=300.0,
            unit="mm",
            method="bounding_box",
        ),
    ],
    source_node="measure",
)

# Access measurements
height = measurements.get_value("ceiling_height")  # 2800.0
```

#### PlaneSet — Detected Planes

```python
from canvastekk_workflow_sdk.contracts import PlaneSet, Plane, Point3D

planes = PlaneSet(
    planes=[
        Plane(
            point=Point3D(x=0, y=0, z=0),
            normal=Point3D(x=0, y=0, z=1),
            label="floor",
        ),
        Plane(
            point=Point3D(x=0, y=0, z=2800),
            normal=Point3D(x=0, y=0, z=-1),
            label="ceiling",
        ),
    ],
    source_node="plane_detect",
)

floor = planes.get_plane_by_label("floor")
```

#### Serialization

All contracts extend `BaseContract` which provides:

```python
# Save to JSON
instance_set.save_json("output.json")

# Load from JSON
loaded = InstanceSet.load_json("output.json")

# Access metadata
print(loaded.contract_version)  # "1.0.0"
print(loaded.source_node)       # "segment"
print(loaded.source_file)       # "scan.ply"
```

### NodeExecutionRequest

Request payload for `POST /execute`:

| Field | Type | Description |
|-------|------|-------------|
| `run_id` | `str` | Workflow run identifier |
| `node_id` | `str` | Node instance ID |
| `inputs` | `dict` | Input values |
| `callback_url` | `str \| None` | For async execution (optional) |
| `output_upload_url` | `dict[str, str] \| None` | Pre-signed S3 URLs for file outputs (optional) |

### NodeExecutionResponse

Response from `POST /execute`:

| Field | Type | Description |
|-------|------|-------------|
| `execution_id` | `str` | Unique execution ID |
| `status` | `"pass" \| "fail"` | Execution result |
| `outputs` | `dict \| None` | Output values (if pass) |
| `token_usage` | `float` | Tokens consumed |
| `duration_ms` | `int` | Execution time |
| `error` | `str \| None` | Error message (if fail) |
| `error_type` | `str \| None` | Error class name (if fail) |
| `error_code` | `str \| None` | Structured error code (e.g. `TIMEOUT`) |

---

## Utilities

### CLI: register + probe (v0.28+)

```bash
# Offline registration probes (validate + engine-request mirror)
python -m canvastekk_workflow_sdk probe my_node.handler:definition

# Publish to the engine registry from CI (service identity)
export CANVASTEKK_REGISTRY_TOKEN=<service token>
python -m canvastekk_workflow_sdk register my_node.handler:definition \
  --engine-url https://cwe.example.com [--invoke-url URL] [--name-suffix -lambda]
```

`register` maps the manifest to the engine vocabulary (`name`=slug, `label`=display),
authenticates via `X-Service-Token`, POSTs to `{engine}/api/workflows/nodes/`, and
verifies via `by-name/{name}`. Exit codes: 0 ok · 2 usage · 3 auth · 4 4xx · 5 5xx ·
6 network. See the External Author Guide for the full contract.

`GET /manifest` also serves `code_digest` (sha256 of the handler module source,
computed at startup, never author-settable) next to `sdk_version`/`mode`.

### CLI Manifest Validation

Validate your node definition offline without starting the server:

```bash
# Basic validation
python -m canvastekk_workflow_sdk validate my_node.handler:definition

# Structured JSON output (for CI)
python -m canvastekk_workflow_sdk validate my_node.handler:definition --json
```

The validator checks:
- All file fields use `format: "file"` (rejects `format: "binary"`)
- File fields have `type: "string"` (not `"object"` or `"array"`)
- Warns on file fields missing `x-accept` or `x-maxSizeBytes` extensions
- Reports detected file input/output fields and their constraints

Exit codes: `0` = valid, `1` = validation errors.

### Echo Node Example

A minimal reference node with file I/O is available at [`examples/echo_node/`](../examples/echo_node/).

It demonstrates:
- File input/output with `format: "file"` and `x-*` extensions
- Auto-download of presigned URL file inputs (SDK handles this automatically)
- Runtime validation with `validate_file_input()` (auto-called after download)
- CLI manifest validation
- Unit and integration tests
- Docker build

---

## Registry & Registration

The SDK provides utilities for registering nodes with the CanvasTEKK Workflow Engine registry. These are typically used in CI/CD pipelines after deployment.

### SDK vs Engine Type Mapping

| SDK Type | Engine Type | Purpose |
|----------|-------------|---------|
| `WorkflowNodeManifest` | `WorkflowNodeManifest` | Registry-level node type (schemas, metadata, styles) |
| `workflow.WorkflowDefinitionNode` | `WorkflowDefinitionNode` | Node instance within a workflow (inputs, position, edges) |
| `workflow.WorkflowDefinitionSpec` | `WorkflowDefinitionSpec` | Complete workflow definition (nodes + edges as a DAG) |

Node authors only interact with `WorkflowNodeManifest`. The engine handles `WorkflowDefinitionNode` internally.

The SDK's `workflow` module provides a local equivalent: `WorkflowBuilder` creates `WorkflowDefinitionSpec` objects that serialize to engine-compatible JSON, and `WorkflowRunner` executes them locally.

### Naming Convention Table

| Artifact | Name | Parent Concept |
|----------|------|----------------|
| Node registration manifest | `WorkflowNodeManifest` | `WorkflowNodeRegistry` (engine) |
| Workflow DAG | `WorkflowDefinition` | — |
| Node in DAG | `WorkflowDefinitionNode` | `WorkflowDefinition` |
| Edge in DAG | `WorkflowEdgeDefinition` | `WorkflowDefinition` |
| Full spec | `WorkflowDefinitionSpec` | `WorkflowDefinition` |

### Backward-Compatible Aliases

Old names still work as aliases and will not be removed:

| Old Name | Current Name |
|----------|-------------|
| `WorkflowNodeManifest` | `WorkflowNodeManifest` |
| `WorkflowWorkflowNodeManifest` | `WorkflowNodeManifest` |
| `WorkflowNode` | `WorkflowDefinitionNode` |
| `WorkflowEdge` | `WorkflowEdgeDefinition` |
| `WorkflowSpec` | `WorkflowDefinitionSpec` |

### Versioning

The `WorkflowNodeManifest.version` field (semantic version string) is the node's authoritative version. The engine stores and enforces this version — re-registering with the same version and changed data is rejected (HTTP 409). Node authors must bump the version for any changes.

### `register_node()`

Register a node with the workflow engine registry via `POST /api/workflows/nodes/`:

```python
from canvastekk_workflow_sdk.registry import register_node

node = MyNode()
result = register_node(
    node,
    registry_url="https://engine.example.com/api/workflows/nodes/",
    invoke_url="https://my-node.example.com",
    service_token="svs_your-token-here",
    tags=["category:utility", "team:platform"],
)

print(result.action)         # "created"
print(result.revision_id)    # "rev-abc123"
print(result["name"])        # dict-like access for backward compat
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `node` | `BaseNode` | Yes | The node instance to register |
| `registry_url` | `str` | Yes | Engine registry endpoint |
| `invoke_url` | `str \| None` | No | URL where the node is reachable |
| `invoke_type` | `InvokeType` | No | `"http"`, `"lambda"`, `"sagemaker"`, or `"in-process"` (default: `"http"`) |
| `api_key` | `str \| None` | Yes* | API key auth (`X-API-Key` header) |
| `service_token` | `str \| None` | Yes* | CI/CD auth (`X-Service-Token` header, takes precedence) |
| `tags` | `list[str] \| None` | No | Searchable tags for the registry |
| `invoke_config` | `dict \| None` | No | Extra invocation parameters (e.g., Lambda region) |
| `timeout` | `int` | No | Request timeout in seconds (default: 30) |

*Either `api_key` or `service_token` must be provided.

### `RegisterNodeResult`

The return type of `register_node()`. Contains the node data and registration metadata:

```python
class RegisterNodeResult(BaseModel):
    node: dict[str, Any]             # Registered node definition
    action: str | None               # "created", "updated", or "unchanged"
    revision_id: str | None          # Engine revision ID
    previous_version: str | None     # Previous version (if updated)
    changes: list[str] | None        # Changed fields (if updated)
```

Supports dict-like access (`result["name"]`, `"name" in result`, `result.get("name")`) for backward compatibility.

### `build_registry_payload()`

Build a registry-compatible payload dict from a `WorkflowNodeManifest`. Used internally by both `register_node()` and `export_definition()` to ensure consistent field mapping:

```python
from canvastekk_workflow_sdk.registry import build_registry_payload

payload = build_registry_payload(
    node.definition,
    invoke_type="lambda",
    invoke_url="arn:aws:lambda:ap-southeast-1:123456789:function:my-node",
    invoke_config={"region": "ap-southeast-1"},
    tags=["ml", "segmentation"],
)
```

**Field mapping** (SDK → Engine `RegisterNodeRequest` / `WorkflowNode`):

| SDK Field | Engine API Field | Notes |
|-----------|-----------------|-------|
| `definition.slug` | `name` | Renamed (engine identity) |
| `definition.name` (display) | `label` | Renamed |
| `definition.default_retry` | `retry` | Renamed |
| `definition.id` (computed) | — | Omitted from payload |
| — | `tags` | New optional field |
| — | `invoke_config` | New optional field |

### `export_definition()`

Export a `WorkflowNodeManifest` as a registry-compatible JSON file:

```python
from canvastekk_workflow_sdk.definition import export_definition

path = export_definition(
    node.definition,
    "node-manifest.json",
    invoke_url="https://my-node.example.com",
    tags=["ci-cd"],
)
```

### `InvokeType`

A `Literal` type for valid invocation types:

```python
from canvastekk_workflow_sdk.registry import InvokeType

# Valid values: "http", "lambda", "sagemaker", "in-process"
```

`register_node()` validates `invoke_type` at runtime and raises `ValueError` for invalid values.

### `RegistrationError`

Raised when registration fails. Contains `status_code` and `body` attributes for debugging:

```python
from canvastekk_workflow_sdk.registry import register_node, RegistrationError

try:
    result = register_node(node, registry_url=url, service_token="svs_xxx")
except RegistrationError as e:
    print(f"Status: {e.status_code}, Body: {e.body}")
```

---

## Workflow Builder & Local Runner

Build, validate, and test-run workflow DAGs locally — without the engine, Temporal, S3, or distributed orchestration.

### Intentional Differences from Engine

| Feature | Engine | SDK Runner |
|---------|--------|------------|
| Orchestration | Temporal (distributed) | In-process (BFS levels, asyncio) |
| Node execution | HTTP calls to deployed services | Direct `.execute()` or HTTP calls |
| File handling | S3 presigned URLs | Local file paths (passthrough) |
| Credentials | Encrypted credential store | Not needed locally |
| Durability | Workflow state persisted | Ephemeral, in-memory |
| Callbacks | Async HTTP callbacks | Synchronous execution |

### Quick Start

```python
from canvastekk_workflow_sdk import WorkflowBuilder, WorkflowRunner
from canvastekk_workflow_sdk.workflow.executor import InProcessExecutor

# Build a workflow
spec = (
    WorkflowBuilder()
    .add_start("start", outputs=["point_cloud"])
    .add_node("segment", slug="segmentation-v1.0.0", inputs={"method": "dbscan"})
    .add_node("measure", slug="measurement-v1.0.0")
    .add_end("end")
    .connect("start", "segment", from_output="point_cloud", to_input="input_file")
    .connect("segment", "measure", from_output="instances", to_input="instance_set")
    .connect("measure", "end", from_output="measurements", to_input="result")
    .build()  # validates the DAG
)

# Test run locally with BaseNode instances
executor = InProcessExecutor()
executor.register("segmentation-v1.0.0", MySegmentNode())
executor.register("measurement-v1.0.0", MyMeasurementNode())

runner = WorkflowRunner(executor)
result = runner.run(spec, inputs={"point_cloud": "/data/scan.las"})

print(result.status)          # "completed" or "failed"
print(result.final_outputs)   # {"result": ...}
print(result.duration_ms)     # total execution time

# Export for engine — produces JSON POSTable to /api/workflows/definitions
import json
payload = {"name": "my-pipeline", "spec": spec.model_dump(mode="json")}
```

### WorkflowBuilder

Fluent API for constructing workflow definitions. All methods return `self` for chaining (except `build()`).

#### `add_start(node_id="start", *, outputs=None, config_schema=None)`

Add a START node (workflow entry point). Exactly one allowed.

```python
builder.add_start("start", outputs=["point_cloud", "metadata"])
```

If `outputs` is provided (list of field names), sets `config_schema` with string properties for each field. These become the START node's output fields that downstream nodes can connect to.

#### `add_end(node_id="end")`

Add an END node (workflow terminal). Multiple allowed.

```python
builder.add_end("end")
```

#### `add_node(node_id, *, slug, name=None, inputs=None, version=None, config_schema=None, workflow_node_id=None)`

Add a user node with a registry slug reference. Slug `"__start__"` and `"__end__"` are reserved.

```python
builder.add_node("segment", slug="segmentation-v1.0.0", inputs={"method": "dbscan"}, version="1.0.0")
```

The created `WorkflowDefinitionNode` includes:
- `workflow_node_id` — optional str, a separate identifier for the node within the workflow
- `config_schema` — optional dict, a JSON Schema describing the node's configuration UI

#### `connect(from_node, to_node, *, from_output="", to_input="", edge_type=EdgeType.DEFAULT, condition=None)`

Add an edge connecting two nodes. Validates that both node IDs exist and rejects self-loops (`from_node == to_node`).

```python
builder.connect("start", "segment", from_output="point_cloud", to_input="input_file")
```

#### `build(*, validate=True)`

Construct the `WorkflowDefinitionSpec`. If `validate=True` (default), validates the graph and raises `WorkflowValidationError` on failure.

### NodeExecutor Strategy

The runner accepts a `NodeExecutor` via constructor — choose how nodes execute:

#### `InProcessExecutor` — Direct Execution

Runs `BaseNode.execute()` directly via `asyncio.to_thread()` (non-blocking):

```python
from canvastekk_workflow_sdk.workflow.executor import InProcessExecutor

executor = InProcessExecutor()
executor.register("segmentation-v1.0.0", MySegmentNode())
executor.register("measurement-v1.0.0", MyMeasurementNode())

runner = WorkflowRunner(executor)
```

#### `HttpExecutor` — HTTP Calls

Calls node `/execute` endpoints via `httpx`. Posts `NodeExecutionRequest`-compatible payloads:

```python
from canvastekk_workflow_sdk.workflow.executor import HttpExecutor

executor = HttpExecutor()
executor.register_url("segmentation-v1.0.0", "http://localhost:8001")
executor.register_url("measurement-v1.0.0", "http://localhost:8002")

runner = WorkflowRunner(executor)
```

### WorkflowRunner

```python
from canvastekk_workflow_sdk import WorkflowRunner

runner = WorkflowRunner(executor, error_policy=ErrorPolicy.FAIL_FAST)
result = runner.run(spec, inputs={"point_cloud": "/data/scan.las"})
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `executor` | `NodeExecutor` | required | Execution strategy (InProcess or HTTP) |
| `error_policy` | `ErrorPolicy` | `FAIL_FAST` | `FAIL_FAST` stops on first error; `CONTINUE` skips downstream of failed nodes |

### WorkflowRunResult

| Field | Type | Description |
|-------|------|-------------|
| `status` | `"completed" \| "failed"` | Overall workflow status |
| `final_outputs` | `dict` | Outputs collected from END nodes |
| `node_results` | `list[NodeResult]` | Per-node execution results |
| `duration_ms` | `int` | Total execution time |

### NodeResult

| Field | Type | Description |
|-------|------|-------------|
| `node_id` | `str` | Node instance ID |
| `slug` | `str` | Node type slug |
| `status` | `"completed" \| "failed" \| "skipped"` | Node execution status |
| `outputs` | `dict \| None` | Output values (if completed) |
| `duration_ms` | `int` | Execution time |
| `error` | `str \| None` | Error message (if failed) |
| `skipped_reason` | `str \| None` | Why skipped (e.g. `"upstream_failed"`) |

### Graph Validation

The builder validates automatically on `build()`. Checks:

- Exactly 1 `__start__` node, at least 1 `__end__` node
- START has no incoming edges, END has no outgoing edges
- No cycles (Kahn's algorithm)
- No orphan nodes (unreachable from START)
- No dead-end nodes (no path to any END)
- All edge references point to existing node IDs
- No duplicate node IDs

### Edge Types

Matching engine routing semantics:

| Type | When it fires |
|------|--------------|
| `DEFAULT` | Always fires on successful execution |
| `SUCCESS` | Fires only on success result |
| `FAILURE` | Fires only on failure result |
| `CONDITIONAL` | Fires based on CEL expression evaluation |

### Engine Compatibility

`WorkflowDefinitionSpec.model_dump(mode="json")` produces JSON compatible with the engine's `SaveWorkflowRequest.spec`:

```python
spec_json = spec.model_dump(mode="json")
payload = {"name": "my-pipeline", "spec": spec_json}
# POST payload to https://engine.example.com/api/workflows/definitions
```

---

## Structured Logging

The SDK provides production-ready structured logging out of the box. It is configured automatically at app startup — no setup required.

### How It Works

`create_node_app()` calls `configure_logging()` during startup. This reads two environment variables:

| Variable | Default | Values | Description |
|----------|---------|--------|-------------|
| `CANVASTEKK_LOG_FORMAT` | `json` | `json`, `text` | `json` = one JSON object per line (CloudWatch/Datadog/ELK). `text` = human-readable for local dev. |
| `CANVASTEKK_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` | SDK-wide log level. |

### JSON Format (default)

```json
{"timestamp":"2026-05-16T12:34:56.789000+00:00","level":"INFO","logger":"node.ff-1","message":"Processing started","run_id":"run-abc123","node_id":"ff-1"}
```

Every log line includes:
- `timestamp` — ISO 8601 UTC
- `level` — `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`
- `logger` — logger name (e.g. `node.ff-1`, `canvastekk_workflow_sdk.app`)
- `message` — the log message
- `run_id` / `node_id` — correlation IDs (when set by middleware)
- Any extra fields passed via `extra={}`

### Text Format (local dev)

```
2026-05-16 12:34:56 [   INFO] node.ff-1: Processing started
[run-abc1] 2026-05-16 12:34:57 [   INFO] node.ff-1: Downloaded 1.2 MB
```

Set `CANVASTEKK_LOG_FORMAT=text` for human-readable output during development.

### Using the Logger in `execute()`

The `ExecutionContext` provides a pre-configured logger:

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    context.logger.info("Processing started")

    # With extra structured fields
    context.logger.info("File downloaded", extra={
        "file_size_bytes": len(data),
        "file_name": "scan.ply",
    })

    # → JSON: {"message":"File downloaded","file_size_bytes":1200000,"file_name":"scan.ply",...}

    return {"result": "done"}
```

### Getting a Logger Outside `execute()`

Use `get_node_logger()` for background tasks or setup code:

```python
from canvastekk_workflow_sdk import get_node_logger

logger = get_node_logger("my-node")

logger.info("Background task started")
logger.error("Upload failed", extra={"url": presigned_url})
```

### Manual Configuration (tests, scripts)

Call `configure_logging()` explicitly when running outside the HTTP server:

```python
from canvastekk_workflow_sdk import configure_logging
import logging

# Use defaults (reads env vars)
configure_logging()

# Or override explicitly
configure_logging(level=logging.DEBUG, fmt="text")
```

### Deployment Examples

**Docker (production):**
```dockerfile
ENV CANVASTEKK_LOG_FORMAT=json
ENV CANVASTEKK_LOG_LEVEL=INFO
```

**Docker (local dev):**
```dockerfile
ENV CANVASTEKK_LOG_FORMAT=text
ENV CANVASTEKK_LOG_LEVEL=DEBUG
```

**Kubernetes:**
```yaml
env:
  - name: CANVASTEKK_LOG_FORMAT
    value: json
  - name: CANVASTEKK_LOG_LEVEL
    value: info
```

**CloudWatch Logs Insights query example:**
```
filter @message like /"level":"ERROR"/
| parse @message '{"message":"*","level":"*","run_id":"*"}' as msg, lvl, rid
| stats count() by msg
```

---

## Advanced: Middleware, Health Checks, and Hooks

### Custom Middleware

Middleware provides hooks around `execute()` for cross-cutting concerns:

```python
from typing import Any
from canvastekk_workflow_sdk import BaseNode, ExecutionContext, WorkflowNodeManifest
from canvastekk_workflow_sdk.middleware import NodeMiddleware


class AuditMiddleware:
    def on_before_execute(
        self, inputs: dict[str, Any], context: ExecutionContext
    ) -> dict[str, Any]:
        context.logger.info(f"Audit: execution started for {context.node_id}")
        return inputs

    def on_after_execute(
        self,
        inputs: dict[str, Any],
        outputs: dict[str, Any],
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        context.logger.info(f"Audit: execution completed in {duration_ms}ms")

    def on_error(
        self,
        inputs: dict[str, Any],
        error: Exception,
        context: ExecutionContext,
        duration_ms: int,
    ) -> None:
        context.logger.error(f"Audit: execution failed: {error}")


# Register middleware (supports chaining)
node = MyNode()
node.add_middleware(AuditMiddleware())
app = node.create_app()
```

Built-in middleware:

| Middleware | Description |
|-----------|-------------|
| `LoggingMiddleware` | Logs execution lifecycle with correlation IDs (added by default) |
| `TimingMiddleware` | Records execution timing as structured data |

### Custom Health Checks

Override `health_check()` to report on external dependencies:

```python
class ModelInferenceNode(BaseNode):
    definition = WorkflowNodeManifest(...)

    def __init__(self):
        super().__init__()
        self.model = None

    def health_check(self) -> dict[str, bool]:
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

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        if self.model is None:
            self.model = self._load_model()
        # ...
```

Health status logic:
- All checks `True` → `"healthy"`
- Some checks `True` → `"degraded"`
- All checks `False` → `"unhealthy"`
- No checks defined → `"healthy"`

### Webhook Hooks

Override `hook()` to handle async callbacks:

```python
class AsyncTaskNode(BaseNode):
    definition = WorkflowNodeManifest(...)

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        # Start a long-running task, return immediately
        task_id = self._start_task(inputs)
        return {"task_id": task_id, "status": "processing"}

    def hook(self, payload: dict) -> dict | None:
        # Handle callback when task completes
        task_id = payload.get("task_id")
        result = payload.get("result")

        if task_id and result:
            return {"task_id": task_id, "status": "completed", "result": result}

        return None
```

By default, `hook()` returns `None` which produces a `501 Not Implemented` response.

### Custom Metrics Collector

```python
from canvastekk_workflow_sdk import BaseNode
from canvastekk_workflow_sdk.observability import MetricsCollector, ExecutionMetric


class RemoteMetricsCollector(MetricsCollector):
    def record(self, metric: ExecutionMetric) -> None:
        super().record(metric)
        # Forward to external system (e.g. Prometheus, Datadog)
        self._push_to_monitoring(metric)

    def _push_to_monitoring(self, metric: ExecutionMetric) -> None:
        # Send metric.to_dict() to your monitoring backend
        pass


node = MyNode()
node.set_metrics_collector(RemoteMetricsCollector())
app = node.create_app()
```

---

## Endpoints

Every node exposes these endpoints automatically:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/execute` | POST | Run the node (JSON body) |
| `/health` | GET | Health check |
| `/manifest` | GET | Node self-description (WorkflowNodeManifest) + `sdk_version` + `mode` |
| `/hook` | POST | Webhook/callback handler (override `hook()`) |
| `/metrics` | GET | Execution metrics summary |
| `/live` | GET | Liveness probe — returns 200 if the process is alive (Kubernetes) |
| `/ready` | GET | Readiness probe — returns 200 if ready to accept traffic (Kubernetes) |

All SDK responses include the `X-SDK-Version` header (e.g. `X-SDK-Version: 0.9.0`).

---

## Philosophy

The SDK is a convenience layer, not a hard dependency. Nodes can "eject" by copying SDK code if true independence is needed.

**When to eject:**
- Node needs behavior the SDK doesn't support
- Node is in a different language
- Team wants zero shared dependencies
- SDK abstraction is fighting you more than helping

---

## Releasing

Releases are automated via [git-cliff](https://git-cliff.org/) based on conventional commits.

### How it works

1. Merge a commit with a conventional prefix to `main` (e.g., `feat:`, `fix:`, `BREAKING CHANGE`)
2. `.github/workflows/release.yml` triggers automatically on any push to `main`
3. git-cliff determines the next version based on commit history since the last `v*` tag
4. Only language directories with changes since the last tag get their version bumped
5. The workflow commits version bump + changelog, tags as `v*`, and creates a GitHub Release
6. `.github/workflows/publish-python.yml` picks up the `v*` tag, checks if `python/` changed, and publishes if so

### Version bump rules

| Commit prefix | Bump | Example |
|---------------|------|---------|
| `feat:` | Minor | 0.4.1 → 0.5.0 |
| `fix:` | Patch | 0.4.1 → 0.4.2 |
| `feat!:` or `BREAKING CHANGE` | Major | 0.4.1 → 1.0.0 |
| `refactor:`, `perf:`, `doc:`, etc. | None | — |

> **Note:** Versions are shared across all languages in this monorepo. If only `python/` changes, only `python/pyproject.toml` gets bumped and published. Other languages stay at their current version until they have changes.

### Conventional commit examples

```bash
git commit -m "feat: add retry middleware support"       # minor bump
git commit -m "fix: handle missing input schema"          # patch bump
git commit -m "feat!: change execute() signature"         # major bump
git commit -m "feat: new endpoint with BREAKING CHANGE"   # major bump
```

---

## Roadmap

- [ ] JWT authentication
- [x] Signed URL handling for file inputs/outputs (v0.6.0 — presigned URL pipeline)
- [ ] Idempotency checks (S3 output exists?)
- [ ] Async callback support
- [x] Input validation against JSON Schema (Draft7Validator)
- [x] CLI manifest validation (v0.6.0 — `python -m canvastekk_workflow_sdk validate`)
- [x] File field constraint validation (v0.6.0 — `validate_file_input()` with `x-accept`, `x-maxSizeBytes`)
- [x] Auto-download of presigned URL file inputs (v0.7.0 — SDK auto-downloads file inputs before execute())
- [x] Node definition versioning with auto-derived `id` field (v0.8.0 — `id` computed from `name` + `version`)
- [x] Registry field mapping for new engine API (v0.9.0 — `title`→`label`, `default_retry`→`retry`, `RegisterNodeResult`, `InvokeType` validation, `tags`, `invoke_config`)
- [x] SDK naming convention alignment with engine WorkflowNode/WorkflowDefinitionNode model (v0.10.0 — docstrings, versioning semantics, type mapping documentation)
- [x] Template variable substitution documentation for node authors (DA-1038 — `{{variable}}` syntax, schema constraints, security notes)
- [x] Workflow Builder & Local Runner (DA-1087 — `WorkflowBuilder`, `WorkflowRunner`, `InProcessExecutor`, `HttpExecutor`, graph validation, engine-compatible JSON export)
