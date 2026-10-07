# A tightened gate updates its stated equivalence claim in the same change

**Source:** #3499 architecture review (canvastekk-workflow-sdk) · **Date:** 2026-10-07 · **Confidence:** 0.85

When an offline gate becomes stricter than the authority it mirrors (e.g.
`_probe_definition` rejecting budgets the engine would accept), its docstring
and probe labels must change in the same commit — the "passes locally ⇔ passes
registration" biconditional silently goes false (⇒ only), and CI debuggers read
that docstring as ground truth. Rename the claim and add the new probe to the
`probes` list so the report self-describes the added strictness.
