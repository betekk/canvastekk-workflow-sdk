# PLAN: Docs sweep — single-lane release procedure everywhere

**Branch**: feat/263
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/263
**Base**: dev

## Acceptance Criteria

- [ ] `grep -rn "prod" README.md AGENTS.md docs/` shows no release-lane references (node-environment `production` mentions are unrelated and stay)
- [ ] Release procedure documented with a worked example
- [ ] #252's AC updated to single-lane; comment posted there referencing this epic

**Revalidation findings (Step 5):** prose is already lane-clean except README:694-696 `## Versioning` — stale on two counts ("merged to `main`" — wrong branch since the #3857 rename; "on conventional commits" — bump size comes from PR semver labels, commits feed the changelog body only). Three workflow dead-vocabulary strings routed from #261/#262 reviews (`reusable-release.yml:11,:113,:197`). No repo AGENTS.md exists (dispatch-contract docs live in other repos).

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `README.md` `## Versioning` | — | all engineers cutting releases; external readers | low — docs |
| `.github/workflows/reusable-release.yml` (3 string edits: input description, dead case line, beta message) | — | `release.yml` caller (strings only — zero behavioral change: a YAML description field, an unreachable case-arm, a dead-channel message) | medium file, negligible delta |
| issue #252 body + comment | #261 merged (mechanism to point at) | future betekk-gha migration picker-upper | low — tracker state |

No structural/code change; no cross-module behavior → zero reviewers selected at Step 7; the requirements gate's zero-reviewer rule applies.

## Implementation Phases

### Phase 1: README — release procedure, worked example, fail-closed
- [ ] **1.1** Rewrite `README.md` `## Versioning` (694-696): shared PEP 440 counter; five tag-derived version sources stamped at release time; **cutting a release** worked example (branch `release/vX.Y.Z` off `origin/dev`, one `chore(release): vX.Y.Z` commit — GitHub needs a diff, labels `release` + one semver label, merge ⇒ tag + changelog + GitHub Release + wheel/tgz publish + `sdk-released` dispatch); **fail-closed** semantics (intent = merged-PR label lookup; failure or PR-less push ⇒ no release; direct pushes can never release; a missed release is a retry, an accidental one is an incident); changelog body = git-cliff over conventional commits
    — **Why:** The only release-documentation surface in-repo is factually wrong (names a dead branch and a dead mechanism); every future release-cutter reads it first.
    — **Done when:** Section renders the full procedure; no mention of `main`/`prod` as release branches; worked example names every label.
    — **Consumers affected:** engineers; external SDK consumers pinning versions.
- [ ] **1.2** Add the `release` label's meaning to the label vocabulary a reader meets (one line in the procedure: `release` = trigger label, semver label = bump size)
    — **Why:** The two-label contract is the procedure's core invariant; burying it invites a `release`-labeled PR without a semver label (which silently defaults to patch).
    — **Done when:** Both labels' roles stated in the same code block as the example.
    — **Consumers affected:** release cutters; reviewers applying labels.

### Phase 2: workflow dead-vocabulary sweep
- [ ] **2.1** `reusable-release.yml:11` input description "prod changelog" → "release changelog"; `:113` delete the dead `prod) SUFFIX=""` case arm; `:197` beta message "next prod release" → "next final release"
    — **Why:** The three routed findings; vocabulary must not outlive the lanes.
    — **Done when:** `grep -n "prod" .github/workflows/*.yml | grep -v production` returns nothing; actionlint green.
    — **Consumers affected:** `release.yml` caller (strings only, zero behavior).

### Phase 3: #252 re-scope
- [ ] **3.1** Edit #252's body: acceptance criterion "…honoring the two-lane tag standard (dev `vX.Y.Z-dev.N`, prod finals)" → "…honoring the single-lane release-PR standard (`release` + semver labels on a PR merged to `dev`; fail-closed label lookup per #261)" — fetch body, replace that criterion, write back (body edits REPLACE, never blindly append); post a comment referencing epic #260, the live mechanism (#261, merged), and this re-scope
    — **Why:** Epic decision (user-confirmed): #252 stays open for the betekk-gha migration but must not re-introduce two-lane semantics; an un-re-scoped AC is a trap for whoever picks it up.
    — **Done when:** `gh issue view 252` shows the single-lane AC; comment posted.
    — **Consumers affected:** #252 assignee; fleet epic tracker#4228.

### Phase 4: verification
- [ ] **4.1** AC grep: `grep -rn "prod" README.md docs/ .github/workflows/ | grep -v production` → empty; README worked example present (label names greppable)
    — **Why:** AC-1 + AC-2 sign-off.
    — **Done when:** Zero hits; example labels found.
    — **Consumers affected:** AC sign-off.
- [ ] **4.2** Exit gate (full tier — workflow file touched): actionlint ×4, tsc ×2, tsup, poetry build, pytest, vitest; e2e n.a (no frontend)
    — **Why:** CI-file anchor regardless of string-only delta; the memo must be push-authorizing.
    — **Done when:** Green ladder; memo appended to Trace.
    — **Consumers affected:** Step 10a citation.

## Technical Notes

- The README procedure's invariant phrasing mirrors the LEARNINGS entry `release-intent-fails-closed-on-label-lookup.md` — same words, one truth.
- `docs/NODE-TOKEN-CONTRACT.md:102` "dev → uat → prod" is token-cutover environment vocabulary — unrelated, stays.
- README:454 `uat/prod` (breaking-change registration note) is node-environment vocabulary — stays.
- No repo AGENTS.md exists; dispatch-contract references live in betekk-skills and the engine repo (out of scope here, noted for #252's migration).

## Dependencies

- blocked-by: #261 — MERGED (f5322f1; mechanism live and proven).
- Sibling: #262 MERGED (c98c115) — lanes already gone; this sweep completes the vocabulary.

## Risks & Mitigation

- **A future release-cutter follows old habits** → worked example is copy-pasteable; fail-closed backstops any mistake (worst case: no release, retry).
- **#252 body edit overwrites concurrent edits** → fetch immediately before write; single-criterion replace, not a rewrite.
- **Workflow string edits regress CI** → actionlint + full ladder in 4.2; strings are inert fields.
