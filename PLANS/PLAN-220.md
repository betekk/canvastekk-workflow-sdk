# PLAN: Standardize node bootstrap — factory, mount, lambda face, layout ADR

**Branch**: feat/220
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/220
**Base**: dev

## Acceptance Criteria
- [ ] `create_authed_app` shipped in the python SDK with central-only default; mirrored generic features in TS per the parity rule
- [ ] `mount_node` + `create_lambda_handler` shipped with tests
- [ ] Layout ADR merged; NODE-TOKEN-CONTRACT.md references the canonical factory
- [ ] Engine-contract findings recorded with decisions (serverless health + long-run semantics)
- [ ] CWN consumption shim landed or tracked

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/app.py` (`create_authed_app`, `mount_node`) | ADR (1.3) | CWN `_shared/authed_app.py` (shim), CLS #448/#449 (future) | med (create_node_app has 57 internal callers — additive only) |
| `python/canvastekk_workflow_sdk/_lambda.py` (`create_lambda_handler`) | mount (2.2) | CLS opencode dual-face (#448), any future lambda-hosted node | med |
| `typescript/src/app.ts` (+ `express.ts`) parity | ADR | TS consumers (parity rule) | med |
| `docs/NODE-SERVICE-LAYOUT.md` (ADR) | engine reads (1.1/1.2) | #448/#449 structure, future node services | none |
| `docs/NODE-TOKEN-CONTRACT.md` | factory (2.1) | node implementers | low |
| CWN `_shared/authed_app.py` shim | SDK release with factory | CWN apps (apps/python/*) | low (delegation keeps signature) |

## Implementation Phases

### Phase 1: Engine-contract reads + ADR (decisions before code)
- [x] **1.1** Record the serverless-health decision: read engine `check_node_health` (nodes/router.py:492 — on-demand 5s httpx probe of `<invoke_url>/health`) + `verify_node` (manifest cross-check, :454); decide whether lambda-hosted nodes register manifest-only or carry health; write the decision + any engine follow-up recommendation into the ADR
    — **Why:** the engine probes a lambda URL at 5s — a cold start can exceed it; #448's registration shape (invoke_url + health vs manifest-only) depends on this decision, and the ticket requires findings BEFORE consumers build
    — **Done when:** decision recorded in the ADR with the evidence (router paths + timeout) and, if engine change is needed, a named follow-up (engine repo issue or explicit deferral)
    — **Consumers affected:** ADR readers, #448 registration design
    — **Done:** decision D1 in ADR (evidence: engine nodes/router.py:492/:511 5s on-demand probe, :454 manifest cross-check) — lambda nodes register WITH invoke_url, serve /health+/manifest from the composite app; per-node probe-timeout engine follow-up recommended in-ADR, non-blocking; files: docs/NODE-SERVICE-LAYOUT.md; fixes: none
- [x] **1.2** Record the long-run decision: read engine `execute_http_node` (temporal/activities.py:655) timeout shape (Temporal start-to-close vs SDK-visible limits); decide blocking-HTTP-within-activity-timeout vs run_id polling for turns up to 840s; write decision + rationale into the ADR
    — **Why:** CLS lane turns run up to 840s (stale-lane sweep at 960s); the SDK must state which execution semantic node authors get, and the engine side must be shown to tolerate it
    — **Done when:** decision recorded with the activity-timeout evidence; polling-based async rejected/accepted explicitly with a trigger condition for revisiting
    — **Consumers affected:** node authors (execute() contract expectations), #448
    — **Done:** decision D2 in ADR (evidence: activities.py:655 per-node timeout_seconds; workflows.py:2098 wait_condition + :1110-1140 async park; activities.py:502 record_async_park DA-3228) — v1 BLOCKING execute (URL ceiling 900s > 840s turns; register timeout_seconds>=960); async-park escape hatch documented; node-side polling rejected; files: docs/NODE-SERVICE-LAYOUT.md; fixes: none
- [x] **1.3** Write `docs/NODE-SERVICE-LAYOUT.md` (the layered-layout ADR: `node/ api/ faces/ domain/ integrations/ cli/ tests/`, downward-only deps, `domain` imports no FastAPI/SDK, faces never contain logic) embedding 1.1/1.2 decisions
    — **Why:** the layout standard is consumed by #448/#449 restructures; it must exist before they build on it
    — **Done when:** ADR committed with the layer table, the placement Q&A, and both engine-contract decisions
    — **Consumers affected:** #448/#449, future node services
    — **Done:** ADR committed — layout table, downward-only rule, placement Q&A, canonical bootstrap, D1+D2, parity boundary; files: docs/NODE-SERVICE-LAYOUT.md; fixes: none

### Phase 2: Python — factory + mount + lambda face
- [x] **2.1** Ship `create_authed_app(node, *, legacy_key_env_var=None, **kwargs)` in the python package (promoted from CWN `_shared/authed_app.py`): delegates to `create_node_app(node, auth=NodeAuth.central(legacy_key_env_var=legacy_key_env_var), **kwargs)`; keep the `extra_routes` ValueError guard iff still true of `create_node_app` (verify at app.py:180 — if extra routes now carry router deps, drop the guard); export from `__init__`
    — **Why:** the factory is the canonical bootstrap; central-only default makes greenfield services secretless by construction while the `legacy_key_env_var` kwarg keeps CWN's dual-accept window alive
    — **Done when:** importable from the package root; signature + docstring state the default and the CWN transition usage; unit tests cover default-central-only and the legacy-kwarg passthrough
    — **Consumers affected:** CWN (shim), #448/#449
    — **Done:** bootstrap.py create_authed_app — central-only default (legacy_key_env_var=None), extra_routes guard KEPT (premise re-verified: app.py:635 include_router carries no deps); lazy __init__ exports; tests: fail-closed default + legacy passthrough + guard; files: bootstrap.py, __init__.py, tests/test_bootstrap.py; fixes: none
- [x] **2.2** Ship `mount_node(root_app, node, *, prefix="/node", legacy_key_env_var=None, **kwargs)` — mounts the authed node sub-app under `prefix` on an existing FastAPI app (dual-purpose services keep their own routes); choose `Mount` vs `include_router` during implementation (Mount preserves sub-app isolation incl. its own OpenAPI; verify auth dependency applies on both shapes) and record the choice in the ADR
    — **Why:** dual-purpose services (CLS lane route + CWE node on one lambda) are the D4 shape; without this every service hand-rolls the composite
    — **Done when:** unit test proves root-app routes and node routes (`/manifest`, `/execute`) both served from ONE app with node auth enforced ONLY on the node sub-app; prefix configurable
    — **Consumers affected:** #448 (composite app), #449
    — **Done:** mount_node via root_app.mount(prefix, sub) + lifespan chaining (asynccontextmanager — bare-async-generator bug caught by test, fixed); tests: auth boundary (root open, node 401/200), custom prefix, lifespan-runs; files: bootstrap.py, tests/test_bootstrap.py; fixes: lifespan context-manager shape (1)
- [x] **2.3** Ship `create_lambda_handler(app, *, plain_event)` in `python/canvastekk_workflow_sdk/_lambda.py`: returns a callable that structurally classifies the Lambda event (httpApi/ALB markers → Mangum ASGI dispatch on `app`; otherwise → `plain_event(payload, context)`); `mangum` stays an optional dependency with a clear ImportError message; python-only, documented as such in the ADR + contract doc
    — **Why:** two hand-rolled copies exist already (CLS `lambda_handler.py:611-626`, ingest worker); a third would be written by #448 without this
    — **Done when:** unit tests prove dual dispatch: an httpApi-shaped event routes through ASGI (Mangum) and a plain dict event routes to the supplied dispatcher; missing-mangum raises the documented ImportError
    — **Consumers affected:** #448, future lambda-hosted nodes
    — **Done:** create_lambda_handler — structural HTTP check (httpMethod / requestContext.http), Mangum(app, lifespan="off") per CLS precedent, plain-event dispatcher; [lambda] extra added (mangum>=0.22,<1) + dev dep; lazy mangum import with actionable ImportError; tests: plain + httpApi dispatch; files: bootstrap.py, pyproject.toml, tests/test_bootstrap.py; fixes: none
- [x] **2.4** Python unit tests for 2.1–2.3 in `python/tests/test_bootstrap.py` (or extend `test_app.py` per nearest-existing-test convention): central-only default, legacy passthrough, mount dual-purpose auth boundary, lambda dual dispatch, extra_routes guard behavior
    — **Why:** the parity rule and downstream consumers require the bootstrap contract pinned by tests, not docs
    — **Done when:** suite green; each helper has at least one positive and one negative assertion
    — **Consumers affected:** CI, consumers
    — **Done:** 9 tests in tests/test_bootstrap.py mirroring test_app.py conventions — all green (9 passed); files: tests/test_bootstrap.py; fixes: response-shape assertion (outputs), sourceIp in synthetic event

### Phase 3: TypeScript parity
- [x] **3.1** Mirror the generic parts in TS: `createAuthedApp(node, opts?)` delegating to the TS app factory with central auth (auth.ts `central` exists — 1 caller today) and `mountNode(root, node, {prefix})` on the express face (`typescript/src/express.ts`); NO TS lambda face (documented python-only exception in the ADR + both READMEs' parity note)
    — **Why:** the SDK's parity rule ships both stacks in the same change; mount semantics are generic, the Mangum face is python-runtime-specific
    — **Done when:** TS tests mirror the python mount/dual-purpose assertions; parity exception documented
    — **Consumers affected:** TS consumers, parity checkers
    — **Done:** typescript/src/bootstrap.ts — createAuthedApp (central-only default, legacyKeyEnvVar) + mountNode (express app.use prefix; no lifespan concept needed — python-only hazard); exported via ./express subpath; extraRoutes guard parity; NO TS lambda face (documented exception); files: typescript/src/bootstrap.ts, typescript/src/express.ts, typescript/tests/bootstrap.test.ts; fixes: Application vs Express return type (1)
- [x] **3.2** TS build + tests green (the repo's TS toolchain — discover from `typescript/package.json` scripts)
    — **Why:** parity that doesn't build is prose
    — **Done when:** TS test runner + build pass locally
    — **Consumers affected:** CI
    — **Done:** vitest 448 passed (27 files, incl. 5 new bootstrap tests); typecheck + typecheck:tests + eslint + tsup build all green; files: (none beyond 3.1); fixes: none

### Phase 4: Contract doc + CWN shim + exit gate
- [ ] **4.1** Update `docs/NODE-TOKEN-CONTRACT.md` to name `create_authed_app` as the canonical factory (central-only default, legacy kwarg semantics, mount/lambda-face references + the layout ADR link); README examples updated to the one-liner
    — **Why:** the contract doc is normative for node implementers; a canonical factory that the contract doesn't name changes nothing
    — **Done when:** doc merged references the factory, its default, and both helpers
    — **Consumers affected:** node implementers
- [ ] **4.2** CWN consumption: in the canvastekk-workflow-nodes checkout, convert `apps/python/_shared/authed_app.py` to a deprecation shim delegating to the SDK factory (signature-compatible, legacy_key_env_var="CANVASTEKK_API_KEY" during the dual-accept window) — land as a CWN branch+PR, or if the CWN SDK floor hasn't absorbed a release yet, file the tracked follow-up issue in CWN and link it here
    — **Why:** the ticket AC accepts "landed or tracked"; the shim is what stops copy three from persisting
    — **Done when:** CWN PR opened (or issue filed) and linked in this ticket
    — **Consumers affected:** CWN apps
- [ ] **4.3** Exit gate (full): python ruff + pytest; TS build + tests; `GATE <sha> tier=full` memo in this PLAN's Trace section
    — **Why:** ticket exit gate runs full unconditionally; both stacks are deliverables
    — **Done when:** all axes green; memo appended; zero unchecked phase boxes
    — **Consumers affected:** PR CI, Step 10a citation

## Technical Notes
- `NodeAuth.central()` already accepts `legacy_key_env_var=None` (auth.py:556) — central-only is a parameter pass-through, zero auth-code change.
- CWN factory guard: `extra_routes` rejected because SDK mounts extra routes without the auth dependency — re-verify against current `create_node_app` before keeping.
- Engine facts (verified 2026-10-31): health probe = on-demand `GET <invoke_url>/health`, httpx timeout 5.0s, `raise_for_status` (nodes/router.py:511); manifest cross-check separate (`verify_node`, :454); workflow execution path = Temporal activity `execute_http_node` (activities.py:655).
- CLS dual-face precedent: `opencode_app/lambda_handler.py:611-626` — structurally-HTTP → `http_app.mangum_asgi`, plain event → run path. The SDK helper must subsume this shape.

## Dependencies
None (root of node chain). Consumers: CLS #448 (blocked-by this), #449, CWN shim.

## Risks & Mitigation
- `create_node_app`'s 57 internal callers — additive-only changes; no signature edits to existing functions.
- Mount-vs-include auth semantics differ subtly — pinned by the 2.2 negative test (auth NOT on root routes).
- TS parity scope creep — the ADR fixes the boundary (generic mount yes, lambda face no) before TS work starts.
- CWN SDK floor lag — 4.2 has the tracked-issue fallback; the AC accepts it explicitly.

GATE 111e7ad tier=light lint=n.a typecheck=n.a build=n.a unit=n.a e2e=n.a (Phase 1: ADR/docs only; ticks ride the Phase-2 commit — script fault, trace-only lag)
GATE 111e7ad tier=light lint=t typecheck=n.a build=n.a unit=t e2e=n.a (Phase 2: bootstrap module + tests 9 passed; scoped ruff ^0.17.2 clean; carries Phase-1 ticks — script fault noted above)
GATE e86f724 tier=light lint=t typecheck=t build=t unit=t e2e=n.a (Phase 3: TS parity — vitest 448, tsc x2, eslint, tsup all green)
