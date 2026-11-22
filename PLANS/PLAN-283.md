# PLAN: x-verdict, check verdict step, result-file layout 1.1.0 (SDK 1.2.0)

**Branch**: feat/283
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/283
**Base**: dev
**Epic**: betekk/canvastekk-tracker#4332 (VS1). Source plan: canvastekk-frontend-nextjs `PLANS/PLAN-model-checker-v2.md` (D85–D100, sections 5.6–5.9).

## Acceptance Criteria
- [x] A 1.1.0-era manifest without `checks` still validates and serializes byte-identically (no `checks` key emitted).
- [x] `judge()` tests cover the 8 operators × tolerance × `bound` × `alternatives` × per-subject counting, and the D90 roll-up.
- [x] A node class with an `x-verdict`-marked input that does not subclass `CheckNodeBase` is rejected (class creation and `check_node_conformance_errors`).
- [x] Layout 1.1.0 and `model_check.check` 1.0.0 body schemas are published; the Python and TypeScript validators accept the shared golden example, and both writers produce byte-identical 1.1.0 headers.
- [x] Released as 1.2.0 with `run_context` (SDK#281) included (release workflow on merge; `feat` commit → minor).

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---|---|---|---|
| `schemas/result-file/1.1.0.json` (new) + packaged copy | — | `result_file.py`, `result-file.ts`, CWE run-end check (VS4), FE reader (VS8a) | low (new file; 1.0.0 untouched) |
| `schemas/result-body/model_check.check/1.0.0.json` (new) + packaged copy | — | `check_verdict.py` body validation, CISA (VS5), FE (VS8a), CISA#614 | low |
| `python/canvastekk_workflow_sdk/result_file.py` (layout 1.1.0: header keys per version, optional `workflow_definition` / `inputs` / `verdict`) | 1.1.0 schema | every node writing result files (CISA check nodes write 1.0.0 via the default; unchanged), CWE header reader via the wheel | medium — `RESULT_FILE_HEADER_KEYS` becomes per-version; 1.0.0 default and bytes unchanged |
| `python/canvastekk_workflow_sdk/check_verdict.py` (new: enums, `CheckSpec`, mark validation, `Rule`, `Reading`, `rules_from_inputs`, `judge`, `rollup`, body builder) | `result_file.py`, body schema | `CheckNodeBase`, manifest validator, CISA `libs/check_contract` (VS5) | low (new module) |
| `python/canvastekk_workflow_sdk/workflow_node_manifest.py` (optional `checks` field; `x-verdict` mark validation) | `check_verdict.py` | every Python node manifest (validator fires only when a mark or `checks` exists — none today), `check_schema_stability.py` (additive), registration payload | medium |
| `python/canvastekk_workflow_sdk/workflow_node_registry.py` + `__main__.py` (`checks` in the registration payload / allow-list) | manifest field | CWE `RegisterWorkflowNodeRequest` (accepts `checks` after VS2; payload carries it only when declared) | medium |
| `python/canvastekk_workflow_sdk/check_node_base.py` (new: `CheckNodeBase`) | `check_verdict.py`, `WorkflowNodeBase` | CISA check nodes (VS5) | low (new) |
| `python/canvastekk_workflow_sdk/workflow_node_base.py` (`__init_subclass__`: marked inputs ⇒ check node) | `check_node_base.py` flag | every Python node class (rule fires only on marked inputs — none today) | medium |
| `python/canvastekk_workflow_sdk/workflow_node_conformance.py` (`check_node_conformance_errors`) | flag | CI / node repos | low |
| `python/canvastekk_workflow_sdk/__init__.py` exports | the above | public surface (`test_consumer_import_freeze.py`) | low |
| `typescript/src/result-file.ts` (layout 1.1.0) + `typescript/src/check-verdict.ts` (enums, body schema const) + `typescript/src/workflow-node-manifest.ts` (`checks` field) + `index.ts` | canonical schemas | TS node authors, FE fixtures | medium |
| `schemas/result-file/golden/` (1.1.0 input/expected) | writers | both suites | low |
| `docs/RESULT-FILE.md`, `docs/CHECK-VERDICT.md` (new), `schemas/*/README.md` | — | node authors | low |

Consumers inspected (2026-11-23): CISA `origin/dev` `09a3932` imports only `write_result_file`, `result_file_output_schema` (`_shared/verdict_output.py:46-49`) — default layout stays 1.0.0, so no behaviour change; CWE `origin/dev` pins SDK 1.1.0 and reads headers with `read_result_file_header` (accepts 1.0.0 today; 1.1.0 only after it pins 1.2.0 — VS4).

## Implementation Phases

### Canonical step format
- [ ] **N.M** <single atomic action — verb + target + outcome>
    — **Why:** <what this unblocks / why it must precede others>
    — **Done when:** <objective, checkable completion signal>
    — **Consumers affected:** <who depends on this; none if N/A>

### Phase 1: Schemas
- [x] **1.1** Add `schemas/result-file/1.1.0.json` (header adds optional `workflow_definition {id, slug, version}`, `inputs` object, `verdict` enum; key order documented) and its packaged copy.
    — **Why:** every later phase validates against it; released schemas are never edited in place.
    — **Done when:** a test asserts the packaged copy equals the canonical file and it is a valid draft-07 schema.
    — **Consumers affected:** CWE VS4, FE VS8a.
- [x] **1.2** Add `schemas/result-body/model_check.check/1.0.0.json` (`checks[]`, `measurements[]` with `subject_id`, `failed_limits`) and its packaged copy, with a README.
    — **Why:** D92 body contract the verdict step validates before writing.
    — **Done when:** copy-equality and draft-07 validity tests pass.
    — **Consumers affected:** CISA VS5, FE VS8a, CISA#614.

### Phase 2: Layout 1.1.0 in Python
- [x] **2.1** Make header keys per layout version in `result_file.py` (`RESULT_FILE_HEADER_KEYS_BY_VERSION`), accept 1.1.0 in `SUPPORTED_RESULT_FILE_VERSIONS`, keep `RESULT_FILE_VERSION = "1.0.0"` as the writer default.
    — **Why:** the reader must check order per version; existing writers must keep producing 1.0.0 bytes.
    — **Done when:** existing `test_result_file.py` passes unchanged (golden 1.0.0 bytes identical) and a 1.1.0 header round-trips through `read_result_file_header`.
    — **Consumers affected:** CWE (header reader), CISA (writer default unchanged).
- [x] **2.2** Extend `build_result_file_header` / `write_result_file` with `result_file_version`, `workflow_definition`, `inputs` (≤16 KB), `verdict`; stamp `workflow_definition` from `context.run_context` when writing 1.1.0.
    — **Why:** D92 header; run context (SDK#281) supplies the definition identity.
    — **Done when:** tests show 1.1.0 keys written in order, the 16 KB `inputs` limit rejects without writing a file, and `workflow_definition` is omitted when no run context exists.
    — **Consumers affected:** CheckNodeBase (phase 4).

### Phase 3: The verdict functions (`check_verdict.py`)
- [x] **3.1** Add enums `TekkCheckRoleEnum`, `TekkCheckOperatorEnum`, `TekkWorkflowRunVerdictEnum`, `rollup()` (FAIL > NOT_EVALUABLE > WARNING > PASS; empty → NOT_EVALUABLE) and `CheckSpec` / `CheckResolution`.
    — **Why:** shared vocabulary (D85, D86, D90) for every later step.
    — **Done when:** roll-up tests cover each precedence pair and the empty case.
    — **Consumers affected:** manifest, judge, CISA.
- [x] **3.2** Add `verdict_mark_errors(input_schema, checks)` (D85/D88 node-side rules: mark shape, known check key, `check` string or list, operator fits the input type, TOLERANCE numeric with `applies_to` naming numeric LIMITs of the same check, every non-FILTER check has a LIMIT, statement placeholders from the fixed list).
    — **Why:** a bad mark must fail at node definition time, not at run time.
    — **Done when:** one failing test per rule plus a passing beam-length example (plan 5.6.2).
    — **Consumers affected:** manifest validator (phase 5).
- [x] **3.3** Add `Rule` and `rules_from_inputs(input_schema, inputs)` (input value, else schema default; null WARNING_LIMIT dropped; TOLERANCE folded into its limits; FILTER kept as filters).
    — **Why:** D97 step 2a — the verdict reads only the marked inputs' run values.
    — **Done when:** tests show override beats default, null warning dropped, tolerance attached only to `applies_to` limits.
    — **Consumers affected:** judge, CheckNodeBase.
- [x] **3.4** Add `Reading` with constructors `value`, `predicate`, `fail_by_name`, `not_evaluable`, `observation`, `scope` (`subject_id` required on judged kinds).
    — **Why:** D97 reading kinds mirror the CISA row classes.
    — **Done when:** constructor tests reject a judged reading without `subject_id`.
    — **Consumers affected:** CISA `measure()`.
- [x] **3.5** Add `judge(rules, readings, checks, policy=None)`: resolution rounding, operators with tolerance and the 1e-10 inclusive allowance, failure sides, bound settling (`<CHECK>_NOT_SETTLED`), alternatives (`straddle_code`), predicates, per-subject counts, per-check `limits_used` / `filters_used`, run verdict and summary.
    — **Why:** the one calculation every check node uses (D91, D92a, D97).
    — **Done when:** the operator/tolerance/bound/alternative/counting matrix passes and the plan 5.6.7 beam example reproduces its verdicts and counts.
    — **Consumers affected:** CheckNodeBase, CISA.
- [x] **3.6** Add `VerdictPolicy` and `build_check_body(judged)` (validated against the 1.0.0 body schema) plus `judged.inline_outputs()`.
    — **Why:** D99 policy hook; D91b inline outputs; D92 body.
    — **Done when:** a policy rejecting a reason code raises; the built body validates; inline outputs carry `verdict`, `verdict_counts`, `requirement_verdicts`.
    — **Consumers affected:** CheckNodeBase, CISA policy.

### Phase 4: CheckNodeBase
- [x] **4.1** Add `check_node_base.py` with `CheckNodeBase` (abstract `measure()`, fixed `execute()` measure → verdict → write with `report_progress`, `result_body_format` `"1.0.0"` or `"legacy"` with the `write_legacy_result` hook) that refuses an `execute` override.
    — **Why:** D91 — the verdict step cannot be skipped or replaced; D91a — calculation and format can switch separately.
    — **Done when:** a test node writes a 1.1.0 file that validates, returns inline outputs, reports three progress steps; a subclass overriding `execute` raises `TypeError`; the legacy path calls the hook.
    — **Consumers affected:** CISA VS5.
- [x] **4.2** Enforce "marked inputs ⇒ CheckNodeBase" in `WorkflowNodeBase.__init_subclass__` and expose `check_node_conformance_errors(node_cls)`.
    — **Why:** the SBCS lesson — code must read the mark, so a marked node outside the standard is an error.
    — **Done when:** a plain `WorkflowNodeBase` subclass with a marked input raises at class creation; the helper reports the same.
    — **Consumers affected:** every node class (fires only with marks).

### Phase 5: Manifest and registration
- [x] **5.1** Add the optional `checks` field to `WorkflowNodeManifest` (omitted when None) and run `verdict_mark_errors` in a model validator.
    — **Why:** D86 manifest map; byte-identical serialization for existing nodes.
    — **Done when:** an existing manifest's `to_dict()` is unchanged; a marked manifest without the check key fails construction; schema stability diff reports no breaking change.
    — **Consumers affected:** all manifests, `check_schema_stability.py`.
- [x] **5.2** Send `checks` in the registration payload when declared and add it to the CLI allow-list.
    — **Why:** CWE stores it in `node_registry.checks` (VS2).
    — **Done when:** payload tests show `checks` present only when declared.
    — **Consumers affected:** CWE register endpoint (VS2).
- [x] **5.3** Export the new public names from `__init__.py` and update the import-freeze expectations.
    — **Why:** CISA imports from the package root.
    — **Done when:** `test_consumer_import_freeze.py` passes with the additions.
    — **Consumers affected:** CISA.

### Phase 6: TypeScript mirror
- [x] **6.1** Layout 1.1.0 in `result-file.ts` (embedded schema const, per-version header keys, writer options) and a shared golden (`schemas/result-file/golden/1.1.0-*`) that both runtimes reproduce byte for byte.
    — **Why:** AC golden parity; TS nodes and tools read the same files.
    — **Done when:** Python and TS golden tests pass on the 1.1.0 golden; the embedded schema equals the canonical file.
    — **Consumers affected:** TS node authors, FE fixtures.
- [x] **6.2** Add `check-verdict.ts` (enums, `VERDICT_MARK`, body schema const) and the optional `checks` field on the TS manifest schema; export from `index.ts`.
    — **Why:** TS manifests and readers share the vocabulary; a TS manifest with `checks` must not be rejected.
    — **Done when:** TS tests: body schema const equals the canonical file; a manifest with `checks` parses; `tsc`, lint, vitest and build pass.
    — **Consumers affected:** TS node authors.

### Phase 7: Docs
- [x] **7.1** Add `docs/CHECK-VERDICT.md` (marks, roles, operators, reading kinds, CheckNodeBase example) and update `docs/RESULT-FILE.md` and the schema READMEs for 1.1.0.
    — **Why:** node authors (CISA VS5, CISA#605 template) need the contract in the SDK.
    — **Done when:** docs reference every exported name and link from `docs/RESULT-FILE.md`.
    — **Consumers affected:** node authors.

## Technical Notes
- Writer default stays layout 1.0.0; only callers that pass `result_file_version="1.1.0"` (CheckNodeBase) write 1.1.0.
- Header key order 1.1.0: `result_file_version, result_schema, result_schema_version, workflow_run_id, workflow_definition, inputs, generated_at, verdict, summary` then `body`.
- `summary` for check nodes: `verdict, pass_count, warning_count, fail_count, not_evaluable_count` (counts are subjects, D92a).
- Python-only for `judge` / `CheckNodeBase`: all check nodes are Python (CISA). TS port is a follow-up with no consumer yet.

## Dependencies
None (VS1 is first). Release 1.2.0 follows the merge through the release workflow.

## Risks & Mitigation
- **CWE rejects `checks` before VS2** → payload carries `checks` only when declared; no node declares it until VS5, which is blocked by VS2 on every lane.
- **Header reader changes break CWE** → 1.0.0 order and bytes unchanged, golden enforced.
- **Over-reach into CISA policy** → policy is a hook; the NOT_EVALUABLE code families live in CISA (VS5 C0).

## Trace

- Plan review (Step 7, inline): requirements gate skipped (ACs concrete in the ticket); architecture review = the epic review (frontend-nextjs PLAN-model-checker-v2.md 5.9) plus a consumer check: CWE reads headers only via `read_result_file_header` (`activities.py:446`), CISA only writes via `write_result_file` (`_shared/verdict_output.py:46`).
- Schema stability vs origin/dev: one ADDITIVE change (`WorkflowNodeManifest.checks`), no breaking change.
- Gate finding fixed: ADR 0001 naming law (`test_rename_map.py`) — two TS root exports removed (`283a29f`).
- GATE 283a29f tier=full: python ruff 0; pytest 1294 passed; typescript tsc 0, eslint 0, vitest 566 passed (32 files), build 0, pack-test 0. Shared golden 1.1.0 reproduced byte for byte by both writers.
- Code review (Step 9, inline, checklist `code-review-subagent.md`): 0 Critical, 0 Major, 2 Minor (straddle code format; bound + warning doc) fixed in 359e290; 1 Note kept (four rounding modes, cheap). Direct callers inspected: CWE `read_result_file_header` (activities.py:446), CLI/registry payload builders, every node class via `WorkflowNodeBase.__init_subclass__` (fires only with marks).
- GATE 359e290 tier=full: python ruff 0; pytest 1295 passed; typescript tsc 0, eslint 0, vitest 566 passed, build 0, pack-test 0.

