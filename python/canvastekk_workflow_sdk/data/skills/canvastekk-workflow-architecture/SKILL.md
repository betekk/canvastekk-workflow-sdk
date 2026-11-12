---
name: canvastekk-workflow-architecture
description: >-
  The CanvasTEKK workflow system model — definition/run/node-registry
  lifecycles, the manifest HTTP contract, dry-run law, and the verification
  pipeline (registration gate, activation pre-flight, health sweep, re-verify).
  Triggers: how do workflows run, node lifecycle, registry states, dry-run
  rules, who can trigger runs, registration 403, contract conformance. For
  building a node, load canvastekk-node-builder instead.
license: Apache-2.0
compatibility: opencode
category: architecture
---

## What I do

I hold the as-built system model of the CanvasTEKK workflow plane: how
definitions, runs, and the node registry live and die, what the node HTTP
contract guarantees, and how each class of caller authenticates a run. Load
me when the question spans the system — a single node's authoring belongs to
`canvastekk-node-builder`, deep auth law to `canvastekk-auth-architecture`,
identity/standing to `access-gating`.

Canonical sources (a mismatch is a doc bug — fix the doc or the code, never
carry both): engine `fastapi_app/docs/node-http-contract.md` (contract spec),
`node-health-sweep-runbook.md` (sweep), SDK `docs/dry-run-contract.md`
(normative dry-run), SDK `conformance.py` (probe behavior).

## The three planes

```
DEFINITION  draft → active → deprecated → retired
            (restore: retired → active re-validates; drifted = degraded until upgrade-nodes re-pins)

RUN         pending → running → completed | failed | cancelled
            created by a trigger (below), attributed at creation, immutable after

NODE        active → inactive (degraded, sweep-marked) → dead (re-verify verdict only)
            retired (unregister door — never set by sweep or re-verify)
            + verified: tri-state column — true | false | NULL (= legacy/grandfathered)
```

**Manifest is the source of truth.** A node's manifest (name, version,
schemas, `contract`) is the single declaration; everything the engine and
verifiers do derives from it. Registered rows are immutable — changed data
requires a new version; the engine resolves `is_latest` for execution.

## The contract (manifest `contract` field)

```json
{
  "contract": {
    "transport": "http",
    "routes": ["/execute", "/health", "/manifest"],
    "capabilities": { "dry_run": true },
    "openapi": "3.2"
  }
}
```

- Closed route vocabulary: `/execute` `/health` `/manifest` `/hook`
  `/metrics` `/live` `/ready` `/openapi`. Minimum set: execute + health +
  manifest.
- A declared-but-unserved route **fails registration** — the engine probes
  every declared route.
- `capabilities.dry_run` absent ⇒ a dry-run request MUST be refused with
  `DRY_RUN_NOT_SUPPORTED` — never silently executed.

### Status-code law: mounted-and-routing

| Probe sends | Passes when |
|---|---|
| `GET /manifest` | 200 + parseable manifest covering declared routes |
| `POST /execute {"unexpected":"probe"}` | 4xx (a 200 means the node executes junk) |
| Presence probe per route | not 404, not 5xx (401/403 pass — an auth wall is not absence) |
| Positive dry-run (capability declared only) | 2xx + `status: "pass"` |

## Dry-run law

A dry run MUST: validate inputs fully, echo `dry_run: true`, keep
`token_usage: 0.0`. MUST NOT: invoke the handler, do file I/O, upload, bill,
or mutate state. The branch sits AFTER input validation, BEFORE any side
effect — position is the guarantee.

## The verification pipeline (when each gate runs)

```
register (POST /api/workflows/nodes/)
  └─ REGISTRATION GATE — full conformance probe per declared route
       fail → refuse registration, per-route report
activate a definition version (or upgrade-nodes)
  └─ PRE-FLIGHT — positive dry-run on the version's nodes
       fail → block activation (asgard force overrides)
periodic (infra cron → POST /api/internal/nodes/health-sweep, X-Service-Token)
  └─ SWEEP — contract-declarers: full probe; legacy: manifest reachability
       pass on inactive → heals to active
       fail → inactive (never dead off a sweep); changed-status writes only
       degraded node logs ERROR "node health DEGRADED" — the alert anchor
on demand (operator/alert → POST /api/internal/nodes/{slug}/re-verify)
  └─ DEAD-VERDICT GATE — full probe + positive dry-run
       pass → active (resurrection)   fail → dead
```

A flapping node is never declared dead off one sweep miss: `dead` requires
the deeper on-demand re-verify.

## Registration law (who may write to the registry)

- **POST registration is owner-scoped** — any authenticated caller registers
  new versions of nodes it owns. No admin needed.
- **Admin-gated seams** (platform-admin JWT, or the dated bridge flag
  `registry_service_token_admin`): `invoke_type="in-process"`, and PATCHing
  the sensitive fields `invoke_url` / `invoke_type` / `node_status`.
- **Deploy pipelines re-register as a new version** carrying the fresh
  invoke URL — never PATCH `invoke_url`. A failed deploy then leaves the
  previous version `is_latest` (no drain possible).
- `is_system` derives from owner/source (first-party vs external); external
  `ctk_` key registration stamps a per-key synthetic owner — not system.

## Invocation flows per caller

| Caller | Credential | Run attribution |
|---|---|---|
| CFE (user clicks Run) | session JWT passthrough + `X-Account-Id` | kind=user, actor=the user |
| CDS / CLS (delegated service) | token exchange → `sub`=user, `azp`=service | kind=user, actor=user, on-behalf-of=service |
| CI / deploy pipeline | `X-Service-Token` (svc identity) | kind=service, system |
| External author (future) | `Authorization: Bearer ctk_...` (CDS-validated key) | key-bound account |

Attribution columns (actor, on-behalf-of, kind, account) are written at run
creation and are read-side immutable — usage and audit read from the row.

## Decision shortcuts

- "Why did registration 403?" → it is never the POST; look for an admin seam
  (in-process type, sensitive-field PATCH) or a missing entitlement.
- "Node went inactive overnight?" → the sweep marked it; check the
  `node health DEGRADED` log, fix, then re-verify — never hand-flip status.
- "Can I PATCH the invoke URL after a Lambda redeploy?" → no; register the
  new version. Immutability is the model.
- "Does my node need dry-run?" → declare `capabilities.dry_run: true` only
  if you can honor the MUST/MUST-NOT law above; pre-flight depends on it.

## Cross-refs (never duplicated here)

- `canvastekk-node-builder` — SDK node authoring, templates, validation CLI
- `canvastekk-node-patterns` — domain code examples (point clouds, models)
- `canvastekk-auth-architecture` — auth matrix deep-dive, token exchange
- `access-gating` — the identity/standing decision tree
