# PLAN: Publish Model Checker result body 2.1.0

**Branch**: feat/293
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/293
**Base**: dev

## Acceptance Criteria

- [ ] The installed SDK ships the schema and example. Its streaming reader opens supported existing fixtures and 2.1.0 findings with or without drawings, preserving row indexes and facts.
- [ ] Validation covers plan-band drawing records and references. Verdict-only consumers can read the existing envelope and summary without the geometry.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
| --- | --- | --- | --- |
| `schemas/result-body/model_check.check/2.1.0.json` and example | Immutable 2.0.0 grouped shape; envelope 1.1.0 | SDK validators, IFC writer, frontend and engine readers | High |
| `python/canvastekk_workflow_sdk/data/schemas/result-body/model_check.check/2.1.0.json`, `python/canvastekk_workflow_sdk/check_verdict.py` | Canonical schema | Installed SDK validators, IFC writer, SDK grouped reader | High |
| `python/canvastekk_workflow_sdk/check_result_reader.py` | Exact-version schema loader and staged header | IFC statement and report assembly; LLM evidence tools; compact existing overview, failure and element readers | High |
| `typescript/src/check-verdict.ts`, `typescript/src/index.ts` | Canonical schema and existing 2.0.0 contract | Published TypeScript validators and parity tests | Medium |
| `python/tests/test_check_result_reader.py`, `typescript/tests/check-verdict.test.ts`, `docs/RESULT-FILE.md` | Both SDK lanes | Published contract examples and evidence of compatibility | Medium |

## Implementation Phases

### Phase 1: Add the optional drawing contract

- [ ] **1.1** Publish the additive 2.1.0 schema and fixture in both SDK packages.
    — **Why:** All producers and consumers need the same optional drawing shape before a workflow emits it.
    — **Done when:** The Python wheel contains the schema and example; Python and TypeScript validators agree with the canonical schema, accept the example and an unchanged grouped body, and reject malformed drawing and reference shapes.
    — **Consumers affected:** Installed Python and TypeScript SDKs, IFC writers and result-body validators.
- [ ] **1.2** Dispatch grouped reads by the recorded body version and expose selected drawing lookup.
    — **Why:** Required findings and the quick verdict must remain available when an optional drawing is absent.
    — **Done when:** Fixtures preserve old results, exact finding indices and compact queries for 2.1.0; result headers stay unchanged; only requested valid drawings are returned when explicitly read; corrupt optional drawings never change verdict facts.
    — **Consumers affected:** IFC statements and report assembly, LLM evidence tools, independent header readers.

## Technical Notes

Keep the `1.0.0` default write body and the `1.1.0` result-file envelope. Do not edit the published `2.0.0` artifacts. The documentation describes explicit, file-local reference keys and narrow `plan_band` views in model-space millimetres. Optional graphics do not participate in judgment; malformed optional references are ignored by the read path while structurally malformed required evidence is still refused. Draft 7 validates record shapes; consumers resolve references in that one saved file. Existing readers do not materialize any report geometry.

## Dependencies

None. IFC, web, and AI readers upgrade after the SDK release and before writer activation.

## Risks & Mitigation

Check both compact and lossless entry points, older layout acceptance, supplied-but-unavailable graphics, and installed package content before merge.

## Trace
