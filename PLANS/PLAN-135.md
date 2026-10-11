# PLAN: SDK#135 — TS twin: ctk_ credentials ride Authorization Bearer

**Branch**: feat/135 · **Issue**: betekk/canvastekk-workflow-sdk#135 · **Base**: main

## Acceptance Criteria

- [x] `registerNode({serviceToken: "ctk_…"})` sends `Authorization: Bearer`, no `X-Service-Token` (test-pinned)
- [x] CLI register routes through the same helper (test-pinned via the helper unit + shared seam)
- [x] Legacy tokens byte-identical to today
- [x] New version published to `npm.pkg.github.com/@betekk` (package.json 0.51.0 → 0.52.0; release.yml's tarball rename expects package.json == git-cliff tag, so the minor label must cut v0.52.0)

## Dependency & Consumer Map

| Node | Depends on | Consumers | Risk |
|------|-----------|------------|------|
| `src/registry.ts` `registryAuthHeader` (new) | — | `registerNode` header site, `src/cli.ts` register POST | low |
| `package.json` 0.52.0 | release.yml pack/rename contract | CISA#205 pins the published version | low |

External: unblocks canvastekk-ifc-service-app#205 (node path: @nus-cee→@betekk scope fix + PATCH deletion + credential swap).

## Phases

- [x] **1.1** Helper + both header sites + cli.ts doc + version bump
    — **Why:** mirror of #134 (python); one shared seam so library and CLI cannot drift
    — **Done:** registry.ts:206 + cli.ts:212 route through `registryAuthHeader`; docstring names both wire forms; 0.52.0
    — **Consumers affected:** every TS registrant (only ctk_-shaped credentials change wire form)
- [x] **1.2** Tests ×4: helper shapes ×2; registerNode fetch-captured headers ×2 (Bearer present/Svc absent; legacy byte-identical)
    — **Why:** AC is test-pinned header behavior
    — **Done:** 396/396 green
    — **Consumers affected:** CI
- [x] **1.3** Exit gate (full): vitest 396/396, eslint, tsc ×2, tsup build — all exit 0
    — **Consumers affected:** PR gate citation

## Technical Notes

- The by-name verify in cli.ts uses the same `headers` object → covered by the shared seam.
- Version parity: python twin shipped Bearer dispatch in v0.51.0; TS publishes 0.52.0 on the next minor tag — consumers pin by exact version (npm/GitHub Packages tarball).

## Dependencies

Server side engine #700 (merged). Unblocks CISA#205.

## Risks & Mitigations

- Release-tag race (another merge shifts the next tag off v0.52.0 → pack rename fails): existing pipeline fragility, noted on the PR; watch the release run.

## Trace

GATE 9e8eac7 tier=full lint=t typecheck=t build=t unit=t e2e=n.a  (vitest 396/396 incl. 4 new; eslint clean; tsc src+tests exit 0; tsup build exit 0; fixes: none)
