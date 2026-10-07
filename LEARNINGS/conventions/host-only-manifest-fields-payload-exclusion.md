# Host-only manifest fields never enter build_registry_payload

**Source:** #3499 code review (canvastekk-workflow-sdk) · **Date:** 2026-10-07 · **Confidence:** high

Host-side-only manifest fields (`retry`, `node_role`, `node_status`,
`hard_max_runtime_seconds`) must never enter `build_registry_payload` — its
explicit-key dict (`registry.py:302`) is the single exclusion seam against the
engine's `extra="forbid"` register request. Pin each new host-only key with a
negative `assert "<key>" not in payload` test in `TestBuildRegistryPayload`
(DA-1955 convention); the register probe's extra-key check is only the runtime
backstop.
