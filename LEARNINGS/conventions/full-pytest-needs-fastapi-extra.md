# Full pytest in a Fresh Venv Needs `-E fastapi`

**Category**: convention
**Confidence**: 1.0
**Scope**: project
**Date**: 2026-10-14
**Source**: #144 exit gate

## Convention

`poetry install` alone in a fresh worktree venv collects 4 import errors
(`No module named 'fastapi'`) across test_app/test_auth/test_router/etc. —
the base install deliberately ships without fastapi since SDK 0.43. CI
matches this: `ci-python.yml:106` installs `--no-interaction -E fastapi`.

Local equivalent:

```bash
cd python/ && poetry install --no-interaction -E fastapi && poetry run pytest -q
```

Collection errors of this shape are environmental, not code regressions —
check the extras flag before diagnosing the tree.
