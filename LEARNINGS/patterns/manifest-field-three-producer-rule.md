# Manifest fields have three producers, not two

**Source:** #3499 architecture review (canvastekk-workflow-sdk) · **Date:** 2026-10-07 · **Confidence:** 0.9

Adding a field to `WorkflowNodeManifest` means deciding its presence in THREE
producers, not two: `build_registry_payload` (engine request, `extra="forbid"`
— usually omit), the `/manifest` model dump (always carries it — pydantic
serializes non-None fields), and `export_definition`'s re-add block
(`definition.py:568-570`, which must re-add host-side fields or an override
silently drops on the export→commit→probe round-trip while the documented
"full manifest shape" equivalence breaks). Missing the third producer was the
one BLOCK finding of the #3499 review.
