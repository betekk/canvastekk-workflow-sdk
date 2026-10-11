# PLAN: SDK#131 — invoke_type lambda is not platform policy

**Branch**: feat/131
**Issue:** https://github.com/betekk/canvastekk-workflow-sdk/issues/131
**Base**: main

## Acceptance Criteria

- [x] Registry audit comment: lambda-typed rows per env (expected 0) — **done pre-PLAN**: dev 10 rows (8 http + 2 in-process, ZERO lambda), uat 10 rows (same, ZERO); prod unreachable from this runner (caveat recorded on the ticket; #699's sweep backstops)
- [ ] SDK rejects `invoke_type="lambda"` with a clear error pointing to the HTTP contract; README marks unsupported
- [ ] canvastekk-node-builder skill (both bundled copies) drops the lambda rung
- [ ] No behavior change for HTTP nodes

## Dependency & Consumer Map

| Node (file/module) | Depends on | Consumers | Change risk |
|---------------------|-----------|------------|-------------|
| `registry.py` `build_registry_payload` guard | — | `register_node` (:463), `export_definition` (definition.py:729), CLI — ALL invoke_type paths route here | low (one guard at the single choke point; http/sagemaker/in-process untouched) |
| `registry.py` `InvokeType` Literal + docstrings | guard | typing surface of every entry point | low (member KEPT so the rejection is a clear ValueError, not a typing error) |
| `README.md` Rung 3 | — | external authors | low (docs) |
| `docs/EXTERNAL-AUTHOR-GUIDE.md` | — | external authors | low (docs) |
| `.agents/skills/canvastekk-node-builder/SKILL.md` + `python/.../data/skills/` copy | — | agents loading the skill; mirror guard (`diff -r` both copies identical) | low (both copies same edit) |
| `tests/test_registry.py`, `tests/test_definition.py` | guard | CI | low (lambda-arm tests become rejection tests) |

External consumers: zero lambda-typed registry rows (audited dev+uat) — no live user of the rung exists to break.

## Implementation Phases

### Phase 1: the guard + docs + skill

- [x] **1.1** `build_registry_payload`: reject `invoke_type == "lambda"` with ValueError naming the platform law (every node is HTTP-contract; Lambda hosting surfaces via Function URL/gateway; register `invoke_type="http"`) — one guard, the seam every path (register_node / export_definition / CLI) routes through
    — **Why:** AC "SDK rejects with a clear error"; the choke point is the root-cause location (a guard per entry point would drift)
    — **Done when:** register_node, export_definition, and the CLI all surface the rejection via their build_registry_payload routing; http/sagemaker/in-process payloads byte-identical
    — **Consumers affected:** all invoke_type paths (only the lambda arm changes)
    — **Done:** UNSUPPORTED_INVOKE_TYPES map + guard at the top of build_registry_payload (the choke: register_node :463, export_definition, CLI); files: registry.py; fixes: none
- [x] **1.2** `InvokeType` docstring + the two registry.py docstrings (:270, :388) drop lambda from the documented vocabulary, note the policy; README Rung 3 rewritten (in-process only, admin-gated engine-side; lambda removed with the policy sentence); EXTERNAL-AUTHOR-GUIDE invoke_type mentions updated
    — **Why:** AC "README marks unsupported"; docs must not teach a rejected path (deprecation-sweep discipline)
    — **Done when:** grep -i "invoke_type.*lambda\|lambda.*invoke_type" in README/docs shows only the policy note; Rung 3 carries no lambda example
    — **Consumers affected:** external authors
    — **Done:** both registry.py docstrings + definition.py export docstring drop lambda; README Rung 3 rewritten (in-process only + policy callout); EXTERNAL-AUTHOR-GUIDE lambda example → Function URL http example + param table updated; fixes: none
- [x] **1.3** canvastekk-node-builder SKILL.md — remove the lambda rung from templates/checklists, BOTH copies (`.agents/skills/` + `python/canvastekk_workflow_sdk/data/skills/`), kept `diff -r`-identical
    — **Why:** AC "node-builder skill mirrors updated" — an agent loading the skill must not be taught the rejected path
    — **Done when:** `diff -r .agents/skills python/canvastekk_workflow_sdk/data/skills` clean; no lambda rung in either copy
    — **Consumers affected:** skill consumers (agents)
    — **Done:** both copies edited identically; diff -r clean; fixes: none
- [x] **1.4** Tests: build_registry_payload lambda → ValueError with the policy message (unit); export_definition lambda → same (via routing); register_node lambda → same pre-HTTP (no network attempted); the parametrized "all four types" test (:699) drops lambda; HTTP regression: payload byte-equality for an http node pinned
    — **Why:** AC reject + no-behavior-change, both test-pinned; the :699 sweep would otherwise red
    — **Done when:** full pytest green; new rejection tests present
    — **Consumers affected:** CI
    — **Done:** rejection tests ×3 (register pre-HTTP, choke direct, export no-file-written) + http byte-pin + :699 sweep drops lambda + custom-invoke test → sagemaker; 217 passed across the 4 touched suites; fixes: manifest field-order/description in new tests

### Phase 2: ticket record + exit gate

- [ ] **2.1** Registry-audit results comment on #131 (dev/uat zero rows with the tally, prod-unreachable caveat, #699 backstop)
    — **Why:** AC 1 explicitly requires the audit as an in-ticket record
    — **Done when:** comment posted naming per-env counts
    — **Consumers affected:** ticket readers
- [ ] **2.2** Ticket-exit gate (full): the SDK's discovered gates (pytest + ruff/mypy per repo manifest) green on the final tree; `GATE <sha> tier=full` in Trace
    — **Why:** the memo Step 10 cites
    — **Done when:** Trace carries the memo
    — **Consumers affected:** PR gate citation

## Technical Notes

- Literal member `"lambda"` is deliberately KEPT: removing it converts the clear ValueError into a typing/Construct error and is the breaking-change class the schema CI flags major. The engine's accepted vocabulary is unchanged by this SDK (engine-side removal belongs to #699's sweep wave).
- `sagemaker` and `in-process` are out of scope here (in-process stays admin-gated engine-side per DA-2030; sagemaker untested by the audit — no rows imply none anywhere).
- Audit evidence (2026-10-12): dev/uat GET /api/workflows/nodes/ public; counts in AC 1.

## Dependencies

None (filler ticket by design). References: engine #699 (bridge/svc-token sweep), epic tracker#3734 A2.5.

## Risks & Mitigations

- **Risk:** an unknown external author used lambda locally (never registered). *Mitigation:* error message states the HTTP contract + Function URL guidance; release notes via semver label (minor).
