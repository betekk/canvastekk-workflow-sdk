# LEARNINGS Index — canvastekk-workflow-sdk

## solutions
- [verify-reindent-with-git-diff-w](solutions/verify-reindent-with-git-diff-w.md) — collapse reindent-heavy diffs to the semantic delta before reviewing
- [tsup-dts-node-prefix-builtin-import-fails](solutions/tsup-dts-node-prefix-builtin-import-fails.md) — dts pass rejects `node:async_hooks` named imports while `node:fs` works; use the bare builtin name
- [gate-memo-sha-amend-orphan](solutions/gate-memo-sha-amend-orphan.md) — never amend the commit carrying its own GATE memo sha; cite the real ancestor and fold the memo forward

## patterns
- [finally-side-defensive-helper](patterns/finally-side-defensive-helper.md) — finally-called helpers must be exception-proof by construction
- [ambient-run-context-als-contextvars](patterns/ambient-run-context-als-contextvars.md) — per-run state on stateless nodes via AsyncLocalStorage/contextvars; store absence = no-op signal

## decisions
- [heap-trim-in-finally-not-background-task](decisions/heap-trim-in-finally-not-background-task.md) — DA-3009 trim placement: synchronous finally over BackgroundTask (Lambda freeze semantics)
- [fixed-tmp-paths-on-shared-runner-pool](anti-patterns/fixed-tmp-paths-on-shared-runner-pool.md) — DA-3160: literal /tmp paths collide cross-run on persistent pool boxes; swap to $RUNNER_TEMP/mktemp before routing
- [pick-gate-working-directory-override](solutions/pick-gate-working-directory-override.md) — DA-3160: workflow-level run defaults break the no-checkout pick gate; job-scoped cwd override, block untouched
- [parity-port-must-widen-wire-schema](anti-patterns/parity-port-must-widen-wire-schema.md) — DA-3314: porting a protocol widening must widen the inbound parse schema (request.ts) not just the handler; descriptors died at safeParse 400 before the uploader ran
- [parity-plans-cite-reference-constants](conventions/parity-plans-cite-reference-constants.md) — parity plans quote reference constants with file:line (backoffs/timeouts/retry rules); every deliberate divergence gets a "diverges because" note
- [ts-method-syntax-bivariance-additive-widening](patterns/ts-method-syntax-bivariance-additive-widening.md) — method-syntax interface members keep parameter widening additive for implementors (bivariance); property-arrow breaks them; pin with tsconfig.tests type-fixture
