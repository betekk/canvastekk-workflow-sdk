# Solution: `uv run pytest` executed a user-global pytest outside the project venv

**Date:** 2026-11-21
**Confidence:** High (hit during SDK#281; suite showed 7 fastapi ImportErrors while `uv run python -c "import fastapi"` worked)
**Scope:** SDK local testing (any uv+poetry hybrid repo)

## Symptom

`uv run pytest` collected with `ModuleNotFoundError: No module named 'fastapi'`
while the same environment imported the package fine — because the venv had no
pytest at all, and `uv run` resolved `pytest` from `~/.local/bin/pytest`
(a user-global install bound to a different interpreter).

## Rule

Pin the interpreter explicitly: `.venv/bin/python -m pytest` (or
`poetry run pytest` when CI uses Poetry). If a fresh `uv sync` didn't install
your dev tools, install them into the venv (`uv pip install pytest …`), and
match CI's extras (`poetry install -E fastapi` ↔ `uv pip install
'fastapi>=…'`) before believing collection errors are code errors.
