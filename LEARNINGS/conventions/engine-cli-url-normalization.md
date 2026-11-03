# Engine-calling CLI commands accept both base and full-endpoint URLs

**Source:** #233 code review (canvastekk-workflow-sdk) · **Date:** 2026-11-03 · **Confidence:** high

`register_node`/`ctk register` takes the FULL registry endpoint
(`.../api/workflows/nodes/`); newer engine-calling commands (`ctk probe
--engine-url`) take the BASE URL. Authors paste whichever they have — so any
new engine-calling seam must normalize the known `/api/workflows/nodes`
suffix off before appending its own path (`fetch_published_definition`,
registry.py). Docstrings must not claim normalization the code doesn't do —
that gap was the one Major of the #233 review.
