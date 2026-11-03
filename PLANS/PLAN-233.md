# PLAN: Pre-flight registry diff in ctk probe

**Branch**: feat/233
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/233
**Base**: dev

## Acceptance Criteria

From ticket #233:

- [ ] `ctk validate`/`ctk probe` performs the registry diff when engine URL + `ctk_` key are present
- [ ] All five matrix rows behave exactly as specified, with field names in the failure message
- [ ] New-node case passes without false blocks
- [ ] Identical re-registration passes (deploy-rerun idempotency preserved)
- [ ] Offline / no-creds / unreachable-engine skips the diff with a warning and exit 0
- [ ] Bump level (major/minor/patch) is never asserted
- [ ] Unit tests cover all five rows + the offline skip

AC1 amended at authoring and **confirmed by the user in the Step 7 requirements
gate** (round 1/2): the diff surface is `ctk probe --engine-url <url>` —
`validate` stays the fast offline validator; the diff needs the engine, so it
rides `probe --engine-url` and `validate` gains no engine dependency. The
sixth matrix row (older-version-than-published → fail fast) was confirmed in
the same round.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/registry.py` (new `fetch_published_definition`, `diff_against_published`) | httpx, existing `_registry_auth_header` | `__main__` probe; future CLI verify paths | low |
| `python/canvastekk_workflow_sdk/__main__.py` (`_probe_definition` + probe arg parsing) | registry.py helpers | `ctk probe` users (node authors, CI) | low |
| `python/tests/test_registry_diff.py` (new) | both above | CI | low |

No cross-module consumers beyond the SDK package itself (thin map — no
architecture review expected). No frontend files.

## Implementation Phases

### Phase 1: registry fetch + diff helpers

- [x] **1.1** Add `fetch_published_definition(engine_url, name, *, token, timeout=10.0) -> dict | None` to `registry.py` — GET `{engine_url}/api/workflows/nodes/by-name/{name}` with `_registry_auth_header(token)`; 404 returns `None` (new node); HTTP errors propagate to caller for degradation
    — **Why:** single engine-truth fetch every later step reuses; mirrors the engine's own `GET /by-name/{name}` route
    — **Done when:** function exists with docstring; unit test proves 200-parse, 404→None, and auth-header ride (`ctk_` → Bearer)
    — **Consumers affected:** none yet (new API)
    — **Done:** implemented in registry.py (also tolerates trailing-slash base URLs); tests: 200-parse+Bearer, 404→None, X-Service-Token legacy, transport-error propagation, slash tolerance; files: registry.py, tests/test_registry_diff.py; fixes: ruff import-sort autofix
- [x] **1.2** Add `diff_against_published(local_payload: dict, published: dict) -> list[str]` to `registry.py` — compares every local manifest key except the engine's `NON_COMPARISON_FIELDS` `{id, name, owner, source, registered_at, node_status, last_registered_by}` against `published.get(key)`; returns changed field names
    — **Why:** mirrors `workflow_node_service.diff_node_definitions` so "passes locally ⇔ passes registration" holds field-for-field
    — **Done when:** unit tests show changed detection, unchanged pass, and non-comparison fields ignored
    — **Consumers affected:** none yet (new API)
    — **Done:** implemented as the shared-key intersection minus `ENGINE_NON_COMPARISON_FIELDS` (local-only keys skipped — engine drops them at validation, so its own diff never sees them); tests: changed/unchanged/engine-assigned-ignored/local-only-skipped/version-drift; files: registry.py, tests/test_registry_diff.py; fixes: none

### Phase 2: probe wiring + behavior matrix

- [x] **2.1** Wire `--engine-url <url>` into the `probe` command in `__main__.py`; absent (or `CANVASTEKK_NODE_REGISTRATION_KEY`/`CANVASTEKK_REGISTRY_TOKEN` unset) → registry diff skipped with a `"registry diff skipped (no --engine-url / no credential)"` note, exit behavior unchanged
    — **Why:** offline degradation is an AC; the flag is opt-in so plain CI stays unaffected
    — **Done when:** probe without `--engine-url` produces identical report to today plus the skip note; exit 0
    — **Consumers affected:** `ctk probe` users (additive flag)
    — **Done:** `_flag_value` module helper (register's nested `_flag` now delegates — dedup at source); probe branch passes engine_url+env token; skip paths for missing flag and missing credential each carry a distinct warning and never touch validity; tests: both skip rows; files: __main__.py, tests/test_main.py; fixes: missing module-level `import os`, import-order autofix
- [x] **2.2** Extend `_probe_definition` with the registry diff producing the six-row matrix: new-node (published is None) → pass "new node"; same version + no diff → pass "unchanged"; same version + diff → `valid=False` naming changed fields; higher version + diff → pass; higher version + no diff → pass + warning "bumped but nothing changed"; lower version → `valid=False` "older than published latest". Report gains a `registry_diff` block `{status, published_version, changed_fields}`; unreachable engine → skip note, exit 0
    — **Why:** the ticket's core behavior; fail-fast for the two states the engine rejects (409 immutability, older-version conflict)
    — **Done when:** unit tests cover all six rows + unreachable-engine skip; bump level never asserted anywhere
    — **Consumers affected:** `ctk probe` users (report gains a key; failures now possible pre-deploy)
    — **Done:** `_apply_registry_diff` implements all six rows + unreachable-engine and unparsable-version skips; `version` field excluded from the newer-branch identical-data check; report carries the `registry_diff` block; 11 new tests incl. the bump-level-never-asserted row; files: __main__.py, tests/test_main.py; fixes: none

### Phase 3: docs

- [x] **3.1** Update the `probe` usage/help text in `__main__.py` and the README CLI section (if it documents `probe`) with `--engine-url`; note the degradation behavior
    — **Why:** an undocumented flag is an unused flag; authors need to know CI can opt in
    — **Done when:** `ctk` help output and README (if applicable) mention the flag and offline default
    — **Consumers affected:** none (docs)
    — **Done:** module docstring usage block gains the probe line, help text updated, README gains a "Registration Pre-flight (registry diff)" section with the credential requirement, degradation behavior and the never-judges-bump-level note; files: __main__.py, README.md; fixes: none

## Technical Notes

- Engine contract (verified 2026-11-03 against canvastekk-workflow-engine dev):
  - `GET /api/workflows/nodes/by-name/{name}` → `WorkflowNodeSchema` (404 = not found)
  - Immutability diff: `WorkflowNodeSchema.model_fields` minus `NON_COMPARISON_FIELDS` (workflow_node_service.py:47)
  - Older-than-latest semver → `ResourceConflictError`; same version + changed data → 409 `node_version_immutable`
- Auth: `ctk_`-prefixed token rides `Authorization: Bearer` via existing `_registry_auth_header` (registry.py:241)
- Credential env: `CANVASTEKK_NODE_REGISTRATION_KEY` (fallback `CANVASTEKK_REGISTRY_TOKEN`) — same as register
- Semver ordering without new deps: reuse whatever the SDK already imports (`packaging.Version` is used by engine; check SDK deps first — if absent, tuple-compare dotted ints)
- Ticket's "writes a version" wording: manifest echo tests elsewhere already assert presence; nothing to add here

## Dependencies

- None; engine endpoint already live on dev (used by deploy verify-by-name).

## Risks & Mitigations

- Engine response shape drift vs `WorkflowNodeSchema` → diff ignores unknown keys on either side (compare local keys only), so engine-side additive fields never false-positive
- Auth scopes: by-name GET currently unauthenticated on dev; probe still sends the Bearer so it works when auth tightens
- CI adoption is per-repo (flag is opt-in) — no behavior change for existing pipelines

## Trace

GATE c7e6866 tier=light lint=t typecheck=n.a build=n.a unit=t e2e=n.a
GATE 18a09d8 tier=light lint=t typecheck=n.a build=n.a unit=t e2e=n.a
LOG 3 pre-existing failures in test_main.py (validate subprocess tests, /usr/bin/python3 lacks the package) — fail on clean tree too, environmental, not this change.
GATE ae2e816 tier=full lint=t typecheck=n.a build=n.a unit=t e2e=n.a
LOG exit gate: full suite 994 passed after poetry install -E fastapi in the worktree env (6 collection errors and 3 subprocess failures were env gaps, not code). Pre-existing ruff-format drift in 3 untouched files left alone per scoped-lint rule.
