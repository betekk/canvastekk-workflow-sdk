# Solution: run SDK worktree pytest with PYTHONPATH pointed at the worktree

**Date:** 2026-11-27 · **Ticket:** #296 · **Confidence:** high

`python/tests/test_schema_stability_renames.py` shells out to
`[sys.executable, "scripts/check_schema_stability.py", "dump"]`. That subprocess imports
`canvastekk_workflow_sdk`; with no source path on `sys.path` it resolves to an older INSTALLED
copy (fjd_test venv) and fails with `ImportError: WorkflowNodeDeprecationInfo`, looking like a
real regression on a docs-only branch.

Run the suite as:

```bash
PYTHONPATH=<worktree>/python python -m pytest
```

so both pytest and its subprocesses import the edited sources. Symptom to recognise: tests fail
inside a subprocess while the same script succeeds when run directly with the package importable.
