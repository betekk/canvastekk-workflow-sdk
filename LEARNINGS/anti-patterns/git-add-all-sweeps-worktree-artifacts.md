# `git add -A` in a Pipeline Worktree Sweeps Session Artifacts

**Category**: anti-pattern
**Confidence**: 0.85
**Scope**: project
**Date**: 2026-10-14
**Source**: #144 Phase 4 commit review

## Anti-pattern

Running `git add -A` (or `git commit -am`) in a worktree that hosts agent
tooling commits everything the session dropped: a `.opencode/` session-artifact
directory (not gitignored in this repo) and a stray root file named `=0`
created by a shell typo (`echo "---">=0`). Both landed in a pushed phase
commit of a public repo and had to be `git rm`'d in a review-fix round.

## Fix direction

Stage explicit paths per phase commit (the PLAN already names them); reserve
`-A` for never. After shell one-liners that redirect, `git status --porcelain`
before committing catches typo files. Longer term: decide `.opencode/` ignore
policy at repo level so sessions cannot sweep it.
