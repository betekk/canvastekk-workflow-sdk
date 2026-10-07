# Derived bounds are plain properties, not computed_fields

**Source:** #3499 code review (canvastekk-workflow-sdk) · **Date:** 2026-10-07 · **Confidence:** high

A derived value hosts compute from declared fields (`effective_runtime_seconds`
= min of the declared pair) is a plain `@property`, deliberately NOT a
`@computed_field` — computed_field would silently add the key to every
`model_dump` (the `/manifest` and export wire shapes), while the wire carries
only the declared inputs. Pin the absence with a
`"derived_key" not in model_dump()` test.
