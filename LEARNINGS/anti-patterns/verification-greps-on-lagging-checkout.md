# Verification Greps on a Lagging Checkout Produce False Evidence

**Category**: anti-pattern
**Confidence**: 0.85
**Scope**: project
**Date**: 2026-11-19
**Source**: #262 — stale-tree correction (PLAN-262 Trace)

## Anti-pattern

After `git checkout dev` on a main working tree whose local `dev` lags
`origin/dev`, every grep/read against the working tree returns the OLD
content. In #262 the post-deletion verification grep "found" `branches:
[dev, prod]`, `is_prod`, and `release_branches: prod` still present —
false evidence: those changes were merged in #265; the checkout simply
sat on a pre-merge SHA. A conservative branch-prune the same way kept 47
branches that only looked unmerged (ancestry checked against the stale
HEAD).

## Rule

Before treating any working-tree read as verification evidence, confirm
the tree is at the ref you think it is: `git status --porcelain` (tracked
clean) + `git merge-base --is-ancestor <expected-sha> HEAD`, or run the
verification from a fresh worktree cut from the remote ref. When the main
checkout must catch up, verify zero tracked modifications first, then
`git merge --ff-only origin/<base>` — never a blind pull.

Evidence: PLAN-262 Trace stale-tree correction LOG; first 3.3 grep output
vs. re-run at 22da102.
