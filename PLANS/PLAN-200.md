# PLAN: Inline CI heal step fails on fresh hosted runners

**Branch**: feat/200
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/200
**Base**: dev

## Acceptance Criteria
- [x] The TypeScript `typecheck-test-build` and Python `lint-and-test` heal steps run from `${{ github.workspace }}`, so they start on a fresh hosted runner before checkout.
- [x] Every post-checkout project step keeps its existing workflow-level working directory; no build, lint, test, or schema step moves.
- [x] Both workflow files parse as YAML, and the implementation diff adds only the two heal-step `working-directory` settings.

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `.github/workflows/ci-typescript.yml` heal step | Workflow-level `defaults.run.working-directory: typescript`; pre-checkout workspace absence | `typecheck-test-build` job; TypeScript PR/push checks | medium |
| `.github/workflows/ci-python.yml` lint/test heal step | Workflow-level `defaults.run.working-directory: python`; pre-checkout workspace absence | `lint-and-test` matrix; Python PR/push checks | medium |

## Implementation Phases

### Phase 1: Root the pre-checkout heal steps
- [x] **1.1** Add `working-directory: ${{ github.workspace }}` to the TypeScript heal step only.
    — **Why:** the inline run inherits `typescript/`, which does not exist before checkout on a fresh hosted runner, so bash cannot start.
    — **Done when:** the heal step carries the workspace-root override and every later TypeScript step is unchanged.
    — **Consumers affected:** `typecheck-test-build` gains a startable pre-checkout heal on hosted runners; no project step changes directory.
    — **Done:** rooted only the TypeScript heal step at `${{ github.workspace }}`; parsed-step comparison showed no other step change; files: `.github/workflows/ci-typescript.yml`; fixes: fresh-hosted bash startup failure
- [x] **1.2** Add `working-directory: ${{ github.workspace }}` to the Python `lint-and-test` heal step only.
    — **Why:** the same workflow-level `python/` default breaks the pre-checkout bash startup; the mirror job already overrides its default and needs no change.
    — **Done when:** the lint/test heal step carries the workspace-root override, the mirror heal stays unchanged, and every later Python step is unchanged.
    — **Consumers affected:** both `lint-and-test` matrix legs gain a startable pre-checkout heal on hosted runners; no project step changes directory.
    — **Done:** rooted only the Python lint/test heal step; mirror job left unchanged because its job default already roots it; files: `.github/workflows/ci-python.yml`; fixes: fresh-hosted bash startup failure

## Technical Notes
The old composite action did not inherit caller workflow defaults; the inline conversion does. This is the same rule the repo already records for `pick-runner`: any pre-checkout `run` block needs an explicit workspace-root `working-directory`. Local executable checks are YAML parsing plus parsed-step assertions that exactly the two affected heal steps move to the workspace root and no other `run` step changes working directory. A fresh hosted PR run remains the authoritative runtime proof.

## Dependencies
None.

## Risks & Mitigation
- A later step could accidentally inherit the override: assert through parsed YAML that only the two heal steps gain `working-directory`.
- A self-hosted-only PR run could mask the bug: keep the lockfile Dependabot queue as the runtime probe and read the heal step outcome before merging.
- YAML indentation drift: parse both files and require exactly two added lines in the scoped diff.

## Trace

LOG Exit gate (ticket): full — CI configuration change plus the fresh-hosted startup failure is a critical-area anchor.
LOG Full-gate evidence: parsed-step comparison proved exactly two heal steps gained workspace-root working-directory and no other run step moved; TS lint, source/test typechecks, build, and 435 tests passed; Python Ruff, wheel/sdist build, and 952 tests passed; skill-mirror diff passed. E2E not applicable (no frontend change).
