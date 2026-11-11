# PLAN: Confirm Workflow SDK 0.64 consumer compatibility

**Branch**: feat/244
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/244
**Base**: dev

## Acceptance Criteria
- [ ] SDK `v0.64.0` compatibility report exists.
- [ ] Manifest and execute contracts are recorded.
- [ ] Consumer pin inventory is current.
- [ ] CLS and OpenCode alignment is documented.
- [ ] Any required SDK change is filed separately (verdict: none required — recorded with rationale).
- [ ] No SDK release is made unless a gap is found (verdict: no gap — no release).

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `docs/COMPATIBILITY-v0.64.0.md` (new) | contract inspection (v0.64.0 tag sources) | none — new doc, no code imports | low |
| `PLANS/PLAN-244.md` | — | this pipeline (Step 8) | low |

Docs-only ticket: zero code-path nodes, so no cross-module consumers exist. Consumer Map is intentionally thin — architecture review triage (Step 7) relies on this being honest.

## Implementation Phases

### Phase 1: Record v0.64.0 contracts and consumer inventory
- [ ] **1.1** Author `docs/COMPATIBILITY-v0.64.0.md` recording (a) the Python + TypeScript node manifest shape (`WorkflowNodeManifest`: identity, schemas, token_cost, retry, metadata, `sdk_version` provenance stamp, `code_digest`, `mode`, `effective_contract` routes), (b) the execute contract (`POST /execute` JSON body; presigned-GET file inputs; multipart upload-session outputs, legacy presigned-PUT fails `NodeIOError` DA-3340), (c) the `/manifest` discovery endpoint shape, and (d) registration behavior (`POST` registry payload, `RegisterNodeResult{node,action,revision_id,previous_version,changes}`, `ctk_`-only credentials with offline validation #239/#3760)
    — **Why:** ACs 1–2 — the report is the ticket's deliverable; contracts must be recorded from the v0.64.0 tag sources, not dev HEAD assumptions
    — **Done when:** the file exists in the worktree and every recorded fact cites its source file:line in the v0.64.0 tree
    — **Consumers affected:** none (new doc)
- [ ] **1.2** Record the consumer pin inventory table verified against each consumer repo's remote `dev` branch (CLS gateway pyproject v0.64.0; CLS OpenCode lambda Dockerfile v0.61.0; CISA apps/python v0.64.0; CISA apps/node v0.61.0; workflow-engine fastapi_app v0.64.0; workflow-nodes apps/python v0.64.0) with the v0.61.0→v0.64.0 delta analysis (ctk_-only auth, `ctk` bin, registry-diff probe; manifest/execute contracts unchanged — verified via `git diff --stat v0.61.0 v0.64.0`)
    — **Why:** AC 3 — "current" means verified against remote dev, not local checkouts that may lag
    — **Done when:** each table row names the consumer manifest file path and the exact pinned URL as fetched from `repos/*/contents?ref=dev`
    — **Consumers affected:** none (report only)
- [ ] **1.3** Document the CLS/OpenCode alignment verdict: v0.64.0 is a drop-in for node code (no manifest/execution contract change); the ONLY upgrade prerequisite for the two v0.61.0 consumers (CLS OpenCode lambda, CISA apps/node) is registry credentials already rotated to `ctk_` keys; verdict **no SDK change required, no release**; consumer-side pin bumps listed as recommended follow-ups (parent betekk/canvastekk-tracker#4211)
    — **Why:** ACs 4–6 — the alignment decision + no-release verdict is the point of the ticket
    — **Done when:** the report states the verdict explicitly and the PR body carries it (PR target `dev`, `Closes betekk/canvastekk-workflow-sdk#244`)
    — **Consumers affected:** none (no code change)

### Phase 2: Verification gate + ship
- [ ] **2.1** Run the gate: docs-only diff → both CI lanes are paths-filtered out (`python/**`, `typescript/**`), so gate = tier light: verify the report renders as valid Markdown (headings/tables/fences), every source citation resolves in the v0.64.0 tree, and the working tree is clean of stray artifacts
    — **Why:** exit-gate discipline — even docs tickets need an objective completion check
    — **Done when:** gate memo line `GATE <sha> tier=light` appended to this PLAN's Trace
    — **Consumers affected:** none
- [ ] **2.2** Commit + push `feat/244`, land LEARNINGS capture (if any), create the PR targeting `dev`
    — **Why:** ship the verification
    — **Done when:** PR URL exists and background merge watcher is armed
    — **Consumers affected:** none

## Technical Notes
- v0.64.0 tag = merge `2d54486` of dev PR #241; dev HEAD `872c6c7` is its content parent — dev carries the same contracts (pyproject `version` fields on branches are cosmetic; releases stamp at build time from PR labels via git-cliff).
- The engine retired `X-Service-Token`/`X-API-Key` registry auth (#3760); v0.61.0 already dispatched `ctk_` via `Authorization: Bearer` (DA-1949) but still accepted legacy tokens — v0.64.0 rejects them locally.
- `sdk_version` in the manifest is provenance-only since #123/D16 — never an admission gate, so consumers on older wheels never fail registration against a newer engine on version grounds.

## Dependencies
- None (ticket states Dependencies: None).

## Risks & Mitigation
- **Pin drift between report authoring and merge** — mitigation: every pin cited with the `ref=dev` fetch; re-verify at PR creation if >24h elapse.
- **Report read as an upgrade mandate** — mitigation: verdict section states explicitly that no SDK release is made and consumer bumps are follow-ups, not part of this ticket.

## Trace
