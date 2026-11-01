# Convention: PEP 562 `__getattr__` preserves importers through a module→package split

**Category: conventions** · **Confidence: high** · **Scope: python packaging** · **Date: 2026-11-01**

Splitting `foo.py` into `foo/__init__.py` + submodules without touching a
single importer: re-export what must stay eager at module top (framework-free
names), and serve the rest (framework-gated or heavy names) via a module-level
`__getattr__` (PEP 562). `from foo import Name` consults `__getattr__` for
missing attributes, so even *private* names (`_ApiKeyAuth`, `_is_dev_mode`)
keep resolving for tests, and gated names can raise a guided ImportError
(naming the extra) instead of a raw ModuleNotFoundError.

Worked example: `canvastekk_workflow_sdk/auth.py` → `auth/` (sdk#225) —
967 pre-existing tests passed with zero import-line edits, including tests
that monkeypatch `type(instance)._method` on the re-exported adapter classes
(adapters subclass the moved core classes, so class-level patch targets
survive).

Trigger: any module→package conversion, or any split where importers must
not churn. Cost: one `__getattr__` + a frozenset of lazy names.
