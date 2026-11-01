# PLAN: Wave 1 — auth/core split, Tekk aliases, explicit auth errors

**Branch**: feat/225
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/225
**Base**: prod (d4b4d1f, v0.60.0 promotion head; PR targets dev — dev is tree-identical to prod)

## Acceptance Criteria

- [ ] `auth/core.py` imports clean with fastapi uninstalled (CI test), zero fastapi/starlette imports
- [ ] `auth/fastapi.py` is adapter-only; `auth/__init__.py` preserves `NodeAuth` lazy gate + adds eager `TekkNodeAuth`
- [ ] All censused HTTPException raise sites (19 by full census; ticket said 17) map to `TekkAuth*`; adapter responses byte-identical to v0.60.0 (status + detail)
- [ ] `Tekk*` aliases exported python + TS; consumer-import freeze test green
- [ ] TS: express absent from `dependencies`; pack-test green
- [ ] ADR amended; python + TS suites green

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/auth.py` → `auth/` package (core.py, fastapi.py, __init__.py) | — | `app.py:31` (imports `NodeAuth, _AuthBackend` at module level), `bootstrap.py:66`, root `__init__._LAZY_SERVER_EXPORTS`, tests `test_auth.py`/`test_app.py`/`test_conformance.py`/`test_lazy_server.py`, external: CLS root `NodeAuth` ×2 | high |
| `python/canvastekk_workflow_sdk/__init__.py` (eager Tekk* exports) | auth/core.py | every importer of the root package | med |
| `python/tests/test_lazy_server.py` (extended probe) | auth/core.py | CI only | low |
| `python/tests/test_consumer_import_freeze.py` (new) | final surface | CI only; guards the Wave-2 contract | low |
| `typescript/package.json` (express out of dependencies) | — | ifc `apps/node` (declares own `express ^5.3` — verified), CI `npm ci --legacy-peer-deps` (devDependencies still carries express) | med |
| `typescript/src/auth.ts` + `src/index.ts` (TekkNodeAuth alias) | — | ifc root imports, TS tests | low |
| `typescript/scripts/pack-test.sh` + `.github/workflows/ci-typescript.yml` | package.json fix | CI | low |
| `docs/NODE-SERVICE-LAYOUT.md` (ADR amendment) | — | none (documentation) | low |

## Implementation Phases

### Phase 1: Python auth split (core / fastapi adapter / compat package)

- [ ] **1.1** Create `auth/core.py` — framework-free: `TekkAuthError` base (`.status`, stable `.code`) + `TekkAuthNotConfigured`/`TekkAuthMissingCredential`/`TekkAuthInvalidCredential`/`TekkAuthTokenExpired` (401) + `TekkAuthUnavailable` (503); `_is_dev_mode`; `_VerifyUnavailableError` sentinel; `TekkAuthBackend` ABC + `TekkApiKeyAuth`/`TekkCentralAuth`/`TekkJwtAuth`/`TekkKeycloakAuth` with `verify(<header value>) -> dict` (logic moved verbatim from v0.60.0 backends, HTTPException sites → TekkAuth* with byte-identical detail strings); `TekkNodeAuth` factory (same signatures, minus the fastapi globals hack)
    — **Why:** the framework-free verify standard is the deliverable; everything else hangs off it.
    — **Done when:** module imports with zero fastapi/starlette (stdlib + lazy PyJWT only); every v0.60.0 raise site has a mapped TekkAuth* raise.
    — **Consumers affected:** fastapi.py (1.2), __init__.py (1.3), root __init__ (1.4); future non-FastAPI hosts.
- [ ] **1.2** Create `auth/fastapi.py` — top-level `from fastapi import HTTPException, Request`; `_AuthBackend` ABC (`authenticate(request)` abstract, `as_dependency`, `__call__`); `_ApiKeyAuth`/`_CentralAuth`/`_JwtAuth`/`_KeycloakAuth` as **subclasses of the core Tekk backends** adding only `authenticate(request)` = header extraction → `self.verify(...)` → TekkAuthError-to-HTTPException mapping (`status_code=exc.status, detail=str(exc)`); `NodeAuth` factory (same four staticmethods, same signatures)
    — **Why:** adapter-only seam; subclassing preserves class-level monkeypatch targets (`type(auth)._remote_verify`) the existing tests use.
    — **Done when:** `test_auth.py` passes unmodified except the private-import surface still resolving via the package.
    — **Consumers affected:** `app.py` (unchanged), all FastAPI consumers (byte-identical responses).
- [ ] **1.3** Convert `auth.py` → `auth/__init__.py` — eager `from .core import ...` (Tekk* + errors + `_is_dev_mode`); module `__getattr__` serving `NodeAuth`, `_AuthBackend`, `_ApiKeyAuth`, `_CentralAuth`, `_JwtAuth`, `_KeycloakAuth`, `_VerifyUnavailableError` from `.fastapi` behind the same guided fastapi ImportError as root (`[fastapi]` in message)
    — **Why:** compat layer — every existing importer path (`from canvastekk_workflow_sdk.auth import NodeAuth`, app.py:31, tests) keeps resolving; core stays importable without fastapi.
    — **Done when:** `python -c "from canvastekk_workflow_sdk.auth import NodeAuth, _ApiKeyAuth, _is_dev_mode"` succeeds with fastapi installed; `import canvastekk_workflow_sdk.auth.core` succeeds with fastapi blocked.
    — **Consumers affected:** app.py, bootstrap.py, tests, CLS.
- [ ] **1.4** Root `__init__.py`: eager-export `TekkNodeAuth` + the five error classes from `.auth.core` (add to `__all__`, import after `_version`); `_LAZY_SERVER_EXPORTS` unchanged
    — **Why:** "Tekk* aliases exported python" AC; eager import is fastapi-free so the lazy contract holds.
    — **Done when:** `from canvastekk_workflow_sdk import TekkNodeAuth, TekkAuthError` works; `test_lazy_server.py` probe still passes (core import blocked-env clean).
    — **Consumers affected:** all root importers (additive only).
- [ ] **1.5** Gate: ruff + full python suite (existing tests are the compat proof)
    — **Why:** existing tests are the compat proof for the split; running them immediately catches migration slips at the smallest diff.
    — **Done when:** ruff clean and full pytest suite green in the fresh venv.
    — **Consumers affected:** none (verification step).

### Phase 2: Guard tests (python)

- [ ] **2.1** Extend `test_lazy_server.py` probe: `import canvastekk_workflow_sdk.auth.core` with fastapi+starlette blocked; `sdk.TekkNodeAuth` eager without fastapi; `from canvastekk_workflow_sdk.auth import NodeAuth` gated with `[fastapi]`-naming ImportError; static source scan — `auth/core.py` contains no fastapi/starlette import lines
    — **Why:** AC 1 is CI-enforced, not aspirational.
    — **Done when:** probe subprocess exits 0 on those assertions; breaking core.py with a fastapi import fails the scan.
    — **Consumers affected:** CI only.
- [ ] **2.2** Add `test_consumer_import_freeze.py` — census table of every enumerated consumer import (CWN root/exceptions/definition/testing/contracts/create_authed_app; CLS root `NodeAuth` + `app.create_node_app` ×2 + BaseNode/definition; engine `registry.build_registry_payload`, `node_token.*`, `_version.__version__`, `workflow.models`, `definition.SDK_SERVED_CONTRACT_ROUTES`; ifc-equivalent root names) resolved via importlib+getattr
    — **Why:** freezes the import surface the Wave-2 zero-change gate depends on.
    — **Done when:** all table rows resolve with fastapi installed; removing any frozen name fails the test.
    — **Consumers affected:** CI only; contract guard for Wave 2.
- [ ] **2.3** Add taxonomy assertions to `test_auth.py`: each TekkAuth* class carries its v0.60.0 status + stable code + default detail string
    — **Why:** the error taxonomy is a public contract (`.code` stability).
    — **Done when:** assertions pass; a status/detail drift fails them.
    — **Consumers affected:** none (additive tests).

### Phase 3: TS plane

- [ ] **3.1** `typescript/package.json`: remove `express` from `dependencies` (peer + peerDependenciesMeta + devDependencies stay)
    — **Why:** the packaging bug — dependency entry defeats the optional peer and ships a framework to every install.
    — **Done when:** `dependencies` contains only `ajv`, `zod`; `npm ci && npm run build && npx vitest run` green (devDependencies still provides express for tests/build).
    — **Consumers affected:** ifc apps/node (own express, verified safe), all future installs.
- [ ] **3.2** `src/auth.ts`: `export const TekkNodeAuth = NodeAuth;` alias; `src/index.ts`: re-export `TekkNodeAuth` alongside `NodeAuth`
    — **Why:** Tekk* canonical naming on both planes (AC 4).
    — **Done when:** typecheck+lint+tests green; `import { TekkNodeAuth } from "@betekk/canvastekk-workflow-sdk"` resolves in dist.
    — **Consumers affected:** additive; ifc optional adoption.
- [ ] **3.3** `tests/auth.test.ts`: alias-identity assertions (`TekkNodeAuth === NodeAuth`, static methods present)
    — **Why:** alias is load-bearing (same object), pin it.
    — **Done when:** vitest green.
    — **Consumers affected:** none.
- [ ] **3.4** Add `typescript/scripts/pack-test.sh`: build → `npm pack` → temp dir → install tgz (no express) → dynamic-import root (assert ok, ajv/zod resolved) → dynamic-import `./express` (assert rejection naming `express`); wire as a CI step in `ci-typescript.yml` after Build
    — **Why:** AC 5 — proves the pack artifact is installable without express and fails clearly, not just the source tree.
    — **Done when:** script exits 0 locally and in CI; reintroducing express to `dependencies` would still pass install but the test would no longer be proving absence (absence itself is asserted by 3.1's file shape).
    — **Consumers affected:** CI.
- [ ] **3.5** Gate: npm ci, tsc --noEmit, eslint, vitest run, build, pack-test
    — **Why:** the TS changes span packaging + source + CI; one combined gate proves the plane end-to-end.
    — **Done when:** all five commands exit 0 in typescript/.
    — **Consumers affected:** none (verification step).

### Phase 4: ADR amendment

- [ ] **4.1** `docs/NODE-SERVICE-LAYOUT.md`: add the framework-free law — root = framework-free core including auth; framework face = extra (python) / subpath + optional peer (TS); new auth features land framework-free in both planes first, adapters second; aliases never removed before a major
    — **Why:** AC 6 — the ADR is what stops the next drift.
    — **Done when:** section present, states the four clauses, references auth/core.py + src/auth.ts as the anchors.
    — **Consumers affected:** documentation only.
- [ ] **4.2** Exit gate (full): ruff + python suite + tsc + eslint + vitest + build + pack-test; write `tier=full` memo
    — **Why:** ticket exit gate is full-tier per the verification-loop contract; Step 10a cites this memo.
    — **Done when:** every gate command green on the final tree; `GATE <sha> tier=full` line appended to this PLAN's Trace.
    — **Consumers affected:** none (verification step).

## Technical Notes

- Raise-site census (auth.py @ d4b4d1f): 19 HTTPException sites — L107, L111, L237, L255, L263(503), L265, L320, L324, L335, L337, L402, L410(503), L442, L450, L454, L474, L496, L507, L509 — each maps to a TekkAuth* carrying the exact v0.60.0 detail string; internal `_VerifyUnavailableError` (L207/209/215) stays a core sentinel, mapped to `TekkAuthUnavailable("Token validator unavailable")` in `verify()`; the two optional-dep ImportErrors (L305, L387) stay verbatim.
- Detail strings are the response contract: "Authentication not configured", "Invalid API key", "Missing API key", "Token validator unavailable", "Invalid node token", "JWT authentication not configured", "Missing Bearer token", "Token has expired", f"Invalid token: {e}", "Keycloak server URL and realm must be configured", f"Failed to fetch JWKS from Keycloak: {e}", "Invalid token header", "Token header missing required 'kid' field", f"Token signing key (kid='{kid}') not found in JWKS".
- `authenticate()` returns identical dicts (auth_mode/run_id/node_id/payload keys) — dev_bypass included, moved to core.
- Keycloak cooldown retry re-raise (`except HTTPException: raise` L488) becomes `except TekkAuthError: raise` in core.
- Poetry packaging needs no change (`packages` include covers the new subpackage). Repo version stays 0.54.0 — release stamping is ephemeral (release.yml).
- TS: `npm ci --legacy-peer-deps` already ignores peers; devDependencies keeps express for tests. Node engine >=24 (dynamic-import probes fine).
- Local gates: python via fresh venv at /tmp/opencode/sdk225-venv (`pip install -e "python[fastapi]" pytest pytest-asyncio ruff`); TS via `npm ci` in typescript/.

## Dependencies

- Parent epic: betekk/canvastekk-workflow-sdk#224
- Blocks: #226 (release v0.61.0) → CWN#626, CLS#467, ifc#423
- External deps: none new (PyJWT/cryptography stay optional extras)

## Risks & Mitigation

- **Byte-identical response drift** → taxonomy tests assert exact detail strings; existing test_auth.py assertions (already detail-string-exact) are the primary proof.
- **Missed consumer import** → freeze test (2.2) enumerates the audited census; CWN/CLS/ifc suites re-run against artifacts in #226's gate.
- **Monkeypatch-target breakage in tests** → adapters subclass core backends; class-level patches keep landing on the class the tests see.
- **TS install breakage for silent express dependents** → only known TS consumer (ifc) declares own express (verified 2026-11-01); pack-test proves the artifact shape; #423 re-proves on real bump.
