# PLAN: Release v0.61.0 — ship the auth standardization Wave 1

**Branch**: feat/226 (docs leg) + promotion PR dev→prod (release leg)
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/226
**Base**: prod (lane promotion from dev)

## Acceptance Criteria

- [ ] v0.61.0 released (final) with wheel + sha256 + TS tgz attached; publish run green
- [ ] Clean-venv: wheel installs; `TekkNodeAuth` and `canvastekk_workflow_sdk.auth.core` import **without fastapi**; `create_authed_app` gate error (with fastapi absent) unchanged
- [ ] Consumer zero-change gate: CWN suite, CLS tests, ifc build green against the release artifacts with no consumer diffs
- [ ] `sdk-released` dispatch fired

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| release-content build (wheel+tgz from dev head, version 0.61.0 stamped ephemerally) | dev@db2a6cb (= PR #227, fully gated) | clean-venv check, all three consumer gates | med |
| clean-venv framework-free check | wheel build | release promotion decision | low |
| CWN suite vs wheel | wheel build | Wave-2 tickets (CWN#626 canary) | med |
| CLS tests vs wheel | wheel build | Wave-2 (CLS#467) | med |
| ifc build vs tgz | tgz build | Wave-2 (ifc#423) | med |
| docs PR feat/226→dev (this PLAN) | — | promotion PR (must merge first so dev carries the PLAN) | low |
| promotion PR dev→prod, `minor`, merge-commit | all gates green + docs PR merged | release.yml (mints v0.61.0 final), CWN (sdk-released dispatch) | high |

## Implementation Phases

### Phase 1: Pre-release verification (the gate)

- [ ] **1.1** Build release-content artifacts ephemerally: `git archive origin/dev` export → stamp version 0.61.0 exactly as release.yml does (`python3 scripts/bump_versions.py 0.61.0` + `npm version`) → `poetry build` (wheel) + `npm pack` (tgz) — in /tmp, nothing committed (ephemeral stamping law)
    — **Why:** every downstream check must run against the exact bytes release.yml will publish, without mutating any checkout.
    — **Done when:** wheel `canvastekk_workflow_sdk-0.61.0-*.whl` and `betekk-canvastekk-workflow-sdk-0.61.0.tgz` exist in /tmp; no repo file changed.
    — **Consumers affected:** 1.2–1.5.
- [ ] **1.2** Clean-venv framework-free check: fresh venv, `pip install <wheel>` (no extras), assert `from canvastekk_workflow_sdk import TekkNodeAuth, TekkAuthError` + `import canvastekk_workflow_sdk.auth.core` succeed, `sdk.create_authed_app` raises ImportError naming `[fastapi]`
    — **Why:** the ticket's framework-free AC, proven against the artifact (not the source tree).
    — **Done when:** probe exits 0 with all four assertions green.
    — **Consumers affected:** none (verification).
- [ ] **1.3** CWN zero-change gate: throwaway worktree of canvastekk-workflow-nodes origin/dev; fresh venv; install CWN python deps + the 0.61.0 wheel over the pin; run the app suite; assert green and `git -C <worktree> status` clean (zero consumer diffs)
    — **Why:** CWN is the largest consumer and the Wave-2 canary; its suite passing against the new wheel with untouched files is the alias-wave proof at scale.
    — **Done when:** suite result ≥ baseline expectation (1091 passed / 1 skipped at v0.60.0; suite may exceed it), zero modified files.
    — **Consumers affected:** CWN (informational; no changes land).
- [ ] **1.4** CLS zero-change gate: throwaway worktree of canvastekk-llm-service origin/dev; fresh venv; install gateway deps + the 0.61.0 wheel; run `pytest fastapi_gateway_app/tests` (unit lane); assert green, zero modified files
    — **Why:** CLS imports root `NodeAuth` ×2 — the lazy-gate compat must hold against the artifact.
    — **Done when:** unit suite green, zero modified files.
    — **Consumers affected:** CLS (informational).
- [ ] **1.5** ifc zero-change gate: throwaway worktree of canvastekk-ifc-service-app origin/dev; point apps/node SDK dep at the local 0.61.0 tgz; `npm install` + build + test; assert green
    — **Why:** the TS packaging fix must be proven against the only TS consumer with its own express — the exact scenario the pack-test simulated.
    — **Done when:** install + build + tests exit 0 with own-express satisfying the optional peer.
    — **Consumers affected:** ifc (informational).
- [ ] **1.6** Gate memo: all four checks green → append `tier=full` line to Trace
    — **Why:** Step 10a's promotion-PR citation requires the full-tier memo naming the gated tree.
    — **Done when:** `GATE <sha> tier=full` line present in this PLAN's Trace.
    — **Consumers affected:** none (verification record).

### Phase 2: Release promotion

- [ ] **2.1** Docs PR: push feat/226 (this PLAN) → PR to dev → merge (watcher, squash)
    — **Why:** the pipeline contract lands the PLAN on the lane; promotion PR then carries it to prod.
    — **Done when:** PR merged; dev head contains PLANS/PLAN-226.md.
    — **Consumers affected:** none (docs-only).
- [ ] **2.2** Promotion PR dev→prod: merge-commit, labels `minor` + `enhancement`, body cites the Phase-1 gate memo + `Closes #226`; merge via watcher (`--merge`, NOT squash — long-lived head, #223 precedent)
    — **Why:** the `minor` label is load-bearing (label-driven bump: fallback patch would mint 0.60.1); merge-commit preserves lane ancestry; this triggers release.yml → v0.61.0 final.
    — **Done when:** PR merged with merge commit on prod; release.yml run starts.
    — **Consumers affected:** release.yml, CWN (sdk-released dispatch).

### Phase 3: Post-merge verification

- [ ] **3.1** Verify the release: v0.61.0 final exists; wheel + .sha256 + tgz attached; publish run green
    — **Why:** the release must be real and complete before Wave 2 unblocks.
    — **Done when:** `gh release view v0.61.0` lists all three assets; the release run's jobs are green.
    — **Consumers affected:** all Wave-2 tickets.
- [ ] **3.2** Verify `sdk-released` dispatch fired (repository-dispatch event / CWN workflow run)
    — **Why:** the dispatch is CWN's rebuild signal — the release isn't done for consumers until it fires.
    — **Done when:** dispatch event or downstream CWN run observed.
    — **Consumers affected:** CWN rebuild flow.

## Technical Notes

- Version stamping is ephemeral (never committed): release.yml stamps all five sources via `scripts/bump_versions.py` + `npm version`; the local build mirrors this in a /tmp export.
- release.yml label logic: prod-only — the promotion PR's `minor` label → next final = v0.61.0 (latest final v0.60.0, minor bump). Dev pushes mint `-dev.N` prereleases regardless (harmless; already fires on every dev merge).
- CWN pin override: install the wheel into the gate venv; CWN files stay untouched so `test_sdk_pin_drift.py` (a file-consistency check) stays green.
- CLS suite: unit lane only (`fastapi_gateway_app/tests` without `-m integration` — integration needs the local-db compose profile).
- ifc: dep override is a package.json edit INSIDE the throwaway worktree only (never pushed) — the AC is "install+build+test green against the artifact", the real pin bump is ifc#423.

## Dependencies

- blocked-by: betekk/canvastekk-workflow-sdk#225 (MERGED — PR #227, db2a6cb)
- Blocks: CWN#626, CLS#467, ifc#423 (all Wave-2)

## Risks & Mitigation

- **Consumer suite fails against the wheel** → stop before promotion; fix SDK-side (the whole point of gating before release); Wave 2 stays blocked.
- **Wrong semver minted (patch instead of minor)** → `minor` label verified on the PR before merge; release run's tag checked in 3.1 before declaring success.
- **Promotion squash (ancestry break)** → watcher uses `--merge` (head-class rule: long-lived head).
