# Wire-Parse Tolerance Plus Loud Seam on Legacy-Target Removal

**Category**: decisions
**Confidence**: 0.85
**Scope**: project
**Date**: 2026-09-30
**Source**: DA-3340 (removing `str` from `UploadTarget`)

## Decision

When removing a member from a wire-level union (here `UploadTarget = str | UploadSession` → session-only), keep the request-parse boundary tolerant and fail at the domain seam instead:

- `request.py` `output_upload_url` became the inline `dict[str, str | UploadSession] | None` (NOT the narrowed public alias) so legacy payloads still parse.
- `uploads.py` `upload_file` raises `NodeIOError("engine sent deprecated presigned target — upgrade the engine")` for strings; `app.py`'s existing catch converts it to `fail`/`UPLOAD_FAILED`.

## Why

Narrowing the parse field to the session-only alias would 422 legacy payloads at the boundary — the ticket's required `NodeIOError` would be unreachable, and authors would debug an opaque validation error instead of the upgrade-the-engine message. TS parity: `request.ts` keeps `z.string()` in the parse union; `app.ts` casts to `Record<string, UploadTarget>` at the call site (commented) because the runtime guard lives in `uploadFile`.

## Rule

Parse boundaries admit superseded wire shapes; the seam that knows the domain raises the domain error. Never let validation errors replace the fail-loud contract a breaking removal promises.

See also: `parity-port-must-widen-wire-schema` (anti-patterns) — the widening direction of the same principle (DA-3314).
