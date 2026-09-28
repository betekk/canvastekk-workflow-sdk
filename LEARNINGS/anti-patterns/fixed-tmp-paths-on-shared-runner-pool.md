# Fixed `/tmp` paths are safe on hosted, colliding on a shared self-hosted pool

**Category:** anti-pattern · **Confidence:** high · **Scope:** every local-if-idle conversion
**First seen:** 2026-09-28, DA-3160 review round 1 (canvastekk-workflow-sdk)

Hosted VMs are ephemeral — `/tmp/schema-base.json`, `/tmp/release-notes.md`,
`/tmp/pre-publish-venv` are private-per-run there. On the persistent pool (8 agents/box,
2 boxes) concurrent runs landing on the same box read/clobber each other's files: corrupted
release notes published, false schema-break CI failures, venvs that persist forever.

**Rule:** grep every job being routed for literal `/tmp/` and swap to `$RUNNER_TEMP`
(per-job, runner-cleaned) or `mktemp -d` BEFORE merge — the hazard is activated by the
routing itself, so it is an evidence-driven pre-merge fix, not a follow-up.

## Reference

ci-python.yml schema-stability steps; release.yml notes/venv steps (DA-3160 fix);
release.yml's own mktemp usage was the in-file reference form.
