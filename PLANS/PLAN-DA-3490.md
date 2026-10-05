# PLAN: DA-3490 — workflow-sdk package namespace migration (nus-cee → betekk)

**Branch**: feat/DA-3490
**Issue**: https://betekk.atlassian.net/browse/DA-3490
**Base**: main (the repo's only long-lived branch — no dev exists; origin/dev base impossible here)

## Acceptance Criteria

- [ ] No `nus-cee` reference remains in live files (workflows, sources, docs, shipped package data; PLANS history excluded)
- [ ] npm package identity flipped: `typescript/package.json` + lockfile root → `@betekk/canvastekk-workflow-sdk` (names MUST match or `npm ci` fails)
- [ ] PyPI publish index flipped: `pyproject.toml` tool URL + release.yml twine flags → `pypi.pkg.github.com/betekk/`
- [ ] The PR's own live checks green (ci-python + ci-typescript exercise the fixed probe blocks)

## Dependency & Consumer Map

| Node (file/module) | Depends on | Consumers | Change risk |
|---------------------|------------|-----------|-------------|
| `typescript/package.json` + `package-lock.json` (name) | — | **every npm consumer** (workflow-nodes first; installs must flip to `@betekk/…` after the next publish) | **high** — package identity move |
| `.github/workflows/release.yml` (publish/smoke/dispatch) | package.json name | the release pipeline; `canvastekk-workflow-nodes` dispatch target | med |
| `python/pyproject.toml` (repo/homepage/publish URL) | — | PyPI consumers (unscoped name; index URL change) | med |
| `python/canvastekk_workflow_sdk/data/…` (shipped SKILL.md/AGENTS.md) | — | files ship INSIDE the wheel consumers receive | med |
| `python/tests/test_bump_versions.py` (fixture) | — | the test suite | low |
| READMEs / docs / cliff.toml / src comments | — | humans, changelog links | low |

## Implementation Phases

### Phase 1: the namespace flip

- [x] **1.1** Flip every live `nus-cee` reference to `betekk` (18 files): publish targets, package identities, install docs, shipped data, test fixture, changelog owner, probe blocks
    — **Why:** the org rename killed the `nus-cee` login; the package namespace moved with the org and publishes/installs must follow. Dual-publish is impossible (the old scope no longer exists), so this is a clean cutover
    — **Done when:** grep is empty; lockfile name matches package.json; the PR's checks green
    — **Consumers affected:** every `@nus-cee/canvastekk-workflow-sdk` / old-index pip consumer — coordinated consumer flip is DA-3500 (workflow-nodes), external consumers get the release-notes notice

### Phase 2: exit gate

- [ ] **2.1** Gate: the PR's own live checks (CI runs the fixed workflows from the head) — memo appended
    — **Why:** CI-only-plus-identity change; the live run is the honest verification (release smoke tests verify at the NEXT release)
    — **Done when:** checks green; memo appended
    — **Consumers affected:** PR citation

## Gate memo trace

(pending)

## Technical Notes

- Release history: releases succeeded Oct 1–2 with the old scope (rename landed after, or GitHub served the old scope) — consumers are not provably on fire, but the dead login makes the move mandatory.
- Sequencing contract: **DA-3490 merge → next release publishes `@betekk/…` (smoke tests in release.yml verify) → DA-3500 flips workflow-nodes installs.** Consumers cannot flip before the first `@betekk` publish exists.
- Version guidance: continue the 0.x sequence (0.37.3 → 0.38.0); the move is consumer-breaking but the API is unchanged — release notes carry the migration line.
- `python/tests/test_bump_versions.py` fixture flipped WITH pyproject (they reference each other).
