# PLAN: Remove deprecated name aliases and release 1.0.0

**Branch**: feat/272
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/272
**Base**: dev

## Acceptance Criteria

- [ ] A search across every dependent repo's `origin/dev` finds no old SDK name (result recorded on this ticket)
- [ ] Shims and aliases removed in Python and TypeScript; guard test fails if one returns
- [ ] Released as 1.0.0 with a migration note in the changelog

## Dependency & Consumer Map

The 0.67.0 rename (#271, ADR 0001) left three alias mechanisms, each marked "removal in 1.0.0 (#272)": old-path shim modules (17 Python files + 13 TypeScript files), old public-name aliases (Python lazy `__getattr__` at package root + PEP 562 blocks in 5 non-renamed modules + TypeScript `index.ts` re-export blocks + the `NodeAuth` const in `auth.ts`), and the legacy `definition` class attribute dual-support on the node base class in both stacks. Every row with an external consumer is cross-module: the whole point of the aliases was consumer compatibility.

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| AC-1 evidence: `git grep` of old names over `origin/dev` in the 8 dependent repos (workflow-engine, workflow-nodes, llm-service, ml-service, audio-service-app, ifc-service-app, point-cloud-app, report-service-v2), result comment on #272 | — | ticket AC-1; go/no-go for every deletion below | low (read-only; a hit stops the run) |
| 17 Python shim modules (`definition.py`, `diff.py`, `registry.py`, `convergence.py`, `conformance.py`, `base.py`, `app.py`, `router.py`, `request.py`, `response.py`, `context.py`, `protocol.py`, `uploads.py`, `multipart.py`, `contracts.py`, `workflow/models.py`, `workflow/executor.py`) — delete | AC-1 green | only external old-path importers (verified none by AC-1); `test_rename_aliases.py` (rewritten in same phase); wheel build (files leave the package) | high |
| 13 TypeScript shim files (`definition.ts`, `diff.ts`, `registry.ts`, `base-node.ts`, `app.ts`, `request.ts`, `response.ts`, `context.ts`, `protocol.ts`, `uploads.ts`, `multipart.ts`, `workflow/models.ts`, `workflow/executor.ts`) — delete | AC-1 green | only external old-path importers (verified none by AC-1); `rename-aliases.test.ts` (rewritten in same phase); tsup build | high |
| `python/canvastekk_workflow_sdk/__init__.py`: `_DEPRECATED_NAME_ALIASES` map + its `__getattr__` branch | shim deletion (same commit) | old-name root imports (`from canvastekk_workflow_sdk import BaseNode`) — consumers verified migrated | high |
| PEP 562 `_DEPRECATED_ALIASES` blocks in `exceptions.py`, `bootstrap.py`, `observability.py`, `workflow/validation.py`, `workflow/runner.py` | — | old-name module-level imports | medium |
| `typescript/src/index.ts` deprecated alias blocks (phase 3 + phase 4 + manifest/registry blocks) and `typescript/src/auth.ts` `NodeAuth` deprecated const | — | old-name index imports; `rename-aliases.test.ts` | high |
| `definition` attribute dual-support: `workflow_node_base.py` legacy descriptor + `workflow-node-base.ts` deprecated getter and the internal `?? self.definition` fallback read | — | legacy node classes that named their manifest `definition`; `test_legacy_definition_class_attribute_still_works_and_warns` (removed in same phase) | high |
| Guard inversion: rewrite `python/tests/test_rename_aliases.py` (old paths now `ModuleNotFoundError`, old names `AttributeError`), retarget `python/tests/test_consumer_import_freeze.py` rows to the new names/paths (deliberate, reviewed staleness change per LEARNINGS), update `python/tests/test_rename_map.py` expectations, rewrite `typescript/tests/rename-aliases.test.ts` as absence guards, retarget the 10 TS test files importing old `../src/*.js` paths | alias deletions (same commit — a red gate otherwise) | CI suites both stacks; future regressions (the "fails if one returns" AC) | medium |
| Surface sweep: `examples/echo_node/handler.py` (still imports `BaseNode`/`ExecutionContext`), `python/README.md` + `typescript/README.md` migration sections, `docs/EXTERNAL-AUTHOR-GUIDE.md`, `docs/COMPATIBILITY-v0.64.0.md`, `docs/adr/0001-explicit-node-naming.md` (consequences: removal executed), bundled skills ×2 copies (`.agents/skills/**` + `python/canvastekk_workflow_sdk/data/skills/**`), `.github/workflows/ci-python.yml` paths-filter row for `definition.py`, `CHANGELOG.md` `## [1.0.0]` migration entry | alias deletions (docs describe the new state) | external node authors; CI paths-filter; PR reviewers | medium |
| Release pipeline + gate-script alias consumers (architecture-review F1/F2): `.github/workflows/release.yml` pre-publish/post-publish smoke tests, `typescript/scripts/pack-test.sh` root-alias assertion | alias deletions (same commit — they import/assert removed root names) | the 1.0.0 publish job itself; the Phase 4.1 exit gate | high |
| Release staging: PR labels `release` + `major` (v0.67.0 → v1.0.0 via `mathieudutour/github-tag-action`); post-merge append of the migration note to the `v1.0.0` GitHub Release body (cliff renders subjects only — commit bodies never reach it) | all phases merged | release workflow (tag → cliff → publish → nodes-repo rebuild dispatch); every dependent repo | medium |

Kept by design (recorded so reviewers can challenge): `NodeValidationError` stays a public class — it is the runtime base of `WorkflowNodeManifestValidationError` and `NodeInputValidationError`, exported non-deprecated in both stacks; the wire `error_type` strings (`"NodeValidationError"`, `"WorkflowExecutionError"`, `"WorkflowValidationError"`) are unchanged per ADR 0001 "no wire change". `check_schema_stability.py` `RENAMED_MODELS` canonicalization stays — BASE dumps come from pre-rename tags.

## Implementation Phases

### Phase 1: AC-1 evidence — dependent-repo search, recorded on the ticket

- [ ] **1.1** For each of the 8 dependent repos, `git fetch origin dev` in the local sibling checkout and run a tracked-files-only `git grep` at `origin/dev` for old SDK names: (a) old module paths (`canvastekk_workflow_sdk.(definition|diff|registry|convergence|conformance|base|app|router|request|response|context|protocol|uploads|multipart|contracts)( |$|\.` + `workflow.(models|executor)`, and `@betekk/canvastekk-workflow-sdk/(definition|diff|registry|base-node|app|request|response|context|protocol|uploads|multipart|contracts|workflow/(models|executor))` deep imports); (b) old public names on SDK-mentioning lines (import-from-sdk lines or `sdk.` attribute access matching `BaseNode|ExecutionContext|ExecutionMetric|MetricsCollector|HealthResponse|LivenessResponse|ReadinessResponse|MetricsSummaryResponse|MultiNodeHealthResponse|NodeExecutionStatus|parse_node_execution_status|parseNodeExecutionStatus|NODE_PROTOCOL_HEADER|NODE_PROTOCOL_VERSION|PROTOCOL_2_OUTCOMES|outcome_for_protocol|outcomeForProtocol|read_outcome|readOutcome|requested_protocol|requestedProtocol|OutputUploader|S3PresignedUploader|UploadSession|UploadTarget|UploadSessionDescriptor|get_default_uploader|getDefaultUploader|upload_via_session|uploadViaSession|BaseContract|BaseContractData|CONTRACT_VERSION|create_node_app|createNodeApp|create_multi_node_app|createMultiNodeApp|mount_node|mountNode|create_authed_app|createAuthedApp|create_lambda_handler|createLambdaHandler|ValidationResult|NodeResult|ErrorPolicy|NodeExecutor|InProcessExecutor|HttpExecutor|WorkflowExecutionError|WorkflowValidationError|export_definition|exportDefinition|NodeContract|ContractCapabilities|RetryConfig|ColorPreset|DeprecationInfo|SDK_SERVED_CONTRACT_ROUTES|RegisterNodeResult|RegistrationError|register_node\b|registerNode\b|build_registry_payload|buildRegistryPayload|fetch_published_definition|fetchPublishedDefinition|diff_against_published|diffAgainstPublished|diff_manifests|diffManifests|ManifestDiff|getNodeId|NodeAuth\b`); (c) an unconstrained second net for the rarest tokens (`export_definition|exportDefinition|SDK_SERVED_CONTRACT_ROUTES|MultiNodeHealthResponse|MetricsSummaryResponse`) to catch attribute-style uses off SDK-importing lines
    — **Why:** AC-1 is the go/no-go gate for every deletion in Phase 2; the search must run against each repo's `origin/dev` (tracked files only — `git grep <ref>` cannot walk venv/node_modules), not the local checkout's working branch. Architecture-review F3: consumer repos keep negative-test fixtures quoting old names as planted violations (e.g. llm-service `fastapi_gateway_app/tests/test_vocabulary_guard.py:204-212` self-tests its guard by planting `from canvastekk_workflow_sdk.definition import …`) — a raw zero-hit predicate would stall the run on those.
    — **Done when:** all 8 repos searched with (a)+(b)+(c); per-repo hit counts captured; zero *unclassified* hits — every hit either zero or a cited negative-test/guard fixture quoting old names as planted violations, with the classification listed per repo.
    — **Consumers affected:** none (read-only); a non-empty result stops this plan and reports on the ticket.
- [ ] **1.2** Post the search result to #272 as a comment (per-repo: ref searched, patterns, hit count 0), satisfying AC-1's "result recorded on this ticket"
    — **Why:** the AC demands the evidence on the ticket, not only in the PR.
    — **Done when:** `gh issue comment 272` posted and visible.
    — **Consumers affected:** ticket readers; epic #4301 close-out audit.

### Phase 2: The removal — shims, aliases, `definition` dual-support, inverted guards (py+ts one commit)

- [ ] **2.1** Delete the 17 Python shim modules and the 13 TypeScript shim files listed in the Consumer Map (`git rm`)
    — **Why:** the shims are the old module paths; deleting them is the ticket's core ask and must land before/with the guard inversion so the gate ends green.
    — **Done when:** `git status` shows exactly those 30 deletions; `python -c "import canvastekk_workflow_sdk.workflow_node_manifest"` still succeeds; `ls typescript/src/*.ts` shows no shim filenames.
    — **Consumers affected:** external old-path importers (verified zero by 1.1); wheel/tsup artifacts (files leave the build).
- [ ] **2.2** Remove `_DEPRECATED_NAME_ALIASES` and its `__getattr__` branch from `python/canvastekk_workflow_sdk/__init__.py`; remove the PEP 562 `_DEPRECATED_ALIASES` blocks from `exceptions.py`, `bootstrap.py`, `observability.py`, `workflow/validation.py`, `workflow/runner.py`
    — **Why:** package-root and in-module old-name resolution is the second alias mechanism; leaving it after deleting shims would strand half the aliases.
    — **Done when:** `grep -rn "_DEPRECATED" python/canvastekk_workflow_sdk/` is empty; `python -c "import canvastekk_workflow_sdk as s; getattr(s, 'BaseNode')"` raises `AttributeError`.
    — **Consumers affected:** old-name importers (verified zero); `_LAZY_SERVER_EXPORTS` machinery stays untouched.
- [ ] **2.3** Remove the deprecated alias blocks from `typescript/src/index.ts` (phase-3 block, phase-4 block, manifest/registry block, and the `NodeAuth` re-export) and the `NodeAuth` deprecated const from `typescript/src/auth.ts` (class keeps the canonical `TekkNodeAuth` name)
    — **Why:** the TS index aliases are the third alias mechanism; the py/ts parity rule requires both stacks change in the same commit.
    — **Done when:** `grep -n "@deprecated" typescript/src/index.ts typescript/src/auth.ts` returns nothing; `npm run build` succeeds.
    — **Consumers affected:** old-name index importers (verified zero); TS consumers using `NodeAuth` (verified zero by 1.1 — Python keeps its distinct `NodeAuth` FastAPI class, TS drops the alias).
- [ ] **2.4** Remove the legacy `definition` attribute dual-support: the descriptor in `python/canvastekk_workflow_sdk/workflow_node_base.py` (including class-attribute warning support), and in `typescript/src/workflow-node-base.ts` the deprecated `get definition()` plus the internal `?? self.definition` fallback in the manifest read path — canonical `manifest` only, both stacks
    — **Why:** the dual-support is a deprecated alias in attribute form; keeping it would leave "definition" alive on node classes after 1.0.0.
    — **Done when:** py: `node.definition` raises `AttributeError` on a canonical class, declaring `definition = WorkflowNodeManifest(...)` no longer feeds `node.manifest`; ts: `node.definition` is `undefined`-free (no getter), manifest read no longer consults a legacy field; both stacks' suites green.
    — **Consumers affected:** legacy node classes (verified zero — consumers migrated via #697/#809/…); internal health-slug path already reads the canonical manifest (#275).
- [ ] **2.5** Rewrite `python/tests/test_rename_aliases.py` as absence guards: all 17 old module paths raise `ModuleNotFoundError` on import; all old public names raise `AttributeError` from the package root and from their old home modules; `WorkflowNodeBase` no longer accepts/services `definition`; delete the legacy-attribute warning test; keep `test_node_validation_error_split_preserves_catching` and `test_split_wire_names_unchanged` (kept-by-design rows)
    — **Why:** the ticket demands a guard that fails if any alias returns; inverting in the same commit keeps the phase gate green.
    — **Done when:** `pytest python/tests/test_rename_aliases.py` green with the inverted assertions.
    — **Consumers affected:** CI python suite.
- [ ] **2.6** Retarget `python/tests/test_consumer_import_freeze.py`: old rows (`canvastekk_workflow_sdk.definition`/`.app`/`.registry`/`.contracts`, root names `BaseNode`/`ExecutionContext`/`create_authed_app`/`mount_node`/`create_lambda_handler`) move to the new modules and names, cross-checked against what the migrated consumers actually import (per the 1.1 evidence); update `python/tests/test_rename_map.py` expected surfaces if it pins the alias-era export counts
    — **Why:** the freeze suite is the consumer-surface oracle; with consumers migrated and aliases gone, the old rows would red — retargeting is the deliberate, separately reviewed staleness change the LEARNINGS convention reserves for exactly this ticket.
    — **Done when:** `pytest python/tests/test_consumer_import_freeze.py python/tests/test_rename_map.py` green; every row resolves against a real module path.
    — **Consumers affected:** CI python suite; future rename oracles.
- [ ] **2.7** Rewrite `typescript/tests/rename-aliases.test.ts` as absence guards (dynamic `import()` of each old path rejects; old names absent from the index namespace object) and retarget the old-path imports in the 10 TS test files (`app`, `base-node`, `bootstrap`, `cli`, `definition`, `deprecation-pipeline`, `diff`, `protocol`, `registry` + `rename-aliases`) to the new module paths; rename `tests/definition.test.ts` → `tests/workflow-node-manifest.test.ts` and `tests/diff.test.ts` → `tests/workflow-node-manifest-diff.test.ts` to keep test names honest
    — **Why:** TS tests must not import through shims once deleted; the parity rule makes the TS guard inversion the twin of 2.5.
    — **Done when:** `grep -rn 'src/\(definition\|diff\|registry\|base-node\|app\|request\|response\|context\|protocol\|uploads\|multipart\)\.js\|src/workflow/\(models\|executor\)\.js' typescript/tests/` is empty (absence-guard dynamic imports in rename-aliases.test.ts are the sanctioned exception, asserted to reject); `npm run test` green.
    — **Consumers affected:** CI typescript suite.
- [ ] **2.8** Sweep SDK-internal references to the old surface so nothing routes through a deleted path: `grep -rn` old paths/names across `python/`, `typescript/` (src **and scripts**), and `.github/workflows/` — excluding tests already handled and `check_schema_stability.py`'s `RENAMED_MODELS` (kept by design); fix every hit. Architecture-review F1+F2 named the two known hits: `.github/workflows/release.yml:121` and `:170` (pre-publish + post-publish smoke tests import root aliases `RetryConfig, BaseNode, ExecutionContext` → canonical `WorkflowNodeRetryConfig, WorkflowNodeBase, NodeExecutionContext` — the release that ships 1.0.0 must not die on its own smoke test) and `typescript/scripts/pack-test.sh:25` (pins `root.BaseNode` → `root.WorkflowNodeBase`)
    — **Why:** ADR 0001's "internal code never routes through a shim" invariant must survive the deletion; #271's review already fixed the known `workflow_node_app` health-path case, this proves none remain — including CI publish steps and gate scripts, which are alias consumers exactly like source files.
    — **Done when:** the sweep grep over `python/`, `typescript/`, and `.github/workflows/` returns zero old-path imports and zero old-name references outside kept-by-design rows (release.yml smoke tests and pack-test.sh included).
    — **Consumers affected:** wheel/tsup builds and the release pipeline's publish job (a missed internal import breaks them — the full gate catches the builds; the release.yml sweep protects the post-merge publish).

### Phase 3: Surface sweep — docs, examples, bundled skills, CI filter, changelog entry

- [ ] **3.1** Update every teaching surface to the post-removal state: `examples/echo_node/handler.py` (retarget `BaseNode`→`WorkflowNodeBase`, `ExecutionContext`→`NodeExecutionContext`), migration sections in `python/README.md` + `typescript/README.md` + `docs/EXTERNAL-AUTHOR-GUIDE.md` + `docs/COMPATIBILITY-v0.64.0.md` ("deprecated but works" → "removed in 1.0.0; see ADR 0001 map"), bundled skill copies `.agents/skills/canvastekk-node-patterns/SKILL.md`, `.agents/skills/canvastekk-workflow-sdk-assistant/SKILL.md` and their `python/canvastekk_workflow_sdk/data/skills/` mirrors (byte-identical pairs stay identical)
    — **Why:** LEARNINGS `py-ts-sdk-changes-sweep-root-readme` + `incomplete-deprecation-sweep-in-docs`: a doc that still teaches an old name after 1.0.0 ships dead code to every new author; the mirrors drift if swept unequally.
    — **Done when:** repo-wide grep for old names over `README.md docs/ examples/ .agents/ python/canvastekk_workflow_sdk/data/` returns only historical/ADR-map mentions (tables explicitly documenting old→new) and zero runnable code samples using old names; mirror pairs `diff` clean.
    — **Consumers affected:** external node authors; the SDK-assistant skill's shipped guidance.
- [ ] **3.2** Update `docs/adr/0001-explicit-node-naming.md` Consequences: record the 1.0.0 removal as executed (shims/aliases/`definition` dual-support gone, guards inverted, `NodeValidationError` + wire names kept by design)
    — **Why:** the ADR is the rename law; its "removed in 1.0.0 (#272)" promises need a closing record or the doc reads as perpetually pending.
    — **Done when:** ADR committed with the removal record; kept-by-design note present.
    — **Consumers affected:** future readers; Step 7 reviewers.
- [ ] **3.3** Remove the dead `python/canvastekk_workflow_sdk/definition.py` row from the `.github/workflows/ci-python.yml` paths-filter (the other rows already point at renamed modules)
    — **Why:** the filter row references a file deleted in Phase 2; leaving it is a dead trigger path.
    — **Done when:** `grep -n "definition.py" .github/workflows/ci-python.yml` empty; YAML still parses.
    — **Consumers affected:** CI job gating (schema-stability leg).
- [ ] **3.4** Add the `## [1.0.0] - 2026-11-20` breaking-change entry to `CHANGELOG.md`: removal summary, migration note pointing at the ADR 0001 old→new tables and the explicit upgrade rule (0.67.0 aliases → 1.0.0 explicit names), kept-by-design note for `NodeValidationError` and wire strings
    — **Why:** AC-3 demands the migration note in the changelog; the in-repo `CHANGELOG.md` is the only file of that name and the cliff-generated GitHub Release body renders commit subjects only — the durable note must be committed.
    — **Done when:** entry committed at the top of `CHANGELOG.md` with the migration note.
    — **Consumers affected:** upgrading consumers; release-notes readers.

### Phase 4: Exit gate + release staging

- [ ] **4.1** Run the full-tier exit gate over both stacks (ruff, pytest, poetry build, tsc, eslint, vitest, tsup, pack-test per `verification-loop-skill`) and append the `GATE <short-sha> tier=full` memo to this PLAN's Trace
    — **Why:** the ticket exit gate is full by pipeline rule; Step 10a's PR creation cites this memo.
    — **Done when:** all legs green; memo line present with the final implementation SHA.
    — **Consumers affected:** PR gate citation; merge watcher decision.
- [ ] **4.2** Release staging (recorded, executed post-merge): PR carries labels `release` + `major` so the merged squash mints `v1.0.0` from `v0.67.0`; after the merge notification lands, append the migration note to the `v1.0.0` GitHub Release body (`gh release edit`) since cliff-generated notes carry commit subjects only
    — **Why:** AC-3; version files are never hand-bumped (release pipeline stamps all five sources tag-derived — verified in `release.yml`/`bump_versions.py`), so the label pair is the only in-PR release action.
    — **Done when:** PR created with both labels; post-merge steps recorded here and executed at the merge notification (tick only after the release body carries the note).
    — **Consumers affected:** release workflow (tag → cliff → publish → nodes-repo rebuild dispatch); every dependent repo's next rebuild.

## Technical Notes

- Ticket: delete the Python shim modules and the deprecated aliases in both languages; release 1.0.0 (breaking). Base: dev at v0.67.0 (#276).
- ADR 0001 (`docs/adr/0001-explicit-node-naming.md`) is the complete old→new law: module map (17 rows), renamed-symbol clusters, kept-symbol list.
- Release mechanism (verified on `reusable-release.yml`): PR merged to `dev` with `release` label + bump label (`major`) → `mathieudutour/github-tag-action` mints the tag → cliff generates the GitHub Release body from commit subjects (`commit.message` only — bodies and footers never render) → publish job stamps all five version sources tag-derived (`bump_versions.py`), builds and publishes wheel + tarball, dispatches the nodes-repo rebuild. Version files in-repo stay at 0.54.0 by design (ephemeral stamping).
- The freeze suite convention (`LEARNINGS/conventions/consumer-import-freeze-is-rename-oracle.md`): staleness changes are deliberate and separately reviewed — this ticket is that review.
- Dependency trees exclusion rule (`LEARNINGS/anti-patterns/rename-sweep-must-exclude-dependency-trees.md`): any sweep runs `git grep` on refs (tracked files only) or excludes `.venv`/`node_modules`/`dist`/`__pycache__` at collection time.

## Dependencies

- Parent: betekk/canvastekk-tracker#4301
- blocked-by (all verified CLOSED 2026-11-20): workflow-engine#1329, workflow-nodes#697, llm-service#809, ml-service#196, audio-service-app#308, ifc-service-app#553, point-cloud-app#407, report-service-v2#256

## Risks & Mitigation

- **A dependent repo regresses an old name after its migration PR** → Phase 1's recorded search is the empirical gate; any hit stops the run before deletion.
- **A missed internal old-path import breaks the wheel/tsup build** → 2.8 sweep + full-tier gate builds both packages.
- **Freeze-suite retarget over-reaches** (retargeting to names consumers don't use) → rows cross-checked against the 1.1 evidence of what consumers actually import.
- **1.0.0 ships with a stale doc teaching a dead name** → 3.1's repo-wide grep is the exit leg (LEARNINGS doc-sweep rule).
- **Release mints the wrong version** → label pair `release`+`major` verified against the workflow's label→bump mapping and the current `v0.67.0` tag before PR creation.

## Trace

(gate memos appended per phase during execution)
