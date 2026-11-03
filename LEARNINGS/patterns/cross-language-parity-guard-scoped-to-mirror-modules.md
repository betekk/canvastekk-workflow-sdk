# Cross-Language Parity Guard: Scope to Mirror Modules, Not the Whole Package

**Category**: patterns · **Confidence**: High · **Scope**: canvastekk-workflow-sdk python/typescript (generalizes to dual-runtime SDKs)
**Date**: 2026-11-03 · **Ticket**: betekk/canvastekk-workflow-sdk#239

The SDK's py/ts packages are maintained as name-mirrored twins
(`registry_auth_header`↔`registryAuthHeader`, snake↔camel). A naive parity
guard — "walk both packages' public exports and assert set equality" — computed
**70 TS-only / 55 py-only legitimate asymmetries** (zod `*Schema` twins,
type-only exports, idiom helpers like `loadJson`/`saveJson` vs stdlib json): a
full-set guard would fire on every routine change and become a blanket-approval
noise machine, protecting nothing.

Pattern that works (canvastekk-workflow-sdk `python/tests/test_parity.py`):

1. **Pairs table** for the mirror cluster only (the modules where
   correspondence IS the design rule — registry/diff/cli): each pair must exist
   on both sides.
2. **Drift alarm**: every other public name in those modules must appear in an
   explicit, **commented** allowlist (each entry names why the asymmetry is
   real — "ts exports for tests, py keeps `_`-private").
3. **CLI surface table**: shared commands must carry the same flags in both
   usage texts.
4. **Literal pinning**: constants that must be equal across runtimes (the
   DA-1948 key shape: prefix/length/alphabet) are source-text-asserted equal —
   catches the three-way duplication (CDS + py + ts) drifting.

Adding a new export to a mirror module without a pairs/allowlist entry reds the
test — the guard has teeth precisely because its scope is small.
