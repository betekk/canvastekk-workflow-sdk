# PLAN: Document the plan band padding in the 2.1.0 result schema

**Branch**: feat/296
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/296
**Base**: dev

## Acceptance Criteria

- [x] `z_band_mm` description states: bottom = the finding's lowest evidence point − 100 mm, top = its highest point + 100 mm, in model-space millimetres.
- [x] `crop_xy_mm` description states the crop is the evidence's footprint padded by 1 000 mm on every side.
- [x] The two schema copies are still byte-identical, and the bundled 2.1.0 example still validates.
- [x] No change to validation behaviour (a file that validates today still validates).

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `schemas/result-body/model_check.check/2.1.0.json` | — | SDK schema loader (`result_file.py`), `python/tests/test_check_result_reader.py` (loads `SCHEMA_V2` + `examples/nested-2.1.0.json`), node authors reading the contract | low (description-only) |
| `python/canvastekk_workflow_sdk/data/schemas/result-body/model_check.check/2.1.0.json` | the canonical copy (kept byte-identical) | the packaged wheel's schema loader | low |

Only these two copies exist (`find . -name 2.1.0.json`). No TypeScript mirror. `ruff` is the configured
linter and `pytest` the test runner (`python/pyproject.toml`); there is no build step for a JSON edit.

## Implementation Phases

### Phase 1: Describe the padding and prove nothing else changed

- [x] **1.1** Extend the `plan_band.z_band_mm` and `plan_band.crop_xy_mm` descriptions in the canonical `schemas/result-body/model_check.check/2.1.0.json`: Z bottom/top = the finding's lowest/highest viewer-representation point −/+ 100 mm; crop = the evidence footprint padded 1 000 mm per side, all in model-space millimetres. No structural edit.
    — **Why:** the rule exists only in the producer's code today; readers such as the top-down 3D view need it from the contract (epic D5).
    — **Done when:** `git diff` shows changes only inside the two `description` strings, and the file still parses as JSON.
    — **Consumers affected:** schema readers (documentation only).
    — **Done:** z_band_mm and crop_xy_mm descriptions extended with the 100 mm / 1000 mm padding rule; diff is exactly two description lines; files: schemas/result-body/model_check.check/2.1.0.json; fixes: test environment only (PYTHONPATH, see Trace)
- [x] **1.2** Copy the edited file over the packaged mirror `python/canvastekk_workflow_sdk/data/schemas/result-body/model_check.check/2.1.0.json` and assert `cmp` returns identical.
    — **Why:** the wheel ships this copy; the two must never drift.
    — **Done when:** `cmp schemas/.../2.1.0.json python/.../data/schemas/.../2.1.0.json` exits 0.
    — **Consumers affected:** the packaged schema loader.
    — **Done:** packaged mirror overwritten with the canonical file; cmp identical; wheel build verified to contain the documented schema; files: python/canvastekk_workflow_sdk/data/schemas/result-body/model_check.check/2.1.0.json; fixes: test environment only (PYTHONPATH, see Trace)
- [x] **1.3** Prove validation is unchanged: validate `examples/nested-2.1.0.json` against the base schema and the edited schema (both must succeed identically), then run the SDK's schema tests (`python/tests/test_check_result_reader.py`, `test_schema_dialect.py`, `test_schema_stability_renames.py`) plus ruff on the repo's configured targets.
    — **Why:** AC 3 and 4 — descriptions are documentation, and the test run proves the loader still accepts the bundled example.
    — **Done when:** both validations succeed, the named pytest files pass, and ruff reports nothing on the changed paths.
    — **Consumers affected:** none (verification only).
    — **Done:** bundled nested-2.1.0 example validates with 0 errors against BOTH base and edited schemas; schema tests 42/42; full SDK suite 1340 passed; wheel + sdist build green; fixes: test environment only (PYTHONPATH, see Trace)

## Technical Notes

Producer rule being documented: `canvastekk-ifc-service-app` `apps/python/toilet_checks/report_plan_bands.py`
(`_Z_PADDING_MM = 100.0`, `_XY_PADDING_MM = 1_000.0`; crop and band derive from the finding's
`viewer_representation` points).

## Dependencies

None.

## Risks & Mitigation

- **Risk:** an accidental structural edit changes validation. **Mitigation:** 1.1 restricts the diff to descriptions and 1.3 validates the same example against base and edited schemas.
## Trace

GATE bb1719a tier=full lint=n.a typecheck=n.a build=t unit=t e2e=n.a
LOG lint/typecheck n.a: only two JSON schema files changed; no Python/TS sources touched and no JSON linter/typechecker is configured. Scoped SDK schema tests 42/42; full python suite 1340 passed; `uv build` wheel+sdist green and the wheel contains the documented schema. e2e n.a: SDK has no e2e target for a schema description.
LOG test environment fix: the schema-stability subprocess imported an older INSTALLED canvastekk_workflow_sdk (unknown location) instead of the worktree source. Running pytest with PYTHONPATH=<worktree>/python makes the subprocess import the edited sources; without it 2 tests fail on WorkflowNodeDeprecationInfo.
