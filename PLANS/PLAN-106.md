# PLAN: Migrate zod 3.25 to zod ^4.6

**Branch**: feat/106
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/106
**Base**: main

## Acceptance Criteria
- [ ] `typescript/package.json` pins `zod ^4.6`; lockfile updated
- [ ] Full TS gate green: build, vitest, eslint, `tsc --noEmit` (src + tests)
- [ ] No `zod/v3` or `zod/v4` subpath imports in `src/` (top-level `from "zod"` everywhere)
- [ ] Public schema surface documented: any consumer-visible validation-message/shape changes listed in the PR body
- [ ] CHANGELOG note renders via commit subject (no hand-editing the generated file)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `typescript/package.json` (zod line) | — | `package-lock.json`, npm consumers (zod is a direct dep — dedupe friction possible when consumers pin v3) | medium |
| `typescript/src/definition.ts` | zod bump | `index.ts` exports, tests, consumers of `NodeDefinitionSchema` | medium |
| `typescript/src/request.ts` | zod bump | executor/engine boundary, tests | medium |
| `typescript/src/response.ts` | zod bump | executor, tests | medium |
| `typescript/src/uploads.ts` | zod bump | multipart flow, tests | medium |

Cross-module note: no in-repo module redesign — version bump + API spelling fixes; consumers are external (npm installers, schema builders). Zero reviewer selection justified; Step 9 code review backstops.

## Implementation Phases

### Phase 1: Bump and migrate
- [ ] **1.1** Bump `zod` to `^4.6` in `typescript/package.json`; `npm install`
    — **Why:** every later step compiles/tests against the new major; install first so breakage surfaces in one sweep
    — **Done when:** lock resolves zod 4.6.x; `node -e "console.log(require('zod/package.json').version)"` prints 4.x
    — **Consumers affected:** npm consumers (dedupe note in PR body)
- [ ] **1.2** Run `tsc --noEmit` + `vitest run` and fix every surfaced breakage in `src/` (imports stay top-level `from "zod"`)
    — **Why:** the compiler+suite is the authoritative inventory of v3-only API usage; fixing against real errors beats spec-guessing
    — **Done when:** both commands exit 0
    — **Consumers affected:** the four zod-importing modules and their exports
- [ ] **1.3** Modernize deprecated-in-v4 spellings surfaced by the sweep (known: `z.string().date()` → `z.iso.date()`); keep still-supported APIs (`.superRefine()`, `.preprocess()`) unless the compiler/deprecation warnings say otherwise
    — **Why:** migrating onto deprecated shims re-creates this ticket's work at zod 5; modern spellings are the migration's point
    — **Done when:** `grep -rn "string().date()" src/` is empty; no new deprecation warnings in build output
    — **Consumers affected:** `definition.ts` date-field validation (behavior-equivalent strict YYYY-MM-DD)
- [ ] **1.4** Gate Phase 1: `npm audit --omit=dev`, `npm run build`, `vitest run`, `npm run lint`, `tsc --noEmit` + `tsc --noEmit -p tsconfig.tests.json`
    — **Why:** the ticket's green-bar definition; audit proves the bump brings no new advisories
    — **Done when:** all commands exit 0
    — **Consumers affected:** CI node jobs

### Phase 2: Contract checks and exit gate
- [ ] **2.1** Verify no subpath imports: `grep -rn "zod/v3\|zod/v4" src/ tests/` is empty; document the public schema surface in the PR body (exported schema names from `definition/request/response/uploads` + any validation-message changes observed in test diffs)
    — **Why:** AC contract — consumers must know exactly what moved and how to build schemas against the SDK
    — **Done when:** grep clean; PR body section drafted
    — **Consumers affected:** schema-builder consumers
- [ ] **2.2** Ticket exit gate: full tier re-run on the final tree; `tier=full` memo appended to `## Trace`
    — **Why:** the run's last gate is full; its memo is the Step 10a citation
    — **Done when:** `GATE <sha> tier=full` recorded for the final tree SHA
    — **Consumers affected:** PR creation (Step 10a cites this memo)

## Technical Notes
- zod 3.25 already bundles v4 under `zod/v4` (the bridge line) — no regression risk from the version number itself; the delta is the API surface the SDK actually touches.
- CHANGELOG renders from the commit subject (`fix(deps)!`/`feat(deps)` decision at commit time based on whether any consumer-visible schema behavior changed).
- If v4 incompatibilities prove deep (not expected — inventory shows core APIs only), fallback is the ticket's documented interim: `zod/v4` subpath on 3.25; record as SKIP deviation instead of forcing.

## Dependencies
None — no `blocked-by` tickets.

## Risks & Mitigation
- **Dedupe friction for consumers pinning zod v3**: two zod copies coexist; types across copies are incompatible. Mitigation: PR body documents the surface; semver label reflects reality.
- **Validation-message changes**: v4 reworded some default messages — vitest asserts on behavior; any message-dependent test updates ride 1.2 and are listed in the PR body.
- **`.date()` behavior drift**: v4 `z.iso.date()` is the same strict YYYY-MM-DD; the existing strict-date test guards it.

## Trace
<!-- gate memos append here -->
