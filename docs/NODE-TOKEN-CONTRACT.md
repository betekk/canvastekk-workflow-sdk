# Node Token Contract (engine → node authentication)

Status: **v1 — normative** (SDK v0.54.0, tracker #3825). The normative
implementation is `python/canvastekk_workflow_sdk/node_token.py`
(mint/verify) and `_CentralAuth` in
`python/canvastekk_workflow_sdk/auth.py` (node-side validation); the
TypeScript mirror is `typescript/src/node-token.ts` + `NodeAuth.central`.
The workflow engine (#3826) implements the issuer and verify endpoint
against this document.

## Purpose

Replaces the fleet-shared static `CANVASTEKK_NODE_API_KEY` ("secretless
nodes"): nodes hold **zero platform credential material**. The engine
mints a run-scoped token per dispatch and presents it in the existing
`X-API-Key` header slot — wire-compatible, semantics changed. Nodes
delegate verification to the engine's verify endpoint (central
validation), cached briefly, fail-closed.

## Token format

```
cwnt_v1.<b64url(payload_json)>.<b64url(hmac_sha256)>
```

- `payload_json` claims: `run_id` (string), `node_id` (string), `iat`
  (epoch seconds), `exp` (epoch seconds).
- The HMAC-SHA256 signature is computed over the ASCII bytes of
  `"cwnt_v1." + <payload_segment>` (domain separation), with the engine's
  signing key (`/canvastekk/platform/{env}/cwe-node-token-signing-key`,
  random ≥ 32 bytes, devops #3827).
- `exp` = run deadline + grace. Retries re-dispatch and **mint a fresh
  token**; tokens are never extended.
- b64url segments are unpadded (`=`-stripped).

Responsibilities:

| Party | Duty |
|---|---|
| Engine (mint) | `mint_node_token(run_id, node_id, signing_key, ttl_seconds)` at dispatch; inject as `X-API-Key` |
| Engine (verify endpoint) | `verify_node_token(token, signing_key)` locally; answer the HTTP protocol below |
| Node | shape-check (`is_node_token`), delegate to verify endpoint, cache verdict, fail closed |

## Verify protocol (node → engine)

```
POST {CWE_API_BASE_URL}/api/nodes/verify-token
Content-Type: application/json

{"token": "cwnt_v1...."}
```

Responses:

| Status | Body | Meaning | Node behavior |
|---|---|---|---|
| 200 | `{"valid": true, "run_id": "...", "node_id": "...", "exp": 123}` | Definitive valid | accept; cache |
| 200 | `{"valid": false}` | Definitive invalid (tampered/expired/wrong key) | **401**; cache |
| any other (5xx, timeout, unreachable, malformed body) | — | No verdict | **503 fail-closed**; never cache |

The endpoint is unauthenticated by design: it reveals only the validity
of the presented token (tokens are unguessable without the signing key),
and the token itself is the credential under test.

## Node-side caching law

- Verdict cache keyed `sha256(token)`, TTL 60s default.
- A **valid** verdict is cached no longer than the token's own `exp`.
- **Transport errors are never cached** (a recovered engine must
  immediately serve verdicts again).
- Cache is bounded (cleared on overflow; per-token LRU if eviction storms
  are ever observed).

## Fail-closed law (DA-1949)

Missing header → 401. Definitive invalid → 401. No verdict available
(engine unreachable, timeout, protocol violation) → **503**. There is no
path where an unverifiable request is accepted.

## Dual-accept transition (rollout window)

`NodeAuth.central()` (default `legacy_key_env_var="CANVASTEKK_API_KEY"`)
first attempts a constant-time match against the legacy static key
(including `<env>_NEXT` rotation); a match is accepted as
`auth_mode: "legacy_api_key"`. The legacy leg is **inert when the env
var is unset** — retirement (#3838) is env removal, not a code change.
Pass `legacy_key_env_var=None` (Python) / `{ legacyKeyEnvVar: null }`
(TS) for central-only.

Rollout order is fixed by epic #3824: nodes dual-accept → engine
dual-sends → env-by-env cutover (dev → uat → prod) → purge the entire
node-api-key family.

## Local development, CI, and external authors

- `NodeAuth.api_key()` (static profile) remains the documented mode for
  local dev, CI conformance fixtures (e.g. ML `ci.yml`'s
  `ci-conformance-key`), and tests. Mode is selected by environment, not
  code.
- `CANVASTEKK_DEV_MODE` bypasses all layers as before — never in
  production.
- External node authors use central mode in org deployments; their own
  deployments may choose any layer. Registration stays on per-repo `ctk_`
  keys (CDS-validated) and is unaffected by this contract.

## Upgrade path (documented, deliberately not chosen)

Asymmetric local verification (engine signs with a private key, nodes
verify offline with the public key; revocation via short exp only) would
remove the verify round-trip. Chosen design keeps revocation power
central (verify endpoint sees every token) at the cost of one cached
call per token-minute. Revisit if verify-endpoint load or engine
availability becomes a constraint.
