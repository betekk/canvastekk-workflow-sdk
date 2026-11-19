# PLAN: Delete prod and promotion branches (post-cutover)

**Branch**: feat/262
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/262
**Base**: dev

## Acceptance Criteria

- [x] `git ls-remote origin` shows no `prod`, no `promotion/*`
- [x] `origin/HEAD` still resolves to `dev` (no default-branch change needed)
- [x] Old release tags (e.g. `v0.65.0`) still resolve to their commits
- [x] Repo-wide grep finds no workflow, doc, or script reference to the `prod` branch or promotion flow — operational paths verified clean; 3 dead-vocabulary strings routed to #263 (user-confirmed scope)
- [x] Published packages from prior releases still install from GitHub Packages — state-intact verification (user-confirmed); fresh install proof rides #264

**Scope note (inherited AC boundary, not a rewrite; user-confirmed at Step 7):** AC-4's "doc" splits operationally — workflows/scripts/config references are THIS ticket's grep; prose-doc references belong to #263 per the epic split. Any prose hits found here are reported and routed to #263 with evidence, not left silent.

**Verification split (user-confirmed at Step 7):** AC-5 is verified as state-intact (releases + assets listed, packages unchanged — deletion touches refs, not artifacts); a fresh end-to-end install proof is #264's dogfood territory.

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
- [x] **1.1** Create the backmerge PR: head `prod` → base `dev` (org precedent: #250), title `chore(release): backmerge prod into dev — final lane reconciliation (#262)`, semver label `patch`, explicitly NO `release` label (a backmerge must not mint a release — #259 already shipped via the 03:26 prod run)
    — **Why:** `origin/dev..origin/prod` holds 3 commits (a0e9c87 #259 fix + 2 merge commits); deleting prod before reconciling loses the only lane carrying them.
    — **Done when:** PR open, CI running, body states the no-release-label invariant.
    — **Consumers affected:** dev trunk; Release workflow (negative path, by design).
    — **Done:** PR #266 created (head prod → base dev, patch label, no release label, invariant stated in body); files: none (PR-side); fixes: none
- [x] **1.2** Watch the backmerge PR's checks to green and merge with `--merge` (long-lived head → merge commit per head-class rule; preserves history linkage), capture merge SHA
    — **Why:** Squash would rewrite #259's commit onto dev; merge-commit keeps the lanes' shared history honest for the final state.
    — **Done when:** PR state merged; merge SHA recorded in Trace.
    — **Consumers affected:** dev HEAD moves; nothing else (no release label → publish skipped).
    — **Done:** all checks green (watch exit 0, own exit code — no piped gate), merged --merge as 22da1029fb2d55d9b6dba0ae85b87960d4d5f95f; zero tags on 22da102 (fail-closed held); files: none; fixes: none

### Phase 2: Lane deletion
- [x] **2.1** Fetch and assert the precondition: `git log origin/dev..origin/prod` is empty
    — **Why:** The deletion gate — prod must be fully contained in dev or the lanes are not reconciled.
    — **Done when:** Command outputs nothing; recorded in Trace.
    — **Consumers affected:** gates 2.2-2.3.
    — **Done:** 0 commits on prod not on dev post-backmerge (hard-gated the deletion on this); files: none; fixes: none
- [x] **2.2** Switch the main checkout from `prod` to `dev` (consent obtained at Step 7; untracked files survive), then delete local branches `prod` and `promotion/dev-to-prod` (plain `-d` — both ancestors of dev after the backmerge)
    — **Why:** A checked-out branch cannot be deleted; the session's main working tree ends on the trunk, matching the new model.
    — **Done when:** `git branch --list prod promotion/dev-to-prod` empty; main checkout on dev, untracked files intact.
    — **Consumers affected:** user's working tree (session cwd).
    — **Done:** checkout dev (tracked tree clean; untracked LEARNINGS intact; local dev then fast-forwarded --ff-only to 22da102 after verifying zero tracked modifications); local prod (a0e9c87) + promotion (5ee0eed) deleted via -d; fixes: none
- [x] **2.3** Delete the remote branches: `git push origin --delete prod promotion/dev-to-prod`
    — **Why:** The ticket's core act — lanes retire; tags keep the old merge commits reachable so no history is lost.
    — **Done when:** `git ls-remote --heads origin` lists neither ref.
    — **Consumers affected:** repo clones everywhere (fetch prunes), #264.
    — **Done:** both remote refs deleted; ls-remote shows neither (41 heads remain); fixes: none
- [x] **2.4** Optional prune: `git remote prune origin`, then delete gone-upstream local branches (`git branch -vv | grep ': gone]'`)
    — **Why:** ~40 stale local branches mislead navigation; cosmetic, rides this ticket's hygiene mandate.
    — **Done when:** `git branch -vv | grep -c ': gone]'` is 0.
    — **Consumers affected:** local navigation only.
    — **Done:** remote prune ran; conservative -d pass deleted `main` (long-gone upstream, merged); 47 stale feature branches KEPT deliberately — squash-merge histories never satisfy -d ancestry and force-deleting 47 refs silently is worse than the clutter (see SKIP line); partial by design; fixes: none

### Phase 3: Verification
- [x] **3.1** Verify the end state: `git ls-remote origin` shows no `prod`/`promotion/*`; `origin/HEAD` → dev; default branch unchanged on GitHub
    — **Why:** AC-1 + AC-2 — the deletion must be complete and the trunk must remain the default.
    — **Done when:** All three checks pass in one command block, recorded in Trace.
    — **Consumers affected:** AC sign-off.
    — **Done:** no prod/promotion heads (41 total), origin/HEAD=dev, default branch untouched; fixes: none
- [x] **3.2** Verify old tags resolve: `git rev-parse v0.65.0^{commit}` (and the newest final) still return commits reachable in history
    — **Why:** AC-3 — deletion must not orphan release history.
    — **Done when:** SHAs resolve and are ancestors of dev.
    — **Consumers affected:** consumers pinning old versions.
    — **Done:** v0.65.0 → 0b0f33c and v0.64.1 → 9b5cc6f resolve; v0.65.0 verified ancestor of dev; fixes: none
- [x] **3.3** Operational grep: workflows/scripts/config free of `prod`-lane references; any prose hits routed to #263 with an evidence comment
    — **Why:** AC-4 — no operational reference may outlive the lanes; prose is #263's by epic split.
    — **Done when:** Grep clean on operational paths; prose hits (if any) linked on #263.
    — **Consumers affected:** AC sign-off; #263.
    — **Done:** triggers/gates/is_prod/release_branches all absent; 3 residual dead-vocabulary strings (reusable-release.yml:11,:113,:197) routed to #263 with evidence comment; lane-vocabulary prose grep: no hits; fixes: none
- [x] **3.4** Verify releases/packages intact: `gh release list` shows prior releases with assets; no deletion path touched artifacts
    — **Why:** AC-5 — branch refs and package artifacts are independent stores; prove the separation.
    — **Done when:** Latest release lists wheel + tgz + sha256 assets.
    — **Consumers affected:** all package consumers.
    — **Done:** v0.65.1 (latest) lists tgz + wheel + sha256; state-intact per Step 7 ruling; fixes: none

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

## Trace

LOG gate-escalation exit gate: full tier — unconditional ticket exit gate (docs-only branch diff, ladder run in-worktree regardless: actionlint, tsc ×2, tsup, poetry build, pytest 1038, vitest 489; e2e n.a — no frontend).
SKIP 2.4 full prune — 47 stale local branches are squash-merge histories (never satisfy -d ancestry); conservative keep beats silent mass force-delete; `main` (long-gone) pruned.
LOG stale-tree correction: first 3.3 grep ran against the main checkout's lagging local dev (pre-#261 files) and produced false evidence; fixed by verifying tracked-tree cleanliness then `merge --ff-only origin/dev` (22da102) and re-running — grep then clean. Recorded as a LEARNINGS candidate.
GATE 49e4481 tier=full lint=t typecheck=t build=t unit=t e2e=n.a — exit gate; Step 9 review returned zero fixes, so 49e4481 remains the gated final implementation SHA.
LOG code-review (Step 9): docs-only diff (PLAN-262.md); evidence claims verified against run outputs; 0 findings; direct-caller gate vacuous (no code symbols).
