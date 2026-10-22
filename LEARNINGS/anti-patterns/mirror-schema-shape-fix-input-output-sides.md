# Anti-Pattern: Mirroring a Schema-Shape Fix on Only One Side of Input/Output Discovery

**Date:** 2026-10-22 · **Repo:** canvastekk-workflow-sdk · **Ticket:** canvastekk-tracker#3971 follow-up (live-run round 4)

## What happened

S.1 (SDK#161) taught `file_input_fields` that a file field is a string with
`format: "file"` **or an array whose items are**. The output-side twin
(`file_output_fields` / `getFileOutputFields`) kept matching top-level
`format: "file"` only. #3969 then shipped the array-output upload walker —
which consumes the discovery property — so the walker was correct but
unreachable for array fields.

Live evidence (v2 model-checker family, dev): url-loader array mode returned
`buffers` and **passed in 2.7s with zero uploads** (run's S3 prefix empty).
The engine stamped `s3://` pointers per contract; the downstream consolidate
node's presigned GETs returned `HTTP 404 downloading file for field
'ifc_paths'`. Three surface symptoms (silent skip, stamping, downstream 404),
one cause an arm's length from an earlier fix.

## Rule

When a schema-shape rule changes for inputs, change it for outputs in the
same breath (and vice versa): enumerate both discovery sites
(`file_input_fields`, `file_output_fields`, TS mirrors) and diff their
predicates. Any later asymmetry is a latent bug that only fires when a node
uses the shape the narrow side can't see.

Shared-helper, not copy-paste: py `_is_file_schema` / ts `isFileField` now
serve both sides, so the next shape rule (e.g. nested object file fields)
lands once.

## Detection

- Grep for paired discovery predicates drifting: `format == "file"` on one
  side, `format + array-items` on the other.
- Engine-side tripwire: a node **passes** with file-output upload targets
  minted but the run's S3 prefix stays empty.
