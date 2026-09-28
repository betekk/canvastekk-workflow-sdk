# Gate-memo SHAs don't survive `git commit --amend`

**Category:** solution
**Confidence:** high (hit on DA-3230; verified orphaned sha)
**Scope:** pipeline gate memos in PLAN trace blocks
**Date:** 2026-09-29 (DA-3230)

## Symptom

Writing a `GATE <sha> tier=full` memo that cites the commit it rides in,
then realizing the sha only exists after committing — and "fixing" it with
commit → sed the sha in → `--amend` rewrites the commit, so the cited sha
( captured pre-amend) no longer exists on the branch. The memo names a
ghost.

## Fix

Never amend the commit that carries its own memo. The working pattern
(observed on DA-2886, DA-3232, DA-3230):

1. Commit the gated tree (code + ticks + memos for EARLIER commits).
2. Append the memo line citing that real, pushed commit.
3. Let the memo ride the next PLAN-touching commit (review-fix /
   `chore(learnings)` / a final tiny `docs(plan)` memo fold).

The final pushed SHA then carries a green `tier=full` memo naming a real
ancestor whose tree matches — which is what the Step 10a citation checks.
If a ghost sha slipped in anyway, sed it to the real commit and fold the
correction into the next commit; never amend.
