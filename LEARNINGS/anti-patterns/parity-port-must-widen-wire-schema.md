# Parity Ports Must Widen the Inbound Wire Schema, Not Just the Handler

**Category:** anti-patterns · **Scope:** canvastekk-workflow-sdk (any dual-language SDK) · **Date:** 2026-09-29

## The anti-pattern

Porting a protocol widening (python `UploadTarget` → TS `UploadTarget`) by widening only the handler interface leaves the feature dead on arrival: the descriptor value is rejected at the inbound zod parse (`NodeExecutionRequestSchema.output_upload_url`, request.ts:20) → 400 at the express safeParse (`app.ts:126`) before the widened uploader ever runs. External consumers parse through the same exported schema (`canvastekk-ifc-service-app/apps/node/src/job-runner.ts:106`), so they inherit both the bug and the fix.

## Rule

When porting a widening across languages: trace the **wire entry seam first** (the parse schema), the handler second. Add the parse-schema row to the PLAN's Dependency & Consumer Map and a parse regression test. Found by architecture review of PLAN-DA-3314 (finding C1) before implementation — the map had listed `context.ts` (grep: zero upload references) and omitted `request.ts`.
