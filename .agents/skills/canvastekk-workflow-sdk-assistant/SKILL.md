---
name: canvastekk-workflow-sdk-assistant
description: Answer any question about the CanvasTEKK Workflow SDK, enforce the node contract when creating nodes, and audit existing nodes — SDK version, dependencies, manifest change classification, and minimum-requirement conformance. Use for "create a node using FastAPI", "review/audit my node", or any SDK how-do-I question.
license: Apache-2.0
---

# canvastekk-workflow-sdk-assistant

Entry point for the CanvasTEKK Workflow SDK. I answer SDK questions, gate node
creation on the contract, and audit existing nodes. I do not carry the deep
code-generation templates — those live in the sibling skills (below).

## Mode dispatch

| Request sounds like | Mode | Do this |
|---------------------|------|---------|
| "create/build a node …" (any framework — FastAPI, Flask, …) | **CREATE** | §The contract + §CREATE, then load `canvastekk-node-builder` (+ `canvastekk-node-patterns` for domain examples) |
| "review my node", "audit my dependencies", "what changed", "am I on the latest SDK" | **AUDIT** | §AUDIT checklist, report PASS/FAIL |
| any other SDK how-do-I question | **ANSWER** | §Quick reference; point into the sibling skills for depth |

Sibling skills (load on demand — never preload both for a question):
`canvastekk-node-builder` (7-step creation workflow, templates, tests),
`canvastekk-node-patterns` (10 domain code examples).

## The contract (non-negotiable minimums)

Every node must satisfy ALL of these before it is done. State each check when
gating a creation; each row is a hard failure, not a style note.

**Manifest (`WorkflowNodeManifest`) — required fields**

| Field | Rule |
|---|---|
| `slug` | lowercase hyphens (`point-cloud-segment`) |
| `version` | semver (`1.0.0`); same version + any change = rejected by the registry — bump for every change |
| `name` | human-readable title |
| `description` | what the node does, one or two sentences |
| `input_schema` / `output_schema` | JSON Schema Draft 7, `type: "object"` |
| `category` | one of `transform`, `inference`, `utility`, `control-flow` |

**Schema rules (file I/O is URL-based, not binary)**

- File fields: `"type": "string", "format": "file"` — NEVER `format: "binary"`, NEVER `type: "object"`/`"array"` (the SDK's validator rejects both).
- Every file input carries `"x-accept": [".ext", …]` and `"x-maxSizeBytes": <int>` — the SDK auto-validates downloads against them.
- `"description"` on every property; required inputs listed in `"required"`.

**Structure rules**

- `definition` is a module-level variable AND a class attribute on the `BaseNode` subclass (module level enables CLI validation; class attribute satisfies `BaseNode.__init_subclass__`).
- `app = MyNode().create_app()` at module level (uvicorn target `handler:app`).
- `execute(self, inputs: dict, context: ExecutionContext) -> dict` implemented; returns a dict matching `output_schema`.

**Offline gate (must exit 0 before "done")**

```bash
python -m canvastekk_workflow_sdk validate handler:definition
```

## CREATE — dependency decision (single source of truth)

Default install is the **base package** — it covers defining, validating,
locally test-running, and registering nodes. Add extras only per the table;
never install an extra "just in case".

| You are doing | Install | Why |
|---|---|---|
| Defining / validating / testing a node, building workflows locally, registering via `register_node` | `canvastekk-workflow-sdk` | Base install is complete for everything except serving HTTP |
| Serving the HTTP contract through the SDK (`create_node_app` / `create_app()`) | `canvastekk-workflow-sdk[fastapi,serve]` | Since SDK 0.43 the base install ships without fastapi; `[serve]` adds uvicorn |
| Hosting the routes yourself (any web framework you already use) | base + your framework | The SDK validates/verifies/registers; it never serves |
| `NodeAuth.jwt()` | `[jwt]` | Adds PyJWT |
| `NodeAuth.keycloak()` | `[keycloak]` | Adds PyJWT + cryptography |

Rung selection: **SDK-served** (recommended — the SDK mounts the contract for
you), **self-hosted** (you serve the routes; the SDK still
validates/verifies/registers), or **no HTTP** (in-process; engine-admin-gated,
not a public surface). After picking the rung and the dependency line, load
`canvastekk-node-builder` and generate the code; finish at the offline gate
above. A node is done only when the contract section passes in full.

## AUDIT — checklist

Run each check; report a PASS/FAIL table with the fix for every FAIL.

1. **SDK version currency** — `pip show canvastekk-workflow-sdk` (or the
   `X-SDK-Version` response header / `sdk_version` in `GET /manifest` on a
   deployed node) vs the latest release on GitHub Releases. Old major →
   plan an upgrade; the SDK warns at import when past its support horizon.
2. **Dependency audit** — read `pyproject.toml`/requirements; cross-check
   extras against what the handler actually imports (uses `create_app`/
   `create_node_app` → `[fastapi]` needed; runs uvicorn → `[serve]`;
   `NodeAuth.jwt` → `[jwt]`; `NodeAuth.keycloak` → `[keycloak]`). Flag
   missing extras (import crashes) and unused extras (cost).
3. **Change review** — classify what changed between versions:
   ```bash
   python -m canvastekk_workflow_sdk export_definition handler:definition --output new.json
   python -m canvastekk_workflow_sdk diff old.json new.json
   ```
   Exit 0 clean · 1 breaking/errors · 2 load failure. Breaking (removed
   output, newly required input) needs a MAJOR bump; same version + any
   change is an error; node name changed → publish a new node instead.
4. **Conformance** — `validate` (exit 0), the node's test suite, and on a
   deployed node `python -m canvastekk_workflow_sdk verify <invoke_url>
   [--api-key …] [--dry-run]` probing the served contract.

## Quick reference (ANSWER mode)

**Install (public repo — no auth needed for the wheel from GitHub Releases;
GitHub Packages needs a PAT with `read:packages`):**
`pip install canvastekk-workflow-sdk` — see the repo README for both paths.

**Auto-served endpoints** (`create_app()` mounts all of these):

| Route | Purpose |
|---|---|
| `POST /execute` | run business logic (inputs validated against `input_schema`) |
| `GET /health` | calls your `health_check()` |
| `GET /manifest` | self-description; `sdk_version`/`mode` are injected — never set them |
| `POST /hook` | webhook; 501 unless you override `hook()` |
| `GET /metrics` | execution statistics |
| `GET /live` · `GET /ready` | Kubernetes liveness/readiness |

**`ExecutionContext` in `execute()`**: `run_id`, `node_id`,
`output_path(name)` for files, `logger`, `report_progress(0..1, msg)`,
`record_token_usage(…)`, `metadata` (download facts per file field).

**File inputs/outputs**: inputs arrive as local paths (the SDK downloads the
presigned URLs and validates against `x-*` first); outputs are written with
`context.output_path(...)` and returned as `str(path)` — the SDK uploads them
via the engine-minted session. Never slice/inspect upload targets.

**Registration** (CI/CD): `register_node(node, registry_url=…,
invoke_url=…, invoke_type="http", service_token=…, verify=True)` — `verify`
probes the served contract first; failures raise before anything registers.
Exactly one of `service_token`/`api_key` for registry auth; `api_key` is also
what the verify probes send to an api-key-guarded node.

**Env vars**: `CANVASTEKK_NODE_ENV` (`dev`/`uat`/`production` → manifest
`mode`), `CANVASTEKK_LOG_LEVEL`, `CANVASTEKK_LOG_FORMAT`
(`console`/`json`), `CANVASTEKK_API_KEY` / `CANVASTEKK_JWT_SECRET` /
`CANVASTEKK_KEYCLOAK_*` (only when the matching auth is configured),
`CANVASTEKK_DEV_MODE` (auth bypass — never in production).

**Versioning**: node `version` is semver and immutable per version — the
registry rejects a changed manifest under the same version; breaking changes
require MAJOR.

Deep mechanics (full API reference, templates, tests, Dockerfile):
`canvastekk-node-builder`. Domain examples (point clouds, measurement,
inference, auth, middleware, webhooks): `canvastekk-node-patterns`.
