# PLAN: Migrate pyproject.toml to PEP 621 [project] tables

**Branch**: feat/105
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/105
**Base**: main

## Acceptance Criteria
- [ ] `poetry check` exits 0 with **zero** deprecation warnings
- [ ] `poetry build` produces a wheel whose METADATA carries identical Requires-Dist / Provides-Extra entries as v0.41.0's wheel (diff the two METADATA files)
- [ ] `pip install dist/*.whl[jwt,keycloak,serve]` resolves all three extras in a fresh venv
- [ ] `poetry lock` + `poetry install --with dev` + full pytest suite green
- [ ] `scripts/bump_versions.py` still finds and bumps the version (leaf moved to `[project.version]`)
- [ ] `poetry.lock` updated if the migration shifts the content-hash; else verified unchanged (hash-only delta allowed)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/pyproject.toml` | — | `python/poetry.lock` (content-hash), `scripts/bump_versions.py` (.toml regex), CI python jobs, release workflow, wheel consumers | medium |
| `python/poetry.lock` | `python/pyproject.toml` | CI reproducibility, `poetry install` | low |
| `scripts/bump_versions.py` | `python/pyproject.toml` (leaf location) | release workflow (auto-bump on main pushes) | medium |
| `python/poetry.lock` build artifacts | baseline wheel (step 1.1) | METADATA equivalence check | low |

Cross-module note: consumers are the release toolchain, not in-repo modules — zero reviewer selection justified; Step 9 code review backstops.

## Implementation Phases

### Phase 1: PEP 621 migration with equivalence proof
- [ ] **1.1** Build the baseline wheel from HEAD (v0.41.0) and save its METADATA to `/tmp/opencode/wheel-baseline/` before any edit
    — **Why:** the equivalence check needs the pre-migration artifact; building after the rewrite would have nothing to diff against
    — **Done when:** `/tmp/opencode/wheel-baseline/METADATA` exists with `Version: 0.41.0`
    — **Consumers affected:** none (artifact is scratch)
- [ ] **1.2** Rewrite `python/pyproject.toml`: add `[project]` with static metadata (name, version, description, readme, license, authors, requires-python, urls) + `dynamic = ["dependencies", "optional-dependencies"]`; keep `[tool.poetry.dependencies]` (caret constraints) and `[tool.poetry.extras]` as the dynamic sources; keep `packages`/`include` in `[tool.poetry]`; bump `[build-system]` to `poetry-core>=2.0`
    — **Why:** the hybrid is Poetry 2.x's supported layout — static metadata silences all 11 deprecation warnings while caret constraints and the resolved lock stay intact; a full PEP 508 rewrite would churn the lock for zero benefit
    — **Done when:** `poetry check` prints no "is deprecated" lines; file carries `[project]` with `dynamic` listing both dependency keys
    — **Consumers affected:** `scripts/bump_versions.py` (leaf moved from `[tool.poetry]` to `[project]` — step 1.5)
- [ ] **1.3** Refresh the lockfile if needed: run `poetry lock`, then `poetry install --with dev`
    — **Why:** the lock's `content-hash` covers the dependency config; the metadata move may or may not shift it — the lock must end consistent with `pyproject.toml` either way
    — **Done when:** `poetry check --lock` passes; `git diff python/poetry.lock` shows no dependency-line changes (content-hash-only delta allowed and committed if present)
    — **Consumers affected:** CI reproducibility
- [ ] **1.4** Rebuild the wheel and diff METADATA against the baseline: Requires-Dist and Provides-Extra lines must be byte-identical
    — **Why:** the AC's equivalence proof — config shape must not change what pip consumes (per the release-bump learning: verify the artifact, never trust config shape)
    — **Done when:** `diff` of the two METADATA files shows no Requires-Dist/Provides-Extra deltas
    — **Consumers affected:** wheel consumers
- [ ] **1.5** Widen `scripts/bump_versions.py`'s `.toml` regex to anchor on `[project]` as well as `[tool.poetry]`, then verify live: run `python3 scripts/bump_versions.py 9.9.9`, assert both manifests + the python leaf report `BUMPED` with 9.9.9, then `git checkout --` the bumped files
    — **Why:** the primary regex is anchored to `[tool.poetry]`; after the move it would miss and fall through to first-match — the DA-3425 class of mis-stamped releases; widening and verifying in the same change is the learning's rule
    — **Done when:** script output shows `BUMPED` for python/typescript leaves with 9.9.9; files reverted to 0.41.0 afterwards (`git status` clean of version bumps)
    — **Consumers affected:** release workflow
- [ ] **1.6** Gate Phase 1: `poetry check` (zero warnings), `ruff check .`, `pytest` (green)
    — **Why:** proves the migration is behavior-neutral for the package and its suite
    — **Done when:** all three exit 0; check output contains zero "deprecated" lines
    — **Consumers affected:** none beyond repo gates

## Technical Notes
- Hybrid layout kept: `[project]` static metadata + `dynamic = ["dependencies", "optional-dependencies"]`; `[tool.poetry.dependencies]` remains the constraint source (caret semantics preserved, lock stable).
- The `.toml` bump regex change is code-shaped: ruff runs on `scripts/` via `ruff check .` — keep the line within 120 cols.
- Wheel METADATA diff scope: Requires-Dist + Provides-Extra only (Version differs only if the bump script test is not reverted).

## Dependencies
None — no `blocked-by` tickets.

## Risks & Mitigation
- **Poetry rejects `dynamic` + present `[tool.poetry.dependencies]` combination**: fallback is the full PEP 508 rewrite (dependencies as ranged strings, extras in `[project.optional-dependencies]`) — METADATA diff still guards equivalence; lock refresh via `poetry lock`.
- **Bump script fallback regex hits the wrong line**: mitigated by widening the primary regex (1.5) and the live 9.9.9 verification.
- **Wheel content-hash churn**: none expected — dependencies unchanged; lock diff asserted hash-only (1.3).

## Trace
<!-- gate memos append here -->
