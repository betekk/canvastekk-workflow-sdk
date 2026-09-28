# Ambient run context: AsyncLocalStorage (TS) / contextvars (Python)

**Category:** pattern
**Confidence:** high (shipped TS leg DA-3232; interleaved-runs test pins isolation)
**Scope:** SDK per-run concerns exposed on stateless node classes
**Date:** 2026-09-29 (DA-3232)

## Pattern

One node instance serves concurrent runs (HTTP handlers / to_thread), so
per-run state must never live on the instance. To give `BaseNode` a
run-scoped helper without threading a context parameter through node
signatures:

- **TS**: `const storage = new AsyncLocalStorage<ExecutionContext>()`
  exported from `context.ts`; `run()` wraps its try-body in
  `storage.run(context, async () => …)`; the helper resolves
  `storage.getStore()` and no-ops when absent (outside a run).
- **Python mirror**: `contextvars.ContextVar` set around `execute()`;
  async tasks and `asyncio.to_thread` both propagate it.

Absence of a store IS the "no run context" signal — local dev / manual calls
degrade to a silent no-op with zero wiring.

## Why worth replicating

The next cross-cutting per-run concern (cancellation helpers, telemetry
correlation, the future async/202 completion flow) can ride the same storage
instead of growing `execute()` signatures. Ceiling already documented: a call
after `run()` returns (detached work) finds no store — explicit context
threading is the escape hatch there.

## Evidence

- `typescript/src/context.ts` (`executionContextStorage`) + `base-node.ts`
  (`reportProgress`, wrapped `run()`)
- `typescript/tests/base-node.test.ts` "interleaved runs each ping their own
  execution_id" pins cross-run isolation
