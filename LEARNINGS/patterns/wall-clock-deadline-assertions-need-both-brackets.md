# Wall-Clock Deadline Assertions Need Both Brackets

**Date:** 2026-10-07 · **Source:** #3515 code review (WARN) · **Confidence:** high
**Scope:** any test deriving a budget/deadline from wall clocks (TS + python)

## The trap

One-sided clock brackets on a future deadline flake in exactly one direction:

```ts
const before = Date.now();
const deadline = downloadDeadline(eff); // producer calls Date.now() internally
const budget = (deadline - before) / 1000;
expect(budget).toBeLessThanOrEqual(5760); // ❌ budget = 5760 + (t_inner − t_outer)
```

The producer's inner `Date.now()` always runs *after* the outer capture, so a
single 1 ms tick (GC safe-point, deschedule) makes the budget `K + ε` and the
`≤ K` assertion fails spuriously — intermittent red CI on a correct change.

## The fix

Bracket both ends, or freeze time:

```ts
const before = Date.now();
const deadline = downloadDeadline(eff);
const after = Date.now();
expect(budget).toBeGreaterThanOrEqual(5760);
expect(budget).toBeLessThanOrEqual(5760 + (after - before) / 1000);
```

(`vi.setSystemTime` / python `freezegun` give exact assertions when the clock
can be frozen.)

## Evidence

- `typescript/tests/base-node.test.ts` (#3515) — caught by review before merge.
- Elapsed-time upper bounds that already bracket both ends:
  `typescript/tests/app.test.ts:94-101` (the safe form).
