# PLAN: Framework-optional core + registration-time route verifier

**Branch**: feat/104
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/104
**Base**: main

## Acceptance Criteria
- [x] Fresh `npm install @betekk/canvastekk-workflow-sdk` does NOT install express; `import { createNodeApp }` from the `/express` subpath works with express peer-installed
- [x] Fresh `pip install canvastekk-workflow-sdk` does NOT install fastapi/uvicorn; `[fastapi]` extra provides them; `create_node_app` import path documented and lazy
- [x] `register_node(verify=True)` refuses registration when `/health`, `/manifest`, or `/execute` are missing/malformed; registers when a conforming self-hosted node (non-SDK server) passes
- [x] `verify` CLI command prints per-route conformance results
- [x] node-builder skill template updated to the subpath/extra imports
- [x] Both test suites green; consumer migration notes in CHANGELOG (commit subjects — git-cliff renders them)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `typescript/package.json` (express → optional peer, `./express` export) | — | npm installers, tsup build, `base-node.ts` | high |
| `tsup.config.ts` + `src/express.ts` (new) | package.json export map | `/express` subpath consumers | medium |
| `src/index.ts` (drop express re-exports) | src/express.ts exists | root-entry consumers (breaking import move) | high |
| `src/base-node.ts` `createApp` (static → dynamic import, async) | src/express.ts | node authors calling `node.createApp()` (breaking: async) | high |
| `src/auth.ts` (express types → structural) | — | `NodeAuth` consumers in core (type-level only today) | medium |
| `python/pyproject.toml` (fastapi → `[fastapi]` extra) | — | poetry/pip, `poetry.lock`, bump script (regex already `[project]`-aware via #105) | medium |
| `python/app.py`, `router.py`, `auth.py` (fastapi imports lazy) | pyproject extra | `__init__.py` exports, tests, node authors (import paths UNCHANGED) | high |
| `python/__init__.py` (PEP 562 `__getattr__` for the three symbols) | lazy modules | every `import canvastekk_workflow_sdk` | medium |
| `python/conformance.py` (new verifier) | httpx, jsonschema (both core) | `register_node`, CLI, CI | medium |
| `python/registry.py` (`register_node(..., verify=)`) | conformance.py | CI/CD registration flows | medium |
| `python/__main__.py` (`verify` command) | conformance.py | node authors, CI | medium |
| node-builder `SKILL.md` + `.agents/` mirror | pyproject extras | node authors (sync BOTH copies — mirror-guard CI) | low |

Cross-module note: `base-node.ts ↔ app.ts` and `__init__ ↔ app/auth/router` are real in-repo cross-module edges → architecture review selected. `architecture-review-skill` is ABSENT from this session's skill set → skipped with note per Step 7 soft-dep rule; Step 9 code review + full gates backstop. CLI (`cli.ts`) confirmed free of app.ts imports — the verify command lands cleanly.

## Implementation Phases

### Phase 1: TypeScript — express to optional peer behind `/express`
- [x] **1.1** Create `src/express.ts` re-exporting `createNodeApp`, `createMultiNodeApp`, `CreateNodeAppOptions` from `./app.js`; add `"./express"` to `package.json` exports + `express` entry to `tsup.config.ts`
    — **Why:** the subpath is the new canonical import home; tsup must emit it as its own entry so express stays out of the root bundle
    — **Done when:** `dist/express.js` + `dist/express.d.ts` exist after build
    — **Consumers affected:** new subpath consumers
- [x] **1.2** `package.json`: move `express` from `dependencies` to `peerDependencies` (`"^5.3"`) with `peerDependenciesMeta.express.optional = true`
    — **Why:** optional peers are not auto-installed — the core install sheds express entirely
    — **Done when:** `dependencies` lacks express; `peerDependenciesMeta.express.optional` is true
    — **Consumers affected:** all installers (AC-1)
- [x] **1.3** `src/index.ts`: remove the four express-coupled exports (`createNodeApp`, `createMultiNodeApp`, `CreateNodeAppOptions`, app-types line)
    — **Why:** any static path from the root entry to app.ts pulls express into the core bundle — the re-export must go for the split to exist
    — **Done when:** `grep -n "app.js" src/index.ts` is empty; `npx tsc --noEmit` flags every in-repo root-importer (all fixed in 1.4/1.5)
    — **Consumers affected:** root-entry consumers (breaking — CHANGELOG subject carries it)
- [x] **1.4** `src/base-node.ts`: `createApp` becomes async via dynamic import (`const { createNodeApp } = await import("./app.js")`), returning `Promise<unknown>`; update every in-repo caller to `await` (tests included)
    — **Why:** the last static edge from core to app.ts; dynamic import lets tsup code-split express out of the root bundle while `node.createApp()` keeps working (express must be installed when called)
    — **Done when:** `grep -n 'from "./app.js"' src/base-node.ts` shows only the dynamic import; vitest green with awaited callers
    — **Consumers affected:** node authors using `node.createApp()` (breaking: async — CHANGELOG)
- [x] **1.5** `src/auth.ts`: replace `import type { Request, Response, NextFunction } from "express"` with minimal structural handler types local to core
    — **Why:** the emitted `auth.d.ts` would force `@types/express` resolution on every core consumer's typecheck even without express installed; structural types keep `NodeAuth` in core cleanly
    — **Done when:** `grep -n "from \"express\"" src/auth.ts` is empty; `tsc --noEmit` green
    — **Consumers affected:** `NodeAuth` consumers (no runtime change — types only)
- [x] **1.6** Gate Phase 1: `npm run build` + verify laziness (`grep -c "from\"express\"" dist/index.js` is 0 AND `dist/express.js` contains it), `vitest run`, `eslint`, `tsc --noEmit` ×2, `npm pack --dry-run` shows no express in deps
    — **Why:** the AC-1 proof — root artifact express-free, subpath artifact express-wired, suite green
    — **Done when:** all commands green; both grep assertions hold
    — **Consumers affected:** CI node jobs

### Phase 2: Python — fastapi to `[fastapi]` extra with lazy imports
- [x] **2.1** `python/pyproject.toml`: move `fastapi` from `[tool.poetry.dependencies]` to a new `[fastapi]` extra (`^0.143`); `poetry lock` + `poetry install --with dev` (lock: content-hash + fastapi optional-marker delta expected)
    — **Why:** the pip-side mirror of AC-2; #105's `[project]` layout makes this a two-line edit
    — **Done when:** base deps exclude fastapi; `[fastapi]` extra present; `poetry check` + `check --lock` green
    — **Consumers affected:** pip installers (AC-2)
- [x] **2.2** `python/app.py`, `router.py`, `auth.py`: move `from fastapi import ...` to a `TYPE_CHECKING` block (annotations — modules already use `from __future__ import annotations`) and function-local imports for runtime symbols (`FastAPI`, `APIRouter`, `Depends`, `HTTPException`, `JSONResponse`); no import-path changes
    — **Why:** import paths stay stable for existing consumers (ticket AC-2 "import path documented and lazy") while `import canvastekk_workflow_sdk` stops pulling fastapi
    — **Done when:** `grep -n "^from fastapi" python/canvastekk_workflow_sdk/{app,router,auth}.py` is empty; pytest green
    — **Consumers affected:** module-level import time only
- [x] **2.3** `python/__init__.py`: replace the three static imports with a PEP 562 module `__getattr__` lazy-loading `create_node_app`, `create_multi_node_app`, `NodeAuth` — raising ImportError naming `[fastapi]` when fastapi is absent; keep `__all__` unchanged
    — **Why:** the core import must not touch fastapi; the error must teach the fix (`pip install canvastekk-workflow-sdk[fastapi]`)
    — **Done when:** subprocess `python -c "import sys; sys.modules['fastapi']=None; import canvastekk_workflow_sdk"` succeeds; attribute access raises the `[fastapi]`-naming error (new test)
    — **Consumers affected:** every Python importer (transparent when fastapi installed)
- [x] **2.4** New test: fastapi-blocked subprocess import + lazy attribute error message; plus existing suite green (fastapi installed — lazy path invisible)
    — **Why:** AC-2's mechanical proof — the same suite that runs WITH fastapi must also prove the WITHOUT path
    — **Done when:** new test passes; full pytest green
    — **Consumers affected:** none beyond repo gates
- [x] **2.5** Gate Phase 2: `poetry check` + `check --lock`, `ruff check .`, `pytest`
    — **Why:** phase green-bar
    — **Done when:** all exit 0
    — **Consumers affected:** CI python jobs

### Phase 3: Route verifier + registration gate
- [x] **3.1** New `python/canvastekk_workflow_sdk/conformance.py`: `verify_node(base_url, *, timeout=10.0, api_key=None) -> VerifyReport` probing GET `/health` (200), GET `/manifest` (200 + jsonschema manifest validation), POST `/execute` with a malformed payload (expect 4xx contract-shape response); framework-free (httpx only); dataclass report with per-route results
    — **Why:** the enforcement half of the ticket — conformance becomes checkable for ANY server, not just SDK-built ones
    — **Done when:** unit tests via `httpx.MockTransport` cover pass + each failure mode
    — **Consumers affected:** register_node, CLI
- [x] **3.2** `python/registry.py`: `register_node(..., verify: bool = False, verify_timeout: float = 10.0)` — when True, run `verify_node` against the invoke target first; raise `RegistrationError` naming the failing routes on failure
    — **Why:** AC-3 — the registry refuses non-conforming nodes; the default stays False (no behavior change for existing flows)
    — **Done when:** MockTransport tests cover refuse + accept paths
    — **Consumers affected:** CI/CD registration automation (opt-in)
- [x] **3.3** `python/__main__.py`: `verify <url> [--api-key KEY] [--timeout S]` command printing per-route results and exiting non-zero on failure
    — **Why:** AC-4 — CI-usable standalone probe
    — **Done when:** CLI test covers pass + fail exit codes
    — **Consumers affected:** node authors, CI pipelines
- [x] **3.4** node-builder `SKILL.md` (bundled) + `.agents/` mirror: python install line → `canvastekk-workflow-sdk[fastapi,serve]`; TS install instructions → `@betekk/canvastekk-workflow-sdk` + `express` (or the `/express` subpath note)
    — **Why:** AC-5; both copies must change together (skill-mirror-guard CI) — the #102 lesson
    — **Done when:** both SKILL.md copies reference the extras; `diff -r .agents/skills data/skills` clean
    — **Consumers affected:** node authors
- [x] **3.5** Gate Phase 3 = ticket exit gate, full tier: both language suites (pytest, ruff, poetry checks; audit/build/vitest/eslint/tsc ×2) + dist-laziness grep + mirror diff; `tier=full` memo to `## Trace`
    — **Why:** the run's last gate is full; the memo is the Step 10a citation
    — **Done when:** everything green; memo recorded for the final tree SHA
    — **Consumers affected:** PR creation (Step 10a cites this memo)

## Technical Notes
- Breaking changes (CHANGELOG subjects carry both): root-entry import of `createNodeApp`/`createMultiNodeApp` moves to `@betekk/canvastekk-workflow-sdk/express`; `node.createApp()` returns a Promise (TS). Python import paths do NOT move (lazy, not relocated) — Python is non-breaking except the missing-extra error message.
- `cli.ts` confirmed free of app.ts imports — no severing needed there.
- Verifier deliberately framework-free (httpx): it must be able to probe nodes that do NOT use the SDK's server — that is its purpose.
- PR-overlap note: `#106` (zod) touched `typescript/package.json` while this branch was open — the 10a authoritative check governs; rebase + full re-gate before PR if it holds.

## Dependencies
None — no `blocked-by` tickets. Follow-up to #102.

## Risks & Mitigation
- **tsup code-splitting emits express into the root chunk anyway**: verified by the 1.6 dist grep; fallback is `treeshake`/manualChunks config or splitting base-node's server path into its own module.
- **auth structural types too loose**: keep the fields auth actually touches (headers, status, json); eslint no-explicit-any guards; runtime unchanged (types only).
- **Lazy-import misses a fastapi symbol**: the 2.4 subprocess test with `sys.modules['fastapi']=None` fails loudly on any static import left behind.
- **Verifier false-negatives against strict-but-conforming nodes**: probe payloads mirror the engine's own calls; report carries per-route detail so failures are diagnosable, and `verify` stays opt-in at registration.
- **Mirror drift on SKILL.md**: both copies edited in one step + mirror diff in the exit gate.

## Trace
<!-- gate memos append here -->
- TICKET-EXIT GATE 98e3e7d tier=full lint=t typecheck=t build=t unit=t e2e=n.a. — python: poetry checks + ruff + pytest 833 (9 new); typescript: audit 0 + build + vitest 378 + eslint + tsc x2; dist laziness (root 0 express refs, /express 3/3); skill mirrors in sync
- LOG 10a rebase onto origin/main (post-#106/#105 merges): package.json union-resolved (zod ^4.6 from main + express optional peer from branch), lock regenerated via npm install; re-gate below
- RE-GATE (post-rebase final tree) tier=full lint=t typecheck=t build=t unit=t e2e=n.a. — TS 378/audit 0/laziness proven, py 833/poetry checks/ruff, mirrors synced (all on v0.42.0 base)
- LOG CI red round 1: schema-stability job failed at 'Install dependencies (base)' — my blanket sed put -E fastapi on the schema job's base/PR installs too; base checks out main (no [fastapi] extra yet) -> poetry 'Extra [fastapi] is not specified'. Fix: -E only on the lint-and-test pytest install (line 106); schema-dump installs stay extras-free (its PR-side dump now doubles as a fastapi-free import proof)
- RE-GATE (red-fix tree) tier=full lint=t typecheck=t build=t unit=t e2e=n.a. — py 833 + ruff + poetry checks; TS 378 + audit 0 + build + eslint + tsc x2
- LOG CI red round 2: schema-stability PR dump failed with ModuleNotFoundError starlette — middleware.py (imported by core base.py) held a module-level starlette import for SDKVersionMiddleware; the phase-2 subprocess proof blocked fastapi but not starlette and the dev venv had starlette via -E fastapi, so it passed vacuously. Fix: SDKVersionMiddleware moved to gated _server_middleware.py (lazy via package __getattr__); middleware.py core-safe; lazy proof hardened to block BOTH fastapi and starlette
- RE-GATE (red-fix-2 tree) tier=full lint=t typecheck=t build=t unit=t e2e=n.a. — py 833 (hardened proof green), ruff, poetry checks; TS 378 + audit 0 + build + tsc x2; mirrors synced
- LOG (phase 2) fix 1: shim-block placement caused E402/I001; relocation pass corrupted router.py via partial-string cut — recovered with git checkout + line-based rewrite
- LOG (phase 2) fix 2: PEP 562 module __getattr__ does NOT service global lookups inside the module's own functions — replaced with function-local imports; fastapi/pydantic resolve string annotations against module globals, so create_node_app + NodeAuth factories publish the lazy names via globals().update/setdefault
- GATE (phase 2) tier=light lint=t typecheck=n.a. build=t unit=t e2e=n.a. — pytest 824 (incl. 2 lazy-server tests), ruff clean, poetry checks green
- GATE (phase 1) tier=light lint=t typecheck=t build=t unit=t e2e=n.a. — dist laziness proven: root bundle 0 express refs, /express entry 3/3 artifacts
    — **Done:** src/express.ts created; exports map + tsup entry added; dist/express.{js,cjs,d.ts} emitted; files: src/express.ts, package.json, tsup.config.ts; fixes: none
    — **Done:** express → peerDependencies ^5.3 with peerDependenciesMeta.optional; added to devDependencies (tests exercise the adapter); dependencies block now ajv+zod only; files: package.json, package-lock.json; fixes: 1 (fresh-worktree npm ci was missing before typecheck)
    — **Done:** index.ts express re-exports removed; tsc surfaced no other root importers (tests import src/app.js directly); files: src/index.ts; fixes: none
    — **Done:** createApp async via dynamic import; core-safe structural CreateNodeAppOptions defined in base-node (express-typed version stays on the subpath; documented cast at the dynamic boundary); no in-repo .createApp() callers to await; files: src/base-node.ts; fixes: none
    — **Done:** express type import replaced by AuthRequest/AuthResponse/AuthNext structural types + header() helper; all 4 middleware annotations + unauthorized() migrated; files: src/auth.ts; fixes: 1 (initial edit dropped isDevMode — restored)
    — **Done:** build OK; dist/index.js express refs 0; dist/express.{js,cjs,d.ts} 3/3; vitest 378; eslint OK; tsc tests OK; files: none; fixes: none
    — **Done:** fastapi → [fastapi] extra (PEP 508 range mirrors ^0.143); poetry lock regenerated; check + check --lock green; files: python/pyproject.toml, python/poetry.lock; fixes: none
    — **Done:** PEP 562 lazy shims attempted first, then replaced after gate failure: module __getattr__ serves EXTERNAL attribute access only — internal global lookups (FastAPI(, JSONResponse( inside create_node_app) bypass it. Final: TYPE_CHECKING blocks + function-local imports at runtime sites (create_node_app imports the five names and publishes to globals() for fastapi/pydantic hint resolution; NodeAuth factories + as_dependency inject Request); import paths unchanged; files: app.py, router.py, auth.py; fixes: 2
    — **Done:** __init__ __getattr__ with fastapi probe: missing extra → guided ImportError naming [fastapi]; present → resolves + caches; files: __init__.py; fixes: 1 (probe added after first proof showed attribute access returning the raw function unguided)
    — **Done:** tests/test_lazy_server.py: subprocess probe with sys.modules['fastapi']=None proves core import + guided errors; with-fastapi test proves resolution; 2 passed; ci-python.yml poetry install lines gained -E fastapi (3 sites); files: tests/test_lazy_server.py, .github/workflows/ci-python.yml; fixes: none
    — **Done:** poetry check + check --lock + ruff + pytest 824 all green; files: none; fixes: 3 (E402/ruff block relocation + router corruption recovered via git checkout; PEP 562 internal-lookup discovery; string-annotation hint resolution via globals injection)
    — **Done:** conformance.py: verify_node probes /health (200), /manifest (200 + WorkflowNodeManifest.model_validate), /execute (malformed must 4xx); framework-free (httpx+pydantic); frozen dataclasses VerifyReport/RouteCheck with ok + summary(); files: canvastekk_workflow_sdk/conformance.py; fixes: none
    — **Done:** register_node(..., verify=False, verify_timeout=10.0): probe-before-POST; RegistrationError carries report.summary(); requires invoke_type=http + invoke_url; files: registry.py; fixes: none
    — **Done:** CLI `verify <url> [--api-key] [--timeout]` prints per-route PASS/FAIL + verdict, exits 0/1; files: __main__.py; fixes: none
    — **Done:** SKILL.md bundled + mirror: install lines -> canvastekk-workflow-sdk[fastapi,serve]; extras prose updated; diff -r clean; files: data/skills/canvastekk-node-builder/SKILL.md, .agents/skills/canvastekk-node-builder/SKILL.md; fixes: none
    — **Done:** full tier green: pytest 833 (9 new conformance/gate/CLI tests), ruff, poetry checks, audit 0, build, vitest 378, eslint, tsc x2, root dist 0 express refs, /express 3/3 artifacts, mirrors in sync; files: PLANS/PLAN-104.md; fixes: 3 on the phase-2 gate carried into this phase's tree (documented in its LOG lines)
