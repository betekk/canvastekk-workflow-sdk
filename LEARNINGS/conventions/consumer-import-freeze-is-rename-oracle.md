---
title: The consumer-import freeze is the rename-completeness oracle
type: convention
---

# The consumer-import freeze is the rename-completeness oracle

When a public-API rename lands, the frozen consumer-import inventory
(`python/tests/test_consumer_import_freeze.py` — CWN/CLS/CWE rows from the
2026-11-01 audit) doubles as the blast-radius oracle: every FREEZE row must
keep resolving, and rename PRs should assert freeze ⊆ alias coverage instead
of inventing a parallel enumeration. The freeze suite stayed byte-identical
through all of #271's five phases — that was the standing proof the consumer
surface held.

- **Rule:** rename PRs never modify the freeze suite; a red freeze row is a
  missed alias, not a stale row (staleness is a deliberate, separately
  reviewed change).
- **Boundary:** the inventory is a snapshot — names consumers adopted after
  the audit aren't in it, so alias tests still enumerate the full ADR map
  (a superset of any consumer usage). Freeze pins reality; the map pins
  intent.
