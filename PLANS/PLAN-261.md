# PLAN: Release-PR trigger replaces prod-lane release gates

**Branch**: feat/261
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/261
**Base**: dev

## Acceptance Criteria

- [ ] Push to `dev` whose merged PR lacks the `release` label: no tag minted, no GitHub Release, publish job skipped
- [ ] Merged PR labeled `release` + `minor`: final tag minted, changelog + GitHub Release created, publish job runs
- [ ] Label-lookup API failure ⇒ `is_release=false` (no release), warning logged — verified by review or simulation
- [ ] `prod` absent from every workflow trigger list
- [ ] `release` label exists; PR semver-label semantics unchanged (exactly one semver label per PR)
- [ ] `sdk-released` dispatch payload byte-identical (event-type + `sdk_version`/`breaking`/`breaking_changes`/`released_at`)

**Verification split (stated, not silent)**: AC-1 and AC-3 are proven live by this PR's own merge (it carries no `release` label → the Release workflow must mint nothing) and by code review of the fail-closed branch. AC-2's live proof is #264's dogfood release — this ticket delivers and statically verifies the mechanism (actionlint + review); it does not cut a release. AC-6 is enforced by diff shape: no step below `tag_version`/`new_tag` is edited.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `.github/workflows/reusable-release.yml` | — | `release.yml` release job (calls it; consumes `new_tag`, `new_version`, now `is_release`) | high — release mechanism |
| `.github/workflows/release.yml` | reusable-release.yml outputs | push events on `dev`; publish job → GitHub Packages (wheel + tgz), release assets, `sdk-released` dispatch to canvastekk-workflow-nodes (CWN/CRS/CASA listen) | high — fleet consumers on dispatch |
| `.github/workflows/ci-python.yml` | — | PR status checks, push CI on dev | low |
| `.github/workflows/ci-typescript.yml` | — | PR status checks, push CI on dev | low |
| gh-side `release` label (created in-session) | — | `release_intent` label lookup | low |

Cross-module consumers exist beyond the repo (nodes repo dispatch) → architecture review selected at Step 7.

## Implementation Phases

### Phase 1: reusable-release.yml — release-intent gate
- [x] **1.1** Add `is_release` output at both levels: workflow `on.workflow_call.outputs` (description + `value: ${{ jobs.release.outputs.is_release }}`) and the `release` job's `outputs:` (`${{ steps.release_intent.outputs.is_release }}`)
    — **Why:** `release.yml`'s publish gate must key on release intent, not branch name; workflow_call outputs are the only channel upward.
    — **Done when:** `actionlint` accepts both blocks and the output resolves through the caller expression.
    — **Consumers affected:** `release.yml` publish job gate (Phase 2).
    — **Done:** is_release threaded through workflow_call.outputs and job outputs; actionlint green on all four workflows; files: reusable-release.yml; fixes: none
- [x] **1.2** Replace the `bump_type` step with a combined `release_intent` step (github-script, no `if:`): one `listPullRequestsAssociatedWithCommit` call emitting `is_release` (label set contains `release`) and `type` (`major`/`minor` from labels, else `patch`). Lookup exception or empty PR list ⇒ `is_release=false` + `::warning` — **fail closed**. Keep the #172 provenance comment, restated for inverted semantics.
    — **Why:** Single API call decides both *whether* to release and the bump size; today's #172 fallback (downgrade-to-patch) is safe for size but would be fail-open for release intent.
    — **Done when:** Step emits both outputs on all three paths (label present / absent / lookup-failed) — exercised by the AC-3 simulation script (4.2).
    — **Consumers affected:** `tag_version`, changelog/release gates (1.3, 1.4), publish gate via 1.1.
    — **Done:** bump_type (branch-gated, patch-fallback) replaced by unconditional fail-closed release_intent emitting is_release + type, #172 provenance restated with inverted semantics; simulation deferred to 4.2 per plan; files: reusable-release.yml; fixes: none
- [x] **1.3** Retire the `is_prod` output from the `prerelease` step (line 114) and retarget its three consumers (`bump_type`-position gate is gone with 1.2; changelog gate :157; GitHub-Release gate :167) to `steps.release_intent.outputs.is_release == 'true'`
    — **Why:** Branch-name identity no longer implies release; the label lookup is the single source of intent. `branch`/`suffix` outputs stay (beta-channel gate :179 still reads `branch`).
    — **Done when:** `grep is_prod` in the file returns zero hits; beta gate still references `prerelease.outputs.branch`.
    — **Consumers affected:** changelog + GitHub Release creation steps.
    — **Done:** is_prod echo removed (comment points to release_intent), changelog + GitHub Release gates retargeted to is_release, step names reworded "(release merges only)", beta gate untouched on prerelease.outputs.branch; grep is_prod → zero; files: reusable-release.yml; fixes: none
- [x] **1.4** `tag_version` (mathieudutour action): add `if: steps.release_intent.outputs.is_release == 'true'`; `release_branches: prod` → `dev`; `default_bump: ${{ steps.release_intent.outputs.type || 'patch' }}`
    — **Why:** Only release-PR merges may mint tags; with the step gated, `dev` must be the action's release branch so it mints bare finals; bump size comes from the intent step.
    — **Done when:** actionlint passes; an ungated dev push structurally cannot reach the action (step-level `if`).
    — **Consumers affected:** tag minting → `new_tag`/`new_version` outputs → publish job.
    — **Done:** step-level if added, release_branches: dev with rationale comment (bare finals; ordinary pushes never reach the step), default_bump sourced from release_intent.type; actionlint green; files: reusable-release.yml; fixes: none

### Phase 2: release.yml — trigger and publish gate
- [x] **2.1** `on.push.branches: [dev, prod]` → `[dev]` (keep `workflow_dispatch`)
    — **Why:** Single-lane; prod pushes stop triggering releases once #262 deletes the branch — removing it now makes the cutover a no-op for CI.
    — **Done when:** `prod` appears nowhere in the file's trigger config.
    — **Consumers affected:** none beyond the workflow itself.
    — **Done:** trigger narrowed to [dev], workflow_dispatch kept; files: release.yml; fixes: none
- [x] **2.2** Publish job: `if: github.ref_name == 'prod' && needs.release.outputs.new_tag != ''` → `if: needs.release.outputs.is_release == 'true' && needs.release.outputs.new_tag != ''`; retitle `(prod finals only)` → `(release merges only)`
    — **Why:** The publish lane (wheel/tgz build, GitHub Packages, `sdk-released` dispatch) is the payload-contract surface — gate swap only, zero step edits below it (AC-6).
    — **Done when:** actionlint passes; `git diff` shows no hunk below the publish job's `env:` block.
    — **Consumers affected:** GitHub Packages consumers, canvastekk-workflow-nodes rebuild (CWN/CRS/CASA).
    — **Done:** gate swapped to is_release && new_tag, job retitled; diff = 3 single-line hunks at :6/:24/:26, zero hunks below the gate — dispatch payload byte-identical; actionlint green; files: release.yml; fixes: none

### Phase 3: CI lane triggers
- [ ] **3.1** `ci-python.yml`: both `branches: [dev, prod]` lists (push + PR) → `[dev]`
    — **Why:** prod lanes retire; triggers must not reference a soon-deleted branch.
    — **Done when:** `grep -n "prod" ci-python.yml` empty.
    — **Consumers affected:** PR status checks (target unchanged: dev).
- [ ] **3.2** `ci-typescript.yml`: both `branches: [dev, prod]` lists → `[dev]`
    — **Why:** Same as 3.1, TS lane.
    — **Done when:** `grep -n "prod" ci-typescript.yml` empty.
    — **Consumers affected:** PR status checks.

### Phase 4: verification and label
- [ ] **4.1** Run `actionlint` over all four touched workflows; fix every finding
    — **Why:** Expression/schema linter is the strongest local gate for workflow surgery (catches dangling outputs, bad `if:` syntax).
    — **Done when:** `actionlint` exits 0 on all four files.
    — **Consumers affected:** gate memo evidence.
- [ ] **4.2** AC-3 simulation: a standalone Node script feeding the `release_intent` decision logic three mocked label sets (with `release`, without, lookup-thrown) and asserting `is_release`/`type` outputs — the exact script text embedded in the step, extracted to `/tmp` for execution, then asserted and discarded
    — **Why:** AC-3 demands review-or-simulation proof of fail-closed; the negative branch cannot be exercised on GitHub without a real outage.
    — **Done when:** Script prints three PASS lines; no repo file added (evidence goes in the gate memo, not the tree).
    — **Consumers affected:** AC-3 sign-off.
- [ ] **4.3** Create the `release` label in-repo (`gh label create release --color 5319e7 --description "Merging a PR with this label cuts a release"`)
    — **Why:** The trigger label must exist before any release PR can carry it; gh-side, not a repo diff.
    — **Done when:** `gh label list` shows `release`.
    — **Consumers affected:** future release PRs, `release_intent` lookup.
- [ ] **4.4** Record the negative-path live check on ticket #261 after merge: this PR merges without the `release` label → the Release run on that merge must complete with no tag, no GitHub Release, publish skipped
    — **Why:** AC-1's strongest proof is the production system itself refusing to release this very merge.
    — **Done when:** Post-merge observation comment posted on #261 (or handed to the merge watcher report if timing lands after run end).
    — **Consumers affected:** AC-1 sign-off, #264 baseline.

## Technical Notes

- Fail-closed inversion: #172's downgrade-to-patch fallback survives only for *bump size*; *release intent* never defaults to true.
- Tag action mints bare finals because the step runs only when `dev ∈ release_branches` and the intent gate held; ordinary pushes skip the step entirely — strictly quieter than the pre-#3857 era of `-dev.N` prerelease tags.
- `concurrency: release-${{ github.ref_name }}` (reusable :31) stays — serializing release runs per branch is still correct on dev.
- `workflow_dispatch` stays on release.yml for debugging; a dispatch resolves intent from the HEAD commit's PR — normally no `release` label → no-op.
- Dead-but-harmless after this change: the `uat`/`beta` channel cases in the `prerelease` step (org convention; #252/#263 territory).
- Dispatch payload (release.yml :299-305) untouched — byte-identical by diff shape.

## Dependencies

- None blocking (first ticket of epic #260).
- Downstream: #262 (branch deletion), #263 (docs + #252 re-scope), #264 (dogfood) all `blocked-by` this ticket.

## Risks & Mitigation

- **Fail-open regression on lookup failure** → fail-closed branch is the review focus + AC-3 simulation (4.2).
- **Accidental release from a feature PR mislabeled `release`** → deliberate act by a labeler with push rights; #263 documents the label discipline.
- **Tag action behavior change on `release_branches: dev`** → step-level `if` means the action only ever runs on gated pushes; #264's real release is the end-to-end proof.
- **#252 collision (betekk-gha migration preserving two-lane)** → epic decision recorded on #252; #263 re-scopes its AC.

## Trace

LOG gate-escalation Phase 1: full tier — anchor: CI/workflow file touched + Dependency & Consumer Map node with cross-module consumers (reusable-release.yml → release.yml caller).
LOG fix r1 (unit axis): pytest collection failed — ModuleNotFoundError fastapi; env created without extras. Root cause: canonical CI invocation is `poetry install -E fastapi` (ci-python.yml:118). Repaired env, re-ran full unit axis green. total_fixes=1.
GATE 60ebec4 tier=full lint=t typecheck=t build=t unit=t e2e=n.a
LOG gate-escalation Phase 2: full tier — anchor: CI/workflow file touched (release.yml trigger + publish gate; publish lane is the dispatch-contract surface).
GATE f174261 tier=full lint=t typecheck=t build=t unit=t e2e=n.a
LOG gate-escalation Phase 3: full tier — anchor: CI/workflow files touched (ci-python.yml, ci-typescript.yml trigger lists).
