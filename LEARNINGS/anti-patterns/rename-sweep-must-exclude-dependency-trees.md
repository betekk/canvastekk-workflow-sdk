# A tree-wide rename sweep must exclude dependency trees

**Category**: anti-pattern (with solution) · **Confidence:** high · **Scope:** any repo with an in-tree virtualenv or node_modules
**Date:** 2026-11-19 · **Ticket:** canvastekk-workflow-sdk#271 (Phase 3)

## What happened

A `pathlib.Path("python").rglob("*.py")` rename sweep for ADR 0001 walked into
`python/.venv/lib/python3.12/site-packages` and rewrote third-party internals:
httpx's `from .base import AsyncBaseTransport` became
`from .workflow_node_base import ...` and the suite died with
`ModuleNotFoundError: No module named 'httpx._transports.workflow_node_base'`.
Phase 2's narrower import patterns (definition/diff/registry/convergence/
conformance) grazed the venv without breaking anything the suite imported —
the corruption went unnoticed until a later phase used generic module names
(`base`, `context`, `response`) that site-packages also uses.

## Rule

Any tree-wide text sweep over a project root MUST exclude dependency trees
and caches at collection time: `.venv`, `node_modules`, `.tox`, `dist`,
`__pycache__`, `.git`. Exclusion belongs in the file iterator, not in the
replacement patterns — `rglob` has no respect for package boundaries.

## Verification recipe

After any sweep, `git status --porcelain` must show only intended paths; a
`.venv` path appearing there (or the sweep's changed-file count exceeding the
repo's own file count) means the iterator overreached. Rebuild the venv with
`rm -rf .venv && poetry install` rather than trying to reverse-corrupt
site-packages.
