# PLAN: Publish Model Checker result body 2.1.0

**Branch**: feat/293
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/293
**Base**: dev

## Acceptance Criteria

- [x] The installed Python SDK ships the canonical schema and example, and the TypeScript validator exposes the same schema.
- [x] The streaming reader opens supported existing fixtures and 2.1.0 findings with or without drawings, preserving row indexes and facts.
- [x] Validation covers plan-band drawing records and references.
- [x] Verdict-only consumers can read the existing envelope and summary without loading optional geometry.

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

- [x] **1.1** Publish the additive 2.1.0 schema and fixture in both SDK packages.
    — **Why:** All producers and consumers need the same optional drawing shape before a workflow emits it.
    — **Done when:** The Python wheel contains the schema and example; Python and TypeScript validators agree with the canonical schema, accept the example and an unchanged grouped body, and reject malformed drawing and reference shapes.
    — **Consumers affected:** Installed Python and TypeScript SDKs, IFC writers and result-body validators.
    — **Done:** Draft 7 and Ajv match the canonical schema; the built wheel loads the example and the npm package exports the validator. Files: schema, examples, package exports and parity tests; fixes: none.
- [x] **1.2** Dispatch grouped reads by the recorded body version and expose selected drawing lookup.
    — **Why:** Required findings and the quick verdict must remain available when an optional drawing is absent.
    — **Done when:** Fixtures preserve old results, exact finding indices and compact queries for 2.1.0; result headers stay unchanged; only requested valid drawings are returned when explicitly read; corrupt optional drawings never change verdict facts.
    — **Consumers affected:** IFC statements and report assembly, LLM evidence tools, independent header readers.
    — **Done:** Older and new compact and lossless reads preserve recorded facts; the built wheel reads the header verdict and resolves the 1.4–1.8 m band. Files: Python reader, tests and result-file docs; fixes: updated unsupported-version test to select still-unsupported versions.

## Technical Notes

Keep the `1.0.0` default write body and the `1.1.0` result-file envelope. Do not edit the published `2.0.0` artifacts. The documentation describes explicit, file-local reference keys and narrow `plan_band` views in model-space millimetres. Optional graphics do not participate in judgment; malformed optional references are ignored by the read path while structurally malformed required evidence is still refused. Draft 7 validates record shapes; consumers resolve references in that one saved file. Existing readers do not materialize any report geometry.

## Dependencies

None. IFC, web, and AI readers upgrade after the SDK release and before writer activation.

## Risks & Mitigation

Check both compact and lossless entry points, older layout acceptance, supplied-but-unavailable graphics, and installed package content before merge.

## Trace

LOG Full exit gate: schema change and cross-module readers in both SDK packages.
LOG Fix 1: unsupported-version test now probes 2.2.0 and 3.0.0 because 2.1.0 is a supported body.
LOG Scoped Ruff and ESLint, Python compile and built wheel smoke, TypeScript typechecks and package smoke, 1,339 Python tests, 574 TypeScript tests. Backend SDK change; no browser E2E target.
LOG Inline review fix: filter drawing IDs in the parser event stream before building objects. A large unrequested polygon layer stays below the reader's 3 MiB test ceiling.
GATE 5b3ebfe tier=full lint=t typecheck=t build=t unit=t e2e=n.a
LOG Review re-gate: 1,340 Python tests, 574 TypeScript tests, built wheel reads a result header, its finding, and its selected drawing. Inline re-review: no blocking findings or requirements gaps; direct caller coverage complete. PLAN atomicity was checked at Step 7.
