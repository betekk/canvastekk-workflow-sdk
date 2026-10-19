# workflow_call Outputs Do Not Cross the Reusable Boundary Without Re-export

**Category:** anti-pattern · **Confidence:** high · **Scope:** any repo whose caller chains jobs on a reusable workflow's outputs
**Date:** 2026-10-19 · **Ticket:** betekk/canvastekk-frontend-nextjs#2039

## Symptom

Chained jobs gating on `needs.<reusable-job>.outputs.<name> != ''` silently
never run. The wrapper's tag/Release steps complete; the chained publish,
asset-upload, and dispatch steps are skipped with no error anywhere — the
`if:` just evaluates false forever because the output resolves to an empty
string.

## Root cause

Job-level `outputs:` in a reusable workflow stay INTERNAL to that workflow.
GitHub only surfaces outputs to the caller when they are re-exported under
`on.workflow_call.outputs:` (value: `${{ jobs.<id>.outputs.<name> }}`).
`betekk-gha/reusable-release.yml` declared `new_tag`/`new_version` at job
level only — every consumer chaining on them (both library pilots @v1.6.0,
the SDK migration draft) held a latent silent no-op. Nothing in the fleet
had ever exercised the path: @v1.4.0 consumers (CDS/CWE) never read outputs,
and the pilots had run no prod release.

## Rule

- Adding a chained job that reads `needs.<uses-job>.outputs.*` from a reusable
  REQUIRES the reusable to declare those names under `workflow_call.outputs`.
  Verify the reusable's source at the pinned tag before authoring the caller.
- A chained-publish caller that has never observed its publish job run at
  least once is unverified — treat "wrapper green, chained never fired" as
  the signature of this gap, not as "no releases needed yet".
- Fixed in betekk-gha v1.7.2 (PRs #129/#130, tag `8ceff2b0`); callers must
  pin `>= v1.7.2` to chain on outputs.

## Evidence

- v1.6.0 blob grep: outputs only at lines 61-62 (pick-runner) and 116-118
  (release) — no `workflow_call.outputs` block (verified 2026-10-19).
- CDS/CWE callers pin @v1.4.0 with zero `needs.release.outputs` reads.
