# PLAN: Result file standard: layout schema, writer, header reader, manifest convention (Python + TypeScript)

**Branch**: feat/278
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/278
**Base**: dev
**Epic**: betekk/canvastekk-tracker#4309 (RF1)

## Acceptance Criteria
- [ ] Python and TypeScript writers produce byte-identical headers for the same input (shared golden file)
- [ ] Header keys appear before `body` (test reads only the start of the file)
- [ ] An invalid header or a `summary` that is nested, holds a list, exceeds 2 KB or has a non-`snake_case` key is rejected and **no file is written**
- [ ] Header reader returns the header of a 50 MB file without reading `body` (memory stays flat)
- [ ] Manifest convention documented with an example node
- [ ] Released as a 1.x minor with a CHANGELOG entry (release workflow on merge; `feat` commit → minor)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `schemas/result-file/1.0.0.json`, `schemas/result-file/end-value-1.0.0.json` (new, canonical) | — | Python/TS embedded copies, CWE#1378 (contract), FE#3113/#3114 fixtures | low |
| `python/canvastekk_workflow_sdk/data/schemas/result-file/*.json` (new, packaged copy) | canonical schemas | `result_file.py`, wheel consumers (CWE) | low |
| `python/canvastekk_workflow_sdk/result_file.py` (new) | packaged schemas, `exceptions.NodeOutputValidationError`, `NodeExecutionContext.run_id` | node authors (IFC later), CWE#1379 (header reader) | low (additive) |
| `python/canvastekk_workflow_sdk/workflow_node_manifest.py` (`result_file` output validator) | `result_file.RESULT_FILE_OUTPUT_FIELD` | every Python node manifest (validator only fires on a `result_file` output / `x-result-file` marker; no node uses either today — cross-repo grep of CWE/IFC/CWN/CLS `origin/dev`) | medium |
| `python/canvastekk_workflow_sdk/__init__.py` (exports) | `result_file.py` | public surface | low |
| `typescript/src/result-file.ts` (new) + `typescript/src/index.ts` exports | canonical schemas (embedded), `exceptions.NodeOutputValidationError`, `NodeExecutionContext.runId` | TS node authors, FE fixtures | low |
| `typescript/src/workflow-node-manifest.ts` (`validateFileFieldFormats`) | `result-file.ts` constant | every TS node manifest (same narrow trigger) | medium |
| `schemas/result-file/golden/*` (new) | writers | both test suites | low |
| `docs/RESULT-FILE.md` (new), `docs/GLOSSARY.md`, READMEs | — | node authors | low |

## Implementation Phases

### Canonical step format
- [ ] **N.M** <single atomic action — verb + target + outcome>
    — **Why:** <what this unblocks / why it must precede others>
    — **Done when:** <objective, checkable completion signal>
    — **Consumers affected:** <who depends on this; none if N/A>

### Phase 1: Canonical schemas
- [x] **1.1** Add `schemas/result-file/1.0.0.json` (draft-07 layout: header keys, `summary` scalar map with `snake_case` names, `body` any) and `schemas/result-file/end-value-1.0.0.json` (the `__end__.result_file` value) plus `schemas/result-file/README.md`
    — **Why:** single source of truth both runtimes and non-SDK producers read; CWE#1378 generates its contract from the end-value schema
    — **Done when:** both files parse and pass `Draft7Validator.check_schema`
    — **Consumers affected:** Python/TS embedded copies, CWE#1378, FE fixtures
- [x] **1.2** Ship the packaged copy under `python/canvastekk_workflow_sdk/data/schemas/result-file/` with a test asserting byte equality to the canonical files
    — **Why:** the wheel must carry the schema (CWE imports it); the equality test stops drift
    — **Done when:** equality test green
    — **Consumers affected:** wheel consumers

### Phase 2: Python writer, header reader, manifest convention
- [x] **2.1** Add `result_file.py`: constants, `ResultFileFormatError`, `validate_result_file_header`, `build_result_file_header`, `write_result_file` (validate → temp file → atomic rename; header keys before `body`; streamed body encode)
    — **Why:** the only supported writer; enforces the standard before saving
    — **Done when:** unit tests for valid write, every rejection case (no file left behind), key order
    — **Consumers affected:** node authors
- [x] **2.2** Add `read_result_file_header` (incremental top-level decode that stops at `body`, bounded header bytes) to `result_file.py`
    — **Why:** CWE#1379 checks the header without loading the body
    — **Done when:** tests for valid header, misordered keys, truncated input, oversize header, and a 50 MB file read with flat memory (tracemalloc peak < 1 MB)
    — **Consumers affected:** CWE#1379
- [x] **2.3** Add `result_file_output_schema()` and the manifest validator (a `result_file` output must be `type: string`, `format: file`, `x-result-file: true`; the marker is only legal on that output)
    — **Why:** lets CWE#1378 confirm the producer at save time
    — **Done when:** manifest tests for valid/invalid declarations; full suite green
    — **Consumers affected:** every Python node manifest (narrow trigger)
- [x] **2.4** Export the public names from `canvastekk_workflow_sdk/__init__.py`
    — **Why:** public surface for node authors and CWE
    — **Done when:** import test green
    — **Consumers affected:** public surface

### Phase 3: TypeScript twin
- [x] **3.1** Add `typescript/src/result-file.ts` (embedded schemas checked against canonical files, `validateResultFileHeader`, `buildResultFileHeader`, `writeResultFile`, `resultFileOutputSchema`) and export from `index.ts`
    — **Why:** TS nodes get the same writer
    — **Done when:** vitest suite for the same cases as 2.1
    — **Consumers affected:** TS node authors
- [x] **3.2** Extend `validateFileFieldFormats` with the same `result_file` declaration rule
    — **Why:** manifest parity with 2.3
    — **Done when:** manifest tests green
    — **Consumers affected:** every TS node manifest (narrow trigger)

### Phase 4: Golden parity and docs
- [x] **4.1** Add `schemas/result-file/golden/` (input + expected bytes) and assert both writers reproduce it exactly
    — **Why:** AC "byte-identical headers"
    — **Done when:** both suites compare against the golden bytes
    — **Consumers affected:** none
- [x] **4.2** Add `docs/RESULT-FILE.md` (layout, ownership split, writer usage, manifest convention with an example node, header reader, end-value schema), a GLOSSARY entry and README pointers
    — **Why:** AC "manifest convention documented with an example node"
    — **Done when:** docs merged; links resolve
    — **Consumers affected:** node authors

## Technical Notes
- Layout 1.0.0 (D46-D54 in FE `PLANS/PLAN-model-checker-v2.md`): `result_file_version`, `result_schema`, `result_schema_version`, `workflow_run_id`, `generated_at`, optional `summary`, then `body`.
- `result_schema` / `result_schema_version` are app labels (`app.kind`, semver); the SDK never validates `body` (content option B).
- `summary`: flat, scalar values, `snake_case` keys, ≤2048 bytes as compact UTF-8 JSON.
- Serialization is compact JSON (`,` / `:` separators, no ASCII escaping) so both runtimes produce identical header bytes; `generated_at` is UTC with milliseconds and `Z` (`Date.toISOString()` shape).
- "manifest" is not used in result-file names (ADR 0001).

## Dependencies
Parent: betekk/canvastekk-tracker#4309. Unblocks CWE#1378, CWE#1379.

## Risks & Mitigation
- **Number formatting differs between runtimes** (`1.0` vs `1`): golden uses integers/strings; docs tell producers to use integers or strings in `summary` when byte parity matters.
- **Strict manifest validator breaks an existing node**: mitigated by the cross-repo grep (no `result_file` outputs today) and the narrow trigger.

## Trace
