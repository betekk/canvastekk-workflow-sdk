# Never `git checkout -- <file>` to Undo a Scripted Edit in a Tree Holding Uncommitted Phase Work

Date: 2026-10-10 · Confidence: high · Scope: plan-execution worktrees, release tooling

## Summary

Verifying `bump_versions.py` live (run script → 9.9.9 → revert) with
`git checkout -- python/pyproject.toml` also wiped the uncommitted PEP 621
migration edit in the same file — the next gate failed with the legacy
deprecation warnings and a lock/hash mismatch. A file-wide revert in a tree
holding uncommitted phase work reverts BOTH the scripted bump and the phase
edit.

## Evidence

- #105 phase 1: gate attempt 1 failed (`poetry check` emitted the 11 legacy
  warnings again) immediately after the bump-script verification step.
- Recovery: re-apply the phase edit; the regenerated lock already matched the
  migrated config, so `poetry check --lock` went green without re-locking.

## Rule

Revert scripted edits surgically (edit the touched line back, e.g. the
version string), or commit the phase work before running mutation-style
verification. File-wide checkout is only safe on a tree with no uncommitted
changes to that file.
