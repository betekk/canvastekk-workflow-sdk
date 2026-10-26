Solution: Let secret-less app-token steps reach the hosted runner fallback
Scope: project
Confidence: 0.9
Trigger: A workflow creates a GitHub App token before probing runner availability on a Dependabot pull_request run.
Action: Put continue-on-error: true on the app-token step and preserve the probe's empty-token degradation path; verify with a Dependabot PR.
Context: Dependabot pull_request workflows do not receive the repository's GH_APP_PRIVATE_KEY, so actions/create-github-app-token rejects its empty private-key input.
Detail: Without continue-on-error, pick-runner fails before the probe can emit labels=["ubuntu-24.04"], and every dependent quality gate is skipped. The existing probe already converts an unauthenticated runner-list API failure into hosted routing after three attempts.
Rationale: This reuses the established fallback instead of adding actor-specific routing or duplicate fallback logic.
Evidence: TypeScript CI run 40271776615 failed pick-runner and skipped typecheck-test-build; #197 applies the one-step fix in both PR CI workflows and reusable-release.yml.
Files: .github/workflows/ci-typescript.yml, .github/workflows/ci-python.yml, .github/workflows/reusable-release.yml
Date: 2026-10-26
