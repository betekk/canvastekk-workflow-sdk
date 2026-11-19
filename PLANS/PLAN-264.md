# PLAN: Dogfood first single-lane release end-to-end

**Branch**: feat/264
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/264
**Base**: dev

## Acceptance Criteria

- [ ] Final tag exists on the release-PR merge commit on `dev`
- [ ] GitHub Release created with the cliff changelog; wheel + tgz attached
- [ ] Wheel and TS package published to GitHub Packages; post-publish smoke green
- [ ] `sdk-released` dispatch received and acknowledged by ≥1 consumer (CWN)
- [ ] No release artifacts minted from any non-release merge during the window

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| release PR `release/v0.66.0` (gh-side) | #261 trigger live; #262 lanes gone; #263 docs merged (dc67027) | Release workflow (positive path — first live exercise); canvastekk-workflow-nodes rebuild | high — real publish + consumer rebuild |
| Release workflow positive path | release PR merged with `release`+`minor` | GitHub Packages consumers (wheel/tgz v0.66.0); CWN/CRS/CASA dispatch listeners | high |
| evidence comment on #264 / epic #260 | all ACs verified | epic close-out | low |

Operational ticket (branch diff = this PLAN only); zero reviewers selected at Step 7; requirements gate's zero-reviewer rule applies.

## Implementation Phases

### Phase 1: Pre-flight
- [ ] **1.1** Record the baseline: blockers merged (#261 → f5322f1, #262 → c98c115), #263 merged (dc67027) with zero tags on its merge commit (window AC-5 baseline already captured)
    — **Why:** The dogfood must run against the fully-migrated single-lane state, and the window invariant needs its pre-release baseline.
    — **Done when:** All four SHAs + zero-tags fact recorded in Trace.
    — **Consumers affected:** none (evidence).
- [ ] **1.2** Confirm queued content and bump: `git log v0.65.1..origin/dev` shows `feat(protocol)` (#258) among the queued commits → semver label `minor`; expected tag `v0.66.0` (from v0.65.1 + minor via the tag action)
    — **Why:** The label is the bump decision; it must match the shipped content (a feature is in range).
    — **Done when:** Range listed in Trace; label choice recorded with its grounding.
    — **Consumers affected:** version consumers (v0.66.0).

### Phase 2: Cut the release PR
- [ ] **2.1** Create the release PR per the documented procedure (README `## Versioning`): `git switch -c release/v0.66.0 origin/dev`; one `chore(release): v0.66.0` commit (`--allow-empty`); push; PR base `dev`; labels `release` + `minor`
    — **Why:** This IS the dogfood — the procedure documented in #263 executed exactly as written, first live run.
    — **Done when:** PR open with both labels; body states expectation (tag, changelog, publish, dispatch).
    — **Consumers affected:** Release workflow (positive path).
- [ ] **2.2** Merge the release PR (short-lived head → `--squash`), record the merge SHA
    — **Why:** The merge push is the release event; squash keeps the classifier verdict consistent with every other short-lived head.
    — **Done when:** PR merged; SHA in Trace.
    — **Consumers affected:** dev HEAD; Release workflow fires.
- [ ] **2.3** Watch the Release run end-to-end: intent lookup (`is_release=true` this time) → tag mint → cliff changelog → GitHub Release → publish job **runs** (not skipped) → wheel/tgz build + publish + smoke tests → `sdk-released` dispatch step
    — **Why:** First live exercise of the positive path; every link must be observed, not assumed.
    — **Done when:** Run completes success with publish job green; dispatch step logged.
    — **Consumers affected:** all downstream consumers.

### Phase 3: Verification (the ACs)
- [ ] **3.1** `v0.66.0` tag exists on the release-PR merge commit (ls-remote tag → SHA == merge SHA)
    — **Why:** AC-1.
    — **Done when:** SHAs match, recorded in Trace.
    — **Consumers affected:** version pinners.
- [ ] **3.2** GitHub Release v0.66.0 exists with cliff changelog body + wheel + tgz + sha256 assets
    — **Why:** AC-2.
    — **Done when:** `gh release view v0.66.0` shows all three assets and a changelog body.
    — **Consumers affected:** release-asset consumers (external authors pinning tarballs).
- [ ] **3.3** Packages published: run log shows successful publish steps + post-publish smoke green (Python + TS verify steps)
    — **Why:** AC-3.
    — **Done when:** Publish + both smoke steps green in the run log.
    — **Consumers affected:** GitHub Packages consumers.
- [ ] **3.4** `sdk-released` dispatch acknowledged by ≥1 consumer: `gh run list -R betekk/canvastekk-workflow-nodes --event repository_dispatch` shows a fresh run post-merge (CWN rebuild)
    — **Why:** AC-4 — the cross-repo contract is the fleet-facing proof.
    — **Done when:** A nodes-repo run timestamped after the release merge is listed.
    — **Consumers affected:** CWN/CRS/CASA.
- [ ] **3.5** Window invariant: the only new tag in the window is v0.66.0; dc67027 (#268's merge) and any other non-release merges minted nothing
    — **Why:** AC-5 — fail-closed must hold around the real release too.
    — **Done when:** Tag list delta shows exactly one new tag.
    — **Consumers affected:** none (evidence).

### Phase 4: Close-out
- [ ] **4.1** Post the evidence comment on #264 (all five AC proofs with links) and the epic completion note on #260 (all children closed)
    — **Why:** The epic's own AC requires this proof and the close-out.
    — **Done when:** Both comments posted.
    — **Consumers affected:** epic #260; future release-cutters reading the trail.

## Technical Notes

- Expected tag arithmetic: v0.65.1 + `minor` → v0.66.0 (mathieudutour tag action, `default_bump` from the intent step).
- The release PR carries BOTH labels; `release` without semver would silently default to patch — the README procedure documents this trap.
- CWN acknowledgment checked via the nodes repo's dispatch-triggered runs (cross-repo `gh` read; no sibling checkout needed).
- If the publish job fails: ticket fails per the failure policy (bounded fix rounds); a re-release retry is the documented recovery for a missed release.

## Dependencies

- blocked-by: #261 (MERGED f5322f1), #262 (MERGED c98c115) — both satisfied.
- Soft-sequenced after #263 (MERGED dc67027) for the window baseline.

## Risks & Mitigation

- **Real publish, real consumer rebuild** → content is fully reviewed/CI-green (4 merged PRs, all full-tier gated); CWN rebuild is the designed response to a release.
- **Breaking-change false positive forces nodes rebuild** → run's detect-breaking step only WARNS + sets payload flags; #258 is non-breaking (minor).
- **Tag action mints wrong version** → 3.1 verifies tag == merge SHA; version arithmetic checked in 1.2.
