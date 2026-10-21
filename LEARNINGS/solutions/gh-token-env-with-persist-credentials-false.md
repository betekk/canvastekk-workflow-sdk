# Chained Jobs Need Explicit GH_TOKEN When Checkout Disables Credential Persistence

**Category:** solution · **Confidence:** high · **Scope:** GitHub Actions jobs that call `gh` after `persist-credentials: false`
**Date:** 2026-10-19 · **Ticket:** betekk/canvastekk-frontend-nextjs#2039

## Solution

`actions/checkout` with `persist-credentials: false` (correct for
tag-checkout publish jobs — no implicit push rights leak into later steps)
also removes the implicit auth the `gh` CLI relies on. Every later `gh
release upload` / `gh api` step then fails with a 401/"not logged in" even
though `secrets.GITHUB_TOKEN` exists in the job.

Give each `gh` step an explicit env:

```yaml
- name: Attach assets
  env:
    GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: gh release upload "$NEW_TAG" dist/* --clobber
```

Registry publishes need the same treatment through their own channels:
twine (`GITHUB_TOKEN` env), npm (`NODE_AUTH_TOKEN` env, fed by
`setup-node` with `registry-url`).

## Why it matters

The failure only appears at runtime on the publish lane — local YAML
validation and CI lint both pass. Pattern proven in the fleet library
pilots and replicated in the SDK chained publish job.
