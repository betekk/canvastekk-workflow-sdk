# PLAN: Security-driven dependency upgrades and extras repair

**Branch**: feat/102
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/102
**Base**: main

## Acceptance Criteria
- [ ] `npm audit --omit=dev` reports 0 vulnerabilities
- [ ] OSV clean for locked starlette, anyio, qs, proxy-addr, fast-uri, express, fastapi, pydantic
- [ ] `poetry check` exits 0; `jwt`/`keycloak` extras resolve
- [ ] Base install excludes uvicorn; `canvastekk-workflow-sdk[serve]` installs it
- [ ] Python `pytest` + `ruff check` green; TS `vitest` + `eslint` + `tsc --noEmit` + build green
- [ ] CHANGELOG documents the express 5 consumer note, uvicorn demotion, extras fix
- [ ] Both manifests still at 0.40.1 (release script owns the bump)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/pyproject.toml` | — | `python/poetry.lock`, CI python jobs, end-user `pip install` (incl. `[jwt]`/`[keycloak]`/`[serve]` extras), node-builder skill template (installs uvicorn itself — unaffected) | medium |
| `python/poetry.lock` | `python/pyproject.toml` | CI reproducibility, `poetry install` | low |
| `typescript/package.json` | — | `typescript/package-lock.json`, CI node jobs, `npm install` consumers, `extra_routes` consumers (express 5 router types — CHANGELOG note) | medium |
| `typescript/package-lock.json` | `typescript/package.json` | CI reproducibility, `npm ci` | low |
| `CHANGELOG.md` | all rows above | release-notes readers, git-cliff config | low |
| `README.md` (verify-only) | manifests | SDK users | low |

Cross-module note: consumers are external (end-user installs, CI), not in-repo code modules — no code paths change; zero reviewer selection is justified, Step 9 code review backstops.

## Implementation Phases

### Phase 1: Python dependency repair
- [x] **1.1** Edit `python/pyproject.toml`: bump `fastapi` constraint `^0.135` → `^0.143`; remove `uvicorn` from `[tool.poetry.dependencies]`; declare `PyJWT = {version = "^2.15", optional = true}` and `cryptography = {version = "^50", optional = true}`; add `serve = ["uvicorn"]` extra plus `uvicorn = {version = "^0.54", optional = true}` dependency
    — **Why:** fastapi bump is the only path to patched starlette/anyio; undeclared extras make `poetry check` fail and `pip install ...[jwt]` a no-op; uvicorn is never imported (FastAPI's own convention: no bundled server, extras encode the serving standard)
    — **Done when:** `grep` shows `fastapi = "^0.143"`, no bare `uvicorn =` in the main dependency block, `optional = true` on PyJWT/cryptography/uvicorn, extras `jwt`/`keycloak`/`serve` all reference declared names
    — **Consumers affected:** end-user installs (smaller base footprint), `[serve]` users (new extra)
    — **Done:** manifest rewritten with all three optional deps + serve extra; files: python/pyproject.toml; fixes: none
- [x] **1.2** Regenerate `python/poetry.lock` (`poetry lock`) and sync the venv (`poetry install --with dev`)
    — **Why:** the lockfile must reflect the manifest or CI/dev diverge; the venv must match for the phase gates to be meaningful
    — **Done when:** lock contains fastapi 0.143.x, starlette ≥1.3.1, anyio ≥4.14.2, pydantic 2.14.0; no `uvicorn` entry outside extras-conditional paths; `poetry install` exits 0
    — **Consumers affected:** CI python jobs
    — **Done:** lock regenerated (fastapi 0.143.0, starlette 1.7.0, anyio 4.15.1, pyjwt 2.15.1, cryptography 50.0.2, uvicorn 0.54.0) + `poetry update pydantic --lock` (2.14.0); files: python/poetry.lock; fixes: none
- [x] **1.3** Gate Phase 1: `poetry check` (must exit 0 — extras resolve), `pytest` (green), `ruff check` (green)
    — **Why:** proves the extras repair and the fastapi 0.143 runtime compatibility against the SDK's behavior suite
    — **Done when:** all three commands exit 0
    — **Consumers affected:** none beyond the repo gates
    — **Done:** poetry check exit 0 (deprecation warnings only — deferred item), ruff clean, pytest 822 passed; files: python/tests/test_base.py; fixes: 1 (test_create_app route introspection moved to `app.openapi()["paths"]` — fastapi 0.143 nests routes under `_IncludedRouter`)

### Phase 2: TypeScript security upgrade
- [x] **2.1** Edit `typescript/package.json`: `express` `^4.21` → `^5.3`
    — **Why:** express 4's `qs ~6.15.1` pin caps below the 6.16.0 fix — v4 can never clear the 2 DoS moderates; 5.3.0 also pins `proxy-addr ^2.0.8` (critical fix) and matches the already-used `@types/express ^5`
    — **Done when:** `grep '"express"' package.json` shows `^5.3`
    — **Consumers affected:** `extra_routes` consumers must pass express 5 routers (CHANGELOG note in Phase 3)
    — **Done:** constraint set to `^5.3`; files: typescript/package.json; fixes: none
- [x] **2.2** Refresh `typescript/package-lock.json` (`npm install`)
    — **Why:** lockfile must carry express 5.3.0 + patched transitives (qs 6.16.0, proxy-addr 2.0.8, fast-uri fix)
    — **Done when:** lock resolves express 5.3.0; `npm ls qs proxy-addr` shows 6.16.x / 2.0.8+; `npm ci` dry-run consistent
    — **Consumers affected:** CI node jobs
    — **Done:** lock has express 5.3.0, qs 6.16.0, proxy-addr 2.0.8, body-parser 2.3.0; fast-uri needed `npm update fast-uri` (3.1.2 → 3.1.8 — ajv caps ^3.0.1, fixes are in-range patches `npm install` won't bump); files: typescript/package-lock.json; fixes: 1
- [x] **2.3** Gate Phase 2: `npm audit --omit=dev` (0 vulnerabilities), `npm run build`, `vitest run`, `eslint`, `tsc --noEmit` + `tsc --noEmit -p tsconfig.tests.json`
    — **Why:** proves the express 5 runtime migration against the SDK's test suite (routes are static paths; no wildcard patterns exist)
    — **Done when:** audit reports 0 vulnerabilities and every command exits 0
    — **Consumers affected:** none beyond the repo gates
    — **Done:** audit 0 vulnerabilities; build, vitest (378 passed), eslint, tsc src+tests all green; files: none beyond 2.1/2.2; fixes: none

### Phase 3: Documentation and exit gate
- [ ] **3.1** Add CHANGELOG.md entries: express 5 consumer note (`extra_routes` must be express 5), uvicorn → `[serve]` extra demotion (install uvicorn separately or via the extra), `jwt`/`keycloak` extras repair, fastapi/pydantic bumps
    — **Why:** all four are consumer-visible changes; release notes are the announcement channel for the express 5 migration
    — **Done when:** CHANGELOG contains all four notes under an Unreleased/current-version section consistent with existing format
    — **Consumers affected:** CHANGELOG readers, release tooling
- [ ] **3.2** Sweep docs for stale dependency claims (grep README.md, docs/, skill templates for "uvicorn", express version claims); edit only where a claim is now false
    — **Why:** doc-claims-drift rule — the node-builder skill template already installs uvicorn itself and must keep working verbatim; no doc may imply the SDK bundles a server
    — **Done when:** remaining uvicorn mentions are run-commands or explicit separate-install instructions; README express/fastapi version claims (if any) match the new constraints
    — **Consumers affected:** SDK users reading docs
- [ ] **3.3** Ticket exit gate: full tier — re-run both language gate suites on the final tree plus an OSV spot-check on the changed locks; append the `tier=full` memo to `## Trace`
    — **Why:** the pipeline's last gate is full; its memo line is the Step 10a PR citation
    — **Done when:** `GATE <sha> tier=full` line recorded in `## Trace` for the final tree SHA, and both manifests still read `0.40.1` (`grep '"version"' package.json` / `grep '^version' pyproject.toml`)
    — **Consumers affected:** PR creation (Step 10a cites this memo)

## Technical Notes
- Deferred (separate future tickets): zod 3→4 migration (`zod/v4` subpath exists in 3.25), `[tool.poetry]` → `[project]` packaging migration (Poetry 2.x deprecation warnings are out of scope), framework-optional peer split + registration-time route verifier.
- Version stays 0.40.1 in both manifests; `scripts/bump_versions.py` owns the 0.41.0 bump at release (parity: both manifests bump together).
- Security evidence (2026-10-10): OSV queries — starlette 1.0.0: 10 advisories (GHSA-82w8-qh3p-5jfq, GHSA-86qp-5c8j-p5mr, GHSA-jp82-jpqv-5vv3, GHSA-wqp7-x3pw-xc5r, GHSA-x746-7m8f-x49c, PYSEC-2026-161/2280/2281/248/249); anyio 4.13.0: 4 (GHSA-5p39-cfhj-2xmp fixed 4.14.2, +3); npm audit: proxy-addr critical (GHSA-jqcg-44mw-7w3h), qs ×2 moderate (GHSA-x5fp-wj9c-mxmx, GHSA-4mjr-xmp4-gh2g), fast-uri high, body-parser moderate; all direct deps otherwise clean.

## Dependencies
None — no `blocked-by` tickets.

## Risks & Mitigation
- **express 5 behavioral changes** (async error forwarding, body-parser 2.x): SDK routes are all static paths; full vitest suite gates the migration; CHANGELOG carries the consumer note.
- **fastapi 0.143 / starlette 1.7 drift**: pytest suite (TestClient-based) gates it; constraint caret keeps future 0.x drift bounded.
- **poetry extras metadata**: `poetry check` gate proves `jwt`/`keycloak`/`serve` resolve; a fresh `pip install` of the built wheel is the belt (skipped — CI publish flow validates on release).
- **Stale venv**: `poetry install --with dev` in 1.2 re-syncs before gates run (venv was observed behind the lock: pydantic 2.13.4 vs 2.13.5).

## Trace
<!-- gate memos append here -->
- LOG 1.3 fix attempt 1: fastapi 0.143 nests the router under `_IncludedRouter` in `app.routes`; `test_create_app` now asserts via `app.openapi()["paths"]` (public, version-stable surface)
- GATE 3add7ee tier=light lint=t typecheck=n.a. build=n.a. unit=t e2e=n.a.
- LOG 2.2 fix attempt 1: `npm install` never bumps locked transitives — fast-uri needed `npm update fast-uri` (3.1.2 → 3.1.8, in ajv's ^3.0.1 range; 8 advisories all patched ≤3.1.8)
- GATE ba12624 tier=light lint=t typecheck=t build=t unit=t e2e=n.a.
