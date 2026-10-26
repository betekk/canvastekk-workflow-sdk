# Workflow-level `defaults.run.working-directory` breaks any pre-checkout run block

**Category:** solution · **Confidence:** high · **Scope:** any repo with workflow-level run defaults and pre-checkout steps
**First seen:** 2026-09-28, DA-3160 (canvastekk-workflow-sdk)

The canonical pick gate has NO checkout step; a workflow-level
`defaults.run.working-directory: <lang>/` therefore points its bash at a directory that
does not exist at gate time — `An error occurred trying to start process '/usr/bin/bash'
... No such file or directory`, pick fails, every worker skips. Invisible until the first
live run (PR #82 runs 36383949006 → fix → 36384080223 green).

**Fix (minimal, block untouched):** job-scoped override on pick-runner —
`defaults: run: working-directory: ${{ github.workspace }}` (job-level beats
workflow-level). Omit entirely in files without workflow-level defaults. Conversion
precondition: grep the target workflow for top-level `defaults:` before inserting the block.

**Recurrence, inline pre-checkout step (#200, 2026-10-26):** converting the private
`heal-workspace` composite action to an inline `run` block (#198) reintroduced the trap —
composite actions do not inherit caller workflow defaults, inline runs do. The heal step
inherited `typescript/` / `python/`, which do not exist before checkout on a fresh hosted
runner (PR #192 run 40288725922 failed starting bash). Root EVERY pre-checkout inline run
with step-level `working-directory: ${{ github.workspace }}`; a job-scoped default works
only when every later step in that job is also workspace-rooted.

## Reference

sdk ci-python.yml / ci-typescript.yml pick jobs; heal-workspace inline steps (#198/#200);
feed back into devops docs/ci/local-if-idle.md as a conversion precondition note.
