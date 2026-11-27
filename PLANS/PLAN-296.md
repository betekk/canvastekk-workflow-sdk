# PLAN: Document the plan band padding in the 2.1.0 result schema

**Branch**: feat/296
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/296
**Base**: dev

## Acceptance Criteria

- [ ] `z_band_mm` description states: bottom = the finding's lowest evidence point − 100 mm, top = its highest point + 100 mm, in model-space millimetres.
- [ ] `crop_xy_mm` description states the crop is the evidence's footprint padded by 1 000 mm on every side.
- [ ] The two schema copies are still byte-identical, and the bundled 2.1.0 example still validates.
- [ ] No change to validation behaviour (a file that validates today still validates).

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `schemas/result-body/model_check.check/2.1.0.json` | — | SDK schema loader (`result_file.py`), `python/tests/test_check_result_reader.py` (loads `SCHEMA_V2` + `examples/nested-2.1.0.json`), node authors reading the contract | low (description-only) |
| `python/canvastekk_workflow_sdk/data/schemas/result-body/model_check.check/2.1.0.json` | the canonical copy (kept byte-identical) | the packaged wheel's schema loader | low |

Only these two copies exist (`find . -name 2.1.0.json`). No TypeScript mirror. `ruff` is the configured
linter and `pytest` the test runner (`python/pyproject.toml`); there is no build step for a JSON edit.

## Implementation Phases

### Phase 1: Describe the padding and prove nothing else changed

- [ ] **1.1** Extend the `plan_band.z_band_mm` and `plan_band.crop_xy_mm` descriptions in the canonical `schemas/result-body/model_check.check/2.1.0.json`: Z bottom/top = the finding's lowest/highest viewer-representation point −/+ 100 mm; crop = the evidence footprint padded 1 000 mm per side, all in model-space millimetres. No structural edit.
    — **Why:** the rule exists only in the producer's code today; readers such as the top-down 3D view need it from the contract (epic D5).
    — **Done when:** `git diff` shows changes only inside the two `description` strings, and the file still parses as JSON.
    — **Consumers affected:** schema readers (documentation only).
- [ ] **1.2** Copy the edited file over the packaged mirror `python/canvastekk_workflow_sdk/data/schemas/result-body/model_check.check/2.1.0.json` and assert `cmp` returns identical.
    — **Why:** the wheel ships this copy; the two must never drift.
    — **Done when:** `cmp schemas/.../2.1.0.json python/.../data/schemas/.../2.1.0.json` exits 0.
    — **Consumers affected:** the packaged schema loader.
- [ ] **1.3** Prove validation is unchanged: validate `examples/nested-2.1.0.json` against the base schema and the edited schema (both must succeed identically), then run the SDK's schema tests (`python/tests/test_check_result_reader.py`, `test_schema_dialect.py`, `test_schema_stability_renames.py`) plus ruff on the repo's configured targets.
    — **Why:** AC 3 and 4 — descriptions are documentation, and the test run proves the loader still accepts the bundled example.
    — **Done when:** both validations succeed, the named pytest files pass, and ruff reports nothing on the changed paths.
    — **Consumers affected:** none (verification only).

## Technical Notes

Producer rule being documented: `canvastekk-ifc-service-app` `apps/python/toilet_checks/report_plan_bands.py`
(`_Z_PADDING_MM = 100.0`, `_XY_PADDING_MM = 1_000.0`; crop and band derive from the finding's
`viewer_representation` points).

## Dependencies

None.

## Risks & Mitigation

- **Risk:** an accidental structural edit changes validation. **Mitigation:** 1.1 restricts the diff to descriptions and 1.3 validates the same example against base and edited schemas.
