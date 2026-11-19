# PLAN: Explicit module and public names in Python and TypeScript (0.67.0)

**Branch**: feat/271
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/271
**Base**: dev

## Acceptance Criteria

- [x] ADR and glossary committed; the complete rename map (every public name in `__all__` and the TS index) committed before code changes
- [x] Every module and public name in the map renamed in Python and TypeScript
- [x] Old module paths and names still import and work, warning as deprecated (tests in both languages)
- [x] Guard tests: Python/TypeScript name parity for renamed modules and symbols; no node-level module or public name contains "definition"
- [x] `NodeAuth` / `TekkNodeAuth` and `NodeValidationError` resolved
- [x] No behavior or wire change: existing suites green with only import updates; README, CLI help and bundled skills use the new names
- [ ] Released as 0.67.0

## Dependency & Consumer Map

External consumers (CWE, FE, workflow-nodes, llm/ml/audio/ifc/point-cloud/report node-hosts — epic R2–R10) import the SDK public surface; the deprecated aliases exist precisely so they keep working. That makes every row below a cross-module node.

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `docs/GLOSSARY.md` + `docs/adr/0001-explicit-node-naming.md` (complete map) | — | every later phase; epic #4301 close-out; reviewers | low (docs-only, but the map is the law — a wrong entry propagates into every phase) |
| py `workflow_node_manifest.py` / `workflow_node_manifest_diff.py` / `workflow_node_registry.py` / `workflow_node_registry_convergence.py` / `workflow_node_conformance.py` (+ shims `definition.py`, `diff.py`, `registry.py`, `convergence.py`, `conformance.py`) | ADR | py `__init__`, `__main__`, `bootstrap`, `base`, `testing`, `auth/`, `workflow/`, all consumer repos via shims | high |
| ts `workflow-node-manifest.ts` / `workflow-node-manifest-diff.ts` / `workflow-node-registry.ts` (+ @deprecated shims `definition.ts`, `diff.ts`, `registry.ts`) | ADR (same commit as py twins — parity rule) | ts `index.ts`, `cli.ts`, `app.ts`, `base-node.ts`, `bootstrap.ts`, consumer repos via shims | high |
| py `workflow_node_base.py` / `workflow_node_app.py` / `multi_node_router.py` / `node_execution_{request,response,context}.py` / `node_call_protocol.py` / `node_output_uploads.py` / `cds_multipart_upload.py` / `node_io_data_contracts.py` (+ shims at old paths) | phase 2 (imports the manifest cluster) | py `__init__` lazy exports, `middleware`, `observability`, `testing`, `_server_middleware`, `data/` scaffold templates, consumer repos | high |
| ts `workflow-node-base.ts` / `workflow-node-app.ts` / `node-execution-*.ts` / `node-call-protocol.ts` / `node-output-uploads.ts` / `cds-multipart-upload.ts` / `node-io-data-contracts/` (+ shims) | phase 2 (same commit as py twins) | ts `index.ts`, `cli.ts`, `express.ts`, `middleware.ts`, consumer repos | high |
| py `workflow/workflow_definition.py` / `workflow/node_executor.py` (+ shims `workflow/models.py`, `workflow/executor.py`); `exceptions.py` class renames | phase 3 | `workflow/__init__`, `builder`, `runner`, `resolver`, `validation`, `level`, consumer repos | high |
| ts `workflow/workflow-definition.ts` / `workflow/node-executor.ts` (+ shims); `exceptions.ts` renames | phase 3 (same commit as py twins) | `workflow/index.ts`, `builder.ts`, `runner.ts`, consumer repos | high |
| guard tests (`test_rename_map.py` / `rename-map.test.ts` extensions of the `test_parity.py` pattern; alias tests `test_rename_aliases.py` / `rename-aliases.test.ts`) | phases 2–4 | CI; epic AC guard | medium |
| surface sweep: root `README.md`, `python/README.md`, `typescript/README.md`, `docs/*.md`, CLI usage (`py __main__.py`, `ts cli.ts`), bundled skills `python/.../data/skills/**` + `.agents/skills/**` mirrors | phases 2–4 (names must exist first) | external node authors; node-host repos copy these examples | medium (docs-only but wide; mirrors drift) |
| release PR `release/v0.67.0` (labels `release`+`minor`) | all phases merged to dev | Release workflow (tag→cliff→publish→dispatch); every consumer repo (R2–R10 rebuild signal) | medium |

## Implementation Phases

Phases 2–4 each land **Python and TypeScript in the same commit** (ticket parity rule). Shims: Python old-path modules re-export the new module carrying `_deprecated_alias_of = "<new module>"` and a module-import `DeprecationWarning`; old public names resolve via lazy `__getattr__` (package root already uses this pattern — `_LAZY_SERVER_EXPORTS`) so new-name users never see warnings. TypeScript old-path files are `/** @deprecated */` re-export shims; old index names re-export as deprecated aliases.

### Phase 1: Vocabulary law — glossary, ADR, complete rename map (docs-only)

- [x] **1.1** Commit `docs/GLOSSARY.md` with the epic #4301 term table (workflow definition / workflow definition node / workflow node manifest / workflow node / workflow run / node execution·node call / node I/O data)
    — **Why:** the vocabulary law every later step cites; the epic's AC requires it recorded in this repo.
    — **Done when:** file committed with the seven-term table verbatim from the epic.
    — **Consumers affected:** all phases (citation target); epic close-out.
    — **Done:** docs/GLOSSARY.md written (seven-term table + rollout pointer); files: docs/GLOSSARY.md; fixes: none
- [x] **1.2** Commit `docs/adr/0001-explicit-node-naming.md`: the decision, the alias mechanism law, the complete rename map — every name in python `__all__` and the TS index classified `old → new` or `kept (already explicit)` — plus the two resolutions: (a) `NodeAuth` vs `TekkNodeAuth`: TS `TekkNodeAuth` is already `export const TekkNodeAuth = NodeAuth` (`auth.ts:476`) → TS keeps `TekkNodeAuth` canonical and marks `NodeAuth` deprecated; Python has two genuinely distinct classes (`auth/core.py:587 TekkNodeAuth` credential vs `auth/fastapi.py:113 NodeAuth` FastAPI dependency) → both kept, documented as distinct; (b) `NodeValidationError`: raised for both manifest (`definition.py:553`) and input (`base.py:181`, `contracts.py:90`) failures → keep `NodeValidationError` as base, add subclasses `WorkflowNodeManifestValidationError` and `NodeInputValidationError`, raise the specific ones (existing `except NodeValidationError` keeps catching both — zero behavior change)
    — **Why:** the ticket demands the complete map before code changes; the two open names need decided, recorded resolutions before any phase can order its renames.
    — **Done when:** ADR committed; enumeration cross-check (1.3) confirms every `__all__` name and every `index.ts` export appears exactly once with a verdict.
    — **Consumers affected:** phases 2–5 (the map is their worklist); Step 7 reviewers.
    — **Done:** ADR written: decision, ambiguity rule, alias mechanism, both resolutions, module map (17 rows), renamed-symbol map (9 clusters), kept-symbol list, Schema-twin enumeration, N1 pin note; files: docs/adr/0001-explicit-node-naming.md; fixes: none
- [x] **1.3** Cross-check the map by enumeration: parse `__all__` from `python/canvastekk_workflow_sdk/__init__.py` and exports from `typescript/src/index.ts`, diff against the ADR table
    — **Why:** a map that misses one name silently skips its rename — completeness must be proven, not assumed.
    — **Done when:** zero-name diff both directions; counts recorded in the ADR (py `__all__` N names, TS index M exports, every one classified).
    — **Consumers affected:** phase-5 guard tests re-pin this invariant permanently.
    — **Done:** enumeration diff: py __all__ 85 names + ts index 122 names + 17 modules' publics → zero missing both directions (11 Schema/auth names added on first pass); counts recorded in ADR §Verification; files: docs/adr/0001-explicit-node-naming.md; fixes: none

### Phase 2: Manifest + registry cluster (py + ts, one commit)

- [x] **2.1** Python: `git mv` `definition.py`→`workflow_node_manifest.py`, `diff.py`→`workflow_node_manifest_diff.py`, `registry.py`→`workflow_node_registry.py`, `convergence.py`→`workflow_node_registry_convergence.py`, `conformance.py`→`workflow_node_conformance.py`; rename in-module public symbols per the map (`export_definition`→`export_workflow_node_manifest`, `NodeContract`→`WorkflowNodeManifestContract`, `ContractCapabilities`→`WorkflowNodeContractCapabilities`, `RetryConfig`/`ColorPreset`/`DeprecationInfo`→`WorkflowNode*`, `register_node`→`register_workflow_node`, `RegisterNodeResult`→`WorkflowNodeRegistrationResult`, `RegistrationError`→`WorkflowNodeRegistrationError`, `build_registry_payload`→`build_workflow_node_registry_payload`, `fetch_published_definition`→`fetch_published_workflow_node_manifest`, diff symbols per map); write shims at the five old paths (marker + `DeprecationWarning` + re-export); retarget every internal import; update `__init__.py` (new imports + lazy deprecated aliases)
    — **Why:** the manifest cluster is the epic's namesake confusion ("definition means workflow definition everywhere else"); it must land before clusters that import it.
    — **Done when:** `import canvastekk_workflow_sdk` green; old paths import with warning; no internal import references the old module paths outside shims.
    — **Consumers affected:** py `__init__`/`__main__`/`bootstrap`/`base`/`testing`/`auth/`/`workflow/`; consumer repos via shims.
    — **Done:** five modules git-mv'd; 15 symbols renamed; 5 shims (marker+warning+star+assignments); 23 files swept; __init__ lazy aliases; ruff green; files: canvastekk_workflow_sdk/{workflow_node_manifest,workflow_node_manifest_diff,workflow_node_registry,workflow_node_registry_convergence,workflow_node_conformance}.py + 5 shims + __init__.py; fixes: shim E402/I001 (assignments not aliased imports), SDK_SERVED_CONTRACT_ROUTES missing from root aliases
- [x] **2.2** TypeScript: `git mv` `definition.ts`→`workflow-node-manifest.ts`, `diff.ts`→`workflow-node-manifest-diff.ts`, `registry.ts`→`workflow-node-registry.ts`; rename symbols per the map (`exportDefinition`→`exportWorkflowNodeManifest`, `NodeContract`→`WorkflowNodeManifestContract`, `getNodeId`→`getWorkflowNodeManifestId`, `diffManifests`→`diffWorkflowNodeManifests`, `ManifestDiff`→`WorkflowNodeManifestDiff`, registry twins incl. `*Schema` twins per map); @deprecated shims at old paths; `index.ts` exports new names + deprecated old aliases; retarget internal imports
    — **Why:** py-ts parity rule — the twin lands in the same commit.
    — **Done when:** `npm run build` + `npm test` green; old paths resolve with `@deprecated` markers in emitted `.d.ts`.
    — **Consumers affected:** ts `index.ts`/`cli.ts`/`app.ts`/`base-node.ts`/`bootstrap.ts`; consumer repos via shims.
    — **Done:** three modules git-mv'd; symbols+Schema twins renamed (incl. missed twins fetchPublishedDefinition/diffAgainstPublished found via parity guard); @deprecated shims; index aliases; tsc+eslint+vitest(496)+tsup green; files: src/{workflow-node-manifest,workflow-node-manifest-diff,workflow-node-registry}.ts + 3 shims + index.ts + cli.ts; fixes: RegistrationError alias repointed to exceptions.js
- [x] **2.3** Update affected test imports (both languages), create `python/tests/test_rename_aliases.py` + `typescript/tests/rename-aliases.test.ts` asserting old paths import and (py) warn; run both suites; commit `feat(naming): explicit manifest + registry names, deprecated aliases (py+ts)`
    — **Why:** AC-3 requires alias tests in both languages; the commit is the parity-rule unit.
    — **Done when:** py + ts suites green; alias tests cover every renamed name in this cluster; every `FREEZE` row in `python/tests/test_consumer_import_freeze.py` touching this cluster resolves through an alias (freeze suite green unmodified).
    — **Consumers affected:** CI.
    — **Done:** alias tests extended to all phases (py 78 tests incl. split-catching + wire-name proofs; TS 9 tests); map == alias-test coverage holds; py 1121 + ts 505 green; files: tests/test_rename_aliases.py, tests/rename-aliases.test.ts; fixes: PEP 562 blocks missing in validation/runner, double-comma gen bug
    — **Done:** alias tests extended: py 58 tests (15 shims, 45 names, in-module warn, root aliases) — total suite 1100 passed; TS alias tests carried by phase-2 file (old-path re-exports verified); deprecated root names warn on every access (no caching); files: python/tests/test_rename_aliases.py; fixes: freeze-test pollution via alias caching (removed cache)
    — **Done:** test_rename_aliases.py (35 tests: shim import+warn, old-name identity, root aliases) + rename-aliases.test.ts (old paths + old index names + type aliases); test_parity.py moved to new module names/pairs; freeze suite green unmodified; py 1063 + ts 496 passed; files: python/tests/test_rename_aliases.py, typescript/tests/rename-aliases.test.ts, python/tests/test_parity.py; fixes: sys.modules-pop for shim re-warn, root-scope narrowed to old __all__ names

### Phase 3: Node runtime + node execution cluster (py + ts, one commit)

- [x] **3.1** Python: `git mv` `base.py`→`workflow_node_base.py`, `app.py`→`workflow_node_app.py`, `router.py`→`multi_node_router.py`, `request.py`→`node_execution_request.py`, `response.py`→`node_execution_response.py`, `context.py`→`node_execution_context.py`, `protocol.py`→`node_call_protocol.py`, `uploads.py`→`node_output_uploads.py`, `multipart.py`→`cds_multipart_upload.py`, `contracts.py`→`node_io_data_contracts.py`; symbols per map (`BaseNode`→`WorkflowNodeBase`, `create_node_app`→`create_workflow_node_app`, `mount_node`→`mount_workflow_node`, `create_authed_app`→`create_authed_workflow_node_app`, `create_lambda_handler`→`create_workflow_node_lambda_handler`, `create_multi_node_app`→`create_multi_workflow_node_app`, `HealthResponse`→`WorkflowNodeHealthResponse`, `ExecutionContext`→`NodeExecutionContext`, `ExecutionMetric`→`NodeExecutionMetric`, `NodeExecutionStatus`→`WorkflowNodeCallOutcome`, `parse_node_execution_status`→`parse_workflow_node_call_outcome`, `NODE_PROTOCOL_HEADER`→`NODE_CALL_PROTOCOL_HEADER`, `outcome_for_protocol`→`node_call_outcome_for_protocol`, `read_outcome`→`read_node_call_outcome`, `requested_protocol`→`requested_node_call_protocol`, `OutputUploader`/`S3PresignedUploader`/`UploadSession`/`UploadTarget`→`NodeOutput*`, `get_default_uploader`→`get_default_node_output_uploader`, `BaseContract`→`NodeIoDataContract`, `CONTRACT_VERSION`→`NODE_IO_DATA_CONTRACT_VERSION`); shims at all ten old paths; retarget `_LAZY_SERVER_EXPORTS` module paths, internal imports, and the `data/` scaffold templates (new scaffolds emit new names); `__init__.py` new + deprecated-lazy exports
    — **Why:** the runtime/execution cluster holds most of the unnamed-surface pain (`base`, `app`, `context`); depends on phase-2 modules it imports.
    — **Done when:** package imports green; old paths warn; scaffolded project (`-m canvastekk_workflow_sdk init` template output) uses new names.
    — **Consumers affected:** py lazy-export consumers, `middleware`/`observability`/`testing`/`_server_middleware`; node-host repos via shims.
    — **Done:** 10 modules git-mv'd; 30 symbols renamed; 10 shims; observability+bootstrap PEP 562 in-module aliases; _LAZY_SERVER_EXPORTS retargeted; data/ templates swept; 88 files total; files: canvastekk_workflow_sdk/* (10 new modules + 10 shims + __init__ + observability + bootstrap + internal retargets); fixes: venv corruption from sweep overreach (rebuilt, LEARNING captured), from-pkg-import-submodule form missed (3 tests), bootstrap missing in-module aliases
- [x] **3.2** TypeScript: `git mv` twins (`base-node.ts`→`workflow-node-base.ts`, `app.ts`→`workflow-node-app.ts`, `request/response/context.ts`→`node-execution-*.ts`, `protocol.ts`→`node-call-protocol.ts`, `uploads.ts`→`node-output-uploads.ts`, `multipart.ts`→`cds-multipart-upload.ts`, `contracts/`→`node-io-data-contracts/`); symbols per map (`BaseNode`→`WorkflowNodeBase`, `createNodeApp`→`createWorkflowNodeApp`, `createMultiNodeApp`→`createMultiWorkflowNodeApp`, `ExecutionContext`→`NodeExecutionContext`, `uploadViaSession`→`uploadViaCdsMultipartSession`, `getDefaultUploader`→`getDefaultNodeOutputUploader`, `CONTRACT_VERSION`→`NODE_IO_DATA_CONTRACT_VERSION`, protocol constants/fns per map, `*Schema` twins per map); @deprecated shims at old paths; `index.ts` + internal imports retargeted
    — **Why:** parity rule — same commit as the python twin.
    — **Done when:** `npm run build` + `npm test` green; old paths resolve deprecated.
    — **Consumers affected:** ts consumers via shims; `cli.ts`/`express.ts`.
    — **Done:** 8 files + contracts/ dir git-mv'd; symbols+Schema twins renamed; TekkNodeAuth made canonical class with NodeAuth deprecated alias const; 8 shims; index phase-3 aliases; tsc+eslint+vitest(501)+tsup green; files: src/* (8 new modules + node-io-data-contracts/ + 8 shims + index.ts + auth.ts + bootstrap.ts); fixes: mid-path import specs (../src/contracts/…) missed by path regex
- [x] **3.3** Update test imports, extend the alias tests to this cluster, both suites green; commit `feat(naming): explicit node runtime + execution names, deprecated aliases (py+ts)`
    — **Why:** alias coverage must grow with the cluster it covers.
    — **Done when:** suites green; alias tests cover every renamed name in this cluster.
    — **Consumers affected:** CI.

### Phase 4: Workflow definition + workflow run cluster (py + ts, one commit)

- [x] **4.1** Python: `git mv` `workflow/models.py`→`workflow/workflow_definition.py`, `workflow/executor.py`→`workflow/node_executor.py`; symbols per map (`validate`→`validate_workflow_definition`, `ValidationResult`→`WorkflowDefinitionValidationResult`, `NodeResult`→`WorkflowRunNodeResult`, `ErrorPolicy`→`WorkflowRunErrorPolicy`, `NodeExecutor`→`WorkflowRunNodeExecutor`, `InProcessExecutor`→`InProcessNodeExecutor`, `HttpExecutor`→`HttpNodeExecutor`); in `exceptions.py`: `WorkflowExecutionError`→`WorkflowRunError`, `WorkflowValidationError`→`WorkflowDefinitionValidationError`, plus the `NodeValidationError` subclass split (`WorkflowNodeManifestValidationError`, `NodeInputValidationError`) — old names become module-`__getattr__` deprecated aliases (PEP 562) or subclass-preserving aliases so existing `except` clauses keep catching; shims at old workflow paths; `workflow/__init__` + package `__init__` updated
    — **Why:** the workflow cluster completes the vocabulary split; depends on phases 2–3 for its imports.
    — **Done when:** package imports green; old names import with warning; `except NodeValidationError` semantics proven by a test.
    — **Consumers affected:** `workflow/builder|runner|resolver|validation|level`; consumer repos via aliases.
    — **Done:** workflow_definition.py + node_executor.py moved, 2 shims; 9 symbols renamed; exceptions split (subclasses, raise-sites moved) with _wire_error_type preserving historical error_type wire names; PEP 562 blocks in validation/runner/exceptions; py 1121 green; files: workflow/* + exceptions.py + workflow_node_base.py; fixes: multiline import-list renames missed, workflow/executor shim assignments, CLI `validate` command word reverted (manifest-scoped verb, UX compat)
- [x] **4.2** TypeScript: `git mv` `workflow/models.ts`→`workflow/workflow-definition.ts`, `workflow/executor.ts`→`workflow/node-executor.ts`; symbols per map (`validate`→`validateWorkflowDefinition`, `ValidationResult`→`WorkflowDefinitionValidationResult`, `NodeResult`→`WorkflowRunNodeResult`, `ErrorPolicy`→`WorkflowRunErrorPolicy`, executor classes per map); `exceptions.ts` twins incl. the `NodeValidationError` split; @deprecated shims + index aliases
    — **Why:** parity rule.
    — **Done when:** `npm run build` + `npm test` green.
    — **Consumers affected:** ts workflow consumers via shims.
    — **Done:** workflow-definition.ts + node-executor.ts moved, 2 shims with explicit old-name re-exports; 9 symbols + exceptions split (wireErrorType helper); index phase-4 aliases; TS 505 green; files: src/workflow/* + exceptions.ts + workflow-node-base.ts + node-execution-response.ts + index.ts; fixes: import/export-list validate entries, local const validate call-sites reverted
- [x] **4.3** Update test imports, extend alias tests, both suites green; commit `feat(naming): explicit workflow definition + run names, deprecated aliases (py+ts)`
    — **Why:** alias coverage completes with the cluster.
    — **Done when:** suites green; every mapped name now has an alias test (map == alias-test coverage).
    — **Consumers affected:** CI.

### Phase 5: Guard tests, surface sweep, exit gate (one commit + final push)

- [x] **5.1** Guard tests both languages: (a) rename parity — for every renamed module pair and symbol pair, assert the python name and TS name both exist (extend the `test_parity.py` MIRROR_PAIRS pattern); (b) no node-level module or public name contains "definition" — enumerate root modules (shim-marker-aware: files carrying `_deprecated_alias_of` exempt) and the canonical `__all__`/index exports, excluding the workflow-definition domain (`workflow/` + `WorkflowDefinition*`/`WorkflowDefinitionValidation*` names are workflow-level and correct)
    — **Why:** AC-4; the invariant must outlive this PR as a red test, not a one-off grep.
    — **Done when:** both guards green in both languages; the no-definition guard demonstrably fails if fed an old name (spot-check by temporarily reverting one rename in a scratch run or by construction from the map).
    — **Consumers affected:** CI; epic close-out evidence.
    — **Done:** test_rename_map.py (50 tests: 43 parity pairs both sides, no-node-level-definition guards py+ts incl. workflow-definition allowlist); parser bugs fixed (type-only specifiers, shim-file detection); pairs rescoped to index-level twins; files: python/tests/test_rename_map.py; fixes: missing TS index canonical exports added then de-eagered (express regression caught by pack-test), TS bootstrap twins mountNode/createAuthedApp found+renamed
- [x] **5.2** Surface sweep: root `README.md`, `python/README.md`, `typescript/README.md`, `docs/*.md`, CLI usage text (`python __main__.py` + `typescript/src/cli.ts` `usage()`), bundled skills (`python/canvastekk_workflow_sdk/data/skills/**` and `.agents/skills/**` mirrors) — replace old names with new, keep deprecated-name mentions only where deliberately teaching the alias; symbol-scoped renames only (verify each replaced symbol against the map — never vocabulary-replace names that were never renamed, e.g. `WorkflowNodeManifest`, `NodeExecutionRequest` keep their names)
    — **Why:** AC-6; LEARNINGS `py-ts-sdk-changes-sweep-root-readme`, `incomplete-deprecation-sweep-in-docs`, `vocabulary-rename-overapplies-to-doc-examples` all fire on this step.
    — **Done when:** grep exit-gate: no old canonical name outside shims/aliases/deprecation-notes (sweep list recorded in Trace); doc examples still compile/import (skill examples run against the test venv where feasible).
    — **Consumers affected:** external node authors; node-host repos.
    — **Done:** root README + both language READMEs + 4 living docs + cli.ts usage strings swept symbol-scoped; historical records (COMPATIBILITY-v0.64.0, temp-lane) left verbatim; skill mirrors resynced identical (diff -r); README example verified importable; NEW: manifest class-attribute dual-support (manifest canonical, legacy definition warns — py descriptor + TS getter, both languages) — the epic's namesake violation removed from the base class; files: README.md, python/README.md, typescript/README.md, docs/*4, cli.ts, data/skills, .agents/skills, workflow_node_base.py, workflow-node-base.ts; fixes: sweep overreach into local test vars (normalized file-wide), TS field-init order traps
- [x] **5.3** Full exit gate (`tier=full`) on the final tree: py lint+typecheck+build+test, ts lint+build+test; verification greps (old module paths referenced only by shims; `grep -rn "export_definition\|create_node_app\|BaseNode" --include="*.py" --include="*.ts"` hits only shims/aliases/docs-with-deprecated-mention); push
    — **Why:** the ticket exit gate is full; the final pushed SHA must carry the green `tier=full` memo for the PR citation.
    — **Done when:** all gates green; memo line `GATE <sha> tier=full` written in Trace; branch pushed.
    — **Consumers affected:** Step 10 PR citation.
    — **Done:** full ladder green: ruff, pytest 1168, poetry build, tsc, eslint, vitest 506, tsup, pack-test; verification greps zero old paths outside shims/freeze, old names only in alias tables; branch pushed; files: PLANS/PLAN-271.md; fixes: none post-ladder

### Phase 6: Release 0.67.0 (post-merge — orchestrator-executed, NOT a Step-8 phase)

- [ ] **6.1** After `feat/271` merges to `dev`: cut `release/v0.67.0` per README `## Versioning` (`git switch -c release/v0.67.0 origin/dev`; one `--allow-empty` `chore(release): v0.67.0` commit; push; PR base `dev`; labels `release` + `minor`); merge; watch the Release workflow to green; verify tag `v0.67.0` on the merge SHA, GitHub Release with cliff changelog, wheel+tgz published, `sdk-released` dispatch
    — **Why:** AC-7; version files are never committed for a release — the pipeline stamps all five sources tag-derived at publish (`bump_versions.py` in CI).
    — **Done when:** tag `v0.67.0` exists on the release-PR merge commit; Release run success; publish job ran.
    — **Consumers affected:** every consumer repo (R2–R10 rebuild signal).

## Technical Notes

- Vocabulary law (epic #4301): "definition" only ever means a workflow definition; node-level things say "manifest"; every name names the object it belongs to.
- **N1 version pinning (user directive, run record):** the N1 tickets pin exactly `v0.66.0`; CLS and IFC call the protocol helpers by their current names (`outcome_for_protocol` / `outcomeForProtocol`). Releasing 0.67.0 does NOT switch any N1 PR off v0.66.0 — published v0.66.0 is immutable and stays the pin. Old protocol names keep working as deprecated aliases for consumers that later upgrade; the move to new names happens in the migration tickets (CLS `#809`, IFC `#553`). The `sdk-released` dispatch is informational — the release must not force-upgrade any N1-pinned repo.
- No wire change: manifest/registry/payload JSON keys unchanged — only Python/TS identifiers.
- Alias mechanism: py shims carry `_deprecated_alias_of` marker (machine-checkable for guards/alias tests) + module-import `DeprecationWarning`; package-root old names via lazy `__getattr__` so new-name users never warn; TS shims + index re-exports carry `/** @deprecated */`.
- `bump_versions.py` enumerates five version sources; version files are NEVER hand-bumped in this PR (release stamps at publish).
- TS build (tsup) entries are `index.ts`/`cli.ts`/`express.ts` only — internal file renames need no build-config change; package exports are root-only.
- Ticket's suggested phase mapping preserved: (1)=Phase 1, (2)=Phase 2, (3)=Phase 3, (4)=Phase 4, (5)=Phase 5.

## Dependencies

- Parent epic: betekk/canvastekk-tracker#4301 (link, not a blocker).
- Consumer migrations R2–R10 are separate tickets; this PR must not break them (aliases).

## Risks & Mitigation

- **Consumer breakage via missed alias** → shims re-export the full old module surface; alias tests enumerate from the ADR map (map == test coverage, proven at 1.3/4.3); the frozen consumer-import inventory (`python/tests/test_consumer_import_freeze.py` — CWN/CLS/CWE rows) is the completeness oracle: every FREEZE row must resolve through an alias, and the alias tests assert that superset.
- **N1 pinned consumers disturbed by the release** → v0.66.0 tag and published artifacts are immutable; N1 PRs keep the exact v0.66.0 pin (user directive); `sdk-released` dispatch is a rebuild signal to canvastekk-workflow-nodes only, never a pin bump; protocol-helper old names work via aliases when CLS (#809) / IFC (#553) migrate.
- **Doc-example drift** (broken copy-paste examples) → symbol-scoped sweep verified against the map; LEARNINGS rules applied as greps.
- **`except` semantics change on the `NodeValidationError` split** → subclass-preserving design (old name stays the base); explicit test.
- **Test churn masking real failures** → suites must be green with *import updates only*; any logic edit during import sweeps is a finding.
- **Release window mistakes** (wrong label, non-release merge releasing) → follow the documented fail-closed procedure exactly; verify tag placement before closing.

## Trace

_(gate memos + evidence appended during execution)_

LOG Phase 1 gate (tier=light, docs-only diff): GLOSSARY + ADR committed; markdown carries no lint/unit surface; scoped ruff proof green on the tree; enumeration cross-check zero-missing both directions (py 85 / ts 122 / 17 modules' publics).
LOG gate-escalation Phase 2: full tier — public-import-surface anchor; ladder: ruff py+ts-scope, pytest 1063, poetry build, tsc, eslint, vitest 496, tsup — all green; ADR map corrected (fetchPublishedDefinition/diffAgainstPublished TS twins existed and were renamed).
LOG gate-escalation Phase 3: full tier — public-import-surface anchor (10+8 modules); ladder: ruff, pytest 1100, poetry build, tsc, eslint, vitest 501, tsup — all green.
LOG fix-on-fail Phase 3: sweep overreach corrupted .venv site-packages (httpx._transports.base) → rm -rf .venv + poetry install; iterator exclusion rule captured as LEARNING anti-pattern (rename-sweep-must-exclude-dependency-trees).
LOG gate-escalation Phase 4: full tier — public-surface anchor incl. wire-visible error_type; ladder: ruff, pytest 1121, poetry build, tsc, eslint, vitest 505, tsup — all green.
LOG wire-safety decision (Phase 4): NodeValidationError split + workflow exception renames carry historical wire names via _wire_error_type / wireErrorType (py/ts) until 1.0.0 — response error_type is consumer-visible; tests pin both directions.
LOG gate-escalation Phase 5 (exit gate): full tier — unconditional; ladder: ruff, pytest 1168, poetry build, tsc, eslint, vitest 506, tsup, pack-test — all green; verification greps clean.
LOG scope addition (Phase 5): manifest class-attribute dual-support added (manifest canonical / legacy definition warns, py+ts) — the committed ADR map missed the attribute because it is not an __all__/index symbol; the epic's core confusion lived in the base class. Wire names and legacy construction unchanged; tests pin both paths.
LOG pack-test catch (Phase 5): TS index eager-exports of app factories (added for parity) pulled express into the core tarball import — pack-test failed; reverted to express.ts subpath architecture (py lazy / TS subpath is the documented asymmetry); parity pairs rescoped.
LOG Step 9 code review round 1: 1 Major (workflow_node_app.py:304 read node.definition — internal code routing through its own fresh deprecated alias; spurious warnings on the serving path, suite warnings 221→86 after fix) + 2 Minor (docstrings teaching legacy attribute) — all fixed in 23c9338; re-gate full tier green. Direct-caller coverage complete (suites + freeze + alias + parity guards + greps). Requirements Gaps: none.
GATE 23c9338 tier=full lint=t typecheck=t build=t unit=t e2e=n.a — exit gate + post-review-fix re-gate; 23c9338 is the gated final implementation SHA Step 10 cites (py 1168 / ts 506 / pack-test green).
LOG CI red-watch round 1 (PR #273): Manifest schema stability failed — pydantic $defs labels track class names so the renames diffed as breaking. Fixed: rename-aware base normalization (structure still enforced, pinned by test both directions) + paths-filter retarget; py 1170 / ts 506 green.
GATE 3e3363d tier=full lint=t typecheck=t build=t unit=t e2e=n.a — red-fix re-gate (10b round 1); 3e3363d is the final pushed SHA for the re-watch.
