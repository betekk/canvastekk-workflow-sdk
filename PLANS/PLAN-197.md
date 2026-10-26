# PLAN: Dependabot CI fails before running tests

**Branch**: feat/197
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/197
**Base**: dev

## Acceptance Criteria
- [ ] Missing or invalid app credentials no longer fail `pick-runner` in either PR CI workflow; the existing probe emits `labels=["ubuntu-24.04"]` so downstream quality gates can run.
- [ ] Authenticated local-if-idle routing and every existing `needs`, `runs-on`, and output contract remain unchanged.
- [ ] `reusable-release.yml` has the same graceful degradation when automatic runner selection cannot mint an app token.
- [ ] All three workflow files parse as YAML, and the implementation diff is limited to their three `app-token` steps.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `.github/workflows/ci-typescript.yml` | Existing empty-token probe failure and hosted fallback | `typecheck-test-build`; TypeScript PR/push checks | medium |
| `.github/workflows/ci-python.yml` | Existing empty-token probe failure and hosted fallback | `lint-and-test`, `schema-stability`, `skill-mirror-guard`; Python PR/push checks | medium |
| `.github/workflows/reusable-release.yml` | Existing empty-token probe failure and hosted fallback | `.github/workflows/release.yml` and its `release` job | high |

## Implementation Phases

### Phase 1: Let runner selection reach its hosted fallback
- [ ] **1.1** Add `continue-on-error: true` to the `app-token` step in `.github/workflows/ci-typescript.yml` without changing the probe or downstream jobs.
    — **Why:** Dependabot cannot read `GH_APP_PRIVATE_KEY`; allowing the token step to fail lets the existing empty-token probe path select `ubuntu-24.04` instead of skipping TypeScript gates.
    — **Done when:** the `app-token` step has `continue-on-error: true`, and the `pick` step plus `typecheck-test-build` routing are unchanged.
    — **Consumers affected:** TypeScript CI consumers retain the same `pick-runner.outputs.labels` contract and gain a working no-secret fallback.
- [ ] **1.2** Add `continue-on-error: true` to the `app-token` step in `.github/workflows/ci-python.yml` without changing the probe or downstream jobs.
    — **Why:** Python Dependabot PRs hit the same missing-secret failure and need the existing hosted fallback to reach lint, tests, schema, and mirror gates.
    — **Done when:** the `app-token` step has `continue-on-error: true`, and the `pick` step plus all three dependent jobs are unchanged.
    — **Consumers affected:** Python CI consumers retain the same labels contract and gain a working no-secret fallback.
- [ ] **1.3** Add `continue-on-error: true` to the `app-token` step in `.github/workflows/reusable-release.yml` without changing release routing.
    — **Why:** automatic release runner selection has the same token-before-failure gap; the existing probe already defines the intended hosted degradation.
    — **Done when:** the `app-token` step has `continue-on-error: true`, and the `pick` step, `release` condition, and `runs-on` expression are unchanged.
    — **Consumers affected:** `.github/workflows/release.yml` retains its reusable-workflow interface and gains graceful hosted degradation.

## Technical Notes
The workflows already retry a failed org-runner probe three times and then emit `labels=["ubuntu-24.04"]`. With no app token, `gh api` cannot query the org runner list, so that existing path supplies the fallback. This change adds no action, dependency, secret, or new fallback logic. YAML parsing, scoped invariants, and diff review are the local executable checks; PR CI and a rebased Dependabot PR provide the authoritative runtime checks.

## Dependencies
None.

## Risks & Mitigation
- A genuine app-credentials regression now degrades to hosted runners instead of failing fast: the existing probe emits a visible warning, which is the runner-routing behavior already intended by #64.
- A malformed workflow could skip every gate: parse all three files locally and require green PR CI before merge.
- Release behavior could change beyond fallback: inspect the scoped diff to confirm that no `needs`, `runs-on`, output, or release condition changes.

## Trace
