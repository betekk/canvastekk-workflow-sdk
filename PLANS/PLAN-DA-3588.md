# PLAN: Verify SDK against engine scope rename (verification ticket)

**Branch**: feat/DA-3588
**Issue**: https://betekk.atlassian.net/browse/DA-3588
**Base**: main
**Repo**: canvastekk-workflow-sdk

_Note: premise corrected by inspection (DA-3583 plan review) — the SDK
has zero definition-scope consumers; this ticket verifies zero impact
and records the finding as a regression guard. Authored
post-implementation (orchestrator deviation)._

## Acceptance Criteria
- [x] Parity fixture / verification: engine payload with scope="system" — SDK does not parse definitions payloads (recorded as finding + regression guard)
- [x] SDK test suite green against the renamed engine contract (798 passed)
- [x] Compat gate unchanged (no proven breakage — zero consumers)
- [x] Ticket closes with inspection + test evidence

## Implementation Phases
- [x] **1.1** `tests/test_scope_rename_parity.py`: regression guard (no definitions-scope literals in SDK source; ASGI scope exempt) + documented engine payload evidence
    — **Why:** the ticket's amended AC — record the zero-impact finding so a future parser author meets the DA-3588 context
    — **Done when:** suite passes with the new module
    — **Consumers affected:** none
- [x] **1.2** Full SDK suite + repo gates
    — **Done when:** 798 passed / 0 failed
    — **Consumers affected:** none

GATE (see run record) tier=full lint=n.a typecheck=n.a build=- unit=t e2e=n.a
