# tsup dts fails on `node:async_hooks` while `node:fs` works

**Category:** solution
**Confidence:** high (reproduced + fixed green)
**Scope:** `typescript/` leg, any future `node:` builtin import
**Date:** 2026-09-29 (DA-3232)

## Symptom

`npm run build` (tsup with `dts: { resolve: true }`) fails in the DTS pass:

```
RollupError: "AsyncLocalStorage" is not exported by "node:async_hooks", imported by "src/context.ts".
```

Runtime ESM/CJS builds succeed; only the declaration build reds. The same
file already imports `mkdirSync` from `node:fs` with no complaint.

## Cause

rollup-plugin-dts's builtin-external table resolves `node:fs` but misses
`node:async_hooks` (both are `export * from "<unprefixed>"` re-exports in
@types/node, so the declarations themselves are fine — the externals
recognition is the gap).

## Fix

Use the bare builtin name — identical module at runtime, identical types:

```ts
import { AsyncLocalStorage } from "async_hooks";
```

with a one-line comment naming the reason so nobody "fixes" it back to the
`node:` form. General rule: when a `node:` prefixed import reds the tsup dts
pass but tsc is happy, try the unprefixed form before touching build config.
