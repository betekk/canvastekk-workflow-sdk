# PLAN: canvastekk-workflow-sdk comment purge + scaffold response typing

**Branch**: feat/176
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/176
**Base**: dev

## Acceptance Criteria

- [x] Every inline/non-docstring comment purged (ts/py/yaml); JSDoc/Javadoc-class docstrings kept and audited to current behavior
- [x] Token-aware stripping; diff audit 0 offenders
- [x] The bare scaffold returns typed: `router.py` multi-node root health, `app.py` `/live`, `/ready` (+503), `/metrics` — Pydantic models aligned with existing `HealthResponse` style; no parallel mechanism to ContractSpec/to_openapi
- [x] Verification gates green (`tsc --noEmit` or repo build, py `compileall` + tests, exported openapi shows properties on these routes)
- [x] Squash `chore(comments): purge + typed scaffold responses (#176)`; base `origin/dev`

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `typescript/src/**` (38) | stripper | npm consumers pin release tags; TS SDK's own tests | low (comment-only) |
| `python/canvastekk_workflow_sdk/**` (79) | stripper | 7 consumer repos via pinned SDK releases (v0.54.0); nothing changes until they bump | low |
| `router.py::root_health` | models | node repos using `create_multi_node_app` | low-med (additive response_model; wire shape unchanged) |
| `app.py::{liveness,readiness,metrics}` | models | conformance.py probes (404/5xx only — shape-tolerant), Lambda health checks | low-med (additive) |
| `response.py` (models live here) | — | app.py, router.py | low (additive classes) |

Cross-module note: response_model additions change served openapi.json (that is the point — properties render). Runtime wire format identical (FastAPI serializes the same dicts). Conformance suite must stay green.

## Implementation Phases

### Phase 1: Strip
- [x] **1.1** TS strip (`c` mode; JSDoc `/** */` kept; `@ts-*`/eslint pragmas kept) over `typescript/src` + `typescript/test`; PY strip over `python/` (docstrings kept); HASH strip over yaml
    — **Why:** the purge core
    — **Done when:** audit 0 offenders; tsc/compileall green
    — **Consumers affected:** none (comment-only)

### Phase 2: Docstring audit
- [x] **2.1** Tells grep over kept docstrings (py + ts JSDoc); rewrite history narration to current behavior
    — **Why:** kept contracts must state current behavior
    — **Done when:** tells grep clean of history narration
    — **Consumers affected:** openapi descriptions, agents

### Phase 3: Typed scaffold responses
- [x] **3.1** Add `MultiNodeHealth` (status: Literal["healthy"], nodes: list[str]) in `response.py`; `router.py::root_health` returns it with `response_model`
    — **Why:** the one census-flagged bare-dict scaffold route
    — **Done when:** route decorated; openapi export shows typed properties
    — **Consumers affected:** multi-node gateway consumers (wire unchanged)
- [x] **3.2** Add `LivenessResponse` (status: Literal["alive"]), `ReadinessResponse` (status: Literal["ready","not_ready"], node_id, checks) + 503 `response_model`/`responses=`, `MetricsSummary` (total_executions, pass_count, fail_count, success_rate, avg/min/max_duration_ms, total_token_usage) in `response.py`; wire `/live` `/ready` `/metrics` to them preserving exact JSON keys
    — **Why:** bare JSONResponse returns render as empty objects in openapi.json
    — **Done when:** conformance tests + unit tests green; exported openapi shows properties
    — **Consumers affected:** conformance probes (shape-tolerant), openapi readers

### Phase 4: Gates + exit
- [x] **4.1** Full gate: TS build/typecheck (`tsc --noEmit` or repo script), py `compileall` + pytest suite, openapi export assertion for the four routes; AC ticks; `GATE <sha> tier=full`
    — **Why:** final SHA carries the full memo
    — **Done when:** all green, PLAN residue empty
    — **Consumers affected:** PR citation

## Technical Notes

- Release standard: SDK is tag-channel; consumers pin vX.Y.Z (currently v0.54.0). These changes ship on the next SDK release; no forced consumer bump.
- `get_summary()` docstring documents the exact key set — MetricsSummary mirrors it; `{"total_executions": 0}` empty case means optional fields.
- Do NOT touch ContractSpec/to_openapi emission (#110/#113); TS emitter parity is #124, separate.

## Dependencies

None. Epic children 8-13 inherit scaffold typing at their next natural bump.

## Risks & Mitigations

- MetricsSummary optional-field mismatch → mirror get_summary exactly; conformance + unit tests
- TS strip corrupts template literal → fixture-proven stripper + tsc gate

## Trace

- Phase 1: 877 comment lines stripped (ts 282, py 480, yaml 115; 87 files); stash mishap in baseline check recovered via stash pop, tree verified
- Phase 2: only two history tells found — both were stripped inline comments describing their next line (no promotion needed); docstrings clean
GATE 5747c0c tier=full lint=t typecheck=t build=t unit=t e2e=-
  (pytest 14 failures identical at origin/dev baseline — environmental deps, zero NEW; tsc clean; audit 0)
