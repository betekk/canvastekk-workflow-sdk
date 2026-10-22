# LEARNINGS Index — canvastekk-workflow-sdk

## solutions
- [additive-field-crosses-extra-forbid-rides-freeform-dict](solutions/additive-field-crosses-extra-forbid-rides-freeform-dict.md) — ship manifest-field top-level, cross the wire inside constraints; the receiver promotes it in its own widening
- [verify-reindent-with-git-diff-w](solutions/verify-reindent-with-git-diff-w.md) — collapse reindent-heavy diffs to the semantic delta before reviewing
- [tsup-dts-node-prefix-builtin-import-fails](solutions/tsup-dts-node-prefix-builtin-import-fails.md) — dts pass rejects `node:async_hooks` named imports while `node:fs` works; use the bare builtin name
- [gate-memo-sha-amend-orphan](solutions/gate-memo-sha-amend-orphan.md) — never amend the commit carrying its own GATE memo sha; cite the real ancestor and fold the memo forward
- [rebase-branch-arg-switches-worktree](solutions/rebase-branch-arg-switches-worktree.md) — DA-3340: `git rebase <upstream> <branch>` checks `<branch>` out in the CURRENT worktree; rebase inside the branch's worktree or switch back before `git worktree add`

## patterns
- [manifest-field-three-producer-rule](patterns/manifest-field-three-producer-rule.md) — a WorkflowNodeManifest field lives in three producers: registry payload (omit), /manifest dump (always), export re-add block (re-add or overrides drop)
- [derived-bound-as-plain-property](patterns/derived-bound-as-plain-property.md) — derived bounds are plain @property, never @computed_field; the wire carries only declared inputs
- [finally-side-defensive-helper](patterns/finally-side-defensive-helper.md) — finally-called helpers must be exception-proof by construction
- [ambient-run-context-als-contextvars](patterns/ambient-run-context-als-contextvars.md) — per-run state on stateless nodes via AsyncLocalStorage/contextvars; store absence = no-op signal

## decisions
- [x-api-key-slot-token-semantics](decisions/x-api-key-slot-token-semantics.md) — #3825: keep the X-API-Key wire slot, swap semantics to engine-minted run tokens; dual-accept default makes retirement env removal, not code change
- [heap-trim-in-finally-not-background-task](decisions/heap-trim-in-finally-not-background-task.md) — DA-3009 trim placement: synchronous finally over BackgroundTask (Lambda freeze semantics)
- [wire-parse-tolerance-loud-seam-on-legacy-removal](decisions/wire-parse-tolerance-loud-seam-on-legacy-removal.md) — DA-3340: parse boundaries stay tolerant when a wire union member is removed; the domain seam raises the fail-loud error (companion to parity-port-must-widen-wire-schema)
- [fixed-tmp-paths-on-shared-runner-pool](anti-patterns/fixed-tmp-paths-on-shared-runner-pool.md) — DA-3160: literal /tmp paths collide cross-run on persistent pool boxes; swap to $RUNNER_TEMP/mktemp before routing
- [pick-gate-working-directory-override](solutions/pick-gate-working-directory-override.md) — DA-3160: workflow-level run defaults break the no-checkout pick gate; job-scoped cwd override, block untouched
- [parity-port-must-widen-wire-schema](anti-patterns/parity-port-must-widen-wire-schema.md) — DA-3314: porting a protocol widening must widen the inbound parse schema (request.ts) not just the handler; descriptors died at safeParse 400 before the uploader ran
- [parity-plans-cite-reference-constants](conventions/parity-plans-cite-reference-constants.md) — parity plans quote reference constants with file:line (backoffs/timeouts/retry rules); every deliberate divergence gets a "diverges because" note
- [tightened-gate-updates-its-equivalence-claim](conventions/tightened-gate-updates-its-equivalence-claim.md) — a gate stricter than its authority must rename its ⇔ claim and list the new probe in the same commit
- [host-only-manifest-fields-payload-exclusion](conventions/host-only-manifest-fields-payload-exclusion.md) — host-only manifest fields never enter build_registry_payload; pin each with a negative TestBuildRegistryPayload test (DA-1955)
- [ts-method-syntax-bivariance-additive-widening](patterns/ts-method-syntax-bivariance-additive-widening.md)
- [widened-wire-field-needs-producer-wiring](anti-patterns/widened-wire-field-needs-producer-wiring.md) — a propagation fix needs a producer threading the field to the seam; env-var transport beside a JSON payload is the tell
- [validator-loop-must-cover-new-slug-fields](anti-patterns/validator-loop-must-cover-new-slug-fields.md) — extend _reject_dot_segments' tuple (None-guarded) in the same change as any new slug field, mirrored in a python test
- [version-stamp-tests-import-version-constant](conventions/version-stamp-tests-import-version-constant.md) — stamped sdk_version assertions use toBe(VERSION), never literals; ctor-arg strings exempt — method-syntax interface members keep parameter widening additive for implementors (bivariance); property-arrow breaks them; pin with tsconfig.tests type-fixture
- [pipe-swallows-gate-exit-code](anti-patterns/pipe-swallows-gate-exit-code.md) — `gate | tail && merge` checks tail's exit (always 0); a red CI merged to main (DA-3314 #86). Run gates bare or capture $?
- [release-bump-script-misses-new-version-leaf](anti-patterns/release-bump-script-misses-new-version-leaf.md) — DA-3425: adding a version-source file without widening the bump script's VERSION_FILES ships mis-stamped wheels (0.37.1 stamped 0.37.0); verify by unzipping the wheel, never trust METADATA
- [wall-clock-deadline-assertions-need-both-brackets](patterns/wall-clock-deadline-assertions-need-both-brackets.md) — one-sided clock brackets flake in one direction (producer ticks past the outer capture); bracket both ends or freeze time (#3515)
- [npm-install-wont-bump-locked-transitives](solutions/npm-install-wont-bump-locked-transitives.md) — `npm install` preserves locked in-range transitives; in-range advisory fixes need `npm update <pkg>` (#102)
- [template-runtime-binary-from-transitive-dep](anti-patterns/template-runtime-binary-from-transitive-dep.md) — templates that exec a binary (uvicorn CMD) must declare it where consumed, never ride a transitive (#102)
- [fastapi-0143-nested-routes-openapi-introspection](solutions/fastapi-0143-nested-routes-openapi-introspection.md) — fastapi ≥0.143 nests `app.routes` under `_IncludedRouter`; assert routes via `app.openapi()["paths"]` (#102)
- [file-wide-checkout-revert-wipes-phase-work](anti-patterns/file-wide-checkout-revert-wipes-phase-work.md) — scripted-edit verification in a tree with uncommitted phase work: revert the touched line, never `git checkout -- <file>` (#105)
- [pep562-lazy-imports-globals-and-hint-resolution](solutions/pep562-lazy-imports-globals-and-hint-resolution.md) — module `__getattr__` never serves internal global lookups; string annotations resolve against `__globals__` — inject lazy names via `globals().update` (#104)
- [pipeline-run-order-rebuilt-from-stale-summary-after-restart](anti-patterns/pipeline-run-order-rebuilt-from-stale-summary-after-restart.md) — after a harness restart, re-fetch ticket bodies before claiming the next lane; summary tables go stale (#112/#113)
- [cleanup-runs-before-red-verdict-is-read](anti-patterns/cleanup-runs-before-red-verdict-is-read.md) — cleanup is a MERGED-verdict action; read the watch verdict before any worktree/branch deletion (CRS#110 scene wipe, saved by refs/pull/N/head)
- [selfhosted-exit127-toolcache-triage](patterns/selfhosted-exit127-toolcache-triage.md) — exit 127 loading libpythonX.so on self-hosted = corrupted setup-python toolcache; ops purge fixes it, reruns are a lottery
- [local-red-ci-green-means-env-drift](patterns/local-red-ci-green-means-env-drift.md) — CI-green/local-red divergence is env drift until proven otherwise; diff installed pins vs lock before recording baseline failures (engine minimum_sdk_version/#123)
- [registry-wheel-pin-triple](conventions/registry-wheel-pin-triple.md) — SDK wheel bumps move script + pyproject + poetry.lock together; CASA's drift test enforces it
- [blanket-version-string-replace-corrupts-urls](anti-patterns/blanket-version-string-replace-corrupts-urls.md) — s|vX|vY| on pinned wheel URLs leaves the bare filename behind; full-URL replaces only, verify tag/filename agreement
- [installed-tool-env-contracts-invisible-to-invoker-greps](anti-patterns/installed-tool-env-contracts-invisible-to-invoker-greps.md) — invoker greps prove callers, not the pinned tool; sweep the dependency source before cutting the release that retires a name (ifc run 38508424993/#142)
- [shipped-docs-must-verify-cli-surface](anti-patterns/shipped-docs-must-verify-cli-surface.md) — grep the dispatch surface before shipping any CLI snippet in skills/docs; export_definition is a function, not a subcommand (#144)
- [git-add-all-sweeps-worktree-artifacts](anti-patterns/git-add-all-sweeps-worktree-artifacts.md) — stage explicit paths per phase commit; sessions drop .opencode/ and typo files (e.g. a file named =0) that -A commits (#144)
- [full-pytest-needs-fastapi-extra](conventions/full-pytest-needs-fastapi-extra.md) — fresh venv: poetry install -E fastapi (ci-python.yml:106) before pytest; fastapi collection errors are environmental (#144)

## anti-patterns
- [mirror-schema-shape-fix-input-output-sides](anti-patterns/mirror-schema-shape-fix-input-output-sides.md) — an S.1-class shape rule fixed inputs-only leaves outputs blind; array-mode node passed with zero uploads, downstream 404 (#3971 follow-up)
- [public-repo-cannot-call-private-reusable](anti-patterns/public-repo-cannot-call-private-reusable.md) — public repo + private reusable = "workflow was not found" at any ref; check .private on both sides FIRST; same-repo vendored copy is the escape hatch
- [workflow-call-outputs-need-workflow-level-reexport](anti-patterns/workflow-call-outputs-need-workflow-level-reexport.md) — chained jobs on reusable outputs silently no-op unless the reusable re-exports them under workflow_call.outputs (fixed betekk-gha v1.7.2)
- [urllib-httpexception-escapes-urlerror-catch](anti-patterns/urllib-httpexception-escapes-urlerror-catch.md) — http.client.HTTPException escapes a URLError-only catch as an unhandled 500; add it to any fail-closed urllib guard

## solutions
- [gh-token-env-with-persist-credentials-false](solutions/gh-token-env-with-persist-credentials-false.md) — gh CLI 401s after persist-credentials:false checkouts; every gh step needs explicit GH_TOKEN env
