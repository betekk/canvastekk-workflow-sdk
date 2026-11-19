# Resume Rebase Invalidates Gate-Memo SHA Citations

**Category**: solutions · **Confidence**: High · **Scope**: worktree-pipeline resumes (any repo using GATE memo citation)
**Date**: 2026-11-19 · **Ticket**: betekk/canvastekk-workflow-sdk#257

A `GATE <sha> tier=...` Trace line cites the commit whose tree was gated. A
resume rebase onto a moved base rewrites every commit SHA, so the memo now
names a commit that no longer exists — and a `tier=light` line that happens to
sit where the exit memo belongs satisfies nothing (Step 10a requires
`tier=full` for the pushed SHA). Seen in PLAN-257: the parallel session wrote
`GATE f1d1d28 tier=light` as the exit memo; the rebase onto 0b0f33c turned
f1d1d28 into 366304e and the inherited-test counts (py 1020→1041, ts 480→496)
proved the tree needed re-gating, not memo-restoring.

Fix that works: re-run the **full** gate on the rebased tree, append a fresh
`GATE <impl-sha> tier=full` line plus a LOG line naming the superseded stale
line (Trace is append-only — never rewrite the old line). The memo names the
gated implementation SHA; a docs-only memo-fix commit may ride on top (Step 10a
cites the memo line, not the push head). Test-count deltas after a rebase are
the tell that the base moved under you.
