# Version Tolerance Must Be Bounded by Shipped Schema Resources

**Category**: decisions
**Confidence**: 0.9
**Scope**: project
**Date**: 2026-11-28
**Source**: #297 / `python/canvastekk_workflow_sdk/check_result_reader.py:322-337`

## Decision

Recognize a grouped 2.x version syntactically, but open it only when that exact version's schema resource ships in the package. Optional 2.1+ cleanup may follow the minor-version predicate; it must never make an unshipped future body borrow the newest schema.

## Why

This preserves additive-minor tolerance without turning it into silent forward compatibility. The 2.1.0-content-as-2.2.0 test proves refs survive, while the 2.3.0 counterexample fails at open with `UNSUPPORTED_RESULT_SCHEMA_VERSION` before any finding is read.
