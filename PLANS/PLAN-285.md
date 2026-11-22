# PLAN: CheckNodeBase body extra evidence and cross-referenced checks (SDK 1.3.0)

**Branch**: feat/285
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/285
**Base**: dev
**Epic**: betekk/canvastekk-tracker#4332 (VS1b). Source plan: canvastekk-frontend-nextjs `PLANS/PLAN-model-checker-v2.md` (D90, D92). Reader contract: canvastekk-frontend-nextjs `src/lib/actions-v2/model-checker/check-result-body-v1.ts` (FE#3383, merged).

## Acceptance Criteria
- [ ] A `CheckNodeBase` returning `body_extra` writes it as `body.extra`; the body still validates.
- [ ] A cross-referenced check reports NOT_EVALUABLE with its reason, carries `cross_reference` in `checks[]`, and does not change the run verdict or run counts (test: one PASS check + one cross-referenced check → run PASS).
- [ ] Python tests cover both; schema-stability reports additive only.

## Deviations from the ticket text (compatibility with what already shipped)
- **`cross_reference` stays a string** (the owning check key, `measured_by`). The published body schema `model_check.check/1.0.0.json` already types `checks[].cross_reference` as `string`, and the merged FE reader parses `z.string().min(1)`. An object would break both. The reason code goes in the existing `checks[].not_evaluated_reason {code, message}`.
- **Declared by a reading, not by the manifest.** CWE validates each manifest `checks` entry with the strict SDK `CheckSpec` (`extra="forbid"`, CWE `schemas/api/nodes.py:106`), so a new manifest key would be refused by CWE until it re-pins the SDK. `Reading.cross_reference(check, measured_by=..., reason_code=..., reason=...)` needs no manifest or CWE change.
- **No schema file edit.** `body.extra` is already allowed (root `additionalProperties` unset); the README forbids editing a released schema in place. Docs gain the `extra` and cross-reference contract.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---|---|---|---|
| `python/canvastekk_workflow_sdk/check_verdict.py` (`Reading.cross_reference`; `judge()` excludes cross-referenced checks from run roll-up and subject counts; `JudgedCheck.cross_reference`; `JudgedResult.body(extra=...)`) | — | `CheckNodeBase`, CISA check nodes (VS5), FE reader (VS8a, already reads both) | medium — `judge()` roll-up; unchanged when no cross-reference reading exists |
| `python/canvastekk_workflow_sdk/check_node_base.py` (`body_extra()` hook) | `JudgedResult.body(extra=)` | CISA check nodes (VS5) | low — default `None` keeps today's bytes |
| `docs/CHECK-VERDICT.md`, `schemas/result-body/README.md` | — | node authors | low |

Consumers inspected: `judge()` is called only by `CheckNodeBase.judge_readings` in the SDK; CWE imports `CheckSpec`, `marked_inputs`, `verdict_mark_errors` (all untouched); FE reader excludes `cross_reference` checks from the run verdict and reads `body.extra` as the 0.x `result`.

## Implementation Phases

### Phase 1: Cross-referenced checks
- [ ] **1.1** Add `Reading.cross_reference` and make `judge()` give such a check NOT_EVALUABLE with its reason and `cross_reference`, leaving it out of the run verdict and run counts.
    — **Why:** CISA check 08-style nodes must report PASS where they do today (D90).
    — **Done when:** one PASS check + one cross-referenced check → run PASS, counts from the PASS check only; the body validates.
    — **Consumers affected:** CISA nodes (VS5).

### Phase 2: Body extra
- [ ] **2.1** Add `CheckNodeBase.body_extra(judged, inputs, context)`; a dict is written as `body.extra`.
    — **Why:** screens draw the check's evidence from `extra` (FE#3383 contract).
    — **Done when:** a node returning `body_extra` writes `body.extra` and the body validates; returning `None` writes no `extra`; a non-dict is refused.
    — **Consumers affected:** CISA nodes (VS5).
- [ ] **2.2** Document both in `docs/CHECK-VERDICT.md` and `schemas/result-body/README.md`.

## Trace
