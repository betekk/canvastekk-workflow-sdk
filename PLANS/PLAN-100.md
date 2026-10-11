# PLAN: CI runner sweep — ubuntu-latest → 26.04 (Oct 19) + app-token

**Branch**: feat/100
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/100
**Base**: main

## Acceptance Criteria
- [ ] Every workflow file below audited (`ci-python.yml`, `ci-typescript.yml`, `release.yml`)
- [ ] Runners pinned or verified compatible with 26.04 before Oct 19, 2026
- [ ] `create-github-app-token` bumped or verified
- [ ] CI green on the first run after the change

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `.github/workflows/ci-python.yml` | `vars.GH_APP_ID` / `secrets.GH_APP_PRIVATE_KEY`, org `local` runner pool probe, GitHub-hosted `ubuntu-24.04` label | every PR/push touching `python/**` | medium |
| `.github/workflows/ci-typescript.yml` | same probe block + token | every PR/push touching `typescript/**` | medium |
| `.github/workflows/release.yml` | same probe block + token + `sdk-released` dispatch contract (MUST NOT change per #101) | release pipeline: wheel + npm publish, `peter-evans/repository-dispatch` to canvastekk-workflow-nodes | high |
| `actions/create-github-app-token@v3` (bump from v2 ×3, v1 ×1) | hosted runner on token steps; org-pool runner ≥ v2.327.1 for the `release` job site (can land self-hosted; step already `continue-on-error: true`) | `pick-runner` in all 3 files; nodes-dispatch token in `release.yml` | low–medium |

## Implementation Phases

### Phase 1: Pin runner image in ci-python.yml
- [x] **1.1** Replace every `ubuntu-latest` occurrence in `.github/workflows/ci-python.yml` with `ubuntu-24.04` — the probe job's `runs-on` (line 28), both fallback literals `labels=["ubuntu-latest"]` (lines 72, 75), and the block comment prose (line 24) so the comment stays truthful
    — **Why:** GitHub migrates the `ubuntu-latest` image to 26.04 on Oct 19; the ticket's stated safest sequencing is an explicit pin before that date, relax only after a verified green 26.04 run
    — **Done when:** `grep -c 'ubuntu-latest' .github/workflows/ci-python.yml` returns 0 and `python3 -c "import yaml;yaml.safe_load(open('.github/workflows/ci-python.yml'))"` parses clean
    — **Consumers affected:** every python-lane PR and main push (they run on the pinned image)
    — **Done:** pinned runner image: probe runs-on, both fallback labels, comment/warning prose to ubuntu-24.04; files: .github/workflows/ci-python.yml; fixes: none

### Phase 2: Pin runner image in ci-typescript.yml
- [x] **2.1** Same replacement in `.github/workflows/ci-typescript.yml` — probe job `runs-on` (line 26), fallback literals (lines 70, 73), comment prose (line 22)
    — **Why:** identical 26.04 deadline exposure in the TS lane; same pin semantics keep both CI lanes on one image
    — **Done when:** `grep -c 'ubuntu-latest' .github/workflows/ci-typescript.yml` returns 0 and the file parses via `yaml.safe_load`
    — **Consumers affected:** every typescript-lane PR and main push
    — **Done:** pinned runner image: probe runs-on, both fallback labels, comment/warning prose to ubuntu-24.04; files: .github/workflows/ci-typescript.yml; fixes: none

### Phase 3: Pin runner image in release.yml
- [x] **3.1** Same replacement in `.github/workflows/release.yml` — probe job `runs-on` (line 23), fallback literals (lines 67, 70), comment prose (line 19); no other release-lane behavior changes (the `sdk-released` dispatch contract is out of scope per #101)
    — **Why:** the release lane is the artifact publisher — an unverified 26.04 jump there risks every consumer pin; pin first per the ticket's sequencing
    — **Done when:** `grep -c 'ubuntu-latest' .github/workflows/release.yml` returns 0 and the file parses via `yaml.safe_load`
    — **Consumers affected:** release cuts (wheel + npm + nodes-repo dispatch)
    — **Done:** pinned runner image: probe runs-on, both fallback labels, comment/warning prose to ubuntu-24.04; release-lane dispatch contract untouched; files: .github/workflows/release.yml; fixes: none

### Phase 4: Bump create-github-app-token to v3
- [ ] **4.1** Bump `actions/create-github-app-token@v2` → `@v3` at the three `pick-runner` sites (ci-python.yml:37, ci-typescript.yml:35, release.yml:32) and `@v1` → `@v3` at the release.yml nodes-token (line 417); inputs (`app-id`, `private-key`, `owner`, `repositories`) and the `token` output are unchanged in v3 — no other edits
    — **Why:** ticket AC "bumped or verified"; latest major is v3.2.0. v3 breaking changes checked: custom proxy handling removed (token steps run on hosted runners — no HTTP(S)_PROXY in play) and runner ≥ v2.327.1 for self-hosted (only the `release`-job site can land on the org pool; that step is `continue-on-error: true`, so a mint failure degrades the dispatch, not the release)
    — **Done when:** `grep -rn 'create-github-app-token@v' .github/workflows/` shows only `@v3` (4 sites) and all three files still parse via `yaml.safe_load`
    — **Consumers affected:** `pick-runner` in all 3 workflows; nodes-dispatch on release cuts

### Phase 5: Full gate
- [ ] **5.1** Full gate on the final tree: `yaml.safe_load` parse of all three workflow files; invariant greps (zero `ubuntu-latest`, only `create-github-app-token@v3`); `git diff origin/main --stat` reviewed to confirm only the three workflow files changed
    — **Why:** the exit gate is the last verification before PR; there is no local workflow test-suite, so parse + invariants + diff scope are the executable checks (real CI green on the PR is the authoritative signal, enforced by the merge watcher)
    — **Done when:** all greps/parse green; diff touches exactly `.github/workflows/{ci-python,ci-typescript,release}.yml`
    — **Consumers affected:** none beyond the above

## Technical Notes
- Ticket's own sequencing adopted: pin `ubuntu-24.04` before Oct 19; relaxing back to `ubuntu-latest` requires a verified green 26.04 run and is explicitly NOT part of this ticket.
- The `local-if-idle` canonical block (probe org `local` pool → self-hosted, else hosted fallback) is preserved as-is; only the fallback image literal and probe-job image change.
- `peter-evans/repository-dispatch@v3` and all other actions are out of scope (ticket scopes runner image + app-token only).

## Dependencies
None (no `blocked-by`). Time constraint: Oct 19, 2026 migration date.

## Risks & Mitigation
- Pinned label typo / label retired → `ubuntu-24.04` is a standard GitHub-hosted label; first PR run proves it (merge watcher gates on green).
- v3 token action on org-pool self-hosted runner older than v2.327.1 → only affects release.yml nodes-token; step is `continue-on-error: true` (degrades to no dispatch, logged), and the fleet's runner pool is actively maintained (#101 epic).
- Release-lane regression → Phase 3 changes only the image strings; dispatch payload contract untouched per #101.

## Trace


GATE 78f0f43 tier=light lint=t typecheck=n.a build=n.a unit=n.a e2e=n.a

GATE 7d07b2d tier=light lint=t typecheck=n.a build=n.a unit=n.a e2e=n.a