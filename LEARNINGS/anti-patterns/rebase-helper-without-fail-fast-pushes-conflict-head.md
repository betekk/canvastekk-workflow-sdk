Anti-pattern: A rebase helper without fail-fast pushes the conflict-stage HEAD
Scope: project
Confidence: 0.9
Trigger: A shell script runs `git rebase` followed by `git push --force-with-lease` without `set -e` or an explicit rebase-status check.
Action: Make the helper fail fast (`set -e`) and verify the local head still matches the intended commit before any push; resolve conflicts in a separate step.
Context: A conflicted rebase leaves HEAD at the base commit while the script continues, so the subsequent force-with-lease publishes the base SHA over the PR branch.
Rationale: Dependabot then sees an empty diff and auto-closes the PR; recovery requires resolving the original commit from the reflog and reopening the PR.
Evidence: PR #182's lockfile conflict caused a push of dev SHA 7da2b54 over the eslint branch; the corrected commit e0fb6ad restored it and the PR was reopened.
Files: LEARNINGS/anti-patterns/pipe-swallows-gate-exit-code.md
Date: 2026-10-26
