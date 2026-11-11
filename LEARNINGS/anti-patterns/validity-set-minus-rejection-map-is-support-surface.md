# Validity set ≠ support set: a Literal's values may be rejected by an adjacent UNSUPPORTED map

**Category:** anti-pattern (API-contract reading)
**Confidence:** high
**Scope:** canvastekk-workflow-sdk + every consumer registering nodes
**Date:** 2026-11-11

`InvokeType = Literal["http", "lambda", "sagemaker", "in-process"]`
(python/canvastekk_workflow_sdk/registry.py:23) reads as the accepted set,
but `lambda` sits in `UNSUPPORTED_INVOKE_TYPES` (registry.py:25) and is
rejected with migration guidance. The TS mirror exports the same four
strings (typescript/src/registry.ts:11).

Anti-pattern: trusting a type literal (or exported set) as the *support*
surface without checking for an adjacent rejection map. Registration code
that selects `invoke_type` from the Literal can pick a value that fails at
runtime.

Rule: when a contract exposes BOTH a validity set and a rejection/disabled
map, the support surface is `validity − rejected`. Document the subtraction,
never the literal alone. Caught misrecording this in
docs/COMPATIBILITY-v0.64.0.md §2.4 (initially wrote `{http,lambda,inline…}`
from memory — wrong set, invented member, missed the rejection map).
