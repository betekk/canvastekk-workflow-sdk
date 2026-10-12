# PLAN: Default contract must not declare /hook the node cannot answer

**Branch**: feat/138
**Issue**: betekk/canvastekk-workflow-sdk#138
**Base**: main

## Acceptance Criteria
- [ ] Served `/manifest` contract omits `/hook` when the definition rides the default contract AND the node class does not override `BaseNode.hook`
- [ ] Served contract is untouched when the author declared an explicit contract, and keeps `/hook` when `hook()` IS overridden
- [ ] Version bumped 0.52.2 → 0.52.3 (merge to main triggers the Release workflow → wheel asset)
- [ ] Python CI green; new unit tests cover all three stamping branches

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/app.py` (`/manifest` handler) | — | Every SDK-served node's manifest → engine #658 registration probe → workflow-nodes #456 + point-cloud #241 adoption | medium — the stamped contract changes for all default-contract nodes; that is the fix, and it requires node version bumps downstream (registry immutability) |
| `python/tests/test_app.py` | app.py change | CI | low |
| `python/pyproject.toml` (version) | — | Release workflow, downstream pins | low |

Cross-module consumers exist (two downstream repos) → architecture review note: the change is strictly narrowing (a declared-but-unimplementable route disappears from the default); declared contracts and hook-implementers are byte-identical. No input/output signature changes.

## Implementation Phases

### Phase 1: Instance-aware contract stamping
- [ ] **1.1** In `app.py`'s `/manifest` handler, compute the served contract: default-minus-`/hook` when `definition.contract is None and type(node).hook is BaseNode.hook`; declared and hook-overriding nodes unchanged. Bump version to 0.52.3. Add three tests (default-omits, override-keeps, declared-untouched).
    — **Why:** The SDK stamps `/hook` into every default contract while its own stub returns 501 for it, and the engine's presence bar rejects ≥500 — so every default-contract node fails registration by construction (49 CWN + 15 CPCA handlers, zero hook implementers).
    — **Done when:** the three tests pass locally (or CI if no local venv) and Python CI is green on the PR.
    — **Consumers affected:** workflow-nodes, point-cloud-app (adoption tickets follow); all other SDK consumers see a narrowed default only.

## Technical Notes
- Release: push to main (paths-ignore CHANGELOG) triggers `Release` → v0.52.3 wheel asset; downstream pins are URL-based (`releases/download/v0.52.3/...`).
- Downstream: CWN #456 + CPCA #241 adopt the pin and bump their node versions (stamped manifest data changes → registry immutability, canvastekk-audio-service-app #113's 409 lesson).

## Dependencies
None upstream. Downstream adoption: canvastekk-workflow-nodes#456, canvastekk-point-cloud-app#241.

## Risks & Mitigation
- Risk: a consumer relied on `/hook` being declared to route webhook traffic to a stub. Mitigation: the stub 501s — no working traffic could exist; audio already ships the narrowed shape in production (green).
- Risk: offline fleet gates (wf-nodes #461, point-cloud #239) assert `effective_contract` on definitions — unchanged (the fix is at serving time, definitions untouched).
