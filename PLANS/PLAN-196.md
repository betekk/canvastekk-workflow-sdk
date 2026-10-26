# PLAN: Dual upload contract — capability descriptors + element refs

**Branch**: feat/196
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/196
**Base**: dev

## Acceptance Criteria
- [ ] Legacy descriptor handling remains unchanged on the wire in both SDKs (same JSON fields and status query shape), including array uploads and resume/abort calls
- [ ] Both SDKs accept `multipart-upload-capability` at their inbound request schemas and execute its initiate/complete/abort/status contract in contract tests
- [ ] Replay and array semantics are documented for node authors, including the legacy single-initiate 409 versus capability replay behavior
- [ ] A final SDK release with wheel and TypeScript assets is published and its exact version recorded for the node bumps (post-merge release phase)

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|--------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/uploads.py` | Engine #971 descriptor contract | `request.py` Pydantic parse, `app.py`, `multipart.py`, public `UploadSession` export | high |
| `python/canvastekk_workflow_sdk/request.py` | Widened `UploadSession.kind`; no code edit expected | `/execute` inbound validation and external parser consumers | med |
| `python/canvastekk_workflow_sdk/multipart.py` | Dual descriptor kind | `S3PresignedUploader`, every Python node output upload | high |
| `python/tests/test_multipart_uploads.py`, `python/tests/test_uploads.py` | Python implementation | Default Python CI contract coverage | med |
| `typescript/src/uploads.ts` | Engine #971 descriptor contract | `request.ts` zod parse, `app.ts`, `multipart.ts`, exported descriptor schema | high |
| `typescript/src/request.ts` | Widened zod descriptor; no code edit expected | Express `/execute` and external `NodeExecutionRequestSchema` consumers | med |
| `typescript/src/multipart.ts` | Dual descriptor kind | `S3PresignedUploader`, every TypeScript node output upload | high |
| `typescript/tests/request.test.ts`, `typescript/tests/multipart.test.ts`, `typescript/tests/uploads.test.ts` | TypeScript implementation | TypeScript CI contract coverage | med |
| `python/README.md`, `typescript/README.md` | Final wire semantics | Node authors and the four adoption tickets | low |
| `.github/workflows/release.yml` (unchanged) | `minor` label on the post-merge dev→prod promotion PR | Final version tag, wheel/tgz assets, downstream node pins | med |

The inbound request files are explicit parse-seam consumers per `LEARNINGS/anti-patterns/parity-port-must-widen-wire-schema.md`; widening only the uploader would leave capability descriptors rejected before upload. Both language implementations ship together per the root README parity rule.

## Implementation Phases

### Phase 1: Python dual contract

- [x] **1.1** Widen `UploadSession.kind` to the two engine discriminators, keep `multipart-upload-session` as the default, and document the operation-level legacy/capability differences in the descriptor contract
    — **Why:** Pydantic request parsing must admit the new engine descriptor before the multipart client can feature-detect it; the default preserves existing descriptors constructed without `kind`
    — **Done when:** `NodeExecutionRequest` accepts a complete capability descriptor, an omitted kind still resolves to `multipart-upload-session`, and malformed/unknown kinds remain rejected
    — **Consumers affected:** `request.py`, public `UploadSession`, `multipart.py`, node `/execute` parsing
    — **Done:** UploadSession.kind now accepts session/capability with legacy default; NodeExecutionRequest capability parse, omitted-kind default, and unknown-kind rejection proven; files: python/canvastekk_workflow_sdk/uploads.py, python/tests/test_multipart_uploads.py; fixes: none
- [x] **1.2** Thread capability-only control data through the existing multipart flow: complete and abort add the array element ref only for capabilities; status adds `upload_id` for every capability plus `index`/`suffix` for capability arrays; legacy calls add no body fields or query parameters
    — **Why:** Engine #971 has no server-side session binding on the capability path, while legacy endpoints still require their existing bound-session shapes; one `element if capability else None` value prevents legacy array drift
    — **Done when:** capability single/array flows and legacy single/array flows produce exactly the contract table in Technical Notes, including resume status and best-effort abort
    — **Consumers affected:** Python node uploads against both engine paths; no public method signature changes
    — **Done:** multipart now derives capability-only control element/status params; complete/abort add array element only for capabilities and status adds upload_id plus array coordinates; legacy bodies/URLs unchanged; files: python/canvastekk_workflow_sdk/multipart.py; fixes: none
- [x] **1.3** Add Python wire-contract tests for descriptor parsing, capability single-file status/complete/replay, capability array complete/abort/status, and explicit legacy no-new-fields regressions
    — **Why:** the acceptance criteria require proof at the HTTP boundary, not just model construction; mirrored legacy assertions catch accidental element/query leakage
    — **Done when:** the new tests and all existing Python upload/multipart/request tests pass, with assertions on raw JSON bodies and URL query parameters
    — **Consumers affected:** Python CI and the release's contract evidence
    — **Done:** raw-wire tests cover capability single resume/complete/replay and parameterized legacy/capability array complete/status/abort; affected run 54 passed, full suite 959 passed; files: python/tests/test_multipart_uploads.py; fixes: Ruff formatting only

### Phase 2: TypeScript parity

- [ ] **2.1** Widen `UploadSessionDescriptorSchema.kind` to the same two values with the same legacy default and update its wire documentation
    — **Why:** zod parses `output_upload_url` before the uploader runs, so schema parity is mandatory rather than a type-only change
    — **Done when:** `NodeExecutionRequestSchema` accepts a complete capability descriptor, omitted kind defaults to legacy, and unknown kinds fail parsing
    — **Consumers affected:** `request.ts`, exported descriptor schema, `multipart.ts`, Express `/execute`
- [ ] **2.2** Implement the same capability-only complete/abort element bodies and status query construction in `multipart.ts`, leaving legacy request bodies and URLs unchanged
    — **Why:** both SDK stacks must speak identical engine contracts in the same release; URL `searchParams` preserves correct encoding without string concatenation
    — **Done when:** TypeScript produces the same operation table as Python for capability single/array and legacy single/array flows
    — **Consumers affected:** TypeScript node uploads against both engine paths; no public option/signature changes
- [ ] **2.3** Mirror the Python parsing and raw-wire tests in `request.test.ts`, `multipart.test.ts`, and the existing array uploader coverage
    — **Why:** the repo's feature-parity rule requires mirrored behavioral evidence, not merely equivalent source
    — **Done when:** all new and existing TypeScript request/upload/multipart tests pass, with raw JSON and query assertions for both contracts
    — **Consumers affected:** TypeScript CI and the release's parity evidence

### Phase 3: Migration documentation + ticket exit gate

- [ ] **3.1** Update both README output-upload sections with descriptor feature detection, the operation table, one-MPU-per-array-element behavior, capability replay/no-409 semantics, S3 ListParts resume, and the upgrade-before-engine-flip rule
    — **Why:** node authors need zero handler changes, but operators must not emit capabilities to older SDKs; replay differences otherwise look like legacy 409 regressions
    — **Done when:** both READMEs state that legacy remains supported, old SDKs cannot parse capability descriptors, and nodes must upgrade before the per-env engine flip
    — **Consumers affected:** node adoption tickets #370/#583/#324/#190 and per-env rollout owners
- [ ] **3.2** Run the full Python and TypeScript gates (Ruff + full pytest + wheel/sdist build; ESLint + source/test typechecks + full Vitest + tsup build), tick all pre-release ACs, and append the final-SHA `GATE <sha> tier=full` memo and evidence to Trace
    — **Why:** this is a cross-module public-contract change in both release artifacts; the ticket exit gate is unconditionally full and PR creation cites this memo
    — **Done when:** every check is green on the final implementation tree and the pushed PLAN records the gate SHA and exact commands/results
    — **Consumers affected:** PR gate citation and downstream release consumers

### Phase 4: Post-merge final release (not part of the implementation PR gate)

- [ ] **4.1** After the dev PR merges, promote dev→prod with a `minor`-labeled PR, watch its checks and merge, then verify the Release workflow publishes the next final version with wheel, wheel checksum, and tgz assets; comment the exact tag on #196
    — **Why:** `release.yml` publishes consumer assets only from prod, and node tickets need an immutable final version rather than frozen in-repo version files or a dev prerelease tag
    — **Done when:** the final GitHub Release exists with all three assets and #196 names the verified tag; only then may node adoption pins be updated
    — **Consumers affected:** #370/#583/#324/#190 and `sdk-released` downstream automation

## Technical Notes

Engine #971 merged as `6e96801abc78ac708ba5410ec0349429fd4a15f0`. `kind` is the only client feature-detection signal; token prefixes remain engine-internal and are not parsed by either SDK.

| Operation | Legacy session | Capability single-file | Capability array |
|-----------|----------------|------------------------|------------------|
| Initiate body | Existing fields; array adds `element` | Same as legacy single | Same as legacy array |
| Complete body | Existing `upload_id` + `parts`; never add `element` | Add nothing | Add `element: {index, suffix}` |
| Abort body | Existing `upload_id`; never add `element` | Add nothing | Add `element: {index, suffix}` |
| Status request | Existing bare GET, even for arrays | `?upload_id=...` | `?upload_id=...&index=...&suffix=...` |

The SDK already resumes from the engine's S3 `ListParts`-backed status response; this ticket changes only how capability status is addressed. Legacy single-file re-initiate retains the engine's 409 behavior. Capability replay may create a fresh MPU instead of returning that 409; the SDK does not convert replay into success by itself and the 7-day incomplete-MPU lifecycle remains the orphan backstop.

Version files stay frozen: release CI stamps versions ephemerally from the tag (#2039). The implementation PR gets `minor`; critically, the later dev→prod promotion PR also gets `minor`, because prod's release workflow reads that promotion's label.

## Dependencies

- Engine #971 is merged; devops #901 supplied the per-env key and MPU lifecycle evidence.
- Parent epic: betekk/canvastekk-tracker#4085.
- Downstream node tickets remain held until Phase 4 publishes the final SDK assets.

## Risks & Mitigation

- **Legacy arrays accidentally gain capability fields** → derive control element/status params only when `kind == multipart-upload-capability`; raw-wire legacy array tests are mandatory.
- **Capability descriptors die at request validation** → explicit Pydantic and zod inbound parse tests cover the seam before uploader tests.
- **Status query leaks into legacy URLs** → legacy tests assert an empty query on resume status; implementation passes no params on that branch.
- **Old nodes receive capabilities before upgrade** → engine flag remains off; both READMEs and the PR checklist require fleet SDK upgrades before any per-env flip.
- **Release remains a dev prerelease without assets** → Phase 4 requires the prod promotion and verifies the three final assets before unblocking nodes.

## Trace
LOG full-gate escalation: Phase 1 changed the public Pydantic schema and multipart client with cross-module/fleet consumers
LOG Phase 1 commands: Ruff check + scoped format, compileall, full pytest (959 passed), poetry build (wheel + sdist); E2E n.a (SDK transport, no frontend)
GATE pending-phase1 tier=full lint=t typecheck=t build=t unit=t e2e=n.a
