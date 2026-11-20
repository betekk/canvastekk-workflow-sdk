---
title: Example suites excluded from CI rot silently — mock drift
type: anti-pattern
---

# Example suites excluded from CI rot silently — mock drift

`examples/echo_node/tests/` was green in nobody's CI, and it roted twice
invisibly: (1) its mocks patched `canvastekk_workflow_sdk.base.httpx.get`
while the SDK had long switched input downloads to `httpx.stream` — the mock
never fired and the tests did real HTTP (404); (2) it asserted
`manifest name == "echo"` after the field's semantics moved to
`name="Echo"`. Found only because #272's sweep retargeted the example and ran
its suite by hand (2026-11-20).

- **Rule:** an example that ships tests either runs them in CI (a cheap
  paths-filter job) or loses the tests — a test suite nothing executes is
  negative documentation: it looks like coverage and proves nothing.
- **Detection:** `grep -rl "examples/" .github/workflows/` empty while
  `find examples -name "*test*"` non-empty.
- **Date:** 2026-11-20 · **Ticket:** canvastekk-workflow-sdk#272 (code review)
