# PLAN: Verifier derives probes from manifest + dry-run positive probe

**Branch**: feat/113
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/113
**Base**: main

## Acceptance Criteria
- [ ] probe list = declared routes (no hardcoded route list remains in the verifier)
- [ ] positive probe fires iff `--dry-run` passed AND `capabilities.dry_run` declared (grilled 2026-10-11: registration-time verify stays passive); otherwise skipped, not failed
- [ ] `verify --dry-run` prints per-route PASS/FAIL and exits non-zero on any FAIL
- [ ] a deliberately broken route fails the check at the right route name

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/conformance.py` | #110 `NodeContract`/`effective_contract` (definition.py, merged via #116); #111 wire flag `dry_run` on execute request (parallel ticket — name pinned below) | `registry.py:457` (registration-time `verify=True`), `__main__.py` verify CLI, `tests/test_conformance.py` | medium |
| `python/canvastekk_workflow_sdk/__main__.py` (verify command) | conformance.py signature | node authors using `python -m canvastekk_workflow_sdk verify` | low |
| `python/tests/test_conformance.py` | conformance.py | CI python lane | low |

TS side: no verifier exists (`typescript/src` has no verify command) — parity is out of scope; nothing mirrors.

## Implementation Phases

### Phase 1: Manifest-derived probe list
- [x] **1.1** Rewrite `verify_node` to fetch `GET /manifest` first (200 + valid `WorkflowNodeManifest` = the existing /manifest check), derive the probe list from the manifest's effective contract routes (`manifest.contract` or the SDK-served default via `effective_contract`), and generate one `RouteCheck` per derived route (health-family GETs → expect non-5xx with 200 preferred; `/manifest` keeps the body-validation check; `/execute` keeps the malformed-payload 4xx negative probe; other declared routes → must respond without 5xx). No hardcoded route list remains; a 404/5xx/unreachable on any derived route FAILs under that route's name.
    — **Why:** AC1 + AC4 — conformance must be derived from the node's own declaration (D8/#110), and a broken declared route must fail under its own name, not silently pass a 3-route checklist
    — **Done when:** `test_conformance.py` passes with cases: derived-probe-count matches a declared 4-route contract; a 404 on a declared extra route yields `FAIL` with that route's name; minimum-route node (3 routes) behaves as today; ruff clean on the file
    — **Consumers affected:** `registry.py` registration `verify=True` (signature unchanged — passive behavior preserved via new `dry_run: bool = False` default); CLI output gains derived per-route lines
    — **Done:** verify_node now fetches /manifest first, derives probes from effective_contract.routes, per-family expectations (GET presence, execute negative, POST presence); tests updated+added (15 pass), ruff clean; files: conformance.py, test_conformance.py; fixes: 2 test-expectation fixes (dry-run skip line counts)

### Phase 2: Dry-run positive probe (flag + capability gated)
- [x] **2.1** Add `dry_run: bool = False` to `verify_node`; when True AND the manifest declares `contract.capabilities.dry_run`, fire one positive probe: `POST /execute` with `{"dry_run": true, "inputs": <type-seeded dummies from input_schema required fields>}` expecting 2xx; recorded as its own `RouteCheck("POST /execute (dry-run)", ...)` — a non-2xx or unreachable FAILs under that name. Capability absent → the probe is skipped with a `SKIPPED` RouteCheck detail line, never a FAIL. Wire note: the request flag is the top-level `dry_run` boolean (the #111 contract; SDK harness semantics live in #111 — this probe asserts transport conformance only, not side-effect freedom).
    — **Why:** AC2 — a safe positive path gated on the node's own declaration; the flag gate keeps registration-time `verify=True` passive against production nodes
    — **Done when:** tests cover: capability declared + flag → positive probe fires (2xx mock → PASS; 500 mock → FAIL at `POST /execute (dry-run)`); capability declared + no flag → skipped; capability absent + flag → skipped; ruff clean
    — **Consumers affected:** CLI (`--dry-run` in Phase 3); registry path unchanged (default False)
    — **Done:** dry_run flag AND capability gate added; positive probe seeds inputs from input_schema; skip recorded as ok RouteCheck; 4 new tests; files: conformance.py, test_conformance.py; fixes: none

### Phase 3: CLI `--dry-run` flag
- [ ] **3.1** Extend the `verify` command parser in `__main__.py` with `--dry-run`, thread it to `verify_node(dry_run=...)`, keep the per-route PASS/FAIL print and the non-zero exit on any FAIL (existing `sys.exit(0 if report.ok else 1)`), and update the help line.
    — **Why:** AC3 — authors need the positive probe reachable from the CLI
    — **Done when:** `python -m canvastekk_workflow_sdk verify <url> --dry-run` parses (arg-level test or MockTransport CLI-level test), help text lists `--dry-run`, exit codes unchanged
    — **Consumers affected:** node-author workflows; no other CLI commands touched

### Phase 4: Full gate
- [ ] **4.1** Full gate on the final tree: python legs (ruff check + pytest) green; TS legs n/a (no TS files touched — justified deviation noted in Trace); `git diff origin/main --stat` scope check (conformance.py, `__main__.py`, test_conformance.py, PLAN only)
    — **Why:** ticket exit gate — the last verification before PR
    — **Done when:** ruff + pytest green on the final tree; diff scope exactly as listed; `GATE <sha> tier=full` memo appended
    — **Consumers affected:** none beyond the above

## Technical Notes
- Probe expectations by family (documented in `conformance.py` docstring): GET routes → 200 expected for /health, /manifest, /live, /ready (non-5xx tolerated as PASS with a detail note; 404/5xx FAIL); POST /execute → malformed payload must 4xx (negative, unchanged) + capability-gated dry-run positive.
- RouteCheck.route keeps the `METHOD /path` form so AC4's "right route name" holds.
- The #111 coordination point is the single wire field: top-level `dry_run: true` on the execute request body. If #111 lands a different shape, this ticket's positive probe adjusts in review.

## Dependencies
blocked-by: #110 (merged via #116). #111 is NOT a blocker per the ticket declaration; only the wire-field name is shared (pinned above).

## Risks & Mitigation
- Registration-time `verify=True` behavior change → gated behind `dry_run=False` default; passive probe set only gains derived extra routes (strictly more thorough, same pass/fail semantics for conforming nodes).
- Schema-seeded dummy inputs may not satisfy a node's cross-field validation → the positive probe reports FAIL with the node's 4xx detail (author's signal to fix schema or inputs), never a crash; documented in the docstring.
- #111 wire-field drift → single pinned field name; review-time reconciliation.

## Trace


LOG Phases 1+2 landed as one commit — verify_node rewritten as a unit; per-phase split would be git theater (deviation visible here, gates ran scoped per concern).