# PLAN: node-builder skill — registration auth + verify section

**Branch**: feat/115
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/115
**Base**: main

## Acceptance Criteria
- [ ] bundled skill and .agents mirror identical; mirror-guard CI green
- [ ] registration auth section covers all credential paths incl. verify=True
- [ ] skill triggers updated; description ≤50 words

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/data/skills/canvastekk-node-builder/SKILL.md` (bundled canonical) | `registry.py::register_node` signature + auth semantics (read-only reference) | node-builder agents; ships inside the wheel (`data/skills`) | low |
| `.agents/skills/canvastekk-node-builder/SKILL.md` (mirror) | Phase 1 byte-identical copy | repo agents reading `.agents/`; mirror-guard CI job | low |

Docs-only change — no code paths. The bundled copy is canonical; the mirror MUST be byte-identical (mirror-guard CI, seen in PR checks as "Skill mirrors match bundled canonical").

## Implementation Phases

### Phase 1: Registration section in the bundled SKILL.md
- [ ] **1.1** Add an `## Engine Registration (CI/CD)` section to the bundled SKILL.md (after `## Node Creation Workflow`): `register_node` full signature table; credential paths — `api_key` (node auth; ALSO the X-API-Key used by verify probes) vs `service_token` (engine X-Service-Token), neither → ValueError, precedence when both; `verify=True` semantics (requires `invoke_type="http"` + `invoke_url`, conformance gate raises `RegistrationError` with the report, `verify_timeout`); a worked CI example reading tokens from env vars; note the new `verify --dry-run` positive probe (#113) as an optional pre-registration check
    — **Why:** the ticket's core gap — agents authoring nodes miss registration credentials and the conformance gate; `register_node` today appears only in an import list
    — **Done when:** the section documents every `register_node` parameter, both credential paths with their distinct roles, and verify=True incl. its two ValueError preconditions; description updated with a registration trigger and STILL ≤50 words (word-count check)
    — **Consumers affected:** skill consumers (agents); bundled-wheel content changes

### Phase 2: Mirror to .agents (byte-identical)
- [ ] **2.1** Copy the bundled SKILL.md over `.agents/skills/canvastekk-node-builder/SKILL.md` and verify identity (`cmp` exit 0)
    — **Why:** AC1 — mirror-guard CI fails the PR on drift; one change, both copies
    — **Done when:** `cmp` reports zero differences between the two files
    — **Consumers affected:** mirror-guard CI job; `.agents` readers

### Phase 3: Full gate
- [ ] **3.1** Full gate on the final tree: mirror `cmp` clean; description word count ≤50; markdown renders (no broken fences — fenced-block balance check); diff scope = the two SKILL.md files + PLAN only. Python/TS test legs n.a. (docs-only change — justified deviation in Trace; CI mirror-guard is the authoritative check)
    — **Why:** ticket exit gate — the last verification before PR
    — **Done when:** all local checks green; `GATE <sha> tier=full` memo appended
    — **Consumers affected:** none beyond the above

## Technical Notes
- Canonical copy = the bundled one (ships in the wheel); `.agents/` is the mirror. Never edit the mirror alone.
- Credential semantics sourced from `registry.py` docstring + validation code (lines 355-460), not invented.
- Description is the skill's trigger surface; "triggers updated" = registration keywords present, ≤50 words preserved.

## Dependencies
blocked-by: `#` (malformed, removed 2026-10-11) — no blockers. Content references #113's `--dry-run` (merged via #118 — being watched).

## Risks & Mitigation
- Mirror drift → Phase 2 copies + `cmp` proof; CI mirror-guard double-checks on the PR.
- Word-count creep in description → counted at Phase 1 gate.

## Trace
