# PLAN: Confirm Workflow SDK 0.64 consumer compatibility

**Branch**: feat/244
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/244
**Base**: dev

## Acceptance Criteria
- [ ] SDK `v0.64.0` compatibility report exists.
- [ ] Manifest and execute contracts are recorded.
- [ ] Consumer pin inventory is current.
- [ ] CLS and OpenCode alignment is documented **and applied**: both lagging v0.61.0 pins bumped to v0.64.0 in-ticket (user decision, detection-gate round 1) — CLS `opencode_app/Dockerfile` + CISA `apps/node/package.json` (+lockfile), via sub-PRs in the consumer repos (`Part of` refs; only the report PR carries `Closes`).
- [ ] Any required SDK change is filed separately (verdict: none required — recorded with rationale).
- [ ] No SDK release is made unless a gap is found (verdict: no gap — no release).

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `docs/COMPATIBILITY-v0.64.0.md` (new) | contract inspection (v0.64.0 tag sources) | none — new doc, no code imports | low |
| `canvastekk-llm-service/opencode_app/Dockerfile` (pin line) | v0.64.0 release artifacts | LAMBDA image build; deploy-time node registration (ctk_ creds) | low — URL constant bump |
| `canvastekk-ifc-service-app/apps/node/package.json` + lockfile (pin) | v0.64.0 release artifacts | apps/node build, workflow-node TS registration | low — engine floor unchanged (>=24) |
| `PLANS/PLAN-244.md` | — | this pipeline (Step 8) | low |

Docs + pin-constant ticket: the only "consumers" are build pipelines (no code-interface consumers), so cross-module blast radius is nil — architecture-review triage stays zero-reviewer on an honestly thin code map.

## Implementation Phases

### Phase 1: Record v0.64.0 contracts and consumer inventory
- [x] **1.1** Author `docs/COMPATIBILITY-v0.64.0.md` recording (a) the Python + TypeScript node manifest shape (`WorkflowNodeManifest`: identity, schemas, token_cost, retry, metadata, `sdk_version` provenance stamp, `code_digest`, `mode`, `effective_contract` routes), (b) the execute contract (`POST /execute` JSON body; presigned-GET file inputs; multipart upload-session outputs, legacy presigned-PUT fails `NodeIOError` DA-3340), (c) the `/manifest` discovery endpoint shape, and (d) registration behavior (`POST` registry payload, `RegisterNodeResult{node,action,revision_id,previous_version,changes}`, `ctk_`-only credentials with offline validation #239/#3760)
    — **Why:** ACs 1–2 — the report is the ticket's deliverable; contracts must be recorded from the v0.64.0 tag sources, not dev HEAD assumptions
    — **Done when:** the file exists in the worktree and every recorded fact cites its source file:line in the v0.64.0 tree
    — **Consumers affected:** none (new doc)
    — **Done:** report authored at docs/COMPATIBILITY-v0.64.0.md — manifest/execute/discovery/registration contracts recorded with file:line citations (all verified to resolve); files: docs/COMPATIBILITY-v0.64.0.md; fixes: none
- [x] **1.2** Record the consumer pin inventory table verified against each consumer repo's remote `dev` branch (CLS gateway pyproject v0.64.0; CLS OpenCode lambda Dockerfile v0.61.0; CISA apps/python v0.64.0; CISA apps/node v0.61.0; workflow-engine fastapi_app v0.64.0; workflow-nodes apps/python v0.64.0) with the v0.61.0→v0.64.0 delta analysis (ctk_-only auth, `ctk` bin, registry-diff probe; manifest/execute contracts unchanged — verified via `git diff --stat v0.61.0 v0.64.0`)
    — **Why:** AC 3 — "current" means verified against remote dev, not local checkouts that may lag
    — **Done when:** each table row names the consumer manifest file path and the exact pinned URL as fetched from `repos/*/contents?ref=dev`
    — **Consumers affected:** none (report only)
    — **Done:** inventory table built from `gh api repos/*/contents?ref=dev` fetches (6 consumers, 2 lagging at v0.61.0 identified); files: docs/COMPATIBILITY-v0.64.0.md §3; fixes: none
- [x] **1.3** Document the CLS/OpenCode alignment verdict: v0.64.0 is a drop-in for node code (no manifest/execution contract change); the ONLY upgrade prerequisite for the two v0.61.0 consumers (CLS OpenCode lambda, CISA apps/node) is registry credentials already rotated to `ctk_` keys; verdict **no SDK change required, no release**; both consumer pins are bumped in-ticket (Phase 2, user decision) — the report records this as applied alignment, parent betekk/canvastekk-tracker#4211
    — **Why:** ACs 4–6 — the alignment decision + no-release verdict is the point of the ticket
    — **Done when:** the report states the verdict explicitly and the PR body carries it (PR target `dev`, `Closes betekk/canvastekk-workflow-sdk#244`)
    — **Consumers affected:** none (no code change)
    — **Done:** verdict section written (drop-in, ctk_-only prerequisite, no release, no SDK change to file) + in-ticket bump decision recorded per detection-gate user answer; files: docs/COMPATIBILITY-v0.64.0.md §1/§4; fixes: none

### Phase 2: Apply the alignment — bump both lagging pins to v0.64.0
- [x] **2.1** In canvastekk-llm-service (worktree `worktrees/244-cls-pin`, branch `feat/244-cls-pin` off `origin/dev`): bump `opencode_app/Dockerfile` LAMBDA-stage SDK wheel URL v0.61.0 → v0.64.0; PR targeting `dev`, body `Part of betekk/canvastekk-workflow-sdk#244`
    — **Why:** AC4 as scoped by the user — OpenCode lambda is one of the two lagging consumers; pip installs at build time so no lockfile exists to regenerate
    — **Done when:** the Dockerfile carries the v0.64.0 wheel URL and the PR is open (its watcher merges green)
    — **Consumers affected:** opencode_app LAMBDA image build; registration at deploy requires `ctk_` credentials (already the engine's only accepted credential)
    — **Done:** llm-service feat/244-cls-pin 704d6fb — Dockerfile wheel URL v0.61.0→v0.64.0, asset name verified vs release listing; files: opencode_app/Dockerfile; fixes: none
- [x] **2.2** In canvastekk-ifc-service-app (worktree `worktrees/244-cisa-pin`, branch `feat/244-cisa-pin` off `origin/dev`): bump `apps/node/package.json` `@betekk/canvastekk-workflow-sdk` tgz URL v0.61.0 → v0.64.0, regenerate `apps/node/package-lock.json` (`npm install --package-lock-only`); PR targeting `dev`, body `Part of betekk/canvastekk-workflow-sdk#244`
    — **Why:** AC4 — CISA's TS lane is the other lagging consumer; engine floor unchanged (>=24 both versions, CISA CI pins node 24) so the bump is drop-in
    — **Done when:** package.json + package-lock.json both reference v0.64.0 tgz and the PR is open
    — **Consumers affected:** apps/node build + its workflow-node registration path
    — **Done:** ifc-service-app feat/244-cisa-pin 19eefc2 — tgz pin + lockfile regen (scoped diff: version/resolved/integrity/ctk bin); npm ci + typecheck + lint(0 err) + 126/126 tests green vs new tgz; files: apps/node/package.json, apps/node/package-lock.json; fixes: none

### Phase 3: Verification gate + ship
- [x] **3.1** Run the gate: report diff is docs-only (both CI lanes paths-filtered out) → tier light for the report; each pin bump runs its consumer repo's applicable check (Dockerfile line-only → light; CISA lockfile regen → npm build/typecheck if configured, else light with the lockfile diff verified)
    — **Why:** exit-gate discipline per diff surface
    — **Done when:** gate memo lines appended to this PLAN's Trace (one per PR)
    — **Consumers affected:** none
    — **Done:** CLS bump gate=light (URL constant, no local lane applies; build lane rides CI); CISA bump gate=full (typecheck=t lint=t unit=t vs installed v0.64.0); report gate=light n.a. lanes; fixes: none
- [ ] **3.2** Commit + push all three branches, create all three PRs (report PR carries `Closes betekk/canvastekk-workflow-sdk#244`), arm background merge watchers, land LEARNINGS capture (if any)
    — **Why:** ship the verification + alignment
    — **Done when:** three PR URLs exist with watchers armed
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

GATE n/a tier=light lint=n.a typecheck=n.a build=n.a unit=n.a e2e=n.a — docs-only diff (md), both CI lanes paths-filtered; citations verified to resolve (2026-11-11)
GATE c8ba499 tier=full lint=n.a typecheck=n.a build=n.a unit=n.a e2e=n.a — exit gate, docs-only diff in SDK repo (repo CI paths-filters docs/PLANS out of both lanes); consumer-repo gates green (CLS 704d6fb light; CISA 19eefc2 full typecheck/lint/unit)
LOG review-fix r1: report §2.4 invoke_type set corrected to literal {http,lambda,sagemaker,in-process} with lambda unsupported (UNSUPPORTED_INVOKE_TYPES); §2.2 65-implementations phrasing repo-local. Source: code review (Major docs-accuracy).
GATE PENDING2 tier=full lint=n.a typecheck=n.a build=n.a unit=n.a e2e=n.a — review-fix re-gate, docs-only; corrected claims re-verified vs registry.py:23 + UNSUPPORTED_INVOKE_TYPES (fixes c8ba499 -> this SHA)
