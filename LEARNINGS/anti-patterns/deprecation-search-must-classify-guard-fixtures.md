---
title: Deprecation-removal search predicates must classify negative-test fixtures
type: anti-pattern
---

# Deprecation-removal search predicates must classify negative-test fixtures

A "search every consumer repo for the old name; require zero hits" acceptance
criterion is unsatisfiable as written: consumer repos that built vocabulary
guards against the old names keep the old tokens in *negative-test fixtures* —
planted violations proving their guard fires. In canvastekk-workflow-sdk #272
(2026-11-20), canvastekk-llm-service `origin/dev`
`fastapi_gateway_app/tests/test_vocabulary_guard.py:204-212`
(`test_sdk_guard_detects_planted_tokens`) writes
`from canvastekk_workflow_sdk.definition import …` into a temp file on purpose.

- **Rule:** the predicate is "zero *unclassified* hits". Each hit is either a
  real usage (blocks) or a cited negative-test/guard fixture quoting old names
  as planted violations (allowed, listed in the evidence).
- **Why it matters:** without the classification rule the pipeline stalls on a
  legitimate fixture, or worse, someone "fixes" the consumer repo by deleting
  its guard self-test.
- **Date:** 2026-11-20 · **Ticket:** canvastekk-workflow-sdk#272 (architecture review F3)
