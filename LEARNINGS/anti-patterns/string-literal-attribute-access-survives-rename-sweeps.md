# String-Literal Attribute Access Survives Identifier Rename Sweeps

**Category**: anti-pattern (with solution) · **Confidence:** high · **Scope:** any rename refactor over a dynamic language
**Date:** 2026-11-19 · **Ticket:** canvastekk-workflow-sdk#271 (review round 1)

## What happened

ADR 0001's word-boundary identifier sweeps renamed every `definition`
declaration and member access — but `workflow_node_app.py:304` read the
attribute through a defensive string literal:
`getattr(getattr(node, "definition", None), "slug", None)`. The sweep renamed
declarations; the string key survived, so the SDK's own serving path routed
through its fresh deprecation alias and canonical users got spurious
DeprecationWarnings (suite warnings fell 221 → 86 after the fix).

## Rule

A rename sweep must ALSO sweep string-literal attribute access:
`getattr(x, "old_name"`, `x["old_name"]`, `hasattr(x, "old_name"`,
`Object.keys` lookups, and reflection over field names. Grep the OLD name as
a quoted string after any identifier sweep — surviving hits are either
deliberate alias machinery or bugs. Internal code must never route through
the deprecated alias it just created; wire that invariant into the PR's
verification greps.

## Detection

`grep -rn '"old_name"' package/` plus `grep -rn "'old_name'" package/` after
the sweep, with allowlists for the alias/shim files themselves. A warning
count dropping after a "cosmetic" fix is the runtime tell.
