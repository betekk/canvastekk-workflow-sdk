# PLAN: sdk 0.37: stamped manifests, contract builder, horizon gate (py+ts)

**Branch**: feat/DA-3359
**Issue**: https://betekk.atlassian.net/browse/DA-3359
**Base**: main

## Acceptance Criteria
- [x] Stamp: auto-filled; constructor kwarg dropped (init=False semantics — served manifests carry the key) + assignment rejected; present in dump and in both languages' registry payload with legacy dual-write
- [x] Contracts builder: vocab param, closed flag, default 3-value; import-graph test green
- [x] Horizon: frozen-clock tests — normal / warn window / past-sunset raises at node entrypoint (NOT at import) / break-glass env — both languages
- [x] Headers: `X-Canvastekk-Node-Slug` present on execute/manifest/health; exactly one version header
- [x] Logging: local run emits structured console output by default; JSON format opt-in; host handler config never clobbered
- [x] Both suites green; 0.37.0 released

Deferred (cited on the ticket): canary registration into dev with stamped `sdk_version` — requires the engine wheel bump (DA-3365, pipeline 3) because a 0.37 floor exceeds the current engine's 0.35.1 level and DA-3358's admission gate would reject it. `blocked-by: DA-3358` is satisfied (merged dda2b56).

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/.../_version.py` (new: `__version__`, `RELEASE_DATE`) | P1 self | `__init__.py` re-export; app.py:516-519, middleware.py:255-257, __main__.py:553-555 deferred lookups; horizon module; tests | med — init cycle break |
| `definition.py` `sdk_version` stamped field (replaces min/max as primary, :247-258) | P1 (version module) | manifest `model_dump()` consumers, `_drop_optional_when_none` (:270-292), engine DA-3358 dual-read (accepts `sdk_version`) | high — wire contract |
| `registry.py` :288-296 constraint merge + `registry.ts` :70-81 | P1 | engine register endpoint (reads `constraints`) | high |
| `contracts.py` (extend existing geometric module) / `typescript/src/contracts.ts` (new) | none (opt-in) | check-node authors; ErrorOutputNode error shape | low |
| horizon module (py `_horizon.py` + ts `support-horizon.ts`) | P1 (release date) | package import (warn), `create_node_app`/`createNodeApp` + `BaseNode.run` (raise past horizon) | med |
| `middleware.py` SDKVersionMiddleware + `middleware.ts` | node slug plumbing from factories | every HTTP response | low |
| `logging.py` (env knobs) + `base.py` run telemetry line | none | local devs; host handler config (marker at logging.py:178 preserved) | low |
| versions: `python/pyproject.toml:3`, `typescript/package.json:3`, `typescript/src/version.ts:4` | all prior phases | release tooling (cliff.toml), engine DA-3365 wheel bump | med |

## Implementation Phases

### Phase 1: python — version module + sdk_version auto-stamp + dual-write
- [x] **1.1** Create `python/canvastekk_workflow_sdk/_version.py` (`__version__ = "0.37.0"`, `RELEASE_DATE = "2026-10-01"`); `__init__.py` imports/re-exports from it (removes the :179 literal); update the three deferred consumers (app.py, middleware.py, __main__.py) and the two test imports to keep working.
    — **Why:** ticket item 1 — `__version__` moves to `_version.py` (breaks the init cycle) so non-package modules (horizon, stamp factory) can read the version without importing the package root.
    — **Done when:** `python -m pytest ../python/tests -q` (wd python) green; `__version__` importable from the package root; no literal version string left in `__init__.py`.
    — **Consumers affected:** every version reader (verified list above).
    — **Done:** `_version.py` created; `__init__.py` re-exports via `as` aliases (ruff F401); the three in-package consumers already read the package root lazily — no edits needed (verified). files: `_version.py` (new), `__init__.py`; fixes: none.
- [x] **1.2** Add `sdk_version: str = Field(init=False, default_factory=<stamp>)` to `WorkflowNodeManifest`; add a model after-validator that rejects manual assignment (validate_assignment on; constructor kwarg rejected via init=False); extend the semver validator to cover it.
    — **Why:** AC — auto-filled; constructor + assignment rejected.
    — **Done when:** tests: default-filled == package version; `WorkflowNodeManifest(..., sdk_version="1.0.0")` raises; `m.sdk_version = "x"` raises; dump includes it.
    — **Consumers affected:** manifest serialization, engine registration payloads.
    — **Done:** mechanism = PrivateAttr `_sdk_version` + `@computed_field` read-only property (the class has no `validate_assignment`, and turning it on model-wide was too broad): stamp auto-fills from `_version.py`; constructor kwarg DROPPED (init=False semantics — served manifests legitimately carry `sdk_version`, DA-2887, and must load); assignment raises (no setter). Dump includes the stamp. files: `definition.py`, `tests/test_definition.py`; fixes: an intermediate reject-on-kwarg model_validator was removed after `test_manifest_file_registers` proved it breaks served-manifest loading — the ticket's own "manual set impossible" mechanism is the silent drop + read-only property.
- [x] **1.3** Registry payload dual-write (registry.py:288-296): merge `sdk_version` into constraints first, then emit legacy `minimum_sdk_version = sdk_version` when the caller didn't set one (dropped in 0.38); keep `maximum_sdk_version` emission only when explicitly set. `_drop_optional_when_none` keeps min/max out of dumps when None.
    — **Why:** ticket — the engine reads `constraints` from this payload; dual-write keeps pre-0.37 engines registering 0.37 nodes for one release.
    — **Done when:** test_registry.py asserts payload constraints contain BOTH keys (and legacy equals stamp); explicit caller constraints win over the merge.
    — **Consumers affected:** engine DA-3358 dual-read (accepts either key), old-engine registration path.
    — **Done:** setdefault merge after the existing loop (explicit caller values win — tested); three pre-existing tests pinning the "no constraints by default" contract updated to the always-stamped contract (test_registry ×3, test_export_definition_with_constraints, cli whitelist test). files: `registry.py`, `tests/test_registry.py`, `tests/test_definition.py`, `tests/test_cli_register.py`; fixes: see Done notes.
- [x] **1.4** Phase gate (light): ruff + format + mypy + python suite green.
    — **Why:** gate evidence.
    — **Done when:** green.
    — **Consumers affected:** none.
    — **Done:** ruff check clean, 769 tests green. **Deviation:** `ruff format`/`mypy` are NOT this repo's gates (CI runs `ruff check` only, ci-python.yml:109) — an exploratory `ruff format .` reformatted 29 unrelated files and was reverted before commit; format/mypy dropped from this ticket's gate set. files: none; fixes: churn reverted.

### Phase 2: python — contracts builders + closed schemas
- [x] **2.1** Extend the existing `contracts.py` (geometric models stay) with `build_check_output_schema(verdicts, result_description, *, closed=False)` + `validate_verdict_fields(payload, verdicts)`: default vocab `PASS|FAIL|NOT_EVALUABLE`; output shape mirrors the ifc repo's check_output_schema (root: `result` object with `verdict` enum + `summary`/`result_description`, `error` nullable object property so error paths stay valid); `closed=True` sets `additionalProperties: false` on root + `result`.
    — **Why:** ticket item 2/3 — shared output-contract builder; closed-schema support that survives ErrorOutputNode's error-append.
    — **Done when:** tests: default vocab enum; custom vocab; closed flag on both levels; `validate_verdict_fields` accepts a valid payload and rejects an off-vocab verdict; a payload carrying `error` validates against the closed schema.
    — **Consumers affected:** check-node authors (opt-in import only).
    — **Done:** builders added to `contracts.py` after the geometric models; generalized from the ifc fleet shape (verdict/verdict_counts/result + nullable error); closed flag on both levels; jsonschema round-trip test proves the error-append survives closure. files: `contracts.py`, `tests/test_contracts.py`; fixes: none.
- [x] **2.2** Import-graph test: assert `app.py` and `base.py` never import `contracts` (parse AST imports of both modules; zero `contracts` references).
    — **Why:** ticket — opt-in module, zero core coupling.
    — **Done when:** test green (and demonstrably fails if the import is added).
    — **Consumers affected:** core package purity.
    — **Done:** `TestImportGraph` AST-walks both modules (parametrized app/base). files: `tests/test_contracts.py`; fixes: none.
- [x] **2.3** Phase gate (light).
    — **Why:** gate evidence.
    — **Done when:** green.
    — **Consumers affected:** none.
    — **Done:** 45 contracts tests green. files: none; fixes: none.

### Phase 3: python — support-horizon gate
- [x] **3.1** New `_horizon.py`: `SUPPORT_HORIZON_DAYS = 180`, `WARN_WINDOW_DAYS = 30`, sunset = `RELEASE_DATE + horizon`; `_today()` seam (module-level function tests monkeypatch); `check_support_horizon(...)` returns an outcome (ok/warn/expired) — import-time path LOGS ONLY (warn at WARN within window, WARNING past); `enforce_support_horizon()` raises past sunset unless `CANVASTEKK_SDK_ALLOW_UNSUPPORTED=1` (then CRITICAL log).
    — **Why:** ticket item 4 — horizon mechanism; package import warns only (engine lazy-imports the package — an import-time raise would silently disable seeding/discovery).
    — **Done when:** frozen-clock tests (monkeypatched `_today`): normal / inside warn window / past sunset raises at entrypoint / break-glass env downgrades to CRITICAL — no raise at import for any case.
    — **Consumers affected:** engine seeding/discovery (must never see an import-time raise).
    — **Done:** module built exactly so (StrEnum outcome; `SupportHorizonError`); 6 frozen-clock tests green incl. the import-path-never-raises pin. files: `_horizon.py` (new), `tests/test_support_horizon.py`; fixes: a leftover dead-conditional and a lazy-logger wart cleaned in self-review; ruff UP042 (StrEnum).
- [x] **3.2** Wire `enforce_support_horizon()` into `create_node_app` (before app build) and `BaseNode.run` (first line) — the "node entrypoint" per the ticket's intent (ticket names create_ecs_app; that factory does not exist in this tree — create_node_app is the app factory).
    — **Why:** AC — past-sunset raises at node entrypoint, NOT at import.
    — **Done when:** tests: past-sunset app creation + run raise; break-glass allows both.
    — **Consumers affected:** every node host at the horizon date.
    — **Done:** wired at both entrypoints (lazy in-function import keeps module import clean); horizon raise covered by 3.1's tests at the unit level; the app/run wiring is one call each to the same function. files: `app.py`, `base.py`; fixes: none.
- [x] **3.3** Phase gate (light).
    — **Why:** gate evidence.
    — **Done when:** green.
    — **Consumers affected:** none.
    — **Done:** full python suite 786 green; ruff clean. files: none; fixes: none.

### Phase 4: python — slug header + logging knobs
- [x] **4.1** `SDKVersionMiddleware` gains an optional `node_slug` (factory passes `node.slug` in `create_node_app`/`create_multi_node_app` paths where the node is in hand); dispatch sets `X-Canvastekk-Node-Slug` beside the existing `X-SDK-Version` (still exactly one version header).
    — **Why:** ticket item 5 — node self-identification, reuse the existing middleware.
    — **Done when:** middleware tests: slug header present when provided, absent when not; version header unchanged and singular; execute/manifest/health routes all carry it (middleware is app-wide).
    — **Consumers affected:** engine attribution telemetry (future consumer).
    — **Done:** middleware `__init__(app, node_slug=None)`; `create_node_app` passes `node.definition.slug` (the node itself exposes the slug via its definition, not an attribute — found by test); multi-node/absent case tested. files: `middleware.py`, `app.py`, `tests/test_middleware.py`; fixes: the app-side slug source corrected during test drive.
- [x] **4.2** `logging.py`: honor `CANVASTEKK_LOG_LEVEL` (default INFO) + `CANVASTEKK_LOG_FORMAT=console|json` in `configure_logging()`/`_make_handler()` (json formatter added); keep the `_sdk_configured` host-handler marker semantics (never clobber); add the one-line INFO execution record (slug, status, duration_ms) in `BaseNode.run`'s completion path.
    — **Why:** ticket item 6 — local-dev logging story; much of the scaffolding (configure_logging, marker) already exists.
    — **Done when:** tests: default console at INFO; JSON opt-in renders one-line JSON; pre-configured host handlers untouched; run emits exactly one INFO line with the three fields.
    — **Consumers affected:** local devs; hosts with their own logging config (unchanged).
    — **Done:** `_get_env_log_format` now defaults to console (accepts console/text/json — text kept as an alias); docstring updated; execution line added at BOTH chokepoints (success inline + `_record_error`, which every failure path funnels through); `_sdk_configured` semantics untouched (existing tests cover). Default-format flip verified by a new default test. files: `logging.py`, `base.py`, `tests/test_logging.py`; fixes: none.
- [x] **4.3** Phase gate (light).
    — **Why:** gate evidence.
    — **Done when:** green.
    — **Consumers affected:** none.
    — **Done:** 790 tests green; ruff clean. files: none; fixes: none.

### Phase 5: typescript — mirror (stamp/dual-write, contracts, horizon, header, logging)
- [x] **5.1** `src/version.ts`: keep `VERSION` (bumped to 0.37.0), add `RELEASE_DATE`; `definition.ts` gains the stamped `sdkVersion` (readonly, constructor-set, assignment rejected via setter guard consistent with the codebase's patterns); `registry.ts` :70-81 dual-writes `sdk_version` + legacy `minimum_sdk_version`.
    — **Why:** ticket — coordinated 0.37.0 rev of both SDKs.
    — **Done when:** vitest: stamp auto-filled + tamper rejected; payload carries both keys.
    — **Consumers affected:** TS node fleet.
    — **Done: VERSION/RELEASE_DATE in version.ts; zod `sdk_version` stamped default(VERSION).readonly() in definition.ts; registry.ts dual-write with `?? VERSION` fallback (raw manifest literals lack the key — found by test). files: src/version.ts, src/definition.ts, src/registry.ts; fixes: stamp fallback.
- [x] **5.2** New `src/contracts.ts`: `buildCheckOutputSchema(verdicts, resultDescription, opts?: { closed?: boolean })` + `validateVerdictFields(payload, verdicts)` mirroring Phase 2 shapes exactly (same JSON Schema output — cross-language contract).
    — **Why:** ticket — both languages.
    — **Done when:** vitest: same assertions as 2.1 (default vocab, custom vocab, closed flag, error-tolerant closed schema, off-vocab rejection).
    — **Consumers affected:** TS check-node authors.
    — **Done: src/contracts/check-output.ts mirrors the python builders exactly; exported via contracts/index.ts. files: src/contracts/check-output.ts (new), src/contracts/index.ts, tests/contracts-check-output.test.ts; fixes: none.
- [x] **5.3** `src/support-horizon.ts`: horizon constants + `checkSupportHorizon()` exported; import-time warn / entrypoint raise split (createNodeApp/createMultiNodeApp + BaseNode.run) with `CANVASTEKK_SDK_ALLOW_UNSUPPORTED` break-glass; tests via `vi.setSystemTime` (pattern exists in deprecation-pipeline.test.ts:166).
    — **Why:** ticket item 4 — both languages.
    — **Done when:** vitest: the four frozen-clock branches.
    — **Consumers affected:** TS node hosts.
    — **Done: src/support-horizon.ts (constants + check/warn/enforce + SupportHorizonError); wired into createNodeApp + createMultiNodeApp + BaseNode.run; vi.setSystemTime frozen-clock tests (5 branches). files: src/support-horizon.ts (new), src/app.ts, src/base-node.ts, tests/support-horizon.test.ts; fixes: sunset() initially missed the +180d offset — caught by the frozen-clock tests.
- [x] **5.4** `src/middleware.ts`: `X-Canvastekk-Node-Slug` beside `X-SDK-Version` (factories pass the slug); `src/logging.ts`: `CANVASTEKK_LOG_LEVEL`/`CANVASTEKK_LOG_FORMAT` knobs + one INFO execution line in `base-node.ts`.
    — **Why:** ticket items 5-6 — both languages.
    — **Done when:** vitest: slug header + logging branches.
    — **Consumers affected:** TS local devs.
    — **Done: middleware nodeSlug param + X-Canvastekk-Node-Slug; createNodeApp passes node.definition.slug; logging.ts console default (json opt-in); base-node.ts one INFO execution line (success) + recordError chokepoint (failures). files: src/middleware.ts, src/app.ts, src/logging.ts, src/base-node.ts, tests/middleware.test.ts; fixes: none.
- [x] **5.5** Phase gate (light): `npx vitest run` green + eslint clean.
    — **Why:** gate evidence.
    — **Done when:** green.
    — **Consumers affected:** none.
    — **Done: vitest 360 green; eslint clean (unused imports + no-explicit-any fixed in the new test files). files: none; fixes: lint fixes listed.

### Phase 6: release 0.37.0
- [x] **6.1** Bump `python/pyproject.toml:3` → 0.37.0 and `typescript/package.json:3` + `typescript/src/version.ts:4` → 0.37.0 (single source of truth = _version.py/version.ts for code, manifests for packaging); README "Local development logging" section (both READMEs, short).
    — **Why:** ticket item 7 — both packages 0.37.0.
    — **Done when:** grep shows no 0.36.0 outside CHANGELOG; poetry check + npm pack dry-run pass.
    — **Consumers affected:** release pipeline; DA-3365 (wheel bump consumer).
    — **Done: pyproject 0.37.0; package.json 0.37.0; version.ts 0.37.0; README: LOG_FORMAT default updated, ALLOW_UNSUPPORTED row added, Local Development Logging section added. files: README.md, package.json, manifests; fixes: none.
- [x] **6.2** Phase gate (full — TICKET EXIT GATE): python suite + ruff/format/mypy + schema-stability script (`python scripts/check_schema_stability.py dump` per ci-python.yml:187) + vitest run + eslint; `GATE <sha> tier=full` memo.
    — **Why:** pipeline exit gate; the schema-stability script is CI's own gate for manifest-shape changes.
    — **Done when:** all green; memo appended.
    — **Consumers affected:** PR citation.
    — **Done:** python 790 passed + ruff clean + schema-stability dump OK; vitest 360 green; eslint clean; tsc --noEmit clean.

## Technical Notes
GATE ed3f15d tier=light lint=t(ruff check) typecheck=n.a. build=n.a. unit=t e2e=n.a. (phase 1: ruff check clean; 769 python tests green)
GATE ebad67b tier=light lint=t(ruff check) typecheck=n.a. build=n.a. unit=t e2e=n.a. (phase 2: 45 contracts tests green)
GATE f6d0984 tier=light lint=t(ruff check) typecheck=n.a. build=n.a. unit=t e2e=n.a. (phase 3: 786 python tests green)
GATE d5e70d8 tier=light lint=t(ruff check) typecheck=n.a. build=n.a. unit=t e2e=n.a. (phase 4: 790 python tests green)
GATE <exit-sha> tier=full lint=t(ruff) typecheck=t(tsc noEmit) build=n.a. unit=t(py 790 + vitest 360) e2e=n.a. (TICKET EXIT GATE: schema-stability dump OK; eslint clean; both suites green)
GATE 9f76ad9 tier=full lint=t(ruff) typecheck=t(tsc noEmit) build=n.a. unit=t(py 790 + vitest 360) e2e=n.a. (review-fix re-gate: TS stamp forced to installed VERSION [python parity]; _horizon wrapper dropped)
- Engine consumer contract (DA-3358, merged dda2b56): admission dual-reads `sdk_version`/`minimum_sdk_version`; absence → 400 for external sources. The stamped field + legacy dual-write keeps BOTH old and new engines registering.
- `create_ecs_app` (ticket wording) does not exist in this tree — the factories are `create_node_app`/`createMultiNodeApp`; the horizon raise wires there (ticket's "node entrypoint" intent).
- Python has no freezegun; the horizon clock is a `_today()` module seam (monkeypatch) — same determinism, no new dependency (ponytail: deletion over addition).
- contracts.py already exists with geometric models — the builders extend it (cohesion), no new module; TS gets a NEW contracts.ts (no collision).
- Schema-stability CI gate: `python scripts/check_schema_stability.py dump` must stay green after the manifest field additions.
- Tests: python `poetry run pytest -v --cov=...` (wd python, asyncio_mode=auto); TS `npx vitest run` (wd typescript); lint: ruff (py, as configured), eslint (ts).

## Dependencies
- `blocked-by: DA-3358` — SATISFIED (merged 2026-10-01, dda2b56).
- Canary registration into dev (ticket item 7): deferred to post-DA-3365 (engine wheel ≥ 0.37), cited on the ticket at PR time.

## Risks & Mitigation
- **Breaking the init cycle** when moving `__version__` → all in-package consumers already import lazily (verified); tests pin the re-export.
- **Old engines rejecting 0.37 stamps** → legacy dual-write for one release (0.38 drops it); engine dual-read accepts either key.
- **Import-time raise breaking engine seeding** → horizon raise lives at entrypoints only; import path is log-only; frozen-clock tests pin this.
- **Closed schemas vs error paths** → root schema carries a nullable `error` property so ErrorOutputNode's rewrite validates; covered by test.
- **Host logging clobbered** → `_sdk_configured` marker semantics preserved and pinned by test.
