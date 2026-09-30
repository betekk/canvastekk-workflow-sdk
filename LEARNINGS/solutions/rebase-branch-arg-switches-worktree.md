# `git rebase <upstream> <branch>` Switches the Current Worktree to `<branch>`

**Category**: solutions
**Confidence**: 0.9
**Scope**: project
**Date**: 2026-09-30
**Source**: DA-3340 pipeline run (main checkout landed on feat/DA-3340)

## Problem

Running `git rebase origin/main feat/DA-3340` from the MAIN checkout (to update the ticket branch) silently checked `feat/DA-3340` out in the main working tree — violating the worktree-pipeline guarantee that the main checkout never sits on a feat branch, and blocking `git worktree add <root>/<KEY> feat/<KEY>` ("already used by worktree").

## Fix

Either check the branch out first in its own worktree and run plain `git rebase <upstream>` there, or `git switch main` in the main checkout immediately after the two-arg rebase. The two-arg form is documented git behavior: `<branch>` means "switch, then rebase".

## Evidence

- DA-3340 run: worktree list showed the main checkout on `refs/heads/feat/DA-3340` after the rebase; fixed with `git switch main` before `git worktree add`.
