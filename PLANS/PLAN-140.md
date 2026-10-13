# PLAN: sdk: confirm node contract for image-in/image-out temp node

**Branch**: feat/140
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/140
**Base**: main

## Acceptance Criteria
- [x] Decision recorded on ticket #140: no-change (with evidence) OR release cut (with version + what changed)
- [x] Manifest sketch for `remove-humans` (inputs, outputs, storage convention) attached as a comment for A3 (betekk/canvastekk-ml-service#57) to implement against
- [x] Temp-output storage convention agreed: the node writes its final artifact to `temp-outputs/{run_id}/…` and temp artifacts are NOT registered as `node_results` protected roots

## Investigation Findings (evidence for the decision)

- **v0.40.0 already covers image-in/image-out**: `definition.py` at v0.40.0 has `file_input_fields` / `file_output_fields` (`format: "file"` discrimination) plus `x-accept` / `x-maxSizeBytes` validation (`definition.py:434-485` at tag).
- **File plumbing at v0.40.0**: engine sends presigned GET URLs for file inputs and the SDK downloads them (`app.py:344`); pass outputs upload to engine-sent `output_upload_url` multipart sessions (`app.py:437-444`). `multipart.py`, `uploads.py`, `request.py`, `response.py` are byte-identical v0.40.0 → HEAD (absent from `git diff --stat v0.40.0..HEAD`).
- **Prescribable output prefix is not an SDK surface — by design**: the engine's presigned multipart session carries the S3 key; nodes hold no S3 credentials (DA-3340 model, SDK ≥ 0.36.0). A node-side storage helper for `temp-outputs/{run_id}/` would require S3 creds in the node and contradicts that model. The temp-lane placement is minted engine-side (scope of betekk/canvastekk-workflow-engine#747).
- **Live pin correction**: ml-service's deploy installs the **v0.52.0** wheel (`.github/scripts/deploy/register.sh:32`), superseding the ticket's v0.40.0 premise; v0.52.0 covers everything above plus additive surface (conformance, dry-run, OpenAPI 3.2 emission).

**Decision: NO-CHANGE.** No release cut; no consumer pin updates required.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `docs/temp-lane-node-contract.md` (new) | — | A3 (ml-service#57) implementers; A5 (cwe#747) reviewers | low |
| Ticket comments on #140 | `docs/temp-lane-node-contract.md` (evidence lives there) | A3 implementer (manifest sketch is the build contract) | low |

## Implementation Phases

### Phase 1: Decision record in-repo
- [x] **1.1** Write `docs/temp-lane-node-contract.md` recording the no-change decision with the v0.40.0/v0.52.0 evidence above, the manifest sketch, and the temp-output storage convention
    — **Why:** the durable in-repo record the epic (betekk/canvastekk-tracker#3776) and consumers reference; also the PR vehicle that closes #140 on merge
    — **Done when:** file exists in `docs/`, states NO-CHANGE with file:line evidence, and contains the manifest sketch + storage convention
    — **Consumers affected:** A3 (ml-service#57) implementers; A5 (cwe#747) reviewers
    — **Done:** decision doc written — NO-CHANGE with v0.40.0 tag-line evidence, pin correction to v0.52.0 (register.sh:32), manifest sketch (human_filter-mirrored 10 MiB per user answer), storage convention; files: docs/temp-lane-node-contract.md; fixes: none
- [x] **1.2** Run verification gate on the docs tree, commit and push the decision doc on `feat/140`
    — **Why:** the PR must exist for `Closes #140` to fire; uncommitted work is lost on worktree removal
    — **Done when:** `feat/140` pushed to origin with the decision doc; gate green
    — **Consumers affected:** none beyond this branch
    — **Done:** exit gate run on docs-only tree (see Trace memo); committed and pushed on feat/140; files: PLANS/PLAN-140.md; fixes: none

### Phase 2: Ticket comments (the ticket's own ACs)
- [x] **2.1** Post the decision comment on betekk/canvastekk-workflow-sdk#140: NO-CHANGE + evidence summary (file:line citations, v0.52.0 pin correction)
    — **Why:** AC1 demands the decision be recorded on the ticket itself, not only in-repo
    — **Done when:** comment posted; permalink captured in this PLAN's trace
    — **Consumers affected:** A3 implementer
    — **Done:** decision comment posted; permalink: https://github.com/betekk/canvastekk-workflow-sdk/issues/140#issuecomment-6140673226; files: none (gh comment); fixes: none
- [x] **2.2** Post the manifest-sketch comment on #140 for A3: inputs/outputs JSON Schema + storage convention (engine-minted `temp-outputs/{run_id}/` target; never a `node_results` protected root; 7-day lifecycle expiry)
    — **Why:** AC2 — A3 implements against this sketch; AC3 — the convention must be stated on the ticket thread
    — **Done when:** comment posted; permalink captured
    — **Consumers affected:** A3 (ml-service#57)
    — **Done:** manifest-sketch comment posted; permalink: https://github.com/betekk/canvastekk-workflow-sdk/issues/140#issuecomment-6140676415; files: none (gh comment); fixes: none

## Technical Notes
- Manifest sketch (for A3):

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

- Storage convention (normative for A3/A5): the engine mints the output upload session with key `temp-outputs/{run_id}/<field>`; the node uploads via the SDK exactly as any node does; the engine exempts `temp-outputs/{run_id}/` from `cleanup_run_files()`; the devops lifecycle rule (betekk/canvastekk-devops#613) expires the prefix after 7 days; the artifact is never added to `node_results` protected roots; serving is a presigned GET from the run result.

## Dependencies
- None (first ticket of the temp-lane epic's A-lane; epic: betekk/canvastekk-tracker#3776)

## Risks & Mitigation
- Risk: A3 misreads the decision as "node writes to S3 directly". Mitigation: manifest sketch + storage convention state the engine-minted-target model explicitly, with DA-3340 cited.
- Risk: stale v0.40.0 premise misleads pin updates. Mitigation: decision records the actual live pin (v0.52.0) with the register.sh citation.

## Trace
- Phase 1 gate: docs-only diff vs origin/main (docs/temp-lane-node-contract.md + PLANS/PLAN-140.md) — no lint/typecheck/unit targets touched; scoped-lint rule → n.a. across the board; CI (ci-python.yml) carries the code signal on the PR.
- GATE 79ed285 tier=full lint=n.a typecheck=n.a build=n.a unit=n.a e2e=n.a  (docs-only diff; ruff/pytest targets untouched — zero code delta vs origin/main; CI carries the signal; fixes: none)
