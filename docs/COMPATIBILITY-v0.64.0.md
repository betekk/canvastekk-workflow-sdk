# Workflow SDK v0.64.0 — Consumer Compatibility Report

**Ticket:** betekk/canvastekk-workflow-sdk#244 · **Parent:** betekk/canvastekk-tracker#4211
**Report base:** tag `v0.64.0` (= merge `2d54486` of #241; content parent dev `872c6c7`)
**Date:** 2026-11-11 · **Verdict: ✅ compatible — no SDK change required, no release needed.**

## 1. Verdict

`v0.64.0` is a drop-in upgrade for node code from `v0.61.0`. The entire
`v0.61.0 → v0.64.0` delta (`git diff --stat v0.61.0 v0.64.0 -- python/ typescript/`,
19 files) touches **no node-facing contract file**: `base.py`, `app.py`,
`definition.py`, `contracts.py`, `base-node.ts`, `definition.ts`, `contracts/`
are byte-identical between the two tags. The delta is:

| Area | Change | Release |
|------|--------|---------|
| Registry credentials | `ctk_` API keys are now the **only** accepted credential — offline validation rejects legacy `X-Service-Token` / `X-API-Key` outright (engine retired them, #3760; DA-1948 shape) | #239/#240 |
| CLI | `ctk` bin alias on both lanes (`pyproject [tool.poetry.scripts]` + npm `bin`) | #239 |
| CLI | Pre-flight **registry diff** in `ctk probe` (python #235, TS `--engine-url` #237) | v0.62/v0.63 |
| `convergence.py` | `_get_json` migrated to `registry_auth_header` (same auth change) | #240 |

**The one operational prerequisite** for consumers still on `v0.61.0`:
registry credentials must already be `ctk_` keys (`ctk_` + 43 chars base62
minus lookalikes, 47 total). v0.61.0 already dispatched `ctk_` via
`Authorization: Bearer` (DA-1949) but silently accepted legacy tokens;
v0.64.0 fails fast locally with rotation guidance. The engine side already
enforces this, so any consumer whose registration works today already holds a
`ctk_` key — the upgrade changes nothing for them.

Per this ticket's decision (detection gate, 2026-11-11): the two lagging
consumer pins below are **bumped to v0.64.0 in-ticket** via sub-PRs in the
consumer repos (`Part of` this issue).

## 2. Node contracts (recorded from the v0.64.0 tree)

### 2.1 Manifest shape — `WorkflowNodeManifest`

Python `python/canvastekk_workflow_sdk/definition.py`; TypeScript
`typescript/src/definition.ts:293` (`WorkflowNodeManifestSchema`, Zod).

- **Identity:** `id`, `slug`, `name`, `version`, `description`
- **Schemas:** `input_schema`, `output_schema` (JSON Schema)
- **Cost:** `token_cost`; **Retry defaults**; **Metadata:** `category`,
  `timeout_seconds`, `role`, `docs_url`
- **`sdk_version`** (`definition.py:347`): auto-stamped provenance, read-only.
  Since #123/D16 it is the **sole** version key — versions are provenance,
  never admission gates, so older-wheel consumers never fail registration on
  version grounds.
- **`code_digest`**: sha256 of handler module source, computed at startup,
  auto-injected, never author-settable.
- **`mode`**: `dev` / `uat` / `production`, derived from `CANVASTEKK_NODE_ENV`
  (`app.py:534-540`); the engine reads it for routing/test behavior.
- **`effective_contract`** (`definition.py:366`): declared `NodeContract`
  routes, or the SDK-served default (`SDK_SERVED_CONTRACT_ROUTES`); a declared
  subset wins.

### 2.2 Execute contract

`POST /execute` (`python/canvastekk_workflow_sdk/app.py:342`; TS `app.ts`):

- JSON body of inputs; invalid JSON → `400`; non-dict → `422`
- File input fields arrive as **presigned GET URLs**; the SDK downloads with
  redirect-hop and byte caps (`base.py:_download_one`)
- Outputs upload via **multipart upload-session descriptors**; a legacy
  presigned-PUT string target fails the execution with `NodeIOError`
  (DA-3340)
- Cancellation: `cancel_event` aborts in-flight downloads; `execute()` itself
  cannot be interrupted
- `BaseNode.execute(inputs, context)` is the author surface (the SDK repo's
  own examples and tests carry 65 implementations dispatching through it)

### 2.3 Discovery / version header

`GET /manifest` (`app.py:510-548`) returns the manifest plus `sdk_version`,
`code_digest`, `mode`, and `contract` (effective, hook-route stripped when the
node uses the SDK default). Used by the registry for auto-discovery and
manifest cross-checking.

### 2.4 Registration behavior

Python `registry.py:register_node`, TS `registry.ts:197 registerNode`:

- `POST` the registry payload built from the manifest
  (`buildRegistryPayload`: `invoke_type` — the `InvokeType` literal is
  `{"http", "lambda", "sagemaker", "in-process"}`
  (`registry.py:23`), **but `lambda` is listed in
  `UNSUPPORTED_INVOKE_TYPES` and rejected with migration guidance — the
  supported set today is `http` / `sagemaker` / `in-process`**;
  `invoke_url`, `tags`, `invoke_config`)
- **Credential:** `serviceToken` — a `ctk_` API key, **required** (#239);
  rides `Authorization: Bearer` (`registryAuthHeader`, offline validation:
  prefix check + 43-char base62-minus-lookalikes body, truncation hint on
  malformed)
- Result: `RegisterNodeResult{node, action: created|updated|unchanged,
  revision_id, previous_version, changes}` — `unchanged` makes
  re-registration idempotent
- Conflict (`409`): publish a higher version (`node_version_immutable`
  guidance distinguishes field-change conflicts)

## 3. Consumer pin inventory (verified vs each repo's remote `dev`, 2026-11-11)

| Consumer | Manifest | Pin | State |
|---|---|---|---|
| CLS gateway | `canvastekk-llm-service/fastapi_gateway_app/pyproject.toml` | `v0.64.0` wheel | ✅ aligned |
| CLS OpenCode lambda | `canvastekk-llm-service/opencode_app/Dockerfile` (LAMBDA stage pip-install) | `v0.61.0` wheel | ⬆ bumped in-ticket |
| CISA python | `canvastekk-ifc-service-app/apps/python/pyproject.toml` | `v0.64.0` wheel | ✅ aligned |
| CISA node | `canvastekk-ifc-service-app/apps/node/package.json` (`@betekk/canvastekk-workflow-sdk`) | `v0.61.0` tgz | ⬆ bumped in-ticket |
| Workflow engine | `canvastekk-workflow-engine/fastapi_app/pyproject.toml` | `v0.64.0` wheel | ✅ aligned |
| Workflow nodes | `canvastekk-workflow-nodes/apps/python/pyproject.toml` | `v0.64.0` wheel | ✅ aligned |

Notes:
- CLS `opencode_app/pyproject.toml` deliberately carries **no** SDK dep (#448:
  the serve runtime never imports `node/`; the LAMBDA stage pip-installs the
  wheel directly — hence the Dockerfile is the pin site).
- Engine floors: TS package `engines.node >=24.0.0` in **both** v0.61.0 and
  v0.64.0 (CISA apps/node CI pins node 24 → drop-in); python wheel requires
  `>=3.12` (opencode LAMBDA stage builds on python:3.12 → satisfied).
- `civiltekk-opencode-service` is not a consumer (empty checkout, no SDK
  references).

## 4. CLS / OpenCode alignment

Both lanes of CLS and the OpenCode lambda converge on `v0.64.0` once the two
in-ticket bumps land. Alignment consequences:

1. **One shared contract** — every consumer registers with `ctk_` keys and
   reports the same `sdk_version` provenance; mixed-pin drift (the rejected
   alternative) ends.
2. **No SDK release** is required by this verification (no gap found — §1);
   the next SDK release proceeds on its own merit.
3. **No required SDK change to file separately** — AC5's "file any required
   change separately" has nothing to file: manifest, execute, version-header,
   and registration contracts are unchanged from v0.61.0.

## 5. Follow-ups (consumer-repo, out of SDK scope)

- The two pin bumps land as `Part of` sub-PRs of this ticket (this run).
- Consumers should adopt the new `ctk probe --engine-url` pre-flight registry
   diff in CI where registration drift matters (optional; v0.64 feature).
