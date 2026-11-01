# ADR: Node-Service Layout & Bootstrap (the layered standard)

**Status:** accepted (sdk#220, 2026-10-31) · **Supersedes:** ad-hoc per-repo bootstrap · **Normative for:** every deployable node service (CLS #448/#449, CWN apps, future)

## The layout

One deployable service = one package with fixed layers. Dependencies point
downward only:

```
<service>_app/
├── node/          # CW node surface (BaseNode subclass + manifest + execute)
│   ├── handler.py
│   └── app.py     # create_authed_app() / mount_node() wiring ONLY
├── api/           # the service's own HTTP routes (its lane/consumer face)
├── faces/         # hosting adapters (same image, different entry)
│   ├── asgi.py            # compose/local: uvicorn faces.asgi:app
│   └── lambda_handler.py  # SDK create_lambda_handler(app) — dual dispatch
├── domain/        # transport-agnostic core — imports NO fastapi, NO SDK
├── integrations/  # outbound clients (engine, CDS, S3, …)
├── cli/           # service-specific extras (configs, plugins) — image content
├── tests/         # mirrors the tree 1:1
└── Dockerfile     # ONE image; entrypoint selects the face
```

**The rule:** `faces → {node, api} → domain ← integrations`. `domain` imports
neither FastAPI nor this SDK; only `node/`, `api/`, and `faces/` may. Anything
contentious becomes a placement question with a mechanical answer:

| Question | Answer |
|---|---|
| New route? | serving the engine → `node/`; serving your own consumers → `api/` |
| Mangum / RIE / uvicorn | never in logic — always `faces/` |
| Turn execution, workspace round-trips | `domain/` |
| Calls to engine/CDS/auth | `integrations/` |
| CLI configs + plugins | `cli/` |

## The bootstrap (canonical, SDK-owned)

```python
from canvastekk_workflow_sdk import create_authed_app, mount_node, create_lambda_handler
```

- **`create_authed_app(node, *, legacy_key_env_var=None, **kwargs)`** — the
  canonical authed factory: `create_node_app` + `NodeAuth.central()`.
  Central-only by default (`legacy_key_env_var=None`): greenfield services are
  secretless by construction. Existing fleets pass their key env var during a
  dual-accept window; retirement (#3838 shape) is env removal, not code change.
- **`mount_node(root_app, node, *, prefix="/node", …)`** — dual-purpose
  services: your own routes on the root app, the node sub-app mounted under
  `prefix` with its auth boundary intact.
- **`create_lambda_handler(app, *, plain_event)`** — the serverless face:
  structurally-HTTP events dispatch through Mangum onto `app`; plain events
  route to the supplied dispatcher. Python-only (see Parity).

Normative token contract: `NODE-TOKEN-CONTRACT.md` (this factory is the
blessed `create_node_app` wrapper named there).

## Engine-contract decisions (evidence: canvastekk-workflow-engine dev 2026-10-31)

### D1 — Serverless node health (lambda-hosted nodes)

Engine behavior: `GET /api/workflows/nodes/{name}/health` proxies the node's
`/health` on demand with `httpx timeout=5.0` + `raise_for_status`
(`fastapi_app/api/v2/workflows/nodes/router.py:511`); manifest verification is
a separate on-demand cross-check of `/manifest` (`verify_node`, :454). There
is no background health loop. In-process nodes (no `invoke_url`) report
healthy without probing.

**Decision:** lambda-hosted nodes register WITH `invoke_url` and serve
`/health` + `/manifest` from the composite app (both are cheap routes after
cold start). Probes are operator-triggered, so cold-start exposure is bounded
to probe time, and a 5s probe timeout against a cold lambda URL is an
acceptable, understood failure mode — retry after warm-up succeeds.
**Recommendation to engine (follow-up, not blocking):** accept a per-node
health-probe timeout override in `invoke_config` before fleet-scale lambda
nodes make cold-start probes routine. No SDK change.

### D2 — Long-run execution (turns up to 840s)

Engine behavior: BOTH semantics are engine-native today.
(a) **Blocking:** `execute_http_node` honors a per-node registry
`timeout_seconds` (overrides `NODE_HTTP_TIMEOUT_SECONDS`)
(`fastapi_app/temporal/activities.py:655`).
(b) **Async park (DA-3228):** a node's `/execute` may answer
`{"mode": "async", "execution_id", "s3_pointers"}`; the workflow parks on
`workflow.wait_condition(timeout=timeout_seconds)`
(`workflows.py:2098`), stamps the progress row via `record_async_park`
(`activities.py:502`) so the reconciler distinguishes parked from orphaned,
and resumes on the callback signal.

**Decision:** v1 lambda-hosted nodes use **blocking** `/execute` — the
Function URL timeout ceiling (≤900s) accommodates the 840s turn ceiling, and
the node registers with `timeout_seconds ≥ 960`. The async-park mode is the
documented escape hatch for anything that outgrows URL limits — it needs NO
engine change and NO new SDK surface (it is a response-shape convention).
Run-id polling by the node is rejected: the engine pattern is callback-signal
parking, not node-side polling.

## Parity (python + TypeScript)

The SDK ships both stacks in the same change. `create_authed_app` and
`mount_node` (express sub-app mount) ship in both. `create_lambda_handler` is
**python-only** — Mangum and the Lambda Runtime API are python-runtime
concerns; the TS side documents this exception beside its factory.
