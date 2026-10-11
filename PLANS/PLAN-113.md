# PLAN: OpenAPI 3.2 emission + 2020-12 schema-dialect lint

**Branch**: feat/113
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/113
**Base**: main

> Note: the previous PLAN under this name (verifier scope) was #112's work — merged via #118 and renamed `PLANS/PLAN-112.md` in the branch's first commit (f1d3978).

## Acceptance Criteria
- [ ] `to_openapi()` output declares openapi 3.2.0 and validates against a 3.2 parser
- [ ] dialect lint flags non-2020-12 schema constructs with field paths
- [ ] reconciliation rule vs fastapi served doc documented (manifest doc canonical)
- [ ] golden-file test pins the emitted document shape

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/definition.py` (`to_openapi()`) | `effective_contract` (#110, merged) | gateways/consumers wanting a standard artifact; golden-file test | low |
| `python/canvastekk_workflow_sdk/schema_dialect.py` (new lint) | none | manifest authors; future verifier/CLI wiring | low |
| `definition.py` + `typescript/src/definition.ts` vocabulary (add `/openapi`) | — | both validator loops (SAME-change parity rule); #112-verifier route derivation (merged) | medium |
| `docs/EXTERNAL-AUTHOR-GUIDE.md` (reconciliation rule) | `to_openapi()` semantics | self-hosted authors, gateway teams | low |

## Implementation Phases

### Phase 1: `to_openapi()` + golden-file test
- [ ] **1.1** Add `WorkflowNodeManifest.to_openapi() -> dict` in `definition.py`: emits `{"openapi": "3.2.0", "info": {title: name, version, description}, "paths": {...}}` with one path per `effective_contract.routes` entry; per-family operations mirror the verifier's method mapping (POST for `/execute` with `requestBody` from `input_schema` + 200 response from `output_schema` + 422 validation response; GET for health-family/`/manifest`; POST for other declared POST routes) — presence-level detail, not framework-introspected truth
    — **Why:** AC1 — a standard, derivable interface artifact for gateways; the manifest is the contract of record
    — **Done when:** golden-file test (`tests/test_openapi.py`) pins the full emitted dict for a declaring node AND an effective-default node; assertions: `openapi == "3.2.0"`, every contract route present, `/execute` POST carries input/output schema refs; ruff clean
    — **Consumers affected:** none in-repo (new surface); wheel content grows

### Phase 2: 2020-12 schema-dialect lint
- [ ] **2.1** New `schema_dialect.py`: `lint_schema_dialect(schema: dict) -> list[tuple[str, str]]` returning `(json_path, message)` for non-2020-12 constructs — draft-07 `$schema` URIs, `definitions` (→ `$defs`), object-of-arrays `dependencies` (→ `dependentRequired`/`dependentSchemas`), boolean `exclusiveMinimum/Maximum` (draft-04), `recursiveAnchor` (2019-09) — recursing through `properties`/`items`/`$defs`/`additionalProperties` with accurate `$`-paths
    — **Why:** AC2 — the manifest's schema dialect is unchecked today; authors get named, pathed violations instead of silent dialect drift
    — **Done when:** `tests/test_schema_dialect.py` covers each flagged construct + a clean 2020-12 schema returns `[]`; paths verified for nested cases; ruff clean
    — **Consumers affected:** none in-repo (new surface); CLI/verifier wiring deliberately deferred (noted in PLAN Risks)

### Phase 3: `/openapi` vocabulary entry (both stacks) + reconciliation doc
- [ ] **3.1** Add `/openapi` to `CONTRACT_ROUTE_VOCABULARY` in `definition.py` AND `typescript/src/definition.ts` in the SAME change with parity accept/reject tests both sides (repo rule: validator loops must cover new fields); minimum set unchanged; `SDK_SERVED_CONTRACT_ROUTES` unchanged (adapters do not mount it)
    — **Why:** the ticket's "optional `openapi` route-vocabulary entry" — nodes may now DECLARE an OpenAPI-doc route; the closed vocabulary must admit it before any manifest can
    — **Done when:** python validator accepts a contract declaring `/openapi` and still rejects unknown routes; TS mirror accepts/rejects identically; both test suites green on the same commit
    — **Consumers affected:** both validators; #112-verifier (merged) will probe a declared `/openapi` route as presence-GET — harmless
- [ ] **3.2** Document the reconciliation rule in `docs/EXTERNAL-AUTHOR-GUIDE.md`: the manifest's `to_openapi()` document is CANONICAL for gateways and the engine; a framework-served doc (e.g. fastapi's `/docs` artifact) is the live server's view — reconcile field-level differences toward the manifest; note that framework-served OpenAPI versions track the framework (3.1 today for fastapi per the ticket's own note) while the manifest pins 3.2.0
    — **Why:** AC3 — gateways need one rule for conflicting artifacts
    — **Done when:** the guide section states the canonical-artifact rule + the version note; link added from `to_openapi()`'s docstring
    — **Consumers affected:** documentation surface only

### Phase 4: Full gate
- [ ] **4.1** Full gate on the final tree: python ruff + pytest (runnable subset; fastapi-lane modules → CI, baseline-documented); TS eslint + tsc + typecheck:tests + vitest full; `git diff origin/main...feat/113 --stat` scope check
    — **Why:** ticket exit gate — the last verification before PR
    — **Done when:** all legs green; `GATE <sha> tier=full` memo appended
    — **Consumers affected:** none beyond the above

## Technical Notes
- AC1's "validates against a 3.2 parser": OpenAPI 3.2 tooling is new; the golden-file test carries the parse pin (structural assertions on the emitted document). `# ponytail:` swap in `openapi-spec-validator` (or equivalent) when it ships 3.2 support — one test import, no dependency added today.
- The lint is a pure function this round; wiring it into the CLI `validate` output or the verifier is a follow-up once the violation shapes settle.
- `/openapi` is OPTIONAL (vocabulary admits it, minimum set unchanged, adapters don't mount it).

## Dependencies
blocked-by: #110 (merged via #116).

## Risks & Mitigation
- Vocabulary growth ripples into validators and the verifier → parity tests in the same commit; verifier treats an unmounted `/openapi` as any other broken declared route (fails under its name) — correct semantics for a declared-but-absent route.
- Golden-file brittleness → the file pins ONE representative manifest; schema-level changes to the emitter fail loudly and deliberately.

## Trace
