# PLAN-DA-3160 — [workflow-sdk] local-if-idle: convert ci-python, ci-typescript, release

Base: `origin/main` @ `2d0cd21` (sdk default branch is `main`; no dev branch — PR targets `main`).
Parent workstream A (creds seeding) lives in canvastekk-devops PR #413 → PLAN-DA-3160-seeding.md.

## Context

- **Runner state (re-verified on origin/main, supersedes the audit where main moved):** 5 jobs /
  3 workflows, all ubuntu-latest, zero local-runner usage:
  ci-python.yml (push+PR, paths `python/**`+`.agents/skills/**`, defaults wd `python/`):
  `lint-and-test` (matrix python `['3.12','3.13']` — PRESERVED per ticket),
  `schema-stability`, `skill-mirror-guard` (uses `secrets.GITHUB_TOKEN` — runtime-provided,
  runner-independent); ci-typescript.yml: `typecheck-test-build` (matrix node `['24']` — preserved);
  release.yml (push+dispatch): `release` (release-please + npm publish; already references
  `vars.GH_APP_ID`/`secrets.GH_APP_PRIVATE_KEY` at line ~356 — resolvable only after workstream A).
- **Public-repo constraint:** org-level GH creds are invisible to this repo → repo-level
  `GH_APP_ID`/`GH_APP_PRIVATE_KEY` seeded by devops tofu (workstream A, decision recorded on the
  ticket). Fork PRs never see repo secrets → the mint fails loudly (fail-closed, accepted).
- **Consumer Map (thin):** no workflow_call/reusable consumers; push-trigger classes activate at
  main merge (default branch). Poetry standard already (pip install poetry + python -m poetry).

## Acceptance Criteria (ticket) — status

- [x] ci-python.yml: matrix job + schema-stability + remaining jobs converted; 3.12+3.13 matrix preserved
- [x] ci-typescript.yml and release.yml converted
- [x] Canonical block used verbatim (retry probe + pick timeout-minutes: 5 + provenance comment)
- [ ] Green run (evidence: run URL) — **gated on workstream A apply** (below)

## Steps

### Phase 1 — conversion (workstream B)

- [x] **1.1** 3 files: canonical pick-runner block inserted + all 5 jobs wired
  `needs: [pick-runner]` + `runs-on: fromJSON(...)`; matrices, triggers, paths, defaults,
  steps byte-preserved

### Phase 2 — static gate

- [x] **2.1** yaml parse ×3, canonical fidelity md5 ×3, routing assertions (5 workers),
  matrix assertions (py 3.12+3.13, node 24)

### Phase 3 — evidence (sequencing-gated)

- [ ] **3.1** PR run (pull_request, same-repo → repo secrets visible) = the evidence: mint works
  post-seeding, workers land on pool runners. PR creation deliberately AWAITS workstream A's
  apply (repo-level creds must exist when the pick gate mints).

### Phase 4 — review + PR + merge + JIRA

- [ ] **4.1** Code review (arch review SKIPPED — thin consumer map, pattern proven in 6 repos)
- [ ] **4.2** PR → `main` (`Closes DA-3160`, gate memo cited) → green PR run → Mode-R comment →
  merge → post-merge push run (main push) as second evidence → cleanup → JIRA comments + Done
- [ ] **4.3** Workstream A reference: devops PR #413 (merged SHA recorded in the gate line)

## Gate Trace

_(appended per phase; final `GATE <short-sha> tier=full` line is the 4.2 citation)_

- Workstream A (seeding) RESOLVED: devops PR #413 merged `6d0078b9`; first apply failed —
  **409 Already exists**: repo-level `GH_APP_ID`/`GH_APP_PRIVATE_KEY` pre-existed as MANUAL
  artifacts (early preflight), tofu cannot create over them. Triage: deleted the manual pair +
  the stale unused `GH_APP_CLIENT_ID` variant (DA-3169 dead-config lesson); re-apply
  [36380063155](https://github.com/nus-cee/canvastekk-devops/actions/runs/36380063155) GREEN —
  tofu-managed creds verified present. (`GH_PAT` secret also present, zero workflow usage —
  predates the ticket, left alone, flagged for a future audit.)
- Phases 1–2 gate tier=full: 3/3 parse, 3/3 fidelity md5 bc1c3a4d, 5 workers routed,
  matrices preserved (py 3.12+3.13, node 24), triggers/paths/defaults byte-preserved.
  WORK LOG fix attempts: 0 (conversion) / 1 (workstream A manual-credential conflict).
