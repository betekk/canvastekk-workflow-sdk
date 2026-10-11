---
title: New SDK features ship to both stacks in the same change
type: pattern
---

# New SDK features ship to both stacks in the same change

One PR, both stacks: `python/` AND `typescript/` get every new feature together,
with mirrored tests. A feature merged to one stack only (see #124's debt:
`verify_node` and `to_openapi` landed python-only) splits capability across
authors and forces the engine to pick a canonical side.

- **Rule:** if the diff touches feature code in one language dir and not the
  other, the PR is incomplete — state the reason or split it.
- **Enforcement:** mirrored test names across `python/tests/` and
  `typescript/tests/`; parity noted in the PR checklist.
- **Root README** carries the one-liner under "Available SDKs".
