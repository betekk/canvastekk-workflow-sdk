# fastapi ≥0.143 Nests Routers Under `_IncludedRouter` — Introspect via `app.openapi()`

Date: 2026-10-10 · Confidence: high · Scope: Python SDK tests, fastapi ≥0.143

## Summary

fastapi 0.143 changed `app.routes`: the router's routes are nested under a
private `_IncludedRouter` wrapper (a `BaseRoute` subclass without `.path`).
Naive `[r.path for r in app.routes]` raises
`AttributeError: '_IncludedRouter' object has no attribute 'path'`.
The public, version-stable introspection surface is `app.openapi()["paths"]`.

## Evidence

- tests/test_base.py `test_create_app` broke on the fastapi ^0.135 → ^0.143
  bump (821 passed / 1 failed); fixed by asserting
  `"/execute" in set(app.openapi()["paths"])` etc.
- `_IncludedRouter` lives at fastapi/routing.py:1623 (0.143.0); its
  `effective_candidates` is not a stably-public iterable — do not walk it.

## Rule

Structural route assertions in tests go through `app.openapi()["paths"]`, not
`app.routes` iteration — privates shift between fastapi minors.
