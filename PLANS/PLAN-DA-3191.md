# PLAN: SDK — native NEXT-key support in NodeAuth.apiKey (python + TypeScript)

**Branch**: feat/DA-3191
**Issue**: https://betekk.atlassian.net/browse/DA-3191
**Base**: main

## Acceptance Criteria
- [x] Python `_ApiKeyAuth.authenticate` accepts `X-API-Key` matching `CANVASTEKK_API_KEY` OR `CANVASTEKK_API_KEY_NEXT` (empty filtered); custom `key_env_var` derives `<key_env_var>_NEXT`
- [x] TypeScript `apiKey()` middleware: same dual-key behavior
- [x] Fail-closed preserved (unset current + no NEXT → 401 not-configured; wrong key → 401 invalid; constant-time compares)
- [x] `CANVASTEKK_DEV_MODE` bypass unchanged
- [x] Tests: python 5 new (next-accepted, current-still-accepted, empty-next-ignored, unknown-rejected, next-only edge); TS 2 new (next-accepted, empty-next-ignored)
- [x] README (TS) + docstrings document the rotation window
- [x] Version bump 0.33.0 → 0.34.0 (pyproject + package.json + version.ts) for the release flow

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/auth.py` | — | every python node via `NodeAuth.apiKey()`; ifc `authed_app.py` mirrors semantics | med |
| `typescript/src/auth.ts` | — | node apps declaring `NodeAuth.apiKey()` (ifc node app) | med |
| version files | auth changes | release workflow (auto-tags on main push) | low |

## Implementation Phases

### Phase 1: dual-key auth (both languages) + tests + docs + version bump
- [x] **1.1** Python `_ApiKeyAuth`: `_expected_keys()` (current + `<key_env_var>_NEXT`, empty-filtered); `authenticate` accepts either via constant-time compare
    — **Why:** zero-downtime rotation (DA-3192/DA-3199) needs nodes to accept two keys; the SDK must own the contract so every declared node gets it
    — **Done when:** `pytest tests/test_auth.py` green incl. 5 new NEXT tests
    — **Consumers affected:** all SDK-based node apps (backward-compatible: single-key envs behave exactly as before)
- [x] **1.2** TS `apiKey()`: same dual-key filter + `some(timingSafeEqual)`
    — **Done when:** `npm test` green incl. 2 new NEXT tests (340 total)
    — **Consumers affected:** TS node apps
- [x] **1.3** README rotation-window notes + version bump to 0.34.0
    — **Done when:** version files at 0.34.0; TS README documents NEXT
    — **Consumers affected:** release workflow (publishes 0.34.0 on merge)

## Technical Notes
- `<key_env_var>_NEXT` derivation keeps custom-var consumers consistent.
- Empty NEXT = unset (matches SSM by-path absence; matches ifc authed_app.py semantics).
- Consumers adopt via SDK pin bumps on their next deploys (rotation runbook gates on that).

## Dependencies
None. Downstream: DA-3199 rotation prefers SDK-based nodes on NEXT (ifc python fallback covers meanwhile).

## Risks & Mitigation
- Extra accepted key widens auth surface → only while the operator sets NEXT (rotation window), same protection class as the main key.
- Behavior change is additive-only: single-key deployments unaffected (covered by existing tests, all 46 python + 340 TS green).
