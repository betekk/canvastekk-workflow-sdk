# PLAN: SDK#133 — ctk_ registry credentials ride Authorization Bearer

**Branch**: feat/133
**Issue:** https://github.com/betekk/canvastekk-workflow-sdk/issues/133
**Base**: main

## Acceptance Criteria

- [x] `register_node(service_token="ctk_…")` sends `Authorization: Bearer` (test-pinned on emitted headers)
- [x] CLI `CANVASTEKK_REGISTRY_TOKEN=ctk_…` same (both CLI header uses route through the shared helper)
- [x] Non-`ctk_` tokens byte-identical to today (`X-Service-Token`)
- [x] No new public parameters; docstrings updated

## Dependency & Consumer Map

| Node (file/module) | Depends on | Consumers | Change risk |
|---------------------|-----------|------------|-------------|
| `registry.py` `_registry_auth_header` (new helper) | — | `register_node` (:501 site), CLI `__main__.py` (:299 site) | low (wire form follows credential type; legacy path byte-identical) |
| `register_node` header emission | helper | every registrant (fleet scripts pass the env token) | low |
| `__main__.py` `_request` | helper | CLI register + by-name verify | low |
| tests | implementation | CI | low |

External: point-cloud#232 pilot (+4 followers) consume the released wheel; engine #700 (merged) is the server side.

## Implementation Phases

### Phase 1: dispatch-on-prefix + tests + docs

- [x] **1.1** `_registry_auth_header(token)` helper in registry.py; `register_node` uses it at the service_token site; CLI `_request` uses it at its header site; docstrings (register param + CLI env-var doc) name both wire forms
    — **Why:** the fleet's ctk_ keys cannot authenticate as X-Service-Token (engine dispatches ctk_ on Authorization Bearer); one helper at the shared seam keeps the CLI and library from drifting
    — **Done when:** both sites route through the helper; legacy tokens produce identical requests to today
    — **Consumers affected:** every registrant (only ctk_-shaped credentials change wire form)
    — **Done:** _registry_auth_header helper + both sites route through it (register_node, CLI _request); docstrings name both wire forms; fixes: import placement (function-local at the _request site)
- [x] **1.2** Tests: helper unit ×2 (ctk_→Bearer pair, svs_→X-Service-Token pair); register_node header capture ×2 (ctk_ token → Authorization header present + X-Service-Token absent; legacy → unchanged); CLI site covered via the helper unit + one add_header invocation test if the CLI test harness allows cheaply
    — **Why:** AC is explicitly test-pinned header behavior; byte-identity for legacy is the no-regression guarantee
    — **Done when:** touched suites green
    — **Consumers affected:** CI
    — **Done:** helper unit ×2 shapes + register_node header capture ×2 (Bearer present/Svc absent; legacy byte-identical); 220/220 touched suites
- [x] **1.3** Ticket-exit gate (full): ruff check (CI-parity) + touched suites + full-runnable suite with the documented env-failure exclusions; `GATE 68494ff tier=full` in Trace
    — **Why:** the memo Step 10 cites
    — **Done when:** Trace carries the memo
    — **Consumers affected:** PR gate citation
    — **Done:** ruff check green; touched 220/220; full-runnable 712 passed + 14 pre-existing env-only failures (fastapi-extras class, proven on clean main 2026-10-12)

## Technical Notes

- No new parameters — the wire form follows credential shape, mirroring the engine's own prefix dispatch (DA-1949). Legacy svc tokens keep X-Service-Token for the dated bridge; engine #699 removes that leg later.
- Wheel: this lands as v0.51.0 (main is at v0.50.0, `f77fbd1`); the pilot pins the new tag.

## Dependencies

Unblocks: point-cloud#232 (pilot) → #450/#109/#204/#101. Server side: engine #700 (merged `64be238a`).

## Risks & Mitigations

- **Risk:** a user passes a ctk_-shaped string as `api_key` (wrong param) — unchanged behavior there (X-API-Key), and the engine 401s; docstrings now name the right param for ctk_.

## Trace

GATE 68494ff tier=full lint=t typecheck=t build=t unit=t e2e=n.a  (ruff check green; touched 220/220; full-runnable 712 passed / 14 pre-existing env-only; fixes: CLI import placement)
