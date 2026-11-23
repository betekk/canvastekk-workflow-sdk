# PLAN: Streaming reader for model_check.check result bodies

**Branch**: feat/288
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/288
**Base**: dev

## Acceptance Criteria

- [x] A 0.x fixture (the real dev report 346 file, 0.3.0, plus the 0.1.0 `model_check.rule` fixture) and a 1.0.0 fixture produce the same overview shape (tests).
- [x] Peak memory on a large synthetic fixture stays under a limit stated in the test.
- [x] A file with an unknown major or an unknown label fails with a named error (test).
- [ ] Released; version posted on betekk/canvastekk-llm-service#887. (The release workflow cuts the version when this merges to `dev`; the number is posted after the merge.)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---|---|---|---|
| `python/canvastekk_workflow_sdk/check_result_reader.py` (new) | `result_file.read_result_file_header` (unchanged) | `canvastekk_workflow_sdk/__init__.py` exports; later betekk/canvastekk-llm-service#887 (OpenCode worker tools) | low: new module, nothing calls it yet |
| `python/canvastekk_workflow_sdk/__init__.py` (3 new exports) | the module | every SDK importer sees 3 more names; parity and consumer-import-freeze tests | low |
| `python/pyproject.toml`, `poetry.lock`, `uv.lock` (extra `reader` = `ijson`, dev group) | ijson 3.x | installs with `-E reader`; CI installs with `-E fastapi` and the dev group | low: optional, lazy import |
| `python/tests/fixtures/check_results/*` (2 real files) | IFC report-346 fixture, FE 0.1.0 fixture | the new tests | none |
| `docs/RESULT-FILE.md` | — | readers of the standard | none |

## Implementation Phases

### Phase 1: The reader

- [x] **1.1** Add `check_result_reader.py` with `open_check_result`, `CheckResultReader.overview/failures/element`, named errors, and the optional `ijson` extra
    — **Why:** the agent tools (llm-service#887) need bounded reads of files too large to load.
    — **Done when:** overview, failures and element answer for 0.x and 1.0.0 fixtures; refusals are named; memory test passes.
    — **Done:** reader, named errors and the `reader` extra added; 18 tests incl. memory (peak 0.7 MB on a 13 MB file); files: python/canvastekk_workflow_sdk/check_result_reader.py, pyproject.toml, poetry.lock, uv.lock, tests; fixes: none
    — **Consumers affected:** none until llm-service#887.
- [x] **1.2** Export the three names, document the reader in `docs/RESULT-FILE.md`, run the full SDK suite and lint
    — **Why:** consumers import from the package root; the parity and import-freeze guards must stay green.
    — **Done when:** full pytest and `ruff check` are green.
    — **Done:** 3 exports, docs section, full suite 1325 passed, ruff clean; files: __init__.py, docs/RESULT-FILE.md; fixes: import order
    — **Consumers affected:** all SDK importers (additive names).

## Technical Notes

- Streaming uses `ijson` (pull parser, C backend where available). It is an optional extra because most nodes never read result files; the module imports it on first use and raises `READER_UNAVAILABLE` with the install hint.
- 0.x bodies: `result.requirements` become checks; failing items join failing measurements, failing rows and instance identities (ported from the IFC `check_facts` field mapping, #614), each in its own streaming pass with only the matching rows kept.
- The 1.0.0 fixture is synthetic (written by the tests in the schema's shape); no live 1.0.0 file exists yet (IFC#618, CWE#1477 open).

## Dependencies

None open. Consumed by betekk/canvastekk-llm-service#887.

## Risks & Mitigation

- Pure-Python ijson fallback is slower than the C backend; the worker installs wheels with the C backend.
- 1.0.0 shape may gain fields: additive by policy; unknown fields are ignored.

## Trace
GATE c5420cf tier=full lint=t typecheck=n.a build=- unit=t e2e=n.a
GATE 73f350a tier=full lint=t typecheck=n.a build=- unit=t e2e=n.a
