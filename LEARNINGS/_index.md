# LEARNINGS Index — canvastekk-workflow-sdk

## solutions
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
