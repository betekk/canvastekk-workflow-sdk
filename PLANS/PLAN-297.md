# PLAN: Accept later 2.x result bodies and add body 2.2.0 with layout plans

**Branch**: feat/297
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/297
**Base**: dev

## Acceptance Criteria

- [x] A body tagged 2.2.0 with 2.1.0-only content reads through `CheckResultReader` with `report_visual_refs` preserved; the same input is mishandled on current `dev` (refs stripped).
- [x] The 2.1.0 example file validates unchanged under the 2.2.0 schema.
- [x] A `layout_plan` entry, a `spatial_reference` and a `spatial_context` validate; an unknown `kind`, a measurement with an unknown top-level key and a `layout_plan` with an unknown key are rejected.
- [x] `report_visuals(ids)` returns a valid `layout_plan` and a valid `plan_band` from one body, and omits an entry whose `kind` is unknown without raising.
- [x] A measurement with a malformed `spatial_context` is yielded without it and does not raise; malformed body `spatial_reference` reads as absent.
- [x] A body tagged with a version that has no schema file still raises `CheckResultReadError`.
- [x] All published test vectors pass against reference implementations in both SDK test lanes, and the vectors are importable from the published Python and TypeScript packages.
- [x] `docs/RESULT-FILE.md` documents 2.2.0, the new keys and the grouping rule; the 2.1.0 section is unchanged.
- [x] A 2.2.0 example is added under `schemas/result-body/model_check.check/examples/` and its packaged mirror.
- [x] The version lands as a minor release (`feat` commits), and the release-note source names result body 2.2.0; Step 10 verifies that text in the actual PR body.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---|---|---|---|
| `schemas/result-body/model_check.check/2.2.0.json` + `examples/nested-2.2.0.json` | immutable 2.1.0 schema/example | canonical contract; Python and TypeScript parity tests; downstream CRS/FE/CISA readers | high |
| `python/canvastekk_workflow_sdk/data/schemas/result-body/model_check.check/{2.2.0.json,examples/nested-2.2.0.json}` | canonical schema/example | installed Python `load_check_body_schema`, wheel consumers | high |
| `typescript/src/check-verdict.ts`, `typescript/src/index.ts` | canonical 2.2.0 schema | published TypeScript validators; downstream TypeScript readers | high |
| `schemas/result-body/model_check.check/vectors/floor-groups.json` and packaged Python mirror | 2.2.0 spatial contract | SDK Python/TypeScript reference tests; CRS #309 and FE #3697 grouping tests | high |
| `typescript/src/model-check-floor-group-vectors.ts`, `typescript/src/index.ts` | canonical grouping vectors | published TypeScript package consumers and parity tests | medium |
| `python/canvastekk_workflow_sdk/check_verdict.py` | shipped 2.2.0 schema | grouped schema loader, version predicates, SDK reader and downstream version gates | high |
| `python/canvastekk_workflow_sdk/check_result_reader.py` | version predicates, 2.2.0 definitions | CISA summary/statements, report drawing and spatial reads, all existing finding readers | high |
| `python/tests/test_check_result_reader.py`, `python/tests/test_floor_group_vectors.py`, `typescript/tests/check-verdict.test.ts`, `typescript/tests/floor-group-vectors.test.ts` | schema, vectors and reader | regression evidence and pre-change counterexamples | medium |
| `docs/RESULT-FILE.md` | final schema and grouping semantics | producer/consumer implementers; release documentation | medium |

## Implementation Phases

### Phase 1: Publish the 2.2.0 contract and shared vectors

- [x] **1.1** Add canonical and packaged 2.2.0 schemas as additive copies of 2.1.0: discriminated `plan_band`/`layout_plan` drawings, optional body `spatial_reference`, optional measurement `spatial_context`, and reusable polygon definitions; leave every released schema byte-unchanged.
    — **Why:** downstream readers and producers need one immutable, versioned contract before any 2.2.0 result is emitted.
    — **Done when:** Draft 7 accepts the unchanged 2.1.0 example and the new spatial/drawing example, while unknown drawing kinds and unknown closed-object keys fail validation.
    — **Consumers affected:** Python/TypeScript validators, CRS/FE readers and CISA producers.
    — **Done:** canonical and packaged Draft 7 schemas accept both old and new examples and reject unknown kind/measurement/layout keys; files: schemas/result-body/model_check.check/2.2.0.json, python/canvastekk_workflow_sdk/data/schemas/result-body/model_check.check/2.2.0.json; fixes: none
- [x] **1.2** Add canonical and packaged `nested-2.2.0.json` examples containing one `layout_plan`, one `plan_band`, body spatial reference and measurement spatial context.
    — **Why:** a complete valid example pins the intended additive shape and gives every consumer a common fixture.
    — **Done when:** both example copies are byte-identical and validate against both language schema mirrors.
    — **Consumers affected:** SDK tests, downstream fixture authors and package consumers.
    — **Done:** byte-identical canonical and packaged examples contain both drawing kinds and both spatial objects; files: schemas/result-body/model_check.check/examples/nested-2.2.0.json, python/canvastekk_workflow_sdk/data/schemas/result-body/model_check.check/examples/nested-2.2.0.json; fixes: none
- [x] **1.3** Export the 2.2.0 TypeScript schema and add parity/rejection tests beside the existing 2.0.0/2.1.0 tests.
    — **Why:** publishing only the Python mirror would leave the TypeScript contract at 2.1.0 and split the SDK's cross-language guarantee.
    — **Done when:** Ajv deep-equals the canonical schema, accepts both old and new examples and rejects the required malformed counterexamples.
    — **Consumers affected:** published TypeScript SDK consumers and FE contract tests.
    — **Done:** exported Ajv mirror deep-equals canonical 2.2.0 and passes positive/negative parity tests; files: typescript/src/check-verdict.ts, typescript/src/index.ts, typescript/tests/check-verdict.test.ts; fixes: corrected two pre-existing 2.1.0 description-only mirror drifts proven by the base parity test
- [x] **1.4** Publish floor-grouping JSON vectors in the canonical schema folder, Python package resources and TypeScript exports, covering mixed-height single floor, two floors, degenerate-storey fallback, unplaced rows and a cross-floor path.
    — **Why:** CRS and FE must derive identical report-only floor groups rather than inventing separate measurement semantics.
    — **Done when:** resource/export parity tests match the canonical bytes/data and name all five required cases with deterministic expected groups, display elevations, unplaced rows and continuation labels.
    — **Consumers affected:** SDK reference tests, CRS #309 and FE #3697.
    — **Done:** canonical, Python-resource and TypeScript-export vectors match and name all five required cases with expected groups, elevations, unplaced rows and cross-floor clips; files: schemas/result-body/model_check.check/vectors/floor-groups.json, python/canvastekk_workflow_sdk/data/schemas/result-body/model_check.check/vectors/floor-groups.json, typescript/src/model-check-floor-group-vectors.json, typescript/src/model-check-floor-group-vectors.ts, typescript/src/index.ts, python/tests/test_floor_group_vectors.py, typescript/tests/floor-group-vectors.test.ts; fixes: none

### Phase 2: Read later 2.x bodies safely and document grouping

- [x] **2.1** Add explicit grouped-version and 2.1-or-later predicates, load only syntactically supported versions whose schema resource exists, and replace exact-version checks in schema-part selection, optional-reference cleanup and drawing lookup.
    — **Why:** additive 2.x minors must retain required facts without making an unshipped future schema silently readable.
    — **Done when:** the 2.1-content-as-2.2 counterexample preserves refs, 2.0.0 behavior is unchanged, and an unshipped 2.3.0 tag raises `UNSUPPORTED_RESULT_SCHEMA_VERSION` at open.
    — **Consumers affected:** all `CheckResultReader` users and downstream SDK version-gate imports.
    — **Done:** shipped-schema-bounded grouped/visual predicates now drive layout, part selection and optional cleanup; the 2.1-as-2.2 counterexample and 2.3.0 refusal pass; files: python/canvastekk_workflow_sdk/check_verdict.py, python/canvastekk_workflow_sdk/check_result_reader.py, python/tests/test_check_result_reader.py; fixes: replaced the remaining iter_findings tuple dependency and ordered schema-resource refusal before envelope validation
- [x] **2.2** Validate requested drawings by their `kind`, expose valid body `spatial_reference` through one bounded reader call, and drop malformed optional spatial objects while yielding required measurement facts.
    — **Why:** optional report evidence must never invalidate a check verdict or discard unrelated valid drawings.
    — **Done when:** mixed valid bands/layout plans return together, unknown/malformed/inverted drawings are omitted, malformed spatial context is removed from its yielded row, and malformed spatial reference reads as absent.
    — **Consumers affected:** CISA summary packaging, CRS visuals and downstream finding consumers.
    — **Done:** kind-specific mixed drawing lookup, geometric checks, valid spatial-reference reads and malformed spatial cleanup pass without losing required rows; files: python/canvastekk_workflow_sdk/check_result_reader.py, python/tests/test_check_result_reader.py; fixes: none
- [x] **2.3** Add test-local Python and TypeScript reference implementations of the documented render-time grouping algorithm and run every published vector in both lanes.
    — **Why:** the ticket requires executable proof of the shared rule without creating a new production renderer API that downstream tickets did not request.
    — **Done when:** both test lanes pass all vector cases, including the 1.5 m fallback boundary, home-floor assignment and continuation label for a cross-floor path.
    — **Consumers affected:** CRS/FE implementations that reuse the same vectors; no production API added.
    — **Done:** Python and TypeScript test-local references pass all five vectors including exact-gap clustering and cross-floor clips; files: python/tests/test_floor_group_vectors.py, typescript/tests/floor-group-vectors.test.ts; fixes: passed root fallback gap explicitly, included single-point z evidence and corrected adjacent-segment iteration
- [x] **2.4** Append a 2.2.0 section to `docs/RESULT-FILE.md` without editing the 2.1.0 section, documenting every new key, optional-versus-required containment, source/elevation semantics and all five grouping rules.
    — **Why:** producers and renderers need the contract and report-only grouping semantics in the SDK's canonical documentation.
    — **Done when:** a diff shows the existing 2.1.0 section unchanged and the new section links the schema, example and vectors.
    — **Consumers affected:** SDK users and all downstream ticket implementers.
    — **Done:** appended the 2.2.0 contract and five-rule grouping section with schema/example/vector links; the existing 2.1.0 section is untouched; files: docs/RESULT-FILE.md; fixes: none
- [x] **2.5** Run the full SDK gate on the final tree (Python Ruff, compile/type smoke, full pytest and wheel/sdist build; TypeScript ESLint, both typechecks, full Vitest and tsup build), verify built-package access to schema/example/vectors, tick satisfied ACs and record the final-SHA full-gate memo.
    — **Why:** this is a public schema and cross-module reader change, so both phases and the ticket exit require full verification.
    — **Done when:** every applicable gate is green, built artifacts expose the new resources/exports, the phase's `feat` commit subject and the prepared PR release-note sentence name result body 2.2.0, no implementation AC remains unchecked, and `GATE <short-sha> tier=full` names the pushed tree.
    — **Consumers affected:** all SDK release consumers.
    — **Done:** final full gate passed with 1348 Python and 577 TypeScript tests plus both builds; wheel and dist smoke imports expose 2.2.0 and five vectors; feat commits and prepared PR text name 2.2.0; files: PLANS/PLAN-297.md; fixes: normalized four mirrored JSON files from executable to regular mode

## Technical Notes

- “Every new key is optional” describes additive members on existing body/measurement objects. Within a present drawing or sourced observation, required identity/geometry/source fields remain mandatory; otherwise malformed optional data could not be distinguished from an empty valid object.
- `layout_plan` requires `kind`, `floor_elevation_mm`, `cut_z_mm`, `crop_xy_mm` and `layers`; fixture, region and portal collections may be empty or omitted. `storey_ref` and `true_north_deg` are optional. Reuse `report_visual_refs`; add no parallel reference key.
- Storey refs are labels/references, not stored floor-level authority. Display level prefers `floor_surface.elevation_mm`; only render-time derivation creates floor groups. Never add `level_id`, `level_source` or `primitive_level_ids`.
- Version tolerance is bounded by shipped schema resources. A syntactically later 2.x tag without its schema fails loudly rather than being validated against 2.2.0.
- Reference grouping lives in tests only. The shared package artifact is the vector set; CRS and FE own their production grouping and clipping.
- Release notes are generated from the squash-merged `feat` commit. The PR body must include a release-note sentence naming `model_check.check` result body **2.2.0**; do not hand-edit `CHANGELOG.md`.

## Dependencies

None in the run. Later reader/producer tickets are blocked by this SDK merge and release.

## Risks & Mitigation

- **Risk:** future-version tolerance accidentally accepts an unshipped schema. **Mitigation:** resource-existence checks and an explicit 2.3.0 refusal test.
- **Risk:** optional malformed spatial data invalidates required findings. **Mitigation:** member-level cleanup tests prove rows survive while only malformed optional members are removed.
- **Risk:** Python and TypeScript schemas/vectors drift. **Mitigation:** deep parity tests against canonical JSON and built-package smoke checks.
- **Risk:** large unrequested drawings regress streaming memory use. **Mitigation:** retain the existing parser-event filtering and 3 MiB unrequested-drawing test.

## Trace

LOG Architecture review: one Major malformed-evidence finding corrected before implementation; release-note evidence is now the feat commit plus prepared PR text, with actual PR-body verification pinned to Step 10. Consumers inspected: plan executor, PR create route, Python/TypeScript schema and reader callers. Requirements Gaps: [].
LOG Phase 1 full-gate escalation: public schema additions and cross-module consumers.
LOG Phase 2 full-gate escalation: public reader contract and unconditional ticket exit gate.
LOG Phase 1 gate: Draft 7 positive/negative checks green; Python vector resource test 1 passed; full Python Ruff + compileall + pytest 1341 passed + wheel/sdist build green; TypeScript ESLint + typechecks + Vitest 576 passed + tsup build green. Pre-existing 2.1.0 TS description drift reproduced before correction (23 passed, 1 failed); no validation-rule change. E2E n.a. (backend/package only).
GATE e1a4a88 tier=full lint=t typecheck=t build=t unit=t e2e=n.a
LOG Phase 2 scoped reader gate initially failed 14 tests: one remaining exact-version tuple and resource-vs-envelope error ordering; fixed at the shared seam, rerun 40 passed. Vector implementation fixes recorded per step. Final full gate: Python Ruff + compileall + pytest 1348 passed + wheel/sdist build; TypeScript ESLint + both typechecks + Vitest 577 passed + tsup build. Wheel and dist package smoke green. E2E n.a. (backend/package only).
GATE d6cab63 tier=full lint=t typecheck=t build=t unit=t e2e=n.a
LOG Inline code review: 18 files; zero findings; direct-caller coverage complete; Requirements Gaps: []. One deduplicated learning recorded; derived LEARNINGS/_index.md intentionally not staged per repo policy.
LOG Post-review gate on pushed implementation 00b9b60: Python Ruff + compileall + pytest 1348 passed + wheel/sdist build; TypeScript ESLint + both typechecks + Vitest 577 passed + tsup build. E2E n.a.
GATE 00b9b60 tier=full lint=t typecheck=t build=t unit=t e2e=n.a
