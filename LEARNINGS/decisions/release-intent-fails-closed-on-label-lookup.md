# Release Intent Must Fail Closed on Label Lookup

**Category**: decision
**Confidence**: 0.85
**Scope**: project
**Date**: 2026-11-19
**Source**: #261 — release-PR trigger replaces prod-lane gates

## Decision

Release intent (whether a push to `dev` cuts a release) derives from ONE
`listPullRequestsAssociatedWithCommit` label lookup in `reusable-release.yml`
(`release_intent` step): the pushed commit's merged PR must carry the
`release` label. Any lookup failure or PR-less push resolves to
`is_release=false` — **fail closed**.

## Why the inversion from #172

#172's resilient lookup fell back to `patch` on API failure — safe for bump
*size* (a downgrade never invents intent), and that fallback survives for
`type`. But release *intent* defaulting true on a failed lookup would publish
unreviewed code. The asymmetry is the rule: a missed release is a retry; an
accidental release is an incident.

## Consequences

- Direct pushes to `dev` can never release — releases happen only via a
  labeled PR merge (documented procedure lives with #263).
- A `release`-labeled PR merge is the only path to `tag_version`
  (step-level `if`), changelog, GitHub Release creation, and the publish job.
- Consumers of the semantics: `release.yml` publish gate (via the
  `is_release` workflow_call output), #264's dogfood proof, #263's docs.

Evidence: `reusable-release.yml` release_intent step (fail-closed branch +
warning), PLAN-261 1.2; simulation proof in PLAN-261 Trace (4.2).
