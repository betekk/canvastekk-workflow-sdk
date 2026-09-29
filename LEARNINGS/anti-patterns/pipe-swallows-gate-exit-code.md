# Piping a Gate Through `tail`/`grep` Swallows Its Exit Code — Merge Guards Check the PIPE's Status

**Category:** anti-patterns · **Scope:** CI watcher scripts, gate loops, any `cmd | filter && act` chain · **Date:** 2026-09-29

## The anti-pattern

```bash
gh pr checks 86 --watch 2>&1 | tail -3 && gh pr merge 86 --squash
```

The `&&` gate inspects **`tail`'s exit status (always 0)**, never the watcher's. A red CI sailed straight through a "green-only" merge guard and landed on `main` (DA-3314, PR #86 — `typecheck-test-build` lint failure merged). The identical bug silently faked a gate earlier the same day (`npm run lint 2>&1 | tail -1 && echo GREEN`).

## Rule

- Never interpose a filter between a gate command and its consumer when the exit code matters. Either run the gate bare (output unfiltered), or capture status explicitly:
  ```bash
  gh pr checks 86 --watch; WEXIT=$?; [ $WEXIT -eq 0 ] && gh pr merge 86 --squash
  ```
  or `set -o pipefail` for the whole script.
- Red-fix round discovered post-merge: fixes fixed in the working tree but staged with `git add <subdir>` never reached the push — `git status --porcelain` on the worktree BEFORE trusting any "gate green" claim; a green local gate proves nothing about what was pushed.
