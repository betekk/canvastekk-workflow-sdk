# PLAN: SDK TS parity — host runtime ceiling → release v0.40.0

**Branch**: feat/DA-3609
**Issue**: https://github.com/betekk/canvastekk-tracker/issues/3661
**Base**: main

## Acceptance Criteria
- [x] TS schema carries `hard_max_runtime_seconds` (default 7200, ge 1) + effective-bound helper mirroring Python's `effective_runtime_seconds`
- [x] TS execute (`app.ts`) enforces `min(timeout_seconds, hard_max_runtime_seconds)`
- [x] TS probe (`cli.ts`) rejects over-ceiling budgets and reports `["manifest", "engine-request-mirror", "host-ceiling"]`
- [x] ruff + full pytest + full TS test suite green
- [ ] v0.40.0 GitHub release with both wheel and tgz assets (CI-derived post-merge)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `typescript/src/definition.ts` (schema field + `effectiveRuntimeSeconds`) | — | `app.ts`, `base-node.ts`, `cli.ts`, `tests/definition.test.ts`, external TS consumers (ifc `apps/node`) | medium |
| `typescript/src/app.ts:136` (execute timeout source) | definition.ts helper | every TS-hosted node's `/execute` (ifc-service-app) | low |
| `typescript/src/cli.ts` (`probeManifest`) | definition.ts helper | SDK CLI `probe` users, `tests/cli.test.ts` | low |
| `typescript/tests/registry.test.ts` (payload exclusion pin) | definition.ts field | engine registration payload contract | low |
| Release (CI on merge to main) | feat commit on main | ALL five consumer repos (DA-3610–3614 blocked-by #3661) | medium |

Python side is untouched; pytest re-runs as regression only.

## Implementation Phases

### Phase 1: Schema + helper (definition.ts)
- [x] **1.1** Add `hard_max_runtime_seconds: z.number().int().min(1).default(7200)` to `WorkflowNodeManifestSchema` with the host-side contract doc comment ("Hosts enforce min(timeout_seconds, hard ceiling); not sent in the engine registration request")
    — **Why:** the zod schema is the single manifest gate every TS host/CLI path parses through; without the field the other surfaces cannot derive the bound.
    — **Done when:** `WorkflowNodeManifestSchema.parse({})`-level manifests yield `hard_max_runtime_seconds === 7200` and a `0` value rejects (vitest in `definition.test.ts`).
    — **Consumers affected:** app.ts, cli.ts, base-node.ts (all parse manifests through this schema).
    — **Done:** zod field `hard_max_runtime_seconds` (default 7200, ge 1) added after timeout_seconds with the DA-3499 host-side contract comment; files: typescript/src/definition.ts; fixes: none
- [x] **1.2** Export `effectiveRuntimeSeconds(manifest)` helper returning `min(timeout_seconds, hard_max_runtime_seconds)`, doc comment mirroring Python's property ("every HOST derives its runtime bound from this")
    — **Why:** app.ts and probe must share one derivation so host enforcement and registration-time validation can't drift apart.
    — **Done when:** unit test proves min() semantics for timeout>ceiling, timeout<ceiling, and equal values.
    — **Consumers affected:** app.ts (Phase 2), cli.ts (Phase 3).
    — **Done:** `effectiveRuntimeSeconds()` exported from definition.ts + index.ts barrel, doc mirrors python's property; files: definition.ts, index.ts; fixes: none
- [x] **1.3** Add `tests/definition.test.ts` cases: default 7200, ge-1 rejection, effective-bound math
    — **Why:** the field is a frozen host-side contract (Python froze `NodeTimeoutError` watchdog details likewise); tests are the contract.
    — **Done when:** vitest runs the new cases green alongside existing schema tests.
    — **Consumers affected:** none (test-only).
    — **Done:** 5 new cases green (default 7200, ge-1 rejection, min() math incl. equal); files: tests/definition.test.ts; fixes: none

### Phase 2: Execute enforcement (app.ts)
- [x] **2.1** Change `src/app.ts:136` from `const timeout = def.timeout_seconds` to the effective bound via the Phase 1 helper
    — **Why:** Python's `app.py:397` waits on `effective_runtime_seconds`; the TS host must enforce the same capped bound or TS nodes can outlive their ceiling.
    — **Done when:** `app.test.ts` executes a node with `timeout_seconds` > `hard_max_runtime_seconds` and observes the AbortController fire at the capped value.
    — **Consumers affected:** all TS-hosted `/execute` calls (long-timeout nodes get capped at 7200 by default).
    — **Done:** execute derives AbortController timeout via effectiveRuntimeSeconds(def) (app.ts:137-139); async-execute test proves 408 at ~1s capped bound (not 5s budget) with 'after 1s' detail; files: src/app.ts, tests/app.test.ts; fixes: none

### Phase 3: Probe host-ceiling check (cli.ts)
- [x] **3.1** In `probeManifest`, after the engine-ceiling check, reject `timeout_seconds > hard_max_runtime_seconds` with a message mirroring Python's `_probe_definition` wording, append `"host-ceiling"` to the returned `probes` array (both success and failure returns), and update the `cli.ts:17` module doc's equivalence claim from "passes locally iff it passes registration" to "strictly stricter than registration — passing implies registration passes (not biconditional)"
    — **Why:** Python's probe is "strictly stricter than registration" — passing it implies registration passes; TS parity keeps the cross-language probe contract identical, and the tightened-gate convention requires the doc's equivalence claim to move with the gate.
    — **Done when:** `cli.test.ts` feeds a manifest with `timeout_seconds: 7201` (default ceiling) and asserts `valid: false` with the ceiling error; `7200` passes; `probes` array has length 3.
    — **Consumers affected:** CLI `probe` users; registration-precheck flows.
    — **Done:** host-ceiling rejection after engine ceiling; probes = 3 entries on both return paths; cli.ts:17 doc now 'strictly stricter than registration ... (not biconditional)'; tests: 7201 rejects w/ ceiling msg, 7200 passes, probes length 3; files: src/cli.ts, tests/cli.test.ts; fixes: 0 gate failures (1 deliberate contract update: pre-existing probes assertion moved to 3-entry list)

### Phase 4: Contract pins (registry/base-node tests)
- [x] **4.1** Add a payload-exclusion pin: `buildEngineRequest`/`buildRegistryPayload` output must NOT contain `hard_max_runtime_seconds`
    — **Why:** the field is host-side only; leaking it into the engine request would break the engine's whitelist validation (`extra keys outside the engine whitelist`).
    — **Done when:** `registry.test.ts` asserts the key is absent from both payload builders' output.
    — **Consumers affected:** engine registration contract (protects it).
    — **Done:** exclusion pins: buildRegistryPayload (registry.test.ts) and buildEngineRequest w/ explicit 3600 ceiling (cli.test.ts) both assert key absent; fixes: none
- [x] **4.2** Add a manifest-retention pin: the parsed definition served by GET `/manifest` (base-node `nodeDefinition`) retains `hard_max_runtime_seconds`
    — **Why:** Python re-adds the field on export because it is part of the `/manifest` shape; TS serves the parsed object directly, so the pin proves the field survives parse→serve without a re-add step.
    — **Done when:** test asserts the served definition object carries the field with its default.
    — **Consumers affected:** manifest consumers (engine registration reads).
    — **Done:** GET /manifest serves hard_max_runtime_seconds=7200 through parse->serve; files: tests/app.test.ts; fixes: none

### Phase 5: Verification gate + push
- [x] **5.1** Full gate: TS `vitest run` + `eslint src/ tests/` + `tsc --noEmit` (both tsconfigs) + Python regression `ruff check` + `pytest` (814 expected green)
    — **Why:** ticket exit gate is full-tier; Python re-run proves the TS-only change broke nothing in the shared repo.
    — **Done when:** gate memo `GATE <sha> tier=full` with zero failures recorded in the PLAN trace.
    — **Consumers affected:** PR creation (Step 10a cites this memo).
    — **Done:** full gate green: vitest 376/376, eslint clean, tsc src+tests clean, tsup build ok, ruff clean, pytest 822/822 (PLAN anticipated 814 — main gained 8 tests between v0.38.0 and v0.39.0; delta verified green); fixes: 0
- [x] **5.2** Commit implementation as `feat(sdk): host runtime ceiling TS parity (hard_max_runtime_seconds + effective bound + probe)` and push `feat/DA-3609`
    — **Why:** the `feat:` prefix is load-bearing — git-cliff on merge to main computes the minor bump 0.39.0 → 0.40.0 from it.
    — **Done when:** branch pushed, commit visible on `feat/DA-3609`.
    — **Consumers affected:** release CI (Phase 6).
    — **Done:** committed feat(sdk) on feat/DA-3609 and pushed; files: —; fixes: none

### Phase 6: Release (post-merge, CI-owned)
- [ ] **6.1** After the PR merges to main, verify the release workflow published v0.40.0: `gh release view v0.40.0 -R betekk/canvastekk-workflow-sdk` shows both `canvastekk_workflow_sdk-0.40.0-py3-none-any.whl` and `canvastekk-workflow-sdk-0.40.0.tgz`
    — **Why:** every consumer ticket (DA-3610–3614) pins the release-download URL; missing assets block the fleet.
    — **Done when:** release exists with both assets attached.
    — **Consumers affected:** DA-3610–3614 (unblocked on this).

## Technical Notes
- Python reference: `definition.py` `hard_max_runtime_seconds` (default 7200, ge 1), `effective_runtime_seconds` property, `__main__.py:191` ceiling rejection, `registry_dict` export re-add.
- TS zod default mode strips unknown keys — legacy TS-authored manifests keep parsing after this change (additive, no break).
- The base-node download-deadline swap to the effective bound is deliberately **out of scope** (deferred to #3498 upstream, file-disjoint).
- `probeManifest` early-return path must also carry the 3-entry probes list for shape consistency.

## Dependencies
None upstream. Downstream: DA-3610–3614 (#3663, #3665, #3664, #3662, #3666) are `blocked-by: #3661`.

## Risks & Mitigation
- *Engine payload whitelist break* → Phase 4.1 exclusion pin proves the field never enters `buildEngineRequest`.
- *TS manifests authored without the field* → zod `.default(7200)` keeps them valid (additive).
- *Release CI not firing* → Phase 6.1 verifies assets; fallback is `workflow_dispatch` on release.yml.

## Trace

GATE pre-commit-tree tier=full lint=t typecheck=t build=t unit=t e2e=n.a. — vitest 376/376 (full suite), eslint clean, tsc --noEmit src+tests clean, tsup build ok; python regression ruff clean, pytest 822/822 (TS-only change; python untouched); backend-only -> e2e n.a.; final implementation SHA cited by PR.
