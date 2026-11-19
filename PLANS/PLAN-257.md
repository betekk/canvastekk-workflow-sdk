# PLAN: Registry schemas must not require `error` as a node output

**Branch**: feat/257
**Issue**: betekk/canvastekk-workflow-sdk#257
**Base**: prod

## Acceptance Criteria

- [ ] Generated schemas no longer require `error` — the SDK rejects, at definition time (both packages), any `output_schema` whose `required` array lists an envelope-reserved field (`error`, `error_type`, `error_code`), so protocol-invalid schemas cannot reach the registry; optional envelope-shaped properties stay legal (ErrorOutputNode error-append compat, `contracts.build_check_output_schema`)
- [ ] Contract-authoring docs updated — `docs/EXTERNAL-AUTHOR-GUIDE.md` documents where `error` lives (response envelope, never `outputs`); assistant skill contract table gains the rule (mirrored to `.agents/skills`); README sweeps (root + python + typescript)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|--------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/definition.py` `WorkflowNodeManifest` new model_validator `_validate_output_schema_required_fields` | — | every python SDK surface: `BaseNode` init, `build_registry_payload`/`register_node`, `/manifest` endpoint, CLI `validate`, `diff`, engine registry ingestion (exact wheel pin), all node authors | medium — new definition-time hard error; fires only on protocol-invalid manifests (repo-wide grep: zero existing manifests/tests/goldens require envelope fields in outputs) |
| `typescript/src/definition.ts` zod manifest schema + new `validateOutputSchemaRequiredFields` | — | ts package mirrors python: `BaseNode`, `buildRegistryPayload`, `app`, workflow builder; js node authors | medium — same semantics, same blast radius |
| `python/tests/test_definition.py` + `typescript/tests/definition.test.ts` | validators (1.1, 2.1) | CI suites | low |
| `docs/EXTERNAL-AUTHOR-GUIDE.md` | — | external contract authors (the audience the #257 outage hit) | low |
| `python/canvastekk_workflow_sdk/data/skills/canvastekk-workflow-sdk-assistant/SKILL.md` + `.agents/skills/canvastekk-workflow-sdk-assistant/SKILL.md` | — | agents authoring nodes; CI `skill-mirror-guard` (`diff -r`) requires both copies identical | low — but both copies must land in one commit or CI guard fails |
| `README.md`, `python/README.md`, `typescript/README.md` | — | humans; per LEARNINGS py-ts-sdk-changes-sweep-root-readme | low |

## Implementation Phases

### Phase 1: Python definition-time guard

- [x] **1.1** Add `@model_validator(mode="after")` `_validate_output_schema_required_fields` to `WorkflowNodeManifest` (`python/canvastekk_workflow_sdk/definition.py`): if `output_schema["required"]` (when a list) intersects `{"error", "error_type", "error_code"}`, raise `ValueError` naming the offending field(s), stating the protocol fact (`error` et al. are returned on the response envelope, never in `outputs`), and pointing at the guide. Optional properties with those names are NOT rejected.
    — **Why:** root-cause fix at the single chokepoint every registered manifest routes through (same precedent as the `format: "binary"` definition-time rejection); prevents new protocol-invalid registry entries instead of cleaning up after them
    — **Done when:** constructing a manifest whose output_schema requires `error` raises `ValueError` matching the message; a manifest with an optional `error` property (e.g. `build_check_output_schema` output) still constructs
    — **Consumers affected:** all python SDK surfaces + node authors; zero existing in-repo manifests/tests/goldens affected (verified by grep)
    — **Done:** validator added after `_validate_file_field_formats` with module-level `ENVELOPE_RESERVED_OUTPUT_FIELDS` frozenset (class-attr form avoided — ModelPrivateAttr trap from DA-2627 history); message names fields + protocol fact + guide; files: `python/canvastekk_workflow_sdk/definition.py`; fixes: none

- [x] **1.2** Tests in `python/tests/test_definition.py` (class holding the binary-format tests): (a) rejects each of `error`/`error_type`/`error_code` in output_schema required; (b) accepts output_schema with optional `error` property — pin the `build_check_output_schema` compat; (c) accepts `error` required in input_schema (not protocol-invalid); (d) `required` absent or non-list does not raise.
    — **Why:** the guard's boundary (required-only, output-only, family-of-three) is the safety property; pinned tests stop a future refactor from silently widening or narrowing it
    — **Done when:** `pytest python/tests/test_definition.py` green, new tests fail if the validator is removed
    — **Consumers affected:** CI python suite
    — **Done:** four tests added beside the binary-format tests (rejects-each-field, optional-error via build_check_output_schema, input-side error legal, absent/non-list required safe); test_definition.py 110 passed, full suite 1020 passed 1 skipped via main-checkout poetry venv (worktree lacks its own fastapi extra); files: `python/tests/test_definition.py`; fixes: ruff I001 import order (auto-fixed)

### Phase 2: TypeScript definition-time guard (parity)

- [x] **2.1** Add `validateOutputSchemaRequiredFields(schema)` to `typescript/src/definition.ts`, called from the manifest schema's existing `superRefine` where `validateFileFieldFormats` runs on `output_schema`; identical semantics and near-identical message to python (parity suites compare behavior). Close the parse-site gap (architecture review finding 1): `registerNode` builds its payload from `WorkflowNodeManifestSchema.parse(node.definition)` — parse is otherwise lazy (`base-node.ts` `getDefinition`) and the CLI path (`cli.ts:324`) is the only eager parse today, so a direct `registerNode({ definition: <literal> })` caller would ship an unvalidated manifest.
    — **Why:** the ts package registers the same registry; a python-only guard leaves js-authored nodes able to reintroduce the outage, and structural typing lets object literals skip lazy validation on the direct-API path
    — **Done when:** `WorkflowNodeManifestSchema.parse` throws for required-`error` output schemas and passes for optional-`error` ones; `registerNode` parses before building the payload (test pins a literal definition reaching `buildRegistryPayload` validated)
    — **Consumers affected:** ts SDK surfaces + js node authors
    — **Done:** exported `ENVELOPE_RESERVED_OUTPUT_FIELDS` + `validateOutputSchemaRequiredFields` hooked into the manifest transform's existing try/catch (throws surface as zod issues); `registerNode` payload build now parses (registry.ts, comment cites the lazy-parse gap); files: `typescript/src/definition.ts`, `typescript/src/registry.ts`; fixes: none

- [x] **2.2** Mirror tests in `typescript/tests/definition.test.ts` covering the same four cases as 1.2, plus one `registerNode` test pinning that a raw literal definition with required-`error` outputs is rejected before any network call.
    — **Why:** same boundary-pinning as 1.2, ts side; the registerNode parse hook needs its own pin (it is the fix for the architecture-review bypass finding)
    — **Done when:** `vitest run definition.test.ts registry.test.ts` green
    — **Consumers affected:** CI ts suite
    — **Done:** it.each over the three envelope fields + optional-error + input-side-error + absent/non-list required tests in definition.test.ts; registerNode raw-literal test asserts /envelope field/ rejection with `fetched === false`; definition+registry 107 passed, full ts suite 480 passed; files: `typescript/tests/definition.test.ts`, `typescript/tests/registry.test.ts`; fixes: none

### Phase 3: Contract-authoring docs + skill mirror + README sweep

- [ ] **3.1** `docs/EXTERNAL-AUTHOR-GUIDE.md`: add an "Error fields live on the envelope" note in the output-schema/contract-authoring area — `error`, `error_type`, `error_code` are response-envelope fields (`NodeExecutionResponse`), `outputs` carries only `output_schema`-shaped values and only on `pass`; output schemas must not require envelope fields (SDK rejects at definition time, #257).
    — **Why:** AC "contract-authoring docs updated" — the guide is the document the misrequiring contract authors followed
    — **Done when:** guide states where error lives and the new rule in ≥1 findable place (`rg "envelope"` hits it)
    — **Consumers affected:** external authors

- [ ] **3.2** Assistant skill contract table (`python/canvastekk_workflow_sdk/data/skills/canvastekk-workflow-sdk-assistant/SKILL.md`) gains the rule row in **Schema rules** ("output_schema `required` must never list `error`/`error_type`/`error_code` — envelope fields, never outputs; SDK rejects at definition time"); copy the file byte-identically to `.agents/skills/canvastekk-workflow-sdk-assistant/SKILL.md`.
    — **Why:** the skill gates node creation; the CI `skill-mirror-guard` `diff -r` fails unless both copies land together
    — **Done when:** `diff -r .agents/skills python/canvastekk_workflow_sdk/data/skills` exits 0
    — **Consumers affected:** node-authoring agents, CI mirror guard

- [ ] **3.3** README sweeps: root `README.md` validation table row ("`WorkflowNodeManifest` rejects envelope fields in output_schema `required`") + the same one-liner in `python/README.md` and `typescript/README.md` near their existing manifest/file-format validation notes.
    — **Why:** LEARNINGS py-ts-sdk-changes-sweep-root-readme — SDK behavior changes must sweep the root README in the same change; package READMEs document the validation surface
    — **Done when:** all three READMEs mention the guard; no stale claims contradict it
    — **Consumers affected:** humans reading the docs

### Phase 4: Exit gate + trace

- [ ] **4.1** Run the ticket exit gate at `tier=full` (python: ruff + pytest from `python/`; ts: lint + typecheck + build + vitest from `typescript/`; skill-mirror `diff -r`), append the `GATE <sha> tier=full` memo line and phase LOG lines to this PLAN's Trace, commit ticks + trace, push.
    — **Why:** the ticket exit gate is the run's last gate and must be full (verification-loop-skill tiered gating); Step 10a cites this memo line for the pushed SHA
    — **Done when:** green `tier=full` memo line exists for the final pushed SHA
    — **Consumers affected:** PR gate citation

## Technical Notes

- Protocol fact (prod base, `python/canvastekk_workflow_sdk/response.py`): `NodeExecutionResponse` carries `error`/`error_type`/`error_code` as envelope fields; `outputs` is populated only on `status="pass"` and is validated against `output_schema` (`base.py` `validate_outputs`). A schema requiring `error` in outputs can never be satisfied by a passing run — exactly the #1266-class failure.
- Engine ingestion pins the SDK by exact wheel version, so this hard error cannot break engine re-parses until a deliberate SDK bump adopts it.
- `build_check_output_schema` (py `contracts.py` + ts `contracts/check-output.ts`) already omits `error` from `required`; its optional nullable `error` property is deliberate (ErrorOutputNode error-append rewrite) and stays legal.
- CHANGELOG is git-cliff generated at release — no manual edit.

## Dependencies

None blocking (parent epic tracker#4295 lists A7 as independent). No new external dependencies.

## Risks & Mitigation

- **Risk:** a downstream node repo has an existing manifest requiring `error` — adoption of the new SDK hard-fails it at construction. **Mitigation:** that manifest is already protocol-broken (its required output can never be produced); the error message names the fix. Repo-wide grep shows zero in-repo offenders.
- **Risk:** mirror-copy drift between `.agents/skills` and `data/skills`. **Mitigation:** byte-identical copy in the same commit; CI guard verifies.

## Trace

GATE 7ce10a9 tier=light lint=t typecheck=n.a build=- unit=t e2e=n.a
LOG Phase 1 gate: ruff scoped errored once (I001 import order, auto-fixed), then green; test_definition.py 110 passed; full python suite 1020 passed 1 skipped (main-checkout poetry venv; worktree lacks fastapi extra). GATE memo follows the phase commit.
LOG Phase 2 gate (green first try): eslint scoped on definition/registry + tests, tsc typecheck + typecheck:tests, definition+registry 107 passed, full ts suite 480 passed (npm ci run in worktree — node_modules is untracked and not inherited).

