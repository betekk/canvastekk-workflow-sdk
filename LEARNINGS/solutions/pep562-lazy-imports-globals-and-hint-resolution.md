# PEP 562 Lazy Imports: `__getattr__` Never Serves Global Lookups — And String Annotations Resolve Against Module Globals

Date: 2026-10-10 · Confidence: high · Scope: lazy dependency loading (Python)

## Summary

Two coupled facts bit the #104 fastapi-lazy migration:

1. **PEP 562 module `__getattr__` fires only for external attribute access**
   (`canvastekk_workflow_sdk.FastAPI`). Global-name lookups inside the
   module's own functions bypass it entirely — `FastAPI(...)` in a body
   raises `NameError` even with a perfect `__getattr__` shim. Internal uses
   need real bindings: function-local imports.
2. **fastapi/pydantic resolve string annotations (PEP 563) against the
   handler's module `__globals__` at registration/build time.** Move a
   framework name to `TYPE_CHECKING`-only and every route/hint that names it
   degrades (params become query params → 422) or pydantic raises
   "not fully defined" ForwardRef errors.

## The working pattern

```python
def create_node_app(...):
    from fastapi import APIRouter, Depends, FastAPI, Request   # lazy, call-time
    from fastapi.responses import JSONResponse
    globals().update(Request=Request, JSONResponse=JSONResponse, ...)  # hints resolve
```

Inject into `globals()` from the lazily-entered code path; factories that
build `Depends()` callables inject at construction. Consumers of the symbols
via module attribute access keep working, and external-only `__getattr__`
shims can be deleted.

## Evidence

- #104 phase 2: `pytest` 65 failed → 51 → 13 → 0 across the two discoveries;
  `NameError: name 'FastAPI' is not defined` at app.py:312 and
  `PydanticUserError ... ForwardRef('JSONResponse')` were the tells.
