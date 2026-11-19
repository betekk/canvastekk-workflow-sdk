# PLAN: Delete prod and promotion branches (post-cutover)

**Branch**: feat/262
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/262
**Base**: dev

## Acceptance Criteria

- [ ] `git ls-remote origin` shows no `prod`, no `promotion/*`
- [ ] `origin/HEAD` still resolves to `dev` (no default-branch change needed)
- [ ] Old release tags (e.g. `v0.65.0`) still resolve to their commits
- [ ] Repo-wide grep finds no workflow, doc, or script reference to the `prod` branch or promotion flow
- [ ] Published packages from prior releases still install from GitHub Packages

**Scope note (inherited AC boundary, not a rewrite):** AC-4's "doc" splits operationally — workflows/scripts/config references are THIS ticket's grep; prose-doc references belong to #263 per the epic split. Any prose hits found here are reported and routed to #263 with evidence, not left silent.

**Verification split:** AC-5 is verified as state-intact (releases + assets listed, packages unchanged — deletion touches refs, not artifacts); a fresh end-to-end install proof is #264's dogfood territory.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| backmerge PR (prod→dev) | #261 merged (trigger live) | dev trunk (gains #259 fix); Release workflow (must NOT fire — no `release` label) | high — carries unreleased-on-dev code |
| remote refs `prod`, `promotion/dev-to-prod` | backmerge merged (2.1 gate) | CI triggers (already prod-free since #261); engineers' habits; #264 (dogfood expects lanes gone) | high — irreversible-ish; tags keep history reachable |
| main checkout branch (prod→dev switch) | backmerge merged | user's working tree (session cwd) | medium — untracked files survive; consent obtained at Step 7 |
| gone-upstream local branches (optional prune) | — | local navigation only | low — cosmetic |

No cross-module code consumers (operational ticket, zero source diffs beyond this PLAN) → architecture review not selected at Step 7; the requirements gate's zero-reviewer rule applies (new work, no reviewers).

## Implementation Phases

### Phase 1: Final backmerge prod→dev
- [ ] **1.1** Create the backmerge PR: head `prod` → base `dev` (org precedent: #250), title `chore(release): backmerge prod into dev — final lane reconciliation (#262)`, semver label `patch`, explicitly NO `release` label (a backmerge must not mint a release — #259 already shipped via the 03:26 prod run)
    — **Why:** `origin/dev..origin/prod` holds 3 commits (a0e9c87 #259 fix + 2 merge commits); deleting prod before reconciling loses the only lane carrying them.
    — **Done when:** PR open, CI running, body states the no-release-label invariant.
    — **Consumers affected:** dev trunk; Release workflow (negative path, by design).
- [ ] **1.2** Watch the backmerge PR's checks to green and merge with `--merge` (long-lived head → merge commit per head-class rule; preserves history linkage), capture merge SHA
    — **Why:** Squash would rewrite #259's commit onto dev; merge-commit keeps the lanes' shared history honest for the final state.
    — **Done when:** PR state merged; merge SHA recorded in Trace.
    — **Consumers affected:** dev HEAD moves; nothing else (no release label → publish skipped).

### Phase 2: Lane deletion
- [ ] **2.1** Fetch and assert the precondition: `git log origin/dev..origin/prod` is empty
    — **Why:** The deletion gate — prod must be fully contained in dev or the lanes are not reconciled.
    — **Done when:** Command outputs nothing; recorded in Trace.
    — **Consumers affected:** gates 2.2-2.3.
- [ ] **2.2** Switch the main checkout from `prod` to `dev` (consent obtained at Step 7; untracked files survive), then delete local branches `prod` and `promotion/dev-to-prod` (plain `-d` — both ancestors of dev after the backmerge)
    — **Why:** A checked-out branch cannot be deleted; the session's main working tree ends on the trunk, matching the new model.
    — **Done when:** `git branch --list prod promotion/dev-to-prod` empty; main checkout on dev, untracked files intact.
    — **Consumers affected:** user's working tree (session cwd).
- [ ] **2.3** Delete the remote branches: `git push origin --delete prod promotion/dev-to-prod`
    — **Why:** The ticket's core act — lanes retire; tags keep the old merge commits reachable so no history is lost.
    — **Done when:** `git ls-remote --heads origin` lists neither ref.
    — **Consumers affected:** repo clones everywhere (fetch prunes), #264.
- [ ] **2.4** Optional prune: `git remote prune origin`, then delete gone-upstream local branches (`git branch -vv | grep ': gone]'`)
    — **Why:** ~40 stale local branches mislead navigation; cosmetic, rides this ticket's hygiene mandate.
    — **Done when:** `git branch -vv | grep -c ': gone]'` is 0.
    — **Consumers affected:** local navigation only.

### Phase 3: Verification
- [ ] **3.1** Verify the end state: `git ls-remote origin` shows no `prod`/`promotion/*`; `origin/HEAD` → dev; default branch unchanged on GitHub
    — **Why:** AC-1 + AC-2 — the deletion must be complete and the trunk must remain the default.
    — **Done when:** All three checks pass in one command block, recorded in Trace.
    — **Consumers affected:** AC sign-off.
- [ ] **3.2** Verify old tags resolve: `git rev-parse v0.65.0^{commit}` (and the newest final) still return commits reachable in history
    — **Why:** AC-3 — deletion must not orphan release history.
    — **Done when:** SHAs resolve and are ancestors of dev.
    — **Consumers affected:** consumers pinning old versions.
- [ ] **3.3** Operational grep: workflows/scripts/config free of `prod`-lane references; any prose hits routed to #263 with an evidence comment
    — **Why:** AC-4 — no operational reference may outlive the lanes; prose is #263's by epic split.
    — **Done when:** Grep clean on operational paths; prose hits (if any) linked on #263.
    — **Consumers affected:** AC sign-off; #263.
- [ ] **3.4** Verify releases/packages intact: `gh release list` shows prior releases with assets; no deletion path touched artifacts
    — **Why:** AC-5 — branch refs and package artifacts are independent stores; prove the separation.
    — **Done when:** Latest release lists wheel + tgz + sha256 assets.
    — **Consumers affected:** all package consumers.

## Technical Notes

- The backmerge PR carries NO `release` label — merging it exercises #261's negative path again (publish skipped) while carrying real code; this is intentional and verified via the run's job matrix.
- Local `prod` == `origin/prod` (a0e9c87) — no local-only work strands.
- Tags (v0.65.0 … newest final) keep prod's merge commits reachable post-deletion; GitHub never GCs tagged commits.
- Branch protection: none on any branch (verified 404 on dev; prod assumed same, re-checked in 3.1).

## Dependencies

- blocked-by: #261 — MERGED (f5322f1; trigger live, AC-1 proven).
- Unblocks: #264 (dogfood expects single-lane).

## Risks & Mitigation

- **Deleting prod with unreconciled commits** → hard gate 2.1 (empty `dev..prod`) before any deletion.
- **Main-checkout disruption** → consent at Step 7; untracked files survive `checkout dev`; nothing force-resets.
- **Accidental release on backmerge** → no `release` label on the PR; #261's fail-closed gate is the backstop (already proven live).
- **Someone re-creates the lanes by habit** → #263 documents the new procedure; epic AC requires the re-scope.
