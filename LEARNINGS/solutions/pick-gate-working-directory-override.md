# Workflow-level `defaults.run.working-directory` breaks the inserted pick gate

**Category:** solution · **Confidence:** high · **Scope:** any repo with workflow-level run defaults converting to local-if-idle
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

## Reference

sdk ci-python.yml / ci-typescript.yml pick jobs; feed back into devops
docs/ci/local-if-idle.md as a conversion precondition note.
