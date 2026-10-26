# PLAN: Dependabot CI fails before running tests

**Branch**: feat/197
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/197
**Base**: dev

## Acceptance Criteria
- [x] Missing or invalid app credentials no longer fail `pick-runner` in either PR CI workflow; the existing probe emits `labels=["ubuntu-24.04"]` so downstream quality gates can run.
- [x] Authenticated local-if-idle routing and every existing `needs`, `runs-on`, and output contract remain unchanged.
- [x] `reusable-release.yml` has the same graceful degradation when automatic runner selection cannot mint an app token.
- [x] All three workflow files parse as YAML, every job setup action resolves while the repository is public, and pre-checkout workspace healing remains available without the private `betekk/betekk-gha` dependency.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `.github/workflows/ci-typescript.yml` | Existing empty-token probe failure and hosted fallback | `typecheck-test-build`; TypeScript PR/push checks | medium |
| `.github/workflows/ci-python.yml` | Existing empty-token probe failure and hosted fallback | `lint-and-test`, `schema-stability`, `skill-mirror-guard`; Python PR/push checks | medium |
| `.github/workflows/reusable-release.yml` | Existing empty-token probe failure and hosted fallback | `.github/workflows/release.yml` and its `release` job | high |

## Implementation Phases

### Phase 1: Let runner selection reach its hosted fallback
- [x] **1.1** Add `continue-on-error: true` to the `app-token` step in `.github/workflows/ci-typescript.yml` without changing the probe or downstream jobs.
    — **Why:** Dependabot cannot read `GH_APP_PRIVATE_KEY`; allowing the token step to fail lets the existing empty-token probe path select `ubuntu-24.04` instead of skipping TypeScript gates.
    — **Done when:** the `app-token` step has `continue-on-error: true`, and the `pick` step plus `typecheck-test-build` routing are unchanged.
    — **Consumers affected:** TypeScript CI consumers retain the same `pick-runner.outputs.labels` contract and gain a working no-secret fallback.
    — **Done:** made only the TypeScript `app-token` step non-blocking; probe and downstream routing unchanged; files: `.github/workflows/ci-typescript.yml`; fixes: none
- [x] **1.2** Add `continue-on-error: true` to the `app-token` step in `.github/workflows/ci-python.yml` without changing the probe or downstream jobs.
    — **Why:** Python Dependabot PRs hit the same missing-secret failure and need the existing hosted fallback to reach lint, tests, schema, and mirror gates.
    — **Done when:** the `app-token` step has `continue-on-error: true`, and the `pick` step plus all three dependent jobs are unchanged.
    — **Consumers affected:** Python CI consumers retain the same labels contract and gain a working no-secret fallback.
    — **Done:** made only the Python `app-token` step non-blocking; probe and all three dependent jobs unchanged; files: `.github/workflows/ci-python.yml`; fixes: none
- [x] **1.3** Add `continue-on-error: true` to the `app-token` step in `.github/workflows/reusable-release.yml` without changing release routing.
    — **Why:** automatic release runner selection has the same token-before-failure gap; the existing probe already defines the intended hosted degradation.
    — **Done when:** the `app-token` step has `continue-on-error: true`, and the `pick` step, `release` condition, and `runs-on` expression are unchanged.
    — **Consumers affected:** `.github/workflows/release.yml` retains its reusable-workflow interface and gains graceful hosted degradation.
    — **Done:** made only the reusable-release `app-token` step non-blocking; release conditions and runner expressions unchanged; files: `.github/workflows/reusable-release.yml`; fixes: none

### Phase 2: Make pre-checkout healing public-repository compatible
- [x] **2.1** Replace the private `heal-workspace` action in `.github/workflows/ci-typescript.yml` with the identical inline shell implementation.
    — **Why:** the repository is public and `betekk/betekk-gha` is private, so GitHub fails job setup while resolving the action; step-level conditions cannot intercept that download failure.
    — **Done when:** no private action reference remains, the inline script matches the internal action, and the script passes the disposable skip-worktree recovery check.
    — **Consumers affected:** TypeScript CI retains pre-checkout healing on self-hosted runners and can start jobs while the repository is public.
    — **Done:** inlined the exact v1.17.0 heal script; private action reference removed; YAML and disposable recovery checks passed; files: `.github/workflows/ci-typescript.yml`; fixes: public-repository action-resolution failure
- [x] **2.2** Replace both private `heal-workspace` action references in `.github/workflows/ci-python.yml` with the same inline shell implementation.
    — **Why:** Python lint/test and skill-mirror jobs fail in the same setup phase and need the existing healing behavior without changing repository visibility.
    — **Done when:** both jobs use byte-identical inline scripts, no private action reference remains, and YAML/script checks pass.
    — **Consumers affected:** Python CI and skill-mirror consumers retain pre-checkout healing and can start jobs while the repository is public.
    — **Done:** inlined byte-identical v1.17.0 heal scripts in lint/test and mirror jobs; private action references removed; YAML and disposable recovery checks passed; files: `.github/workflows/ci-python.yml`; fixes: public-repository action-resolution failure

## Technical Notes
The workflows already retry a failed org-runner probe three times and then emit `labels=["ubuntu-24.04"]`. With no app token, `gh api` cannot query the org runner list, so that existing path supplies the fallback. This change adds no action, dependency, secret, or new fallback logic. YAML parsing, scoped invariants, and diff review are the local executable checks; PR CI and a rebased Dependabot PR provide the authoritative runtime checks.

The first PR run proved `pick-runner` green but exposed a separate setup blocker: the currently public repository cannot resolve private `betekk/betekk-gha` actions. Phase 2 inlines the existing v1.17.0 heal script verbatim instead of removing its protection or changing repository visibility. The inline copies are compared through parsed YAML and exercised in a disposable git repository.

## Dependencies
None.

## Risks & Mitigation
- A genuine app-credentials regression now degrades to hosted runners instead of failing fast: the existing probe emits a visible warning, which is the runner-routing behavior already intended by #64.
- A malformed workflow could skip every gate: parse all three files locally and require green PR CI before merge.
- Release behavior could change beyond fallback: inspect the scoped diff to confirm that no `needs`, `runs-on`, output, or release condition changes.

## Trace

LOG Exit gate (ticket): full — CI/release configuration and the cross-module reusable-release consumer are critical-area anchors.
GATE e947140 tier=full lint=t typecheck=t build=t unit=t e2e=n.a
LOG Full-gate evidence: TS lint, source/test typechecks, build, and 435 tests passed; Python Ruff, wheel/sdist build, and 952 tests passed; three YAML parses, skill-mirror diff, and exact three-line scoped-diff assertion passed. E2E not applicable (no frontend change). Local setup required Poetry keyring disablement for the host's Python 3.14/keyring error; no project fix was needed.
LOG Red-fix round 1: PR #198 runs 40285584171/40285584198 passed pick-runner but failed job setup because the public repository could not resolve private betekk/betekk-gha. Replaced all three uses with exact inline v1.17.0 scripts; source-equivalence and disposable skip-worktree recovery checks passed. Re-ran the full gate: TS lint/typechecks/build/435 tests and Python Ruff/build/952 tests green; skill-mirror diff green.
GATE 432fa1f tier=full lint=t typecheck=t build=t unit=t e2e=n.a
