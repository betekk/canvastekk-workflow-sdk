# PLAN: Purge X-Service-Token + ctk_ ergonomics/parity hardening

**Branch**: feat/239
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/239
**Base**: dev

## Acceptance Criteria

- [ ] Non-ctk_ token fails locally with a rotation message on both runtimes (no network call)
- [ ] Zero `X-Service-Token` occurrences in either package's source/tests/READMEs (docs/EXTERNAL-AUTHOR-GUIDE.md swept too — same audience)
- [ ] Both packages expose a `ctk` bin; docs use it uniformly
- [ ] Python probe accepts `--manifest` and `module:attribute`
- [ ] Parity guard test green and wired into CI
- [ ] Full gates green on both runtimes (ruff/pytest · tsc/eslint/vitest/tsup)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/…/registry.py::registry_auth_header` (rename of `_registry_auth_header`, now raising) | — | register_node, fetch_published_definition, `__main__` register/probe, convergence.py (after 1.2), all 7 consumer repos via CLI | **high** — behavior change: non-ctk_ now errors instead of sending a header the engine 401s |
| `python/…/registry.py::register_node` | registry_auth_header | CLI `register`, examples, external library users | med — api_key no longer authenticates the registry call (already dead at engine #3760); stays for invoke verification |
| `python/…/convergence.py` `_get_json`/`_delete` | registry_auth_header | `registry-convergence` command (retired-slug sweeps) | low — was sending a header the engine rejects; now fails fast with the same rotation message |
| `python/…/__main__.py` (probe --manifest, early token validation, usage) | registry.py | CLI users; `ctk` console script (1.4) | med |
| `python/pyproject.toml` `[tool.poetry.scripts]` | __main__.main exists | wheel installers → `ctk` bin on PATH | low |
| `python/README.md`, `docs/EXTERNAL-AUTHOR-GUIDE.md` | code behavior final | node authors | low |
| `typescript/src/registry.ts::registryAuthHeader` (now throwing) | — | registerNode, fetchPublishedDefinition, cli.ts, node-lane deploys | **high** — mirror of the python behavior change |
| `typescript/src/registry.ts::registerNode` | registryAuthHeader | TS library users | med — apiKey registry leg removed (dead at engine); serviceToken required |
| `typescript/src/cli.ts` | registry.ts | `canvastekk-workflow-sdk` / `ctk` bins | med |
| `typescript/package.json` bin `ctk` | dist/cli.js shebang | npm installers → bin links | low |
| `typescript/README.md` | code behavior final | node authors | low |
| `python/tests/test_parity.py` (new) | both packages' surfaces final | CI (ci-python.yml runs it with the monorepo checkout) | low |

Cross-module consumers beyond the node itself: yes — every consumer repo's deploy CLI and library users on both runtimes. (Architecture review selected.)

## Implementation Phases

### Phase 1: Python — purge legacy auth + ctk_ hardening

- [x] **1.1** Make `registry_auth_header` public and strict in `python/canvastekk_workflow_sdk/registry.py`: rename from `_registry_auth_header`, raise `ValueError` with the rotation message ("this SDK requires a ctk_ key — the engine retired X-Service-Token (#3760); ask ops to rotate") on non-`ctk_` tokens, and validate the ctk_ shape (mirror CDS `ApiKeyUtil` DA-1948: `ctk_` + 43 chars of `[A-HJ-NP-Za-km-z1-9]`, 47 total) with a truncation hint on malformed keys; update all internal callers (`register_node`, `fetch_published_definition`) and demote `register_node`'s `api_key` to invoke-verification only (registry auth requires `service_token`)
    — **Why:** one shared guard at the choke point every registry call routes through; root cause of the "mystery 401" class, smallest diff covering register/probe/diff/convergence at once
    — **Done when:** `grep -rn "_registry_auth_header\|X-Service-Token" python/canvastekk_workflow_sdk/` returns only the rotation-message/docstring history notes; non-ctk_ token raises before any httpx call
    — **Consumers affected:** register_node, fetch_published_definition, convergence.py, __main__.py, the 7 consumer repos' deploy CLIs (all verified already sending ctk_ keys — audit in ticket)
    — **Done:** strict public `registry_auth_header` + `invalid_ctk_reason` (DA-1948 mirror, rotation + truncation messages); register_node requires service_token, api_key demoted to verify-only, X-API-Key leg removed; files: registry.py; fixes: none (green first run after fixture shape updates)

- [x] **1.2** Route `convergence.py` `_get_json`/`_delete` through `registry_auth_header` (purge the two hard-coded raw `X-Service-Token` headers)
    — **Why:** these bypassed the shared fn and send a header the engine rejects — same bug class, must not survive the purge
    — **Done when:** convergence.py contains zero literal `X-Service-Token` strings and inherits the strict validation
    — **Consumers affected:** `registry-convergence` command (retired-slug sweeps)
    — **Done:** both helpers build headers via registry_auth_header (Bearer); files: convergence.py; fixes: none

- [x] **1.3** `python/canvastekk_workflow_sdk/__main__.py`: add `--manifest <file.json>` to `probe` (JSON → `WorkflowNodeManifest.model_validate`, same pipeline as module:attribute; positional form unchanged); fail fast on non-ctk_/malformed tokens in both `register` (exit 2, rotation message) and the probe registry-diff path (report invalid, never a skip); update usage/help text
    — **Why:** input parity with TS probe + the AC "fails locally, no network call" at the CLI layer where the message is actionable
    — **Done when:** `ctk probe --manifest m.json` passes offline; a `svs_`-style token exits 2 with the rotation message before any socket opens
    — **Consumers affected:** CLI users on every consumer repo; none broken (all send ctk_)
    — **Done:** probe accepts --manifest (reuses register's `_manifest_from_source`); register + probe-diff validate credentials early (exit 2 / `invalid-credential` report status); usage text names `ctk` alias; files: __main__.py; fixes: none

- [x] **1.4** Add `[tool.poetry.scripts]` → `ctk = "canvastekk_workflow_sdk.__main__:main"` in `python/pyproject.toml`
    — **Why:** the AC's bin alias; `main()` already exists and sys.exits — pure metadata
    — **Done when:** `poetry install` exposes a working `ctk --version` (verified in test via entry-point declaration, not PATH)
    — **Consumers affected:** wheel installers
    — **Done:** console script declared; files: pyproject.toml; fixes: none

- [x] **1.5** Purge + update `python/README.md` auth sections (L1118 register description, L1229 service_token row) and add the one-sentence ctk_ prefix guidance ("your key starts with `ctk_` — treat it like a password; the SDK validates its shape locally")
    — **Why:** the zero-occurrence AC + the prefix-documentation decision (prefix is public by design — secret scanning needs it)
    — **Done when:** zero `X-Service-Token` in python/README.md; ctk_ sentence present in the auth section
    — **Consumers affected:** node authors reading the py package docs
    — **Done:** register paragraph now Bearer/ctk_; param table api_key=verify-only, service_token=required ctk_; ctk_ guidance paragraph + `ctk` examples; files: python/README.md; fixes: none

- [x] **1.6** Update python tests: rewrite the legacy-header assertions (`test_registry.py` L104–141, L691–734; `test_registry_diff.py` L65–69) to assert the raise + rotation message + shape validation (truncation hint case included); add probe `--manifest` tests; add convergence-auth routing test; cover register_node's api_key demotion (api_key alone → ValueError naming service_token)
    — **Why:** tests are the durable spec of the new contract; the AC names the rotation behavior explicitly
    — **Done when:** `ruff check` + full pytest suite green; no test references `X-Service-Token` as an expected header
    — **Consumers affected:** none (internal)
    — **Done:** 12 new/rewritten tests (rotation, truncation, Bearer routing, api_key-alone, CLI exit-2s, invalid-credential probe status, probe --manifest ×2 subprocess); all fake tokens moved to the 47-char DA-1948 shape; files: test_registry.py, test_registry_diff.py, test_main.py, test_cli_register.py, test_conformance.py, test_convergence.py; fixes: E402 import order, helper-indirection AttributeError, validate-message assertion update, svs_/api_key fixture updates across 4 files

### Phase 2: TypeScript — purge legacy auth + ctk_ hardening

- [x] **2.1** `typescript/src/registry.ts`: `registryAuthHeader` throws `Error` with the same rotation message on non-`ctk_` + same CDS shape validation with truncation hint; `registerNode` drops the `apiKey` registry leg (remove `X-API-Key` header branch + param; `serviceToken` required)
    — **Why:** the py/ts mirror is the house rule — the two runtimes must fail identically so CISA's two lanes behave the same
    — **Done when:** `registryAuthHeader("svs_x")` throws; `registerNode` without serviceToken throws naming it; zero `X-Service-Token`/`X-API-Key` literals in registry.ts beyond the rotation message
    — **Consumers affected:** TS library users, node-lane deploys (all send ctk_)
    — **Done:** `invalidCtkReason` + strict `registryAuthHeader` + exported `CTK_PREFIX`/`CTK_BODY_LENGTH` (parity-test pins); registerNode requires serviceToken, apiKey param removed; files: registry.ts; fixes: none

- [x] **2.2** `typescript/src/cli.ts`: validate the credential before any fetch in `runRegister` (exit 2 + rotation message) and in the probe registry-diff path (`applyRegistryDiff`: non-ctk_ → report invalid with the rotation message, never a skip warning); refresh the header docs (usage line, auth note, `ctk` alias mention)
    — **Why:** the probe-diff path catches fetch errors into skips — without an early check, a bad token would masquerade as "engine error: skipped" instead of failing per the AC
    — **Done when:** probe with a `svs_` env token + `--engine-url` exits 1 with the rotation error; register exits 2 before any socket
    — **Consumers affected:** both bins' users
    — **Done:** early validation in runRegister (exit 2) and applyRegistryDiff (`invalid-credential` status added to the union, report invalid); header docs + usage rewritten around `ctk`; files: cli.ts; fixes: none

- [x] **2.3** Add `"ctk": "./dist/cli.js"` to `typescript/package.json` `bin`
    — **Why:** bin parity with the python console script; docs then say exactly `ctk probe --engine-url …`
    — **Done when:** `npm pack` tarball lists both bins; `node dist/cli.js --help` unchanged
    — **Consumers affected:** npm installers
    — **Done:** second bin entry added (same dist/cli.js); files: package.json; fixes: none

- [x] **2.4** `typescript/README.md`: fix L504 stale auth line ("auth (`X-Service-Token`)" → credential env var wording), L879 serviceToken row (drop the X-Service-Token mention), add the ctk_ prefix sentence + `ctk` bin mention in the CLI section
    — **Why:** the stale line is actively wrong since #135/#3760 — worse than missing docs
    — **Done when:** zero `X-Service-Token` in typescript/README.md
    — **Consumers affected:** node authors reading the TS package docs
    — **Done:** CLI section rewritten (ctk examples, credential sentence), registerNode table apiKey row removed, serviceToken row required/ctk_; files: typescript/README.md; fixes: none

- [x] **2.5** Update TS tests: auth-header rotation/shape tests (replacing the 5 legacy sites in `registry.test.ts`), register exit-2 test, probe-diff invalid-token-fails test
    — **Why:** mirror of 1.6 — identical contract, identical coverage
    — **Done when:** typecheck + typecheck:tests + eslint + vitest + tsup build green
    — **Consumers affected:** none (internal)
    — **Done:** 7 net-new tests (throw matrix, no-fetch-before-error, missing-serviceToken, CLI exit 2 ×2, invalid-credential probe ×2); fixtures moved to 47-char shape; files: registry.test.ts, cli.test.ts; fixes: none (gate green first run)

### Phase 3: Parity guard + docs sweep + exit gate

- [ ] **3.1** Add `python/tests/test_parity.py`: (a) a pairs table asserting name correspondence for the mirror cluster (registry/diff/cli surface: `registry_auth_header↔registryAuthHeader`, `register_node↔registerNode`, `fetch_published_definition↔fetchPublishedDefinition`, `diff_against_published↔diffAgainstPublished`, `build_registry_payload↔buildRegistryPayload`, `ENGINE_NON_COMPARISON_FIELDS↔same`, `diff_manifests↔diffManifests`, …) by walking `typescript/src/{registry,diff,cli}.ts` exports vs the python modules' public names after case-normalization, with every intentional asymmetry an explicit commented allowlist entry; (b) a CLI surface table ({register, probe} shared flags) asserted against both CLIs' usage text; (c) both packages expose a `ctk` bin (pyproject scripts + package.json bin); (d) the ctk_ shape rule is identical across runtimes — assert the length/alphabet literals in `typescript/src/registry.ts` match python's validator (source-text assertion, same technique as the export walk; arch-review finding). `skipif` when `typescript/src` absent
    — **Why:** the "copy-derived definitions drift apart" lesson — the mirror is convention today; this makes forgetting it a red test instead of a support ticket
    — **Done when:** test green in ci-python.yml (monorepo checkout carries typescript/), and adding a stray export to either side's mirror modules without an allowlist entry fails it
    — **Consumers affected:** SDK maintainers (the guard's audience)

- [ ] **3.2** Sweep `docs/EXTERNAL-AUTHOR-GUIDE.md`: L336–338 (register wire-form paragraph → ctk_-only), L464–467 auth-method table (retire the X-Service-Token row), L515–516 param table (api_key/service_token wording to match new register_node contract)
    — **Why:** user-facing guide still teaches the dead header — same audience as the READMEs, same AC spirit
    — **Done when:** zero `X-Service-Token` outside the rotation-message string and history notes; `ctk` used in examples
    — **Consumers affected:** external node authors

- [ ] **3.3** Zero-occurrence gate + full exit gate: `grep -rn "X-Service-Token" python/ typescript/ docs/` returns only deliberate history-note contexts (rotation message, changelog); run BOTH runtimes' full gates (ruff+pytest; tsc+typecheck:tests+eslint+vitest+tsup) and record the `tier=full` memo
    — **Why:** the AC's zero-occurrence + full-gates boxes need a single checkable proof point on the final tree
    — **Done when:** both gates green on the same SHA; memo line appended below
    — **Consumers affected:** none (verification)

## Technical Notes

- ctk_ shape (authoritative): CDS `ApiKeyUtil` (DA-1948) — `ctk_` + 43 chars `[A-HJ-NP-Za-km-z1-9]` (base62 minus `0 O I l`), 47 total; masked display = first 8 chars (`ctk_Ab3d`). SDK mirrors the shape with a comment citing DA-1948 so a future CDS format change has a paper trail.
- Rotation message (both runtimes, near-identical): non-ctk_ → "registry credentials must be ctk_ API keys — the engine retired X-Service-Token (#3760); ask ops to rotate". Malformed ctk_ → append the truncation hint ("expected 47 chars (ctk_ + 43); got N — looks truncated or mistyped").
- `verify_node`/`conformance` `api_key` is NODE-level auth (NodeAuth) — intentionally untouched. Only the registry X-API-Key leg dies.
- Engine imports of the SDK (`WorkflowNodeManifest`, `mint_node_token`, `verify_node`, `UploadSession`) never touch the registry-auth surface — strict validation cannot break engine-internal flows.
- Parity guard scope: mirror modules only (registry/diff/cli). Wholesale package-set equality is wrong — zod `*Schema` twins, type aliases, and idiom helpers make ~70 legitimate asymmetries today; a full-set guard would be a blanket-approval noise machine.
- Exit codes: credential-shape failure = exit 2 (usage-class) on both runtimes; probe registry-diff credential failure = invalid report (exit 1). Documented in usage text.
- Versions are stamped from release tags (no in-repo bumps); this lands on `dev` and ships as the next minor after promote.

## Dependencies

- None blocking. Engine-side reference: #3760 (retirement), #699 (future sweep of `/api/internal/*` — out of scope, needs infra-cron credential rotation first).

## Risks & Mitigation

- **A consumer secretly holds a legacy token** → strict raise breaks its deploy locally with a clear message (vs. today's unexplained engine 401). Audit in the ticket covers all seven repos: clean. The message names the fix (rotate).
- **CDS changes key shape later** → SDK rejects valid keys. Mitigation: shape check cites DA-1948 in both codebases; CDS format changes are cross-repo events that touch this mirror deliberately (the parity test's allowlist comment points maintainers there).
- **Library callers passing `api_key=` to register_node** → ValueError naming service_token. Mitigation: message is actionable; the leg has been dead at the engine since #3760 — failing fast is the fix, not the regression.
- **Parity test too clever / regex-fragile** → Mitigation: pairs table is explicit data; the walk only feeds it, and allowlist entries carry comments.

## Trace

GATE ed30a7e tier=full lint=t typecheck=n.a build=n.a unit=t e2e=n.a
LOG phase1 full-tier: auth critical-area anchor (registry credential handling)
LOG phase2 full-tier: auth critical-area anchor (py/ts mirror of the same credential gate)
