# Validator loops must cover new slug fields

**Source:** #3498 code review (canvastekk-workflow-sdk) · **Date:** 2026-10-07 · **Confidence:** high

`NodeExecutionRequest._reject_dot_segments` iterates a hardcoded field tuple;
adding a slug-patterned field without extending the tuple (with a None guard
for optional fields) creates silent cross-leg drift — the TS `slugField`
refinement rejects `a..b` at parse while python accepts it. Extend the tuple
in the same change as the field, and mirror the refinement in a python test.
