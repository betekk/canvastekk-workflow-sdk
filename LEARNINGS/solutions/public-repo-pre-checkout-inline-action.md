Solution: Inline private composite actions used before checkout in public repos
Scope: project
Confidence: 0.9
Trigger: A public repository's workflow uses a private composite action before actions/checkout and fails during Set up job.
Action: Inline the reviewed action's run script at that step; do not rely on a step-level if or a same-repository composite action.
Context: GitHub resolves every uses reference while setting up the job. Public callers cannot download private actions, and step conditions run only after action resolution.
Detail: Moving to uses: ./.github/actions/<name> is not a pre-checkout escape because the local action's files are unavailable until checkout. If the step exists to repair a stale self-hosted workspace before checkout, an inline run block preserves that behavior without changing repository visibility.
Rationale: This fixes the resolution failure at its source while retaining the existing recovery behavior; no extra credential or visibility change is required.
Evidence: PR #198 runs 40285584171 and 40285584198 failed with Unable to resolve action betekk/betekk-gha before any project step. Three inline copies were verified byte-for-byte against heal-workspace@v1.17.0 and exercised in a disposable skip-worktree repository.
Files: .github/workflows/ci-typescript.yml, .github/workflows/ci-python.yml, LEARNINGS/anti-patterns/public-repo-cannot-call-private-reusable.md
Date: 2026-10-26
