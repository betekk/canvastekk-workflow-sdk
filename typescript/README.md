# CanvasTEKK Workflow SDK — TypeScript

> Part of [canvastekk-workflow-sdk](../) monorepo

Node SDK for CanvasTEKK Workflow Engine. Handles HTTP endpoint boilerplate so node authors can focus on business logic.

## Installation

### From GitHub Packages (recommended)

```bash
npm install canvastekk-workflow-sdk --registry https://npm.pkg.github.com/@nus-cee
```

### For Development

All commands run from this `typescript/` directory.

```bash
cd typescript/
npm install
```

### Linting, Testing & Building

```bash
# Lint
npm run lint

# Typecheck
npm run typecheck

# Test
npm test

# Test (watch mode)
npm run test:watch

# Test with coverage report
npx vitest run --coverage

# Build
npm run build
```

### Runtime Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| Node.js | >=24 | Runtime (native fetch, ESM-first) |
| Express | ^4.21 | HTTP framework |
| Zod | ^3.25 | Data validation |
| Ajv | ^8 | JSON Schema Draft 7 validation |
| jsonwebtoken | ^9 (optional) | JWT/Keycloak authentication |

### Dev Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| TypeScript | ^5.8 | Compiler (strict mode) |
| tsup | ^8 | Bundler (ESM + CJS dual output) |
| Vitest | ^3 | Test runner |
| @vitest/coverage-v8 | ^3.2.4 | Coverage reporting |
| Supertest | ^7 | HTTP integration testing |
| ESLint | ^9 | Linter |

---

## Creating Your First Node

### Step 1: Install the SDK

```bash
npm install canvastekk-workflow-sdk --registry https://npm.pkg.github.com/@nus-cee
```

### Step 2: Define Your Node

Create a file (e.g. `handler.ts`) and extend `BaseNode`:

```typescript
import {
  BaseNode,
  WorkflowNodeManifest,
  ExecutionContext,
} from "canvastekk-workflow-sdk";

class UppercaseNode extends BaseNode {
  static override definition: WorkflowNodeManifest = {
    slug: "uppercase",
    version: "1.0.0",
    name: "Uppercase",
    description: "Converts text to uppercase",
    input_schema: {
      type: "object",
      properties: { text: { type: "string" } },
      required: ["text"],
    },
    output_schema: {
      type: "object",
      properties: { result: { type: "string" } },
    },
  };

  override async execute(
    inputs: Record<string, unknown>,
    context: ExecutionContext,
  ): Promise<Record<string, unknown>> {
    context.reportProgress(0.5, "Processing text");
    return { result: (inputs["text"] as string).toUpperCase() };
  }
}

const app = new UppercaseNode().createApp();
export default app;
```

The four requirements:

1. **Extend `BaseNode`** — inherit from `canvastekk-workflow-sdk`'s `BaseNode`
2. **Define `definition`** — a `WorkflowNodeManifest` with all required fields (`slug`, `version`, `name`, `description`, `input_schema`, `output_schema`). Note: `id` is auto-derived from `slug` + `version` and must NOT be provided manually.
3. **Implement `execute(inputs, context)`** — return an object matching your `output_schema`
4. **Call `.createApp()`** — get a ready-to-run Express application

### Step 3: Run It

```bash
# Development (with tsx)
npx tsx handler.ts

# Production (compiled)
node dist/handler.js

# With custom port
PORT=8001 node dist/handler.js
```

### Step 4: Test the Endpoints

```bash
# Health check
curl http://localhost:8001/health
# {"status":"healthy","node_id":"uppercase-v1.0.0","version":"1.0.0","checks":{}}

# Node manifest
curl http://localhost:8001/manifest
# {"id":"uppercase-v1.0.0","name":"uppercase","version":"1.0.0","sdk_version":"0.13.0",...}

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

## Express Endpoint Deep Dive

### How It Works

When you call `node.createApp()`, the SDK creates an Express application with these endpoints:

| Endpoint | Method | Handler | Purpose |
|----------|--------|---------|---------|
| `/execute` | POST | `node.run(request)` | Execute the node's business logic |
| `/health` | GET | `node.healthCheck()` | Health status |
| `/manifest` | GET | Node definition | Node self-description |
| `/hook` | POST | `node.hook(payload)` | Webhook/callback handler |
| `/metrics` | GET | Metrics summary | Execution metrics |
| `/live` | GET | Liveness probe | Returns 200 if process is alive (Kubernetes) |
| `/ready` | GET | Readiness probe | Returns 200 if ready to accept traffic |

### Request/Response Lifecycle

When `POST /execute` receives a request:

```
NodeExecutionRequest
        |
        v
  Input Validation  --(fail)-->  NodeExecutionResponse(status="fail", error_code="VALIDATION_ERROR")
        |
     (pass)
        v
  ExecutionContext created
        |
        v
  Middleware: onBeforeExecute(inputs, context)
        |
        v
  node.execute(inputs, context)  --(exception)-->  Middleware: onError(...)
        |                                            |
     (returns)                                    NodeExecutionResponse(status="fail")
        v
  Middleware: onAfterExecute(inputs, outputs, context, durationMs)
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
| `run_id` | `string` | Yes | Workflow run identifier |
| `node_id` | `string` | Yes | Node instance ID in the workflow |
| `inputs` | `object` | No | Input values (validated against `input_schema`) |
| `callback_url` | `string` | No | URL to POST result to (for async execution) |
| `output_upload_url` | `Record<string, string>` | No | Mapping of output field name to pre-signed S3 PUT URL |

### NodeExecutionResponse

The response from `POST /execute`:

```json
{
  "execution_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pass",
  "outputs": { "result": "HELLO" },
  "token_usage": 0,
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
  "token_usage": 0,
  "duration_ms": 5,
  "error": "Intentional failure for testing",
  "error_type": "Error",
  "error_code": null
}
```

### Error Types and HTTP Status Codes

The SDK provides structured exceptions. When thrown inside `execute()`, they produce specific error codes in the response:

| Exception | Error Code | HTTP Status | When to Use |
|-----------|-----------|-------------|-------------|
| `NodeExecutionError` | `EXECUTION_ERROR` | 500 | Generic execution failure |
| `NodeValidationError` | `VALIDATION_ERROR` | 422 | Input validation failure |
| `NodeOutputValidationError` | `OUTPUT_VALIDATION_ERROR` | 422 | Output validation failure |
| `NodeTimeoutError` | `TIMEOUT` | 408 | Execution exceeded time limit |
| `NodeIOError` | `IO_ERROR` | 500 | File read/write failure |
| `NodeConfigurationError` | `CONFIGURATION_ERROR` | 500 | Invalid node configuration |
| `WorkflowExecutionError` | `WORKFLOW_EXECUTION_ERROR` | 500 | Local workflow execution failure |
| `WorkflowValidationError` | `WORKFLOW_VALIDATION_ERROR` | 422 | Workflow spec validation failure |

Note: When thrown inside `execute()`, the SDK catches them and returns `status: "fail"` with HTTP 200. The structured error codes appear in the `error_code` field.

Usage example:

```typescript
import {
  BaseNode,
  WorkflowNodeManifest,
  ExecutionContext,
  NodeIOError,
} from "canvastekk-workflow-sdk";
import { existsSync } from "node:fs";

class FileProcessorNode extends BaseNode {
  static override definition: WorkflowNodeManifest = {
    slug: "file-proc",
    version: "1.0.0",
    name: "File Processor",
    description: "Processes a file",
    input_schema: {
      type: "object",
      properties: { path: { type: "string" } },
    },
    output_schema: {
      type: "object",
      properties: { line_count: { type: "integer" } },
    },
  };

  override async execute(
    inputs: Record<string, unknown>,
    context: ExecutionContext,
  ): Promise<Record<string, unknown>> {
    const filePath = inputs["path"] as string;
    if (!existsSync(filePath)) {
      throw new NodeIOError(`File not found: ${filePath}`);
    }
    const content = await import("node:fs/promises").then((fs) =>
      fs.readFile(filePath, "utf-8"),
    );
    return { line_count: content.split("\n").length };
  }
}
```

---

## File Handling Guide

### Declaring File Inputs

Mark input fields as files using `"format": "file"` in `input_schema`. Use `x-accept` and `x-maxSizeBytes` extensions to specify accepted file types and size limits:

```typescript
const definition: WorkflowNodeManifest = {
  slug: "segment",
  version: "1.0.0",
  name: "Segment",
  description: "Segments a point cloud",
  input_schema: {
    type: "object",
    properties: {
      point_cloud: {
        type: "string",
        format: "file",
        description: "Point cloud file",
        "x-accept": [".ply", ".pcd"],
        "x-maxSizeBytes": 52428800,
      },
      confidence: { type: "number", default: 0.5 },
    },
  },
  output_schema: {
    type: "object",
    properties: {
      instances: { type: "string" },
    },
  },
};
```

### How File Inputs Work

When the workflow engine executes your node, file input values are presigned GET URLs (strings). The SDK **automatically downloads** them to `context.downloadsDir` before calling `execute()`:

- URL inputs (`https://` or `http://`) are downloaded to a local file
- Local path inputs are passed through unchanged
- Downloaded files are auto-validated against `x-accept` and `x-maxSizeBytes`

```typescript
override async execute(
  inputs: Record<string, unknown>,
  context: ExecutionContext,
): Promise<Record<string, unknown>> {
  // inputs["point_cloud"] is now a LOCAL FILE PATH (auto-downloaded by SDK)
  const cloudPath = inputs["point_cloud"] as string;
  const data = await import("node:fs/promises").then((fs) =>
    fs.readFile(cloudPath),
  );

  const confidence = (inputs["confidence"] as number) ?? 0.5;

  return { instances: "42 objects found" };
}
```

### Writing Output Files

Use `context.outputPath(filename)` for output files:

```typescript
override async execute(
  inputs: Record<string, unknown>,
  context: ExecutionContext,
): Promise<Record<string, unknown>> {
  const outputFile = context.outputPath("result.json");
  const { writeFileSync } = await import("node:fs");
  writeFileSync(outputFile, JSON.stringify({ status: "done" }));

  return { result_path: outputFile };
}
```

`context.outputDir` is created automatically.

**v0.22+ security & behavior changes**

- **SSRF policy**: file-input URLs must be `https://` (production); loopback/private/link-local/metadata/CGNAT IPs are blocked, re-validated per redirect hop (max 5). Escape hatches: `CANVASTEKK_URL_ALLOWLIST` (trusted host suffixes), `CANVASTEKK_DEV_MODE` (dev only — also lifts auth).
- **Streamed downloads with mid-stream size caps**: responses stream to disk (no whole-body RAM buffering); `x-maxSizeBytes` aborts as soon as exceeded; undeclared fields fall back to `CANVASTEKK_MAX_DOWNLOAD_BYTES` (default 10 GiB).
- **Download deadlines**: derived from `timeout_seconds`; timed-out requests cancel in-flight downloads via `context.cancelSignal`.
- **Streamed uploads**: output files upload via `createReadStream` (multi-GB safe, 600 s timeout); upload failures **fail the execution** with `error_code: "UPLOAD_FAILED"`.
- **Request validation**: `run_id`/`node_id` must be slug-safe (no `..`); `context.outputPath()` rejects path traversal.
- **Auth posture**: startup warns loudly when no auth middleware is configured or dev-mode is active.
- **Local `WorkflowRunner` (BREAKING)**: each node now gets `runOutputDir/<node_id>/` (previously shared the run root). Absolute-path hand-off via edge outputs is unchanged. Seeded start inputs merge with static start inputs; mis-wired edges fail one node instead of crashing the run. Resolver rejects `__proto__`/`constructor`/`prototype` keys.

### Output Upload

The engine provides presigned PUT URLs via the `output_upload_url` field in the request. The SDK uploads file outputs automatically after successful execution. If execution fails (`status: "fail"`), the upload is skipped.

### Complete Example

```typescript
import {
  BaseNode,
  WorkflowNodeManifest,
  ExecutionContext,
} from "canvastekk-workflow-sdk";
import { readFileSync, writeFileSync } from "node:fs";

class PointCloudSegmenter extends BaseNode {
  static override definition: WorkflowNodeManifest = {
    slug: "segment",
    version: "1.0.0",
    name: "Segment",
    description: "Segments a point cloud",
    input_schema: {
      type: "object",
      properties: {
        point_cloud: {
          type: "string",
          format: "file",
          description: "Point cloud file",
          "x-accept": [".ply", ".pcd"],
          "x-maxSizeBytes": 52428800,
        },
        confidence: { type: "number", default: 0.5 },
      },
    },
    output_schema: {
      type: "object",
      properties: {
        instances: { type: "string", format: "file" },
        count: { type: "integer" },
      },
    },
  };

  override async execute(
    inputs: Record<string, unknown>,
    context: ExecutionContext,
  ): Promise<Record<string, unknown>> {
    const cloudPath = inputs["point_cloud"] as string;
    const cloudData = readFileSync(cloudPath);
    const confidence = (inputs["confidence"] as number) ?? 0.5;

    const resultData = Buffer.from("Processed point cloud data...");
    const outputFile = context.outputPath("instances.ply");
    writeFileSync(outputFile, resultData);

    return { instances: outputFile, count: 42 };
  }
}

const app = new PointCloudSegmenter().createApp();
export default app;
```

---

## SDK Components

### WorkflowNodeManifest

Defines what a node is. Maps to the engine's **registry-level node type** (`WorkflowNodeManifest` in engine terminology).

**Required fields:** `slug`, `version`, `name`, `description`, `input_schema`, `output_schema`. Note: `id` is auto-derived from `slug` + `version` and must NOT be provided manually.

## CLI: register + probe (v0.28+)

```bash
canvastekk-workflow-sdk probe --manifest manifest.json
CANVASTEKK_REGISTRY_TOKEN=<token> canvastekk-workflow-sdk register \
  --manifest manifest.json --engine-url https://cwe.example.com \
  [--invoke-url URL] [--name-suffix -lambda]
```

Same vocabulary mapping, auth (`X-Service-Token`), and exit codes as the python
CLI. `probe` is fully offline. `GET /manifest` also serves `code_digest` (sha256
of the module calling `createNodeApp`, computed at startup, never author-settable).

**Versioning:** The `version` field is a semantic version string (e.g. `"1.0.0"`) validated against the X.Y.Z pattern. The engine enforces immutability: re-registering with the same version and changed data is rejected. Bump the version for any schema or metadata changes.

```typescript
import { WorkflowNodeManifest } from "canvastekk-workflow-sdk";

const definition: WorkflowNodeManifest = {
  slug: "my-node",
  version: "1.0.0",
  name: "My Node",
  description: "Does something useful",
  input_schema: {
    type: "object",
    properties: { input: { type: "string" } },
  },
  output_schema: {
    type: "object",
    properties: { output: { type: "string" } },
  },
  token_cost: 0.5,
  default_retry: { max_attempts: 3, initial_delay_ms: 1000 },
  category: "inference",
  timeout_seconds: 60,
  styles: { icon: "Brain", color: "emerald" },
};
```

Optional fields with defaults:

| Field | Default | Description |
|-------|---------|-------------|
| `token_cost` | `0` | Cost per execution |
| `default_retry` | `{ max_attempts: 1 }` | Retry policy |
| `category` | `"utility"` | Node category (`transform`, `inference`, `utility`, `control-flow`) |
| `timeout_seconds` | `30` | Max execution time |
| `styles` | `undefined` | Icon/color for UI |
| `deprecation` | `undefined` | Optional `DeprecationInfo` — advisory migration signal (RFC 9745/8594). Omitted from the registry payload when unset. Distinct from the registry's `node_status`; a deprecated node stays `active` until retired. |

### DeprecationInfo

Mark a node deprecated so workflow-definition authors get a migration signal.
`deprecation` is **additive metadata** — setting it does not change the node's
behavior and does not require a `major` version bump.

```typescript
import { WorkflowNodeManifestSchema, type DeprecationInfo } from "canvastekk-workflow-sdk";

const definition = WorkflowNodeManifestSchema.parse({
  slug: "floor-flatness-assessment",
  version: "1.4.2",
  // ...required fields...
  deprecation: {
    deprecated_at: "2026-08-01",                               // RFC 9745
    sunset_date: "2027-01-01",                                 // RFC 8594
    replacement_slug: "floor-flatness-per-check-assessment",
    migration_url: "https://docs.example.com/ff-migration",
    notice: "Use floor-flatness-per-check-assessment for per-check-type outputs.",
  } satisfies DeprecationInfo,
});
```

| Field | Default | Description |
|-------|---------|-------------|
| `deprecated_at` | `null` | Date deprecation took effect, ISO 8601 (RFC 9745) |
| `sunset_date` | `null` | Planned removal date, ISO 8601 (RFC 8594); `null` = no firm date |
| `replacement_slug` | `null` | Slug of the replacement node |
| `migration_url` | `null` | URL to migration docs (RFC 9745 §3 / RFC 8594 §6) |
| `notice` | *(required)* | Human-readable notice shown to workflow-def authors |

### ExecutionContext

Provided to `execute()` method:

```typescript
override async execute(
  inputs: Record<string, unknown>,
  context: ExecutionContext,
): Promise<Record<string, unknown>> {
  // Identifiers
  context.runId;    // "workflow-run-abc123"
  context.nodeId;   // "node-instance-456"

  // File outputs
  context.outputDir;                        // "/tmp/run-abc123/node-456"
  const outputFile = context.outputPath("result.json");

  // Logging
  context.logger.info("Processing started");

  // Progress reporting (0.0 - 1.0)
  context.reportProgress(0.5, "Halfway done");

  // Token usage (for LLM nodes)
  context.recordTokenUsage({ prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 });
  context.tokenUsage; // { prompt_tokens: 100, completion_tokens: 50, total_tokens: 150 }

  return {};
}
```

### Data Contracts

Standard data formats for passing structured data between nodes:

#### InstanceSet — Detected Objects

```typescript
import { InstanceSet, BoundingBox3D, getInstancesByClass } from "canvastekk-workflow-sdk";

const instanceSet: InstanceSetData = {
  contract_version: "1.0.0",
  instances: [
    {
      instance_id: 1,
      class_id: 4,
      class_name: "vent",
      confidence: 0.95,
      point_indices: [0, 1, 2, 3],
      centroid: { x: 100.0, y: 200.0, z: 50.0 },
      bounding_box: {
        min_point: { x: 80.0, y: 180.0, z: 30.0 },
        max_point: { x: 120.0, y: 220.0, z: 70.0 },
      },
    },
  ],
  class_names: ["floor", "ceiling", "wall", "door", "vent"],
  point_count: 10000,
  source_node: "segment",
};

const vents = getInstancesByClass(instanceSet, "vent");
```

#### MeasurementSet — Measurements

```typescript
import type { MeasurementSetData } from "canvastekk-workflow-sdk";

const measurements: MeasurementSetData = {
  contract_version: "1.0.0",
  measurements: [
    {
      name: "ceiling_height",
      value: 2800.0,
      unit: "mm",
      method: "plane_to_plane",
      confidence: 0.98,
      points: [{ x: 0, y: 0, z: 0 }, { x: 0, y: 0, z: 2800 }],
    },
  ],
  source_node: "measure",
};

const height = getValue(measurements, "ceiling_height"); // 2800.0
```

#### PlaneSet — Detected Planes

```typescript
import type { PlaneSetData } from "canvastekk-workflow-sdk";
import { getPlaneByLabel } from "canvastekk-workflow-sdk";

const planes: PlaneSetData = {
  contract_version: "1.0.0",
  planes: [
    { point: { x: 0, y: 0, z: 0 }, normal: { x: 0, y: 0, z: 1 }, label: "floor" },
    { point: { x: 0, y: 0, z: 2800 }, normal: { x: 0, y: 0, z: -1 }, label: "ceiling" },
  ],
  source_node: "plane_detect",
};

const floor = getPlaneByLabel(planes, "floor");
```

#### Serialization

```typescript
import { saveJson, loadJson } from "canvastekk-workflow-sdk";

// Save to JSON
saveJson(instanceSet, "output.json");

// Load from JSON
const loaded = loadJson("output.json");
```

---

## Deploying a Node

### Node.js (Production)

```bash
# Development
npx tsx handler.ts

# Production (compiled)
PORT=8001 node dist/handler.js
```

### Docker

```dockerfile
FROM node:24-slim

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci --omit=dev

COPY dist/ ./dist/

EXPOSE 8001

CMD ["node", "dist/handler.js"]
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
      - CANVASTEKK_LOG_LEVEL=info
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

```typescript
import { describe, it, expect } from "vitest";
import { UppercaseNode } from "./handler.js";
import type { NodeExecutionRequest } from "canvastekk-workflow-sdk";

describe("UppercaseNode", () => {
  it("converts text to uppercase", async () => {
    const node = new UppercaseNode();
    const response = await node.run({
      run_id: "test-run",
      node_id: "test-node",
      inputs: { text: "hello" },
    });

    expect(response.status).toBe("pass");
    expect(response.outputs).toEqual({ result: "HELLO" });
    expect(response.duration_ms).toBeGreaterThanOrEqual(0);
  });

  it("fails on missing required input", async () => {
    const node = new UppercaseNode();
    const response = await node.run({
      run_id: "test-run",
      node_id: "test-node",
      inputs: {},
    });

    expect(response.status).toBe("fail");
    expect(response.error_type).toBe("NodeValidationError");
    expect(response.error_code).toBe("VALIDATION_ERROR");
  });
});
```

### Integration Testing with Supertest

Test the full HTTP stack:

```typescript
import { describe, it, expect } from "vitest";
import request from "supertest";
import { app } from "./handler.js";

describe("UppercaseNode API", () => {
  it("executes via POST /execute", async () => {
    const res = await request(app)
      .post("/execute")
      .send({ run_id: "test", node_id: "n1", inputs: { text: "hello" } });

    expect(res.status).toBe(200);
    expect(res.body.status).toBe("pass");
    expect(res.body.outputs.result).toBe("HELLO");
  });

  it("returns health status", async () => {
    const res = await request(app).get("/health");
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("healthy");
  });

  it("returns manifest", async () => {
    const res = await request(app).get("/manifest");
    expect(res.status).toBe(200);
    expect(res.body.name).toBe("uppercase");
  });
});
```

### Running Tests

```bash
# From typescript/ directory
npm test

# Watch mode
npm run test:watch

# Specific test file
npx vitest run tests/my-node.test.ts
```

---

## Registry & Registration

The SDK provides utilities for registering nodes with the CanvasTEKK Workflow Engine registry.

### `registerNode()`

Register a node with the workflow engine registry:

```typescript
import { registerNode } from "canvastekk-workflow-sdk";

const node = new MyNode();
const result = await registerNode(node, {
  registryUrl: "https://engine.example.com/api/workflows/nodes/",
  invokeUrl: "https://my-node.example.com",
  serviceToken: "svs_your-token-here",
  tags: ["category:utility", "team:platform"],
});

console.log(result.action);      // "created"
console.log(result.revision_id); // "rev-abc123"
```

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `node` | `BaseNode` | Yes | The node instance to register |
| `registryUrl` | `string` | Yes | Engine registry endpoint |
| `invokeUrl` | `string` | No | URL where the node is reachable |
| `invokeType` | `InvokeType` | No | `"http"`, `"lambda"`, `"sagemaker"`, or `"in-process"` (default: `"http"`) |
| `apiKey` | `string` | No | API key auth (`X-API-Key` header) |
| `serviceToken` | `string` | No | CI/CD auth (`X-Service-Token` header, takes precedence) |
| `tags` | `string[]` | No | Searchable tags for the registry |

### `exportDefinition()`

Export a `WorkflowNodeManifest` as a registry-compatible JSON file:

```typescript
import { exportDefinition } from "canvastekk-workflow-sdk";

const path = exportDefinition(node.definition, "node-manifest.json", {
  invokeUrl: "https://my-node.example.com",
  tags: ["ci-cd"],
});
```

---

## Workflow Builder & Local Runner

Build, validate, and test-run workflow DAGs locally — without the engine, Temporal, S3, or distributed orchestration.

### Quick Start

```typescript
import {
  WorkflowBuilder,
  WorkflowRunner,
  InProcessExecutor,
} from "canvastekk-workflow-sdk";

// Build a workflow
const spec = await new WorkflowBuilder()
  .addStart("start", { outputs: ["point_cloud"] })
  .addNode("segment", { slug: "segmentation-v1.0.0", inputs: { method: "dbscan" } })
  .addNode("measure", { slug: "measurement-v1.0.0" })
  .addEnd("end")
  .connect("start", "segment", { fromOutput: "point_cloud", toInput: "input_file" })
  .connect("segment", "measure", { fromOutput: "instances", toInput: "instance_set" })
  .connect("measure", "end", { fromOutput: "measurements", toInput: "result" })
  .build(); // validates the DAG

// Test run locally
const executor = new InProcessExecutor();
executor.register("segmentation-v1.0.0", {
  execute: async (inputs, ctx) => ({ instances: "processed" }),
});
executor.register("measurement-v1.0.0", {
  execute: async (inputs, ctx) => ({ measurements: "measured" }),
});

const runner = new WorkflowRunner(executor);
const result = await runner.run(spec, { point_cloud: "/data/scan.las" });

console.log(result.status);          // "completed" or "failed"
console.log(result.final_outputs);    // { result: ... }
console.log(result.duration_ms);      // total execution time
```

### WorkflowBuilder

Fluent API for constructing workflow definitions. All methods return `this` for chaining (except `build()`).

#### `addStart(nodeId, opts?)`

Add a START node (workflow entry point). Exactly one allowed.

```typescript
builder.addStart("start", { outputs: ["point_cloud", "metadata"] });
```

If `outputs` is provided (array of field names), sets `config_schema` with string properties for each field.

#### `addEnd(nodeId)`

Add an END node (workflow terminal). Multiple allowed.

#### `addNode(nodeId, opts)`

Add a user node with a registry slug reference. Slug `"__start__"` and `"__end__"` are reserved.

```typescript
builder.addNode("segment", { slug: "segmentation-v1.0.0", inputs: { method: "dbscan" } });
```

#### `connect(fromNode, toNode, opts?)`

Add an edge connecting two nodes. Validates that both node IDs exist and rejects self-loops (`fromNode === toNode`).

```typescript
builder.connect("start", "segment", {
  fromOutput: "point_cloud",
  toInput: "input_file",
});
```

#### `build(opts?)`

Construct the `WorkflowSpec`. If `validate` is not `false`, validates the graph and throws `WorkflowValidationError` on failure.

### NodeExecutor Strategy

#### `InProcessExecutor` — Direct Execution

```typescript
import { InProcessExecutor } from "canvastekk-workflow-sdk";

const executor = new InProcessExecutor();
executor.register("segmentation-v1.0.0", {
  execute: async (inputs, ctx) => ({ result: "done" }),
});
```

#### `HttpExecutor` — HTTP Calls

```typescript
import { HttpExecutor } from "canvastekk-workflow-sdk";

const executor = new HttpExecutor();
executor.registerUrl("segmentation-v1.0.0", "http://localhost:8001");
executor.registerUrl("measurement-v1.0.0", "http://localhost:8002");
```

### WorkflowRunner

```typescript
import { WorkflowRunner } from "canvastekk-workflow-sdk";

const runner = new WorkflowRunner(executor, { errorPolicy: "fail_fast" });
const result = await runner.run(spec, { point_cloud: "/data/scan.las" });
```

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `executor` | `NodeExecutor` | required | Execution strategy |
| `errorPolicy` | `"fail_fast" \| "continue"` | `"fail_fast"` | `fail_fast` stops on first error; `continue` runs all levels |

### WorkflowRunResult

| Field | Type | Description |
|-------|------|-------------|
| `status` | `"completed" \| "failed"` | Overall workflow status |
| `final_outputs` | `Record<string, unknown>` | Outputs collected from END nodes |
| `node_results` | `NodeResult[]` | Per-node execution results |
| `duration_ms` | `number` | Total execution time |
| `output_dir` | `string \| null` | Output directory path |

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

| Type | When it fires |
|------|--------------|
| `DEFAULT` | Always fires on successful execution |
| `SUCCESS` | Fires only on success result |
| `FAILURE` | Fires only on failure result |
| `CONDITIONAL` | Fires based on condition expression |

### Resolution Strategies

How `fromOutput` is resolved against source node outputs:

| Strategy | Behavior |
|----------|----------|
| `AUTO` | Default strategy — flat key lookup first (for ALL keys including dotted ones); dot-path traversal as fallback; throws `ResolverError` if not found |

`ResolverError` is a typed error with a discriminating `code` field (`NODE_NOT_FOUND`, `KEY_NOT_FOUND`, `INVALID_PATH`, `TRAVERSAL_ERROR`) and optional `nodeId` for programmatic error handling.

### Naming Convention Table

| Artifact | Name | Parent Concept |
|----------|------|----------------|
| Node registration manifest | `WorkflowNodeManifest` | `WorkflowNodeRegistry` (engine) |
| Workflow DAG | `WorkflowDefinition` | — |
| Node in DAG | `WorkflowDefinitionNode` | `WorkflowDefinition` |
| Edge in DAG | `WorkflowEdgeDefinition` | `WorkflowDefinition` |
| Full spec | `WorkflowDefinitionSpec` | `WorkflowDefinition` |

### Wire-Format Convention (snake_case)

The TypeScript SDK uses a **dual-layer naming convention**:

- **Builder API** (`connect()`, `addNode()`, etc.) uses **camelCase** parameters — idiomatic TypeScript
- **Wire-format types** (`WorkflowEdgeDefinition`, `Instance`, `BoundingBox3D`, etc.) use **snake_case** fields — matching the Python SDK and the CanvasTEKK Workflow Engine's `SaveWorkflowRequest.spec` schema

The builder translates camelCase API parameters to snake_case wire-format objects automatically. This ensures workflow definitions built with the TS SDK are accepted by the engine and interoperate with Python nodes.

### Migration Guide: Field Renames (0.13.0 → 0.16.0)

Exported TypeScript interfaces renamed their fields from camelCase to snake_case for engine wire-format compatibility. If you access these fields directly, update your code:

#### `WorkflowEdgeDefinition`

| Old Field | New Field |
|----------|-----------|
| `fromNode` | `from_node` |
| `toNode` | `to_node` |
| `fromOutput` | `from_output` |
| `toInput` | `to_input` |
| `edgeType` | `edge_type` |

#### `Instance`

| Old Field | New Field |
|----------|-----------|
| `instanceId` | `instance_id` |
| `classId` | `class_id` |
| `className` | `class_name` |
| `pointIndices` | `point_indices` |

#### `InstanceSetData`

| Old Field | New Field |
|----------|-----------|
| `classNames` | `class_names` |
| `pointCount` | `point_count` |
| `semanticLabels` | `semantic_labels` |
| `instanceLabels` | `instance_labels` |

#### `BoundingBox3D`

| Old Field | New Field |
|----------|-----------|
| `minPoint` | `min_point` |
| `maxPoint` | `max_point` |

> **Note:** The `WorkflowBuilder.connect()` method API is unchanged — it still accepts camelCase parameters (`fromOutput`, `toInput`, `edgeType`). Only the resulting wire-format objects use snake_case.

---

Old names are preserved as type aliases and continue to work:

| Old Name | Current Name |
|----------|-------------|
| `WorkflowNodeManifest` | `WorkflowNodeManifest` |
| `WorkflowWorkflowNodeManifest` | `WorkflowNodeManifest` |
| `WorkflowNode` | `WorkflowDefinitionNode` |
| `WorkflowEdge` | `WorkflowEdgeDefinition` |
| `WorkflowSpec` | `WorkflowDefinitionSpec` |

### New Fields on `WorkflowDefinitionNode`

| Field | Type | Description |
|-------|------|-------------|
| `workflow_node_id` | `string` (optional) | Optional custom node identifier |
| `config_schema` | `Record<string, unknown>` (optional) | Additional configuration schema for the node |

### `role` Field

Nodes have a `role` field from the `WorkflowNodeRole` type that determines their position in the workflow:

```typescript
type WorkflowNodeRole = "start" | "end" | "error_gate" | "operation";
```

Defaults to `"operation"`. Set via the builder (`addStart`/`addEnd`) or manually.

---

## Structured Logging

The SDK provides production-ready structured logging out of the box. Configured automatically at app startup.

### Environment Variables

| Variable | Default | Values | Description |
|----------|---------|--------|-------------|
| `CANVASTEKK_LOG_FORMAT` | `json` | `json`, `text` | `json` = one JSON object per line (CloudWatch/Datadog/ELK). `text` = human-readable for local dev. |
| `CANVASTEKK_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARN`, `ERROR` | SDK-wide log level. |

### Using the Logger in `execute()`

```typescript
override async execute(
  inputs: Record<string, unknown>,
  context: ExecutionContext,
): Promise<Record<string, unknown>> {
  context.logger.info("Processing started");

  // With extra structured fields
  context.logger.info({ file_size_bytes: 1200000, file_name: "scan.ply" }, "File downloaded");

  return { result: "done" };
}
```

---

## Authentication

The SDK provides three authentication middleware layers:

### API Key

```typescript
import { NodeAuth } from "canvastekk-workflow-sdk";

const app = node.createApp({
  dependencies: [NodeAuth.apiKey()],
});
```

The middleware reads the key from the `CANVASTEKK_API_KEY` environment variable. Set `CANVASTEKK_DEV_MODE=true` to bypass auth during development.

During a rotation window, `CANVASTEKK_API_KEY_NEXT` is accepted alongside the
current key (empty = ignored). Python `NodeAuth.apiKey()` behaves identically
via `<key_env_var>_NEXT`.

### JWT

```typescript
const app = node.createApp({
  auth: NodeAuth.jwt({ secret: "your-jwt-secret" }),
});
```

### Keycloak

Uses RS256 JWT validation with JWKS key fetching. When a token's `kid` header doesn't match any cached key, the SDK force-refreshes the JWKS cache once before rejecting — this handles Keycloak key rotation gracefully without a service outage window.

> **Note:** Only JWK keys containing an `x5c` (X.509 certificate chain) field are supported. If your Keycloak realm issues non-x5c keys, consider migrating to the `jose` library.

```typescript
const app = node.createApp({
  auth: NodeAuth.keycloak({ serverUrl: "https://keycloak.example.com", realm: "my-realm" }),
});
```

---

## Multi-Node App

Host multiple nodes behind a single Express server:

```typescript
import { createMultiNodeApp } from "canvastekk-workflow-sdk";

const app = createMultiNodeApp([new NodeA(), new NodeB(), new NodeC()]);
export default app;
```

Each node is mounted at `/node/{node-name}`.

---

## Advanced: Middleware and Health Checks

### Custom Middleware

```typescript
import type { NodeMiddleware, ExecutionContext } from "canvastekk-workflow-sdk";

const auditMiddleware: NodeMiddleware = {
  onBeforeExecute(inputs, context) {
    context.logger.info(`Audit: execution started for ${context.nodeId}`);
    return inputs;
  },
  onAfterExecute(inputs, outputs, context, durationMs) {
    context.logger.info(`Audit: completed in ${durationMs}ms`);
  },
  onError(inputs, error, context, durationMs) {
    context.logger.error(`Audit: failed: ${error}`);
  },
};

node.addMiddleware(auditMiddleware);
```

### Custom Health Checks

Override `healthCheck()` to report on external dependencies:

```typescript
class ModelInferenceNode extends BaseNode {
  // ...
  override healthCheck(): Record<string, boolean> {
    return {
      model_loaded: this.model !== null,
      gpu_available: this.checkGpu(),
    };
  }
}
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Server port |
| `CANVASTEKK_OUTPUT_DIR` | `/tmp` | Base output directory |
| `CANVASTEKK_DEV_MODE` | `false` | Enable development mode |
| `CANVASTEKK_LOG_LEVEL` | `INFO` | Log level |
| `CANVASTEKK_LOG_FORMAT` | `json` | Log format (`json` or `text`) |

---

## Philosophy

The SDK is a convenience layer, not a hard dependency. Nodes can "eject" by copying SDK code if true independence is needed.

---

## Releasing

Releases are automated via [git-cliff](https://git-cliff.org/) based on conventional commits. See the [Python README](../python/README.md#releasing) for the full release workflow details.

The TypeScript package version lives in `typescript/package.json` and is published to GitHub Packages under `@nus-cee`.
