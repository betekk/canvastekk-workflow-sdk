# Temp-Lane Node Contract — Decision Record (ticket #140)

**Decision: NO-CHANGE.** The SDK already covers the image-in/image-out temp-node
shape. No release cut, no consumer pin updates. This record was requested by
[betekk/canvastekk-workflow-sdk#140](https://github.com/betekk/canvastekk-workflow-sdk/issues/140)
(epic [betekk/canvastekk-tracker#3776](https://github.com/betekk/canvastekk-tracker#3776)).

## Evidence

| Requirement | v0.40.0 evidence |
|-------------|------------------|
| Image-in (file input + validation) | `definition.py:434-485` at tag: `file_input_fields` (`format: "file"`), `x-accept`, `x-maxSizeBytes` |
| Image-in (transport) | `app.py:344` at tag: engine sends presigned GET URLs for file input fields; SDK downloads |
| Image-out (file output + upload) | `app.py:437-444` at tag: pass outputs upload to engine-sent `output_upload_url` multipart sessions (DA-3340 model, SDK ≥ 0.36.0) |
| Plumbing stability | `multipart.py`, `uploads.py`, `request.py`, `response.py` byte-identical v0.40.0 → HEAD (absent from `git diff --stat v0.40.0..HEAD`) |
| Prescribable output prefix | **Not an SDK surface — by design.** The engine's presigned multipart session carries the S3 key; nodes hold no S3 credentials. A node-side storage helper for `temp-outputs/{run_id}/` would require S3 creds in nodes and contradict DA-3340. Placement is minted engine-side (scope of betekk/canvastekk-workflow-engine#747) |

**Pin correction:** the ticket premise says consumers pin v0.40.0. The live
consumer pin is **v0.52.0** — ml-service's deploy installs the v0.52.0 wheel
(`canvastekk-ml-service/.github/scripts/deploy/register.sh:32`). Both versions
cover every requirement above; v0.52.0 adds only additive surface (conformance
probe, dry-run, OpenAPI 3.2 emission, contract stamping). No pin update is
required.

## Manifest sketch for `remove-humans` (A3 builds against this)

[betekk/canvastekk-ml-service#57](https://github.com/betekk/canvastekk-ml-service/issues/57)
implements this node beside `human_filter`. Input parameters mirror
`human_filter` exactly (same extensions, same `MAX_INLINE_BYTES` = 10 MiB from
`contracts/payload_policy.py:13`):

```json
{
  "slug": "remove-humans",
  "version": "1.0.0",
  "input_schema": {
    "type": "object",
    "required": ["image"],
    "properties": {
      "image": {
        "type": "string", "format": "file",
        "x-accept": [".jpg", ".jpeg", ".png", ".webp"],
        "x-maxSizeBytes": 10485760,
        "description": "Source image (10 MiB cap — mirrors human_filter MAX_INLINE_BYTES)"
      }
    }
  },
  "output_schema": {
    "type": "object",
    "required": ["result"],
    "properties": {
      "result": { "type": "string", "format": "file", "description": "Human-removed image (PNG)" }
    }
  }
}
```

## Storage convention (normative for A3/A5)

- The engine mints the output upload session with key `temp-outputs/{run_id}/<field>`;
  the node uploads via the SDK exactly as any node does — **never** writes S3 directly.
- The engine exempts `temp-outputs/{run_id}/` from `cleanup_run_files()`
  (betekk/canvastekk-workflow-engine#747).
- The devops lifecycle rule (betekk/canvastekk-devops#613) expires the
  `temp-outputs/` prefix after 7 days.
- The artifact is **never** added to `node_results` protected roots — protected
  roots never age-expire, which would break the 7-day temp semantics.
- Serving is a presigned GET from the run result (engine-side, #747).
