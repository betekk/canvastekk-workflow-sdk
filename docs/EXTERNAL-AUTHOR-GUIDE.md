# External Author Guide

> **SDK Version:** This guide targets `canvastekk-workflow-sdk` >= 0.9.0. Features documented here may differ in earlier versions.

End-to-end guide for building, deploying, and registering a CanvasTEKK workflow node.

## Overview

The workflow has four stages:

```
1. Build      → Create a node using the Python SDK
2. Containerize → Package it as a Docker image
3. Deploy     → Push the image and run it on your infrastructure
4. Register   → Tell the engine your node exists via the registry API
```

After registration, the engine can discover your node and include it in workflows.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | Required by the SDK |
| Docker | 20+ | For building container images |
| `httpx` | 0.28+ | SDK dependency for file downloads and registration |
| GitHub account | — | For CI/CD (GitHub Actions) |
| Engine registry URL | — | Provided by the platform team |

---

## Step 1: Install the SDK

**Option A — `pip install` from GitHub Packages (requires PAT):**

> GitHub Packages PyPI registry requires a PAT with `read:packages` scope even for public packages. Create one at [GitHub Settings > Developer settings > Personal access tokens](https://github.com/settings/tokens).

```bash
pip install canvastekk-workflow-sdk \
  --index-url https://USERNAME:TOKEN@pypi.pkg.github.com/nus-cee/
```

**Option B — Direct wheel download from GitHub Releases (no auth):**

```bash
# Download the .whl from https://github.com/nus-cee/canvastekk-workflow-sdk/releases
pip install canvastekk_workflow_sdk-VERSION-py3-none-any.whl
```

For local development:

```bash
cd python/
python3.12 -m venv .venv
source .venv/bin/activate
pip install poetry
poetry install
```

---

## Step 2: Create Your Node

Create a file called `handler.py`. Subclass `BaseNode`, define a `WorkflowNodeManifest`, implement `execute()`, and call `.create_app()`:

```python
# handler.py
from canvastekk_workflow_sdk import BaseNode, WorkflowNodeManifest, ExecutionContext

# Module-level definition — needed for CLI validation
definition = WorkflowNodeManifest(
    slug="my-node",
    version="1.0.0",
    name="My Node",
    description="Does something useful",
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


class MyNode(BaseNode):
    definition = definition  # Class attribute (same object)

    def execute(self, inputs: dict, context: ExecutionContext) -> dict:
        context.report_progress(0.5, "Processing")
        return {"result": inputs["text"].upper()}


app = MyNode().create_app()
```

### Key Requirements

1. **Subclass `BaseNode`** — inherit from `canvastekk_workflow_sdk.BaseNode`
2. **Define `definition`** as both a module-level variable and a class attribute
3. **Implement `execute(inputs, context)`** — return a dict matching your `output_schema`
4. **Call `.create_app()`** — produces a ready-to-run FastAPI app

### Node ID Format

The `id` field is automatically derived from `slug` + `version` as `{slug}-v{version}` (e.g., `my-node-v1.0.0`). Node authors must NOT provide `id` manually.

**Requirements:**
- `slug` must be a valid slug: lowercase alphanumeric characters and hyphens only
- `name` is the human-readable display name (e.g., `My Node`)

> **Migration note (DA-2627):** older SDK versions spelled identity `name=` and display `title=`. That legacy construction still works (it maps with a deprecation warning) but will be removed in a future major version — prefer `slug=` + `name=`.
- `version` must follow semantic versioning (e.g., `1.0.0`, `2.3.1`) — the engine uses this version directly for registry storage

> **Note on versioning:** The engine uses your `WorkflowNodeManifest.version` semantic version string directly. Versions are **immutable** — re-registering with the same version and changed data is rejected. You must bump the version for any schema or metadata changes.

### Marking a node deprecated

When a successor node exists and you want to steer workflow-definition authors away from an older node without breaking existing workflows, set the optional `deprecation` field. This is an **advisory migration signal** — it does not change the node's behavior and does **not** flip the registry's operational `node_status` (`active` / `inactive` / `dead`). A deprecated node stays `active` and keeps running until you separately retire it.

Because `deprecation` is additive metadata (not a schema or behavior change), setting it requires only a **patch** or **minor** version bump, not a major one — the engine's version-immutability only rejects *changed data* on the same version, so adding the field on a new version is a normal re-registration.

| Field | Required | Description |
|-------|----------|-------------|
| `deprecated_at` | no | Date deprecation took effect (RFC 9745). ISO 8601. |
| `sunset_date` | no | Planned removal date (RFC 8594). ISO 8601. Omit if there is no firm removal date yet. |
| `replacement_slug` | no | Slug of the node that replaces this one (the engine resolves it). |
| `migration_url` | no | URL to migration documentation (RFC 9745 §3 / RFC 8594 §6). |
| `notice` | **yes** | Human-readable notice shown to workflow-definition authors. |

```python
from canvastekk_workflow_sdk import BaseNode, DeprecationInfo, WorkflowNodeManifest, ExecutionContext
from datetime import date

class FloorFlatnessNode(BaseNode):
    definition = WorkflowNodeManifest(
        slug="floor-flatness-assessment",
        version="1.4.2",  # bumped patch to register the deprecation metadata
        name="Floor Flatness Assessment (deprecated)",
        description="...",
        input_schema={...},
        output_schema={...},
        deprecation=DeprecationInfo(
            deprecated_at=date(2026, 8, 1),
            sunset_date=date(2027, 1, 1),
            replacement_slug="floor-flatness-per-check-assessment",
            migration_url="https://docs.example.com/ff-migration",
            notice="Use floor-flatness-per-check-assessment for per-check-type outputs.",
        ),
    )

    def execute(self, inputs, context):  # unchanged — behavior is frozen
        ...
```

> **`deprecation` vs `node_status`.** Use `deprecation` to *announce* a migration. Use the registry's `node_status` (managed by the platform, not node authors) to actually *retire* a node (`inactive`/`dead` stops routing). The two are orthogonal: announce first, retire later.

### SDK Types and Engine Terminology

The SDK's `WorkflowNodeManifest` maps to the engine's **registry-level node type** (called `WorkflowNodeManifest` in the engine). This is distinct from `WorkflowDefinitionNode`, which the engine uses to represent a node instance within a specific workflow definition.

| SDK Type | Engine Type | Purpose |
|----------|-------------|---------|
| `WorkflowNodeManifest` | `WorkflowNodeManifest` | Registry-level node type (schemas, metadata, styles) |
| — | `WorkflowDefinitionNode` | Node instance within a workflow definition (inputs, position, edges) |
| — | `WorkflowEdgeDefinition` | Edge instance connecting two nodes in a workflow definition |
| — | `WorkflowDefinitionSpec` | Complete workflow definition (nodes, edges, metadata) |

Node authors only interact with `WorkflowNodeManifest`. The engine handles `WorkflowDefinitionNode`, `WorkflowEdgeDefinition`, and `WorkflowDefinitionSpec` internally.

### Node Role (`WorkflowNodeRole` enum)

Every node has a `role` field (type: `WorkflowNodeRole`) that indicates its function in the workflow:

| Role | Value | Description |
|------|-------|-------------|
| `start` | `"start"` | Workflow entry point. The engine creates an implicit start node for every workflow. |
| `end` | `"end"` | Workflow terminal node. Marks a completion path. |
| `error_gate` | `"error_gate"` | Error handling node. The engine routes failures here when configured. |
| `operation` | `"operation"` | Default. A processing/transform node. |

The `role` field defaults to `"operation"` — most custom nodes do not need to set it explicitly.

### Workflow Definition Node Fields

`WorkflowDefinitionNode` (engine-internal) includes these fields that node authors should be aware of:

| Field | Type | Description |
|-------|------|-------------|
| `workflow_node_id` | `str \| None` | Optional. References a registered `WorkflowNodeManifest` by ID (e.g., `my-node-v1.0.0`). Links the node instance to its registered definition. |
| `config_schema` | `dict \| None` | Optional. Runtime configuration schema overrides for this specific node instance within the workflow. |
| `role` | `WorkflowNodeRole` | Node function in the workflow (see above). Defaults to `operation`. |

### Naming Conventions

SDK and engine types follow a parent→child naming pattern:

| Type | Parent | Purpose |
|------|--------|---------|
| `WorkflowNodeManifest` | `WorkflowNodeRegistry` | Registration artifact stored in the engine registry |
| `WorkflowDefinitionNode` | `WorkflowDefinition` | Node instance within a specific workflow definition |
| `WorkflowEdgeDefinition` | `WorkflowDefinition` | Edge instance connecting two nodes in a workflow definition |
| `WorkflowDefinitionSpec` | `WorkflowDefinition` | Complete workflow spec containing nodes, edges, and metadata |

### Backward-Compatibility Aliases

Old type names remain available as aliases for migration compatibility:

| Old Name | Current Name |
|----------|-------------|
| `WorkflowNodeManifest` | `WorkflowNodeManifest` |
| `WorkflowWorkflowNodeManifest` | `WorkflowNodeManifest` |
| `WorkflowNode` | `WorkflowDefinitionNode` |
| `WorkflowEdge` | `WorkflowEdgeDefinition` |
| `WorkflowSpec` | `WorkflowDefinitionSpec` |

### File Inputs

Use `format: "file"` with `x-accept` and `x-maxSizeBytes`:

```python
input_schema={
    "type": "object",
    "properties": {
        "point_cloud": {
            "type": "string",
            "format": "file",
            "x-accept": [".ply", ".las"],
            "x-maxSizeBytes": 52428800,
        },
    },
}
```

The SDK **automatically downloads** presigned URL file inputs and validates them before calling `execute()`. Your `execute()` method receives local file paths, not URLs:

```python
from pathlib import Path

def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    # inputs["point_cloud"] is already a local file path (auto-downloaded)
    cloud_path = Path(inputs["point_cloud"])
    data = cloud_path.read_bytes()

    # Access download metadata if needed
    meta = context.metadata.get("point_cloud", {})
    # meta contains: original_url, local_path, size_bytes

    output = context.output_path("result.json")
    output.write_text('{"count": 42}')

    return {"result_path": str(output)}
```

> **Note:** Manual download with `httpx.stream()` is only needed for non-file URLs or opt-out scenarios. Standard file inputs are handled automatically.

### Download Security Policy (v0.22+)

The auto-download pipeline enforces an SSRF protection policy:

- **HTTPS required** in production (`http://` URLs are rejected unless `CANVASTEKK_DEV_MODE` is enabled — **breaking change** if you relied on plain-HTTP input URLs; migrate your storage endpoints to HTTPS).
- **Blocked targets**: loopback, RFC1918 private, link-local (incl. cloud metadata `169.254.254.254`), CGNAT `100.64.0.0/10`, and reserved/multicast ranges — resolved before connecting, re-validated on every redirect hop (max 5).
- **Size caps enforced mid-stream**: `x-maxSizeBytes` aborts the download as soon as it is exceeded (no more post-hoc checks). When absent, `CANVASTEKK_MAX_DOWNLOAD_BYTES` (default 10 GiB) applies.
- **Total download deadline**: derived from `timeout_seconds` — a timed-out request stops in-flight downloads cooperatively (`context.cancel_event` / `context.cancelSignal`; `execute()` itself cannot be interrupted).
- **Allowlist escape hatch**: `CANVASTEKK_URL_ALLOWLIST` (comma-separated host suffixes, e.g. `internal.minio.example.com`) bypasses IP checks for trusted internal storage.

Uploads changed too: a failed output upload now **fails the execution** with `error_code: "UPLOAD_FAILED"` instead of silently passing with a local-only path.

### Multipart Output Uploads (v0.29+, session-only since v0.36.0)

Nothing changes in **your** node code — the router, not the developer, performs output uploads. What changed underneath:

- The engine sends a **multipart upload-session descriptor** as the upload target: lazy initiate → bounded parallel part PUTs (per-part `Content-MD5`) → complete, with per-part retry, resume-from-server-status, and abort-on-failure.
- Since SDK **0.36.0** (DA-3340) plain-string targets are **removed**: a legacy presigned-PUT string reaching the SDK raises `NodeIOError` ("engine sent deprecated presigned target — upgrade the engine") and fails the execution — there is no deprecation warning and no fallback. The fix is upgrading the engine (DA-3338/DA-2887), not node changes.
- `fail`/`UPLOAD_FAILED` semantics on terminal upload failure are unchanged (DA-1711).

### Account Context (v0.24.0+)

When the workflow engine invokes your node's `POST /execute`, it forwards the run's active account as the `X-Account-Id` header. The SDK surfaces it on the execution context:

```python
def execute(self, inputs: dict, context: ExecutionContext) -> dict:
    account_id = context.account_id  # int | None
```

Rules to rely on:

- **Routing identity, not a credential.** Use it to route account-scoped calls (e.g. forwarding `X-Account-Id` to account-gated CDS endpoints). Endpoint access is still gated by node auth.
- **Header-only, engine-asserted.** The SDK strips any body-supplied `account_id` and sets the field exclusively from the header — callers cannot forge it.
- **`None` when absent** (local runs, engines that don't send the header). Treat `None` as "no account context": either degrade gracefully or fail with a clear error if the account is required.
- **Strict parsing.** Blank headers are treated as absent; non-numeric, negative, zero, or int64-overflowing values fail with HTTP 400.

In unit tests, skip the header plumbing — construct the request directly: `NodeExecutionRequest(run_id="r1", node_id="n1", inputs={}, account_id=7)`.

### Validate Locally

Before deploying, validate your node definition offline:

```bash
python -m canvastekk_workflow_sdk validate handler:definition
```

Exit code `0` = valid, `1` = errors.

### Probe Registration Locally (v0.28+)

`probe` runs everything `validate` runs **plus the engine-request mirror** — the
exact payload shape the engine's registration endpoint accepts (required keys,
no client-set `slug`, whitelist only). Passes locally ⇔ passes registration:

```bash
python -m canvastekk_workflow_sdk probe handler:definition
```

Fully offline — no network calls. Exit code `0` = registration-ready.

### Publish from CI: `register` (v0.28+)

Publish a node to the engine registry from a pipeline under a service identity:

```bash
export CANVASTEKK_REGISTRY_TOKEN=<service token>
python -m canvastekk_workflow_sdk register handler:definition \
  --engine-url https://cwe.example.com \
  --invoke-url https://nodes.example.com/my-node/execute \
  [--name-suffix -lambda] [--json]
```

The CLI maps the manifest to the engine's request vocabulary automatically
(`name` = the manifest's `slug`, `label` = the display `name`, plus schemas,
cost, timeout, constraints, deprecation), authenticates with the
`X-Service-Token` header, POSTs to `{engine}/api/workflows/nodes/`, and
verifies the row via `by-name/{name}`. Exit codes: `0` ok · `2` usage ·
`3` auth (401/403) · `4` other 4xx · `5` server · `6` network. The token is
read from the environment and never printed.

The TypeScript package ships the same CLI (`canvastekk-workflow-sdk register
--manifest <file.json|URL> --engine-url URL …` / `canvastekk-workflow-sdk
probe --manifest <file.json>`) with identical flags, mapping, and exit codes.

### `code_digest` (v0.28+)

`GET /manifest` now carries `code_digest`: a sha256 over the source bytes of
the module that defines your node (python: the module declaring the node
class; typescript: the module calling `createNodeApp`), computed once at
startup and auto-injected next to `sdk_version`/`mode`. Any handler-code
change changes the digest — it is never author-settable (not a manifest
field). If the handler source cannot be resolved, the key is omitted and a
warning is logged.

> **Bundlers note:** if you single-file-bundle your server (esbuild/pyinstaller
> style), the digest covers the whole bundle — any byte flip changes it. The
> digest signals *deployed-code identity*, not source-line granularity.

---

## Step 3: Containerize

Create a `Dockerfile`. Choose one of two approaches for installing the SDK:

**Option A — GitHub Packages (pass PAT as build arg):**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

ARG SDK_PAT
COPY pyproject.toml handler.py ./
RUN pip install . --index-url https://nus-cee:${SDK_PAT}@pypi.pkg.github.com/nus-cee/

EXPOSE 8001

CMD ["uvicorn", "handler:app", "--host", "0.0.0.0", "--port", "8001"]
```

Build with: `docker build --build-arg SDK_PAT=ghp_xxx -t my-node .`

> **Warning:** Never hardcode the PAT in the Dockerfile. Note that build args are visible in `docker history` — for production images, use Docker BuildKit secrets (`--mount=type=secret`) or a multi-stage build. Alternatively, use Option B (pre-downloaded wheel) to avoid embedding any token.

**Option B — Pre-downloaded wheel (no auth in Docker):**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Download the wheel from GitHub Releases first:
# https://github.com/nus-cee/canvastekk-workflow-sdk/releases
COPY canvastekk_workflow_sdk-VERSION-py3-none-any.whl ./
COPY . ./

RUN pip install canvastekk_workflow_sdk-VERSION-py3-none-any.whl && pip install .

EXPOSE 8001

CMD ["uvicorn", "handler:app", "--host", "0.0.0.0", "--port", "8001"]
```

Create a `pyproject.toml`:

```toml
[project]
name = "my-node"
version = "1.0.0"
description = "My CanvasTEKK workflow node"
requires-python = ">=3.12"
dependencies = [
    "canvastekk-workflow-sdk>=0.9.0,<1.0.0",
]
```

> **Tip:** Pin to a specific minor version for production nodes. This prevents unexpected breakage when the SDK releases a new minor or major version.

Build and test locally:

```bash
docker build -t my-node .
docker run -p 8001:8001 my-node

# Verify
curl http://localhost:8001/health
curl http://localhost:8001/manifest
```

---

## Step 4: Deploy

Push your image to a container registry accessible by the platform:

```bash
docker tag my-node your-registry.example.com/my-node:1.0.0
docker push your-registry.example.com/my-node:1.0.0
```

The platform team will deploy it to the cluster. Once running, your node exposes:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/execute` | POST | Run the node |
| `/health` | GET | Health check |
| `/manifest` | GET | Node self-description |
| `/hook` | POST | Webhook/callback handler (optional, override `hook()`) |
| `/metrics` | GET | Execution metrics summary |
| `/live` | GET | Liveness probe (Kubernetes) |
| `/ready` | GET | Readiness probe (Kubernetes) |

---

## Step 5: Register with the Engine

After deployment, register your node so the engine can discover it. The engine stores your node as a `WorkflowNodeManifest` (registry-level node type) — distinct from a `WorkflowDefinitionNode`, which represents a node instance within a workflow definition.

### Authentication Methods

| Method | Header | Use Case |
|--------|--------|----------|
| **Service Token** | `X-Service-Token` | CI/CD pipelines (recommended) |
| **API Key** | `X-API-Key` | Manual registration, testing |

### Using `register_node()` (Python)

```python
from canvastekk_workflow_sdk import BaseNode, WorkflowNodeManifest
from canvastekk_workflow_sdk.registry import register_node

node = MyNode()

# CI/CD with service token (recommended)
register_node(
    node,
    registry_url="https://engine.example.com/api/workflows/nodes/",
    invoke_url="https://my-node.example.com",
    service_token="svs_your-token-here",
    tags=["category:utility", "team:platform"],
)

# Manual with API key
register_node(
    node,
    registry_url="https://engine.example.com/api/workflows/nodes/",
    invoke_url="https://my-node.example.com",
    api_key="your-api-key",
)

# Lambda invocation
register_node(
    node,
    registry_url="https://engine.example.com/api/workflows/nodes/",
    invoke_type="lambda",
    invoke_url="arn:aws:lambda:ap-southeast-1:123456789:function:my-node",
    invoke_config={"region": "ap-southeast-1"},
    service_token="svs_your-token-here",
)
```

#### Registration Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `node` | `BaseNode` | Yes | The node instance to register |
| `registry_url` | `str` | Yes | Engine registry endpoint (e.g., `/api/workflows/nodes/`) |
| `invoke_url` | `str \| None` | No | URL where the node is reachable |
| `invoke_type` | `"http" \| "lambda" \| "sagemaker" \| "in-process"` | No | Invocation type (default: `"http"`) |
| `api_key` | `str \| None` | Yes* | API key for auth (`X-API-Key` header) |
| `service_token` | `str \| None` | Yes* | Service token for CI/CD (`X-Service-Token` header, takes precedence) |
| `tags` | `list[str] \| None` | No | Searchable tags for the registry |
| `invoke_config` | `dict \| None` | No | Extra invocation parameters (e.g., Lambda region) |
| `timeout` | `int` | No | Request timeout in seconds (default: 30) |

*Either `api_key` or `service_token` must be provided.

### Using `curl` (manual)

```bash
# Get your node manifest
MANIFEST=$(curl -s http://localhost:8001/manifest)

# Register with service token
curl -X POST https://engine.example.com/api/workflows/nodes/ \
  -H "Content-Type: application/json" \
  -H "X-Service-Token: svs_your-token-here" \
  -d "$(echo "$MANIFEST" | jq '. + {invoke_url: "https://my-node.example.com", invoke_type: "http"}')"
```

---

## Required Secrets

Secrets are **never stored in code**. Use your CI/CD provider's secrets store.

| Secret | When Required | Description |
|--------|--------------|-------------|
| `REGISTRY_SERVICE_TOKEN` | CI/CD registration | Service token for automated registration (`X-Service-Token` header). Provided by the platform team. |
| `REGISTRY_API_KEY` | Manual registration | API key for the registry (`X-API-Key` header). Provided by the platform team. |
| `CANVASTEKK_API_KEY` | Node auth (API Key mode) | Shared secret for authenticating requests to your node. Set via `NodeAuth.api_key()`. |
| `CANVASTEKK_KEYCLOAK_SERVER_URL` | Node auth (Keycloak mode) | Keycloak base URL. Only needed if using Keycloak auth. |
| `CANVASTEKK_KEYCLOAK_REALM` | Node auth (Keycloak mode) | Keycloak realm name. |
| `CANVASTEKK_JWT_SECRET` | Node auth (JWT mode) | HS256 signing secret. Only needed if using JWT auth. |

### Auth Mode Summary

| Auth Mode | Secrets Required | Typical Use Case |
|-----------|-----------------|------------------|
| None | None | Local development (`CANVASTEKK_DEV_MODE=true`) |
| API Key | `CANVASTEKK_API_KEY` | Simple shared-secret protection |
| Keycloak | `CANVASTEKK_KEYCLOAK_SERVER_URL` + `CANVASTEKK_KEYCLOAK_REALM` | Production SSO integration |
| JWT | `CANVASTEKK_JWT_SECRET` | Custom token-based auth |

---

## CI/CD Pipeline Example (GitHub Actions)

This workflow builds, pushes, and registers your node automatically:

```yaml
name: Build and Register Node

on:
  push:
    branches: [main]
    tags: ["v*"]

env:
  REGISTRY: your-registry.example.com
  IMAGE_NAME: my-node
  ENGINE_URL: https://engine.example.com/api/workflows/nodes/

jobs:
  build-and-register:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }} .

      - name: Push to registry
        run: |
          echo "${{ secrets.REGISTRY_PASSWORD }}" | docker login ${{ env.REGISTRY }} -u "${{ secrets.REGISTRY_USERNAME }}" --password-stdin
          docker push ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}

      - name: Install SDK
        run: pip install canvastekk-workflow-sdk --index-url https://nus-cee:${{ secrets.GITHUB_TOKEN }}@pypi.pkg.github.com/nus-cee/

      - name: Register node with engine
        env:
          REGISTRY_SERVICE_TOKEN: ${{ secrets.REGISTRY_SERVICE_TOKEN }}
        run: |
          python -c "
          import os
          from handler import MyNode
          from canvastekk_workflow_sdk.registry import register_node

          register_node(
              MyNode(),
              registry_url='${{ env.ENGINE_URL }}',
              invoke_url='https://my-node.example.com',
              service_token=os.environ['REGISTRY_SERVICE_TOKEN'],
              tags=['ci-cd', 'auto-registered'],
          )
          print('Registration successful')
          "

      - name: Validate registration
        run: |
          HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
            -H "X-Service-Token: ${{ secrets.REGISTRY_SERVICE_TOKEN }}" \
            "${{ env.ENGINE_URL }}/my-node-v1.0.0")
          if [ "$HTTP_STATUS" != "200" ]; then
            echo "Registration verification failed (HTTP $HTTP_STATUS)"
            exit 1
          fi
          echo "Registration verified"
```

### Required GitHub Secrets

Configure these in **Settings > Secrets and variables > Actions**:

| Secret | Description |
|--------|-------------|
| `REGISTRY_SERVICE_TOKEN` | Service token for engine registration |
| `REGISTRY_USERNAME` | Container registry username |
| `REGISTRY_PASSWORD` | Container registry password |

---

## Error Handling Reference

When calling the registry API, you may encounter these errors:

| HTTP Status | Error Meaning | Cause | Fix |
|-------------|--------------|-------|-----|
| **401** | Unauthorized | Missing or invalid API key / service token | Check your `api_key` or `service_token` value. Ensure the header is correct (`X-API-Key` or `X-Service-Token`). |
| **403** | Forbidden | Wrong owner — the node is registered under a different owner | Contact the platform team to transfer ownership, or use a different node ID. |
| **404** | Not Found | Node not found in registry (GET/PUT/DELETE) or registry endpoint doesn't exist | Verify the `registry_url` and node ID. |
| **409** | Conflict | Node already exists with a different owner, **or** same version registered with different content (immutability violation) | Use a unique node ID, or **bump your version** if you changed the schema or metadata. |
| **422** | Validation Error | Invalid manifest payload | Validate locally first: `python -m canvastekk_workflow_sdk validate handler:definition` |
| **500** | Internal Server Error | Engine-side failure | Retry after a few seconds. Contact the platform team if persistent. |

### Handling Errors in Python

```python
from canvastekk_workflow_sdk.registry import register_node, RegistrationError

try:
    result = register_node(
        node,
        registry_url="https://engine.example.com/api/workflows/nodes/",
        invoke_url="https://my-node.example.com",
        service_token="svs_your-token-here",
    )
    print(f"Registered: {result['name']} v{result['version']}")
except RegistrationError as e:
    if e.status_code == 401:
        print("Authentication failed: check your service token")
    elif e.status_code == 403:
        print("Forbidden: this node belongs to another owner")
    elif e.status_code == 409:
        print("Conflict: node already registered with different owner")
        print("  OR: same version with changed data — bump your version to resolve")
    else:
        print(f"Registration failed ({e.status_code}): {e}")
```

---

## Quick Reference: Complete Minimal Node

```
my-node/
├── handler.py
├── pyproject.toml
├── Dockerfile
└── tests/
    └── test_handler.py
```

**handler.py** — see [Step 2](#step-2-create-your-node)

**pyproject.toml**:

```toml
[project]
name = "my-node"
version = "1.0.0"
requires-python = ">=3.12"
dependencies = ["canvastekk-workflow-sdk>=0.9.0,<1.0.0"]
```

**Dockerfile** — see [Step 3](#step-3-containerize)

**tests/test_handler.py**:

```python
from fastapi.testclient import TestClient
from handler import app

client = TestClient(app)


def test_execute():
    resp = client.post("/execute", json={
        "run_id": "test", "node_id": "test", "inputs": {"text": "hello"},
    })
    assert resp.status_code == 200
    assert resp.json()["status"] == "pass"
    assert resp.json()["outputs"]["result"] == "HELLO"


def test_manifest():
    resp = client.get("/manifest")
    assert resp.status_code == 200
    assert resp.json()["name"] == "my-node"
```

---

## Template Variable Substitution

The workflow engine automatically resolves `{{variable}}` placeholders in **string** node inputs after edge resolution.

### How It Works

When the engine executes a workflow, it resolves each node's inputs via edges (connecting upstream outputs to downstream inputs). After this resolution, the engine scans all **string** values for `{{key}}` patterns and substitutes them using the same node's resolved input dict.

**Your node receives fully resolved strings.** You do not need to handle `{{}}` syntax in your `execute()` method — the engine handles substitution before your node runs.

```
Engine: resolve edges → resolve {{templates}} → POST /execute to your node
```

### Syntax

| Pattern | Behavior |
|---------|----------|
| `{{variable}}` | Replaced with `str(inputs["variable"])` |
| `{variable}` | **Literal** — single braces are not substituted |
| `{{unknown_key}}` | Left as-is if the key is not in the node's inputs (logged at DEBUG) |

**Key rules:**
- Only `{{double_braces}}` trigger substitution — single braces `{like_this}` are literal
- Substitution is **single-pass** (no recursive resolution — `{{foo}}` in a resolved value is not re-processed)
- Non-string inputs (integers, booleans, arrays, objects) pass through unchanged
- Unresolved placeholders are left as-is and logged at DEBUG level

### Availability

> Template substitution requires an engine version that includes [DA-1037](https://betekk.atlassian.net/browse/DA-1037). On older engines, `{{...}}` placeholders pass through as literal text.

### Examples

**Path construction:**

Workflow definition configures the node with template inputs:

```json
{
  "folder_path": "{{report_id}}/runs/{{run_id}}/output/zip/",
  "report_id": 13,
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

Your node receives the resolved string:

```json
{
  "folder_path": "13/runs/a1b2c3d4-e5f6-7890-abcd-ef1234567890/output/zip/",
  "report_id": 13,
  "run_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
}
```

**URL construction:**

```json
{
  "download_url": "https://api.example.com/reports/{{report_id}}/export?format=pdf",
  "report_id": 42
}
```

After substitution: `"https://api.example.com/reports/42/export?format=pdf"`

### Common Variables

| Variable | Source | Description |
|----------|--------|-------------|
| `run_id` | `__start__` node (via edges) | Workflow run identifier — always available when connected via edges |
| `report_id` | Upstream node output | Report identifier from a preceding node |
| `node_id` | Engine-injected | Node instance ID within the workflow |

Variables must be present in the same node's resolved inputs (from edges, defaults, or overrides). The `run_id` is available when the `__start__` node connects to your node via an edge.

### Design Considerations

#### Input Schema Constraints

Your `input_schema` constraints (`pattern`, `format`, `minLength`, `maxLength`) validate against the **resolved** value, not the template syntax. Design your constraints to match the expected resolved output:

```python
input_schema={
    "type": "object",
    "properties": {
        "folder_path": {
            "type": "string",
            # This pattern must match the RESOLVED value, e.g. "13/runs/abc/output/"
            # NOT the template "{{report_id}}/runs/{{run_id}}/output/"
            "pattern": "^[a-zA-Z0-9/_-]+$",
        },
    },
}
```

#### Security

Template substitution is single-pass, which prevents recursive injection — if a resolved value contains `{{another_key}}`, it is **not** re-substituted. However, node authors should still validate resolved string values before using them in file paths, URLs, or shell commands, as the resolved content depends on upstream node outputs.

#### Avoiding Conflicts

If your node naturally produces or consumes strings containing `{{` and `}}` (e.g., LaTeX templates, Mustache/Handlebars syntax), be aware that the engine will attempt substitution on any string input containing `{{...}}`. To avoid unintended substitution:

- Use single braces `{...}` instead of `{{...}}` where possible
- Structure your workflow so conflicting string fields receive their values from non-edge sources (defaults, overrides)

---

## Testing

### Testing File Download with `LocalFileServer`

The SDK's auto-download pipeline only triggers on `http://`/`https://` URLs — passing a plain local path bypasses the download entirely. To test the full presigned URL download pipeline end-to-end, use `LocalFileServer`:

```python
from canvastekk_workflow_sdk import LocalFileServer, NodeExecutionRequest

def test_downloads_and_processes_file(tmp_path):
    # Create a test file
    (tmp_path / "scan.las").write_bytes(b"fake las data")

    # Serve it over HTTP (simulates a presigned URL)
    with LocalFileServer(tmp_path) as server:
        url = server.url_for("scan.las")

        response = MyNode().run(NodeExecutionRequest(
            run_id="test",
            node_id="n1",
            inputs={"point_cloud": url},
        ))

    assert response.status == "pass"
```

This exercises the complete download → validate → execute path without S3, mocking, or external services.

### Testing with the Local Workflow Runner

Use `WorkflowRunner` with `InProcessExecutor` to test multi-node pipelines:

```python
from canvastekk_workflow_sdk import WorkflowRunner, WorkflowBuilder
from canvastekk_workflow_sdk.workflow.executor import InProcessExecutor

executor = InProcessExecutor()
executor.register("my-node-v1.0.0", MyNode())

# With a shared output_dir — node A writes, node B reads
runner = WorkflowRunner(executor)
result = runner.run(spec, inputs={"input_file": "/data/scan.las"})

# With user-supplied output_dir — preserved after run
import tempfile
with tempfile.TemporaryDirectory() as tmp:
    runner = WorkflowRunner(executor, output_dir=tmp)
    result = runner.run(spec, inputs={"input_file": "/data/scan.las"})
    assert result.output_dir == tmp  # still exists

# Default behavior — auto-created temp dir is cleaned up
runner = WorkflowRunner(executor)
result = runner.run(spec)
assert result.output_dir is None  # cleaned up
```

---

## Further Reading

- [SDK Python README](../python/README.md) — full API reference
- [Echo Node Example](../examples/echo_node/) — minimal reference implementation
- [Root README](../README.md) — SDK overview and architecture
