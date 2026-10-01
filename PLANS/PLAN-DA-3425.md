# PLAN: sdk — bump script stamps _version.py leaf; release 0.37.2

**Branch**: feat/DA-3425
**Issue**: https://betekk.atlassian.net/browse/DA-3425
**Base**: main

## Acceptance Criteria

- [ ] `scripts/bump_versions.py` bumps `python/canvastekk_workflow_sdk/_version.py` (`__version__`) and stamps `RELEASE_DATE` (optional 2nd arg, default today UTC)
- [ ] Test covers the new stamping behavior (pytest, `python/tests/`)
- [ ] PR merged to main; on-push Release workflow publishes v0.37.2
- [ ] v0.37.2 wheel's internal `_version.py.__version__ == 0.37.2` (verified by unzipping the released asset)
- [ ] v0.37.2 tgz `package.json` version == 0.37.2
- [ ] Re-target comments posted on DA-3419..DA-3424 (0.37.1 → 0.37.2)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|--------------------|---------------------------|---------------------------------|-------------|
| `scripts/bump_versions.py` VERSION_FILES + RELEASE_DATE stamp | — | `.github/workflows/release.yml` step `python3 scripts/bump_versions.py "${NEW_VERSION}"`; every future SDK release | med — release tooling; wrong stamp poisons every consumer's manifest stamp |
| `python/tests/test_bump_versions.py` (new) | script change | CI ci-python pytest job | low |
| (downstream) v0.37.2 wheel assets | release run | DA-3419..DA-3424 pins (py legs); engine/node manifest stamps | low once stamp verified |

No runtime SDK code changes — `__init__.py` already re-exports the leaf (`from ._version import __version__`), single source of truth confirmed.

## Implementation Phases

### Phase 1: bump-script fix + test

- [ ] **1.1** Add `python_version_leaf` (`python/canvastekk_workflow_sdk/_version.py`) to `VERSION_FILES`; accept optional release-date arg (default today UTC) and stamp `RELEASE_DATE` alongside `__version__` in `.py` bumps
    — **Why:** the leaf is the DA-3359 stamp source of truth; missing it shipped a 0.37.1 wheel stamping 0.37.0 — the root cause of this ticket
    — **Done when:** running the script against a fixture tree sets both `__version__ = "<v>"` and `RELEASE_DATE = "<date>"` in the leaf
    — **Consumers affected:** release.yml bump step; every future SDK release
- [ ] **1.2** Add `python/tests/test_bump_versions.py` — subprocess-run the script in a `tmp_path` fixture tree (leaf `_version.py`, pyproject, package.json, version.ts), assert all stamps including `RELEASE_DATE`
    — **Why:** 4b test mandate for changed logic; the script had zero coverage, which is how this defect shipped
    — **Done when:** pytest green; test fails if the leaf entry is removed from VERSION_FILES (mutation check)
    — **Consumers affected:** CI ci-python pytest job
- [ ] **1.3** Run the gate (full tier — release tooling is a critical area): ruff + full pytest in `python/`
    — **Why:** release-tooling change feeding every consumer's stamp; exit gate for the ticket
    — **Done when:** `poetry run ruff check` + `poetry run pytest` exit 0; `tier=full` memo recorded
    — **Consumers affected:** CI on the PR

### Phase 2: release + verify + re-target

- [ ] **2.1** PR to main (patch label), merge via green-checks watcher; on-push Release workflow cuts v0.37.2 (git-cliff `fix:` → patch)
    — **Why:** 0.37.1 assets are already published; replacing them would poison caches — a clean patch release is the only correct path
    — **Done when:** release v0.37.2 exists with wheel + tgz assets
    — **Consumers affected:** all six fleet tickets
- [ ] **2.2** Verify assets: unzip the v0.37.2 wheel → `_version.py` `__version__ == "0.37.2"` and `RELEASE_DATE == <release day>`; untgz → `package.json` `version == "0.37.2"`; post re-target comments on DA-3419..DA-3424
    — **Why:** the whole point — prove the stamp before any consumer pins it
    — **Done when:** assertions printed and comments posted
    — **Consumers affected:** DA-3419..DA-3424 bodies (0.37.1 → 0.37.2)

## Technical Notes

- `__init__.py` no longer defines `__version__` (re-export from leaf since DA-3359) — the existing `python_init` entry warns "Could not find pattern" and `main()` tolerates it (no exit-code failure). Leave it or drop it; do NOT let it fail.
- `release.yml` computes `NEW_VERSION` via git-cliff from conventional commits — the fix commit must be `fix:` typed to yield a patch bump (0.37.1 → 0.37.2).
- Wheel built with `python -m poetry build` in `python/`; tgz via `npm pack` — the script stamps sources before builds.

## Dependencies

- Blocks DA-3419, DA-3420, DA-3421 (py leg), DA-3422, DA-3423, DA-3424.

## Risks & Mitigation

- Risk: git-cliff computes minor/major instead of patch. Mitigation: commit strictly `fix(scripts): ...`; verify the release tag before consumers pin; cliff.toml already shipped 0.35.2 as a fix release (precedent).
- Risk: RELEASE_DATE regex drift if the leaf's docstring mentions the literal. Mitigation: `count=1` substitution on the assignment line pattern only; test asserts exact file contents.
