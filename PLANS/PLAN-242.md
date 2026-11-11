# PLAN: register CLI has no retry on engine 5xx — registrations fail on transient restart windows

**Branch**: feat/242
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/242
**Base**: dev (canvastekk-workflow-sdk)

## Acceptance Criteria

- [x] AC1 — the register CLI retries engine 5xx and transport errors with exponential backoff (4 attempts: initial + 3 retries, 2/4/8s sleeps)
- [x] AC2 — terminal 4xx (incl. 401/403 auth, 400 contract-reject, 409 version conflict) fails fast on the FIRST attempt — no retry, existing exit codes and messages byte-identical
- [x] AC3 — every failed attempt prints a per-attempt line to stderr (`attempt n/N failed (reason); retrying in Xs`); final-attempt failures fall through to the existing exit mapping unchanged
- [x] AC4 — tests prove the loop: 5xx-then-200 succeeds (attempt count asserted), persistent 5xx exhausts and exits 5, 4xx exits 4 after exactly one call, transport-error-then-200 succeeds. (Fleet pin-bump consumption rides the repos' existing pin workflow — rollout note, not code.)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/__main__.py` — `_run_register`'s POST call site (+ 2 module constants, `time` import) | — (leaf; the by-name GET and all other `_request` users untouched) | every node repo's deploy job that runs `canvastekk_workflow_sdk register` (the incident path: report-v2, ifc, ml, llm deploys); the orchestrator app-band node jobs that wait on them | med — retry-too-much delays real failures; AC1's bound (4 attempts, ≤14s sleep) caps the worst case; AC2 keeps terminal errors at today's latency |
| `python/tests/test_cli_register.py` (or sibling test file) — retry loop tests | mirrors the existing `fake_urlopen` patch seam (tests lines 135–153) | CI on PRs; future editors of `_run_register` | low |
| `python/canvastekk_workflow_sdk/registry.py` `register_node` | **NOT edited** — library function has zero production callers (tests + docs only; verified by grep) | external SDK consumers (single-shot semantics preserved, unchanged) | none — deliberately out of scope; no incident ever rode this path |

## Implementation Phases

### Phase 1: bounded retry on the CLI register POST

- [x] **1.1** In `__main__.py`: add module constants `_REGISTER_ATTEMPTS = 4` and `_REGISTER_BACKOFF_S = 2.0`; import `time`; wrap ONLY the POST in `_run_register` in an attempt loop — on `urllib.error.HTTPError` with `e.code >= 500` or `(urllib.error.URLError, OSError)`, when attempts remain: print the per-attempt line to stderr and `time.sleep(backoff * 2**(attempt-1))`; on terminal 4xx or final attempt, re-raise so the existing except-blocks map exit codes unchanged
    — **Why:** the engine's ALB answers 502 through every restart window (each orchestrator run restarts the engine before nodes by design); registration is an idempotent upsert by slug (engine returns created/updated/unchanged; same version+data is a no-op), so a bounded retry is always safe and converts the fleet's most expensive false failure into a sub-15s pause
    — **Done when:** a 502-then-200 sequence exits 0 with two per-attempt stderr lines; a persistent 502 makes exactly 4 attempts then exits 5 with today's message; `urlopen` call count is asserted in tests
    — **Consumers affected:** all node deploy jobs (fewer false exit-5s); orchestrator band jobs (fewer skipped verification tails)
    — **Done:** retry loop wraps only the POST (constants _REGISTER_ATTEMPTS=4, _REGISTER_BACKOFF_S=2.0); >=500 + URLError/OSError retry with 2/4/8s sleeps and per-attempt stderr lines; 4xx and final-attempt re-raise into the untouched exit mapping; files: python/canvastekk_workflow_sdk/__main__.py; fixes: none
- [x] **1.2** Add tests beside the existing register CLI tests, using the established `patch("urllib.request.urlopen", side_effect=...)` seam with `time.sleep` patched out: (a) 502, 502, 200 → exit 0, 3 calls; (b) HTTP 409 → exit 4, exactly 1 call; (c) 502 × 4 → exit 5, 4 calls; (d) `URLError` × 2 then 200 → exit 0
    — **Why:** the loop's three behaviors (retry-recover, fail-fast, exhaust) each need a pre-edit counterexample — today every one of these exits on the first failure
    — **Done when:** all four tests pass and `pytest python/tests/` stays green
    — **Consumers affected:** CI gate on this repo
    — **Done:** 4 tests in TestRegisterRetry (502x2-then-201 exits 0 with 3 POSTs + sleeps [2,4] + both attempt lines; 409 exits 4 with exactly 1 call and zero sleeps; 502x4 exits 5 with 4 calls + sleeps [2,4,8]; URLError-then-201 exits 0) — file green: 25 passed; files: python/tests/test_cli_register.py; fixes: none

## Technical Notes

- Scope guard: `registry.py:register_node` (httpx library path) is NOT retried — zero production callers (grep-verified; exported API + test_conformance only). If a future consumer needs it, that's its own ticket; this one is AC-driven on the CLI path that produced every incident.
- The by-name verify GET after successful POST stays as-is (already failure-tolerant — swallows to `node_id=""`).
- Rollout (AC4 tail): the wheel reaches fleet deploy jobs via the repos' regular `betekk-gha`/SDK pin bumps (e.g. devops #1232-style PRs); no coordinated action needed — registrations become resilient as pins move.
- Backoff math: 2 + 4 + 8 = 14s max added latency before the pre-existing failure path; observed 502 windows (Nov 3 + Nov 6/7 incidents) closed within seconds.

## Dependencies

None. Evidence on the issue: run 41602690750 (Nov 3), plus the three incidents commented 2026-11-07 (report-v2 smoke 503, ifc cold-lambda rejects ×2, ml engine-502 exit 5).

## Risks & Mitigations

- **Risk:** retry masks a persistently-broken engine, delaying the failure signal by ≤14s. **Mitigation:** bounded attempts; final failure falls through to today's exit-5 message verbatim — CI diagnosis unchanged.
- **Risk:** sleeping in tests. **Mitigation:** `time.sleep` patched in tests (also asserts the backoff schedule).
- **Risk:** the cold-lambda 503-contract-rejection incident (ifc, exit 4) is NOT fixed by this — the engine's 400 wraps the node's own cold-start 503s, and retrying a 400 is wrong (masks real contract errors). **Mitigation:** documented here; if it recurs enough to matter, the node-side warm-up (deploy step ordering) is the correct lever, not blanket 4xx retries.

## Trace

- LOG: full-gate escalation — deploy-machinery anchor (the fleet register gate every node deploy branches on)
- LOG: full-suite collection errors are environmental (system python lacks the fastapi extra; CI installs it) — touched-surface tests green, ruff clean
- GATE 89b2689343 tier=full lint=t(ruff) typecheck=n.a build=n.a unit=t e2e=n.a
