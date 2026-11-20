---
title: CI publish steps are invisible consumers of deprecated aliases
type: anti-pattern
---

# CI publish steps are invisible consumers of deprecated aliases

When removing deprecated public aliases from a package, the sweep scoped to
`src/` + tests misses in-repo CI workflows that import the package. In
canvastekk-workflow-sdk #272 review (2026-11-20), `.github/workflows/release.yml:121`
(pre-publish smoke test, no `continue-on-error`) imported root aliases
`RetryConfig, BaseNode, ExecutionContext` — the exact release that was supposed
to ship the removal version would have died at its own smoke test, after merge,
past every PR gate. `typescript/scripts/pack-test.sh:25` likewise pinned
`root.BaseNode` as a gate-leg assertion.

- **Rule:** an alias-removal sweep's scope is "everything in the repo that can
  name a symbol": `src/`, `tests/`, `scripts/`, `.github/workflows/`, docs with
  runnable samples, and scaffold templates. Grep the removed names repo-wide
  (excluding dependency trees), not just the package dir.
- **Detection:** `grep -rn "<removed-name>" .github/ scripts/` as a dedicated
  exit-gate leg for removal tickets.
- **Date:** 2026-11-20 · **Ticket:** canvastekk-workflow-sdk#272 (architecture review F1/F2)
