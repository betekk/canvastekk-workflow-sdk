# Check verdicts: `x-verdict`, `CheckNodeBase` and `judge`

Since SDK 1.2.0 (#283, epic betekk/canvastekk-tracker#4332) every check node
decides PASS / WARNING / FAIL / NOT_EVALUABLE with one SDK calculation. The
node measures; the SDK judges, counts, rolls up and writes the result file.
Decisions behind it: canvastekk-frontend-nextjs
`PLANS/PLAN-model-checker-v2.md`, D85–D100.

## Who owns what

| Part | Owner |
|---|---|
| How a value is measured (`measure()`) | The check node |
| Which inputs are verdict variables, their role and operator (`x-verdict`), the `checks` map | The check node's manifest |
| Comparing, tolerance, rounding, bounds, alternative readings, counting, roll-up, the result file | The SDK (`judge`, `CheckNodeBase`) |
| The guideline's numbers (input defaults, `minimum` / `maximum`) and clause references | The workflow definition |

## Marking inputs

```python
"threshold_mm": {"type": "number", "default": 1000,
                 "x-verdict": {"check": "corridor_width", "role": "LIMIT", "operator": "GTE"}},
"exact_tolerance_mm": {"type": "number", "default": 0, "minimum": 0,
                       "x-verdict": {"check": "corridor_width", "role": "TOLERANCE"}},
"toilet_room_scoping": {"type": "boolean", "default": True,
                        "x-verdict": {"check": "corridor_width", "role": "FILTER"}},
```

| Mark key | Meaning |
|---|---|
| `check` | A key of the manifest `checks` map, or a list when one input governs several checks |
| `role` | `LIMIT` (broken → FAIL), `WARNING_LIMIT` (broken → WARNING; `null` = off), `TOLERANCE` (widens limits), `FILTER` (decides what is checked) |
| `operator` | Limits only: `GT`, `GTE`, `LT`, `LTE`, `EQ`, `NE`, `IN`, `NOT_IN` |
| `ignore_case` | Text limits only |
| `applies_to` | Tolerance only: the limit inputs it widens (default: every numeric `LIMIT` of the check) |

The input's type decides the operators: numbers take the six comparisons plus
tolerance; text and booleans take `EQ` / `NE`; a list of text takes `IN` /
`NOT_IN`. A range is two limits (`GTE` + `LT`). A rule nobody may change is a
marked input with `const` (e.g. a fixed yes/no predicate). The manifest
rejects a mark that breaks these rules (`verdict_mark_errors`).

| Operator | Passes when | With tolerance `t` |
|---|---|---|
| `GT` / `GTE` | actual > / ≥ limit | actual > / ≥ limit − t |
| `LT` / `LTE` | actual < / ≤ limit | actual < / ≤ limit + t |
| `EQ` / `NE` | actual = / ≠ limit | \|actual − limit\| ≤ / > t |
| `IN` / `NOT_IN` | actual is / is not in the list | — |

Inclusive bounds also allow 1e-10 of float noise. That is not a tolerance.

## The `checks` map

```python
checks={"corridor_width": {"label": "Corridor width", "unit": "mm",
                           "resolution": {"step": 1, "rounding": "HALF_UP"},
                           "statements": {"FAIL": "{element}: {label} is {actual} {unit}; {broken}."}}}
```

Keys are snake_case and never hold a value (`corridor_width`, not
`corridor_width_1000mm`): the value used is recorded in `limits_used`.
`resolution` rounds the measured value before comparing (whole millimetres,
half up, is `{"step": 1}`). Statement placeholders: `{element}`, `{label}`,
`{actual}`, `{unit}`, `{limits}`, `{broken}`, `{reason}`. Files never store
sentences; readers render them.

## Writing a check node

```python
from canvastekk_workflow_sdk import CheckNodeBase, Reading

class CorridorWidthNode(CheckNodeBase):
    manifest = MANIFEST  # with the marks and the checks map above

    def measure(self, inputs, context):
        rows = []
        for corridor in find_corridors(inputs):
            if corridor.width_mm is None:
                rows.append(Reading.fail_by_name("corridor_width", subject_id=corridor.gid,
                                                 reason_code="CORRIDOR_UNRESOLVED"))
            else:
                rows.append(Reading.value("corridor_width", subject_id=corridor.gid,
                                          actual=corridor.width_mm, element_name=corridor.name))
        return rows
```

`CheckNodeBase.execute()` is fixed and cannot be overridden. It runs
**measure → verdict → write**, reports progress ("Measuring", "Judging",
"Writing result"), writes layout 1.1.0 with the `model_check.check` 1.0.0
body, and returns `result_file` plus the inline outputs `verdict`,
`verdict_counts` and `requirement_verdicts`. A node whose manifest marks an
input but is not a `CheckNodeBase` fails at class creation
(`check_node_conformance_errors` reports the same).

`result_body_format = "legacy"` keeps the SDK verdict but hands writing to
`write_legacy_result(judged, inputs, context)`, so a node can switch its
calculation first and its file format later.

## Readings

| Constructor | Judged how |
|---|---|
| `Reading.value(check, subject_id=, actual=)` | Rounded, then compared with every limit; `bound="LOWER"/"UPPER"` for a reading that bounds the true value; `alternatives={name: value}` + `straddle_code` for readings that must agree |
| `Reading.predicate(check, subject_id=, actual=)` | A yes/no or text finding compared with the check's limit |
| `Reading.fail_by_name(check, subject_id=, reason_code=)` | FAIL with a named reason and no value |
| `Reading.not_evaluable(check, subject_id=, reason_code=)` | NOT_EVALUABLE (absent, or identity in doubt) |
| `Reading.cross_reference(check, measured_by=, reason_code=)` | The whole check is measured by another check (D90): NOT_EVALUABLE with the reason, `cross_reference` on its `checks[]` entry, and left out of the run verdict and run counts. A check takes one such reading and no judged readings |
| `Reading.observation(...)`, `Reading.scope(...)` | Shown, never judged or counted |

Rules: a broken `LIMIT` → FAIL; else a broken `WARNING_LIMIT` → WARNING; else
PASS. A bound that settles every limit decides the row (with a
`verdict_caveat`); one that does not → FAIL `<CHECK>_NOT_SETTLED`. A warning
limit the bound cannot settle is not raised (only a settled break warns).
Alternatives that disagree → FAIL with their `straddle_code`. `EQ` failures
name their side (`BELOW` / `ABOVE`). An app can restrict readings with a
`VerdictPolicy` (`verdict_policy()` on the node).

## Counting and roll-up

Counts are per **subject** (`subject_id`), never per row: a subject's verdict
is the roll-up of its rows. Roll-up everywhere is
**FAIL > NOT_EVALUABLE > WARNING > PASS**; a check with no subjects is
NOT_EVALUABLE (`NO_SUBJECTS_IN_SCOPE`). A cross-referenced check counts
nowhere: the run verdict and counts come from the other checks. The header `summary` is
`verdict`, `pass_count`, `warning_count`, `fail_count`, `not_evaluable_count`.

## The body (`model_check.check` 1.0.0)

Schema: [`schemas/result-body/model_check.check/1.0.0.json`](../schemas/result-body/model_check.check/1.0.0.json).
`checks[]`: `check`, `verdict`, `verdict_counts`, `limits_used[{input, role,
operator, value, tolerance}]`, `filters_used[{input, value}]`, optional
`not_evaluated_reason{code, message}` and `cross_reference` (the owning check).
`measurements[]`: `check`, `subject_id`, `kind`, `verdict`, `failed_limits[{input,
side}]`, `actual` (rounded) and `actual_raw`, `element_name`, `file_id`,
`global_ids`, `reason`, `verdict_caveat`, `extra` (viewer fields).

Optional top-level `extra`: the check's viewer evidence, returned by
`CheckNodeBase.body_extra(judged, inputs, context)` (default `None`, no
`extra`). It never decides a verdict. The frontend reads it as the 0.x
`result`, so put `measurements` (the measurement sets) and `instances` inside
it, not beside it.

## TypeScript

`@betekk/canvastekk-workflow-sdk` exports the vocabulary (`VERDICT_MARK`, the
enums, `rollupVerdicts`, `CheckSpecSchema`, the body schema) and writes layout
1.1.0. `judge` and `CheckNodeBase` are Python-only for now.
