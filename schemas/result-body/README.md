# Result body schemas

Published JSON Schemas (draft-07) for the `body` of result files whose shape
the SDK itself writes. The platform never validates `body`
([`docs/RESULT-FILE.md`](../../docs/RESULT-FILE.md)); these exist because the
SDK's verdict step (`CheckNodeBase`, [`docs/CHECK-VERDICT.md`](../../docs/CHECK-VERDICT.md))
produces the body and validates it before writing.

| File | Describes |
|---|---|
| `model_check.check/1.0.0.json` | Model-check body: `checks[]` (verdict, per-subject counts, limits and filters used) and `measurements[]` (one judged row per reading) |
| `model_check.check/2.0.0.json` | Each check owns its `measurements[]`; the finding can carry a verified IFC target and its drawings independently. |

Copies: the Python wheel ships them under
`python/canvastekk_workflow_sdk/data/schemas/result-body/`; the TypeScript
package embeds them in `typescript/src/check-verdict.ts`. Tests fail when a
copy drifts. Never edit a released schema in place; add a new version file.

`model_check.check` 1.0.0 also carries two optional parts the schema already
allows (SDK 1.3.0, #285): a top-level `extra` object holding the check's
viewer evidence (`CheckNodeBase.body_extra`), and `checks[].cross_reference`
naming the check that measures a cross-referenced one, which then counts
nowhere in the run verdict or counts.

Use layout `1.1.0` for body `2.0.0`. Identify a finding by `(workflow_run_id,
check, original measurement index)`: the index is flat in `1.0.0`, local to
the check in `2.0.0`. `CheckResultReader.iter_findings()` keeps the raw
measurement and recorded limits; the compact suggestion calls keep their
prior output shape. Keep writing `1.0.0` until the targeted producer and its
consumers are ready. If a producer later omits `limits_used`, reconstruct
the exact rules from the pinned definition and inputs or leave the rule
unverified; never fill it from current defaults.
