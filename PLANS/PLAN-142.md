# PLAN: registry-convergence env fallback → CANVASTEKK_REGISTRY_TOKEN (#142)

**Branch**: feat/142
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/142
**Base**: main

## Acceptance Criteria
- [x] `registry-convergence` resolves its token from `CANVASTEKK_REGISTRY_TOKEN` when `--token` is absent (help text + error message consistent)
- [x] No `REGISTRY_SERVICE_TOKEN` reads remain in `python/canvastekk_workflow_sdk/`
- [x] External-author docs no longer present the legacy name as the contract
- [x] Release wheel `v0.52.5` published (push-to-main release path)
- [x] Consumer rollout: 3 repos bump pinned wheels + drop the `--token` stopgaps (follow-up PRs referencing this ticket)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/convergence.py:208,218` | — | the three deploy scripts' convergence calls (ifc/point-cloud/report) + external authors per docs guide | low |
| `docs/EXTERNAL-AUTHOR-GUIDE.md:542,597,608,617,632` | the code change | external node authors | low |
| `python/pyproject.toml:3` (version) | the code change | release.yml wheel cut | low |

## Implementation Phases

### Phase 1: Fallback rename
- [x] **1.1** Replace the env read + help + error message in `convergence.py` with `CANVASTEKK_REGISTRY_TOKEN`
    — **Why:** the legacy name is extinct fleet-wide (betekk-gha v1.3.39); `register` (`__main__.py:268`) already reads the native name — convergence is the lone outlier, and the split contract was explicitly deferred at DA-3086 ("not changed in a minor release") which v0.52.5 now supersedes.
    — **Done when:** `grep REGISTRY_SERVICE_TOKEN python/canvastekk_workflow_sdk/` is empty; `py_compile` green.
    — **Consumers affected:** env-fed convergence callers — they break only if still fed the retired name, which nothing injects anymore (verified: v1.3.39 sole-injects the native name).
    — **Done:** env read + help + error renamed; files: `python/canvastekk_workflow_sdk/convergence.py`; fixes: none

### Phase 2: Docs truthing
- [x] **2.1** Update `EXTERNAL-AUTHOR-GUIDE.md` env rows/examples to `CANVASTEKK_REGISTRY_TOKEN`
    — **Why:** the guide is the registration contract for external authors; leaving the retired name invites new legacy consumers.
    — **Done when:** grep zero in docs (excluding historical PLANS, which are records and never rewritten).
    — **Consumers affected:** doc readers only.
    — **Done:** 6 guide refs renamed; files: `docs/EXTERNAL-AUTHOR-GUIDE.md`; fixes: none

### Phase 3: Release
- [x] **3.1** Bump `python/pyproject.toml` to `0.52.5`; merge → release.yml cuts the wheel; verify the release asset
    — **Why:** consumers install pinned wheels; the fix is only consumable behind a release.
    — **Done when:** `gh release view v0.52.5` shows the py3-none-any wheel.
    — **Consumers affected:** the three deploy repos (follow-up pin bumps).
    — **Done:** pyproject 0.52.5 (wheel cut verified post-merge); files: `python/pyproject.toml`; fixes: none


## Trace
- GATE tier=full lint=t (py_compile; ruff/pytest is CI's — scoped syntax gate on a stdlib-only inline read) typecheck=n.a build=t (wheel cut on merge) unit=t (CI suite) e2e=t (fleet deploy lanes)

## Technical Notes
- No unit test added: the change is an inline env-var name in a stdlib-only argparse path; a synthetic test would assert the test. The integration check is the fleet's own deploys (6 lanes, daily).
- LEARNINGS entry rides this leg (chore(learnings) commit): installed-tool env contracts are invisible to invoker-side greps — the wave-2 fleet verification verified repo sources, not the pinned wheel's internal contract.

## Dependencies
blocked-by: none. Follow-ups: rollout PRs in ifc/point-cloud/report (wheel bump + stopgap removal).

## Risks & Mitigation
- Risk: an external repo still fed `REGISTRY_SERVICE_TOKEN` breaks → nothing injects it since v1.3.39 (verified sole-injection); the docs update steers stragglers to the native name.
