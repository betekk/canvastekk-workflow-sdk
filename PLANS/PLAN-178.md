# PLAN: Bump zod to 4.6.6 in typescript package

**Branch**: feat/178
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/178
**Base**: dev

## Acceptance Criteria

- [ ] typescript/package.json + package-lock.json updated together; lockfile resolves zod ≥4.6.6
- [ ] `npm audit --package-lock-only --omit=dev` reports 0 high/critical in typescript/
- [ ] SDK typescript tests + build pass
- [ ] python/pyproject.toml left untouched (already clean)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `typescript/package.json` | — | npm publish, 7 consumer repos pinning release tags | low |
| `typescript/package-lock.json` | package.json | CI | low |
| `zod` 4.6.5 → 4.6.7 | lockfile regen | every SDK schema/validation surface (src/contracts etc.) | low — patch bump |
| consumer repos (engine, nodes, ifc, report, audio, ml, cls) | **new SDK release tag** | they pin `@betekk/canvastekk-workflow-sdk@X.Y.Z` | none until they re-pin (their own waves) |

## Implementation Phases

### Phase 1: Bump + gates (single-phase ticket — exit gate full)
- [ ] **1.1** `npm install zod@^4.6.6` in typescript/ (manifest + lock atomically); verify audit clean
    — **Why:** zod 4.6.5 is inside the constrained-collection memory-exhaustion advisory range (fix 4.6.6); the SDK is the upstream source for all seven consumer repos.
    — **Done when:** lockfile reads zod ≥4.6.6; `npm audit --package-lock-only --omit=dev` → 0 high/critical; diff = package.json + package-lock.json only.
    — **Consumers affected:** consumers get the fix when they re-pin a new SDK tag (release rides reusable-release patch label — no code coupling).

- [ ] **1.2** Gates: lint, typecheck, typecheck:tests, test, build (CI's ci-typescript lanes)
    — **Why:** CI runs these per PR — mirror locally before the PR.
    — **Done when:** all exit 0.
    — **Consumers affected:** none (read-only gates).

## Technical Notes

- Release tagging is the fleet's one release mechanism (`reusable-release.yml`, PR-label semver): the PR's `patch` label mints the next tag; consumers bump on their own waves — nothing else needed here.
- zod floor `^4.6.6` keeps the range semantics identical to `^4.6.5`.

## Dependencies

- Independent. Epic: betekk/canvastekk-tracker#4039. Consumers' zod overrides (e.g. CISA #345) become redundant once they re-pin ≥ this release — no merge-order coupling.

## Risks & Mitigation

- None identified — patch-level bump of a validation lib within the same major; full gate + consumer CI backstop.
