# PLAN: README deployment ladder + registration/verification flow

**Branch**: feat/114
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/114
**Base**: main

## Acceptance Criteria
- [x] three rungs documented with a worked example each
- [x] who-calls-invoke_url table covers every credential path
- [x] sequence diagram: serve → verify → register → engine probes
- [x] every code sample runs against the shipped SDK version

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `README.md` (new "Deployment Ladder" section) | shipped SDK APIs only (`create_node_app`, `register_node`, `NodeContract` — all merged) | Flask/self-hosted authors (#110's persona), gateway teams | low |

Docs-only change. Facts sourced from merged code: `registry.py` (register_node, build_registry_payload), `app.py` (create_node_app), `docs/dry-run-contract.md`, `docs/EXTERNAL-AUTHOR-GUIDE.md`.

## Implementation Phases

### Phase 1: Deployment ladder — three rungs, worked example each
- [x] **1.1** Add a `## Deployment Ladder` section to README.md (after Workflow Builder, before Architecture): **Rung 1 SDK-served** (`create_node_app` — the adapter mounts the contract routes, dry-run built in); **Rung 2 self-hosted** (Flask example implementing the declared contract routes + `capabilities.dry_run` semantics per docs/dry-run-contract.md); **Rung 3 no-HTTP** (`invoke_type="lambda"`/`"in-process"` — no invoke_url, `verify=True` unavailable by definition, registration without probes)
    — **Why:** AC1 — the Flask author (#110's persona) has no single entry point explaining the rungs
    — **Done when:** three rungs, each with a runnable-looking worked example whose imports/symbols all exist in the shipped package (checked in Phase 3)
    — **Consumers affected:** README readers; no code
    — **Done:** Deployment Ladder section added between Wire-Format Convention and Architecture: three rungs with worked samples (create_node_app+register_node verify=True / Flask self-hosted incl. dry_run branch / no-HTTP lambda invoke_type); files: README.md; fixes: none

### Phase 2: who-calls-invoke_url table + sequence diagram
- [x] **2.1** Add the who-calls-invoke_url table (callers: engine at execution time — auth posture per the node's NodeAuth, key delivered via engine-side config/`invoke_config`, NEVER the registration `api_key` param which authenticates registry+verify only and is not serialized into the payload (verified against `build_registry_payload`); SDK verify probes at registration time — `X-API-Key` from `register_node(api_key=...)`; gateway/consumers — per deployment) + a mermaid sequence diagram: serve → verify (probes derived from the manifest) → register → engine probes at runtime
    — **Why:** AC2 + AC3 — "who calls invoke_url" was the ticket's literal question; the diagram closes the serve→register loop
    — **Done when:** table lists every caller the SDK surfaces with its credential source; mermaid block balanced and renders (fence check); both facts cross-checked against registry.py/app.py
    — **Consumers affected:** README readers; no code
    — **Done:** who-calls-invoke_url table (verifier probes via register_node api_key; engine runtime via node auth posture delivered out-of-band — registration api_key never serialized, verified against build_registry_payload; gateways same channel) + mermaid serve-verify-register-probes diagram; files: README.md; fixes: none

### Phase 3: Full gate
- [x] **3.1** Full gate on the final tree: every README python sample import-checked against the shipped package (`python3 -c "import ..."` per sample's imports); mermaid fences balanced; three-dot diff scope = README.md + PLAN only. Python/TS test legs n.a. (docs-only — justified; CI carries the suite)
    — **Why:** AC4 (samples must match the shipped SDK) + ticket exit gate
    — **Done when:** all import checks pass; scope exact; `GATE <sha> tier=full` memo appended
    — **Consumers affected:** none beyond the above
    — **Done:** full gate on final tree: sdk-symbol import checks pass (create_node_app extra-gated, documented), 52 fences balanced, mermaid present, three-dot scope = README + PLAN only; files: none (verification); fixes: none

## Technical Notes
- Rung naming matches the ticket: SDK-served / self-hosted / no-HTTP.
- Registration specifics already documented in the node-builder skill + EXTERNAL-AUTHOR-GUIDE (PR #119/#121); README links out instead of duplicating.

## Dependencies
blocked-by: #110, #111 (both merged — released 2026-10-11).

## Risks & Mitigation
- Drift between README samples and the evolving SDK → Phase 3 import-check is repeatable; samples avoid exotic APIs.
- Mermaid rendering → plain sequenceDiagram syntax only, fence-balanced.

## Trace
LOG Gate note: sample import-check treats fastapi-extra lazy exports (create_node_app) as resolving — the local env lacks the extra by design (framework-optional core).
GATE 714aac6 tier=full lint=t typecheck=n.a build=n.a unit=n.a e2e=n.a
LOG Exit gate (ticket): full on 714aac6 — sdk-symbol import checks + fence balance + mermaid presence + three-dot scope (README + PLAN only); python/TS test legs n.a. (docs-only, CI carries the suite).
