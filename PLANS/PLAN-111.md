# PLAN: dry_run execution semantics (side-effect-free validation)

**Branch**: feat/111
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/111
**Base**: main

## Acceptance Criteria
- [ ] AC1: dry_run request/response fields present in BOTH python and TS packages (parity)
- [ ] AC2: harness branch: full validation runs, no executor invocation, token_cost 0, ids namespaced dryrun-*
- [ ] AC3: contract doc for self-hosted implementers ships (what dry_run must and must not do)
- [ ] AC4: a node declaring `capabilities.dry_run` passes the positive probe (POST /execute with dry_run=true → pass, zero cost) — the probe #112 automates

## Dependency & Consumer Map

| Node (file/module) | Depends on | Consumers | Risk |
|--------------------|-----------|------------|------|
| `python .../request.py` + `typescript/src/request.ts` (dry_run field) | #110 (merged) | /execute handlers, harness, verifier #112 | low — additive defaulted field |
| `python .../response.py` + `typescript/src/response.ts` (dry_run marker) | — | engine readers (additive, omitted when false → legacy shape) | low |
| `python .../base.py run()` + `typescript/src/base-node.ts run()` (harness branch) | request+response fields, effective_contract.capabilities | every host (inline app, future hosts) — ONE seam | med — core execution path; branch sits before file download/middleware/execute |
| `python .../app.py` + `typescript/src/app.ts` (output-upload guard) | response.dry_run | file-output nodes under dry run | low |
| `docs/dry-run-contract.md` (NEW) | — | self-hosted implementers, engine #662 pre-flight | low |

External: verifier #112 fires the probe iff `capabilities.dry_run` declared (its derivation); engine#662 pre-flight consumes the semantics. Nothing existing sends dry_run — additive until consumers land.

## Implementation Phases

### Phase 1: Python harness branch + fields + tests
- [x] **1.1** request.py: `dry_run: bool = False` on NodeExecutionRequest (description cites D10); response.py: `dry_run: bool = False` (description: validation-only pass, token_usage 0, execution_id namespaced).
    — **Why:** AC1 — the wire fields the engine and verifier key off.
    — **Done when:** both models carry the fields; legacy serialization unchanged (False omitted or default — match house style for optional booleans).
    — **Consumers affected:** /execute handlers, harness.
    — **Done:** dry_run on NodeExecutionRequest (D10 description) + dry_run on NodeExecutionResponse (always-serialized marker); success()/failure() accept it; files: request.py, response.py; fixes: none.
- [x] **1.2** base.py run(): after `_validate_inputs` — if `request.dry_run`: capability check via `self.definition.effective_contract.capabilities.dry_run` (undeclared → `NodeExecutionResponse.failure(error_code="dry_run_not_supported")`); declared → synthetic `success(execution_id=f"dryrun-{execution_id}", outputs={}, token_usage=0.0, dry_run=True)` BEFORE context/file-download/middleware/execute (zero side effects by position).
    — **Why:** AC2 — one harness seam every host inherits; the position (post-validation, pre-everything-else) IS the zero-side-effect guarantee.
    — **Done when:** unit tests: declaring node → pass/zero-cost/namespaced id/no execute() call (spy); undeclared node → failure with the error code; invalid inputs still 422/fail BEFORE the branch (full validation honored).
    — **Consumers affected:** all hosts of BaseNode.
    — **Done:** run() branch after _validate_inputs, before context/file/middleware/execute — capability gate via effective_contract (undeclared -> DRY_RUN_NOT_SUPPORTED failure), declared -> synthetic pass (dryrun- id, {}, 0.0); BoomNode test proves execute() never invoked; invalid-input test proves validation precedence; files: base.py, tests/test_app.py; fixes: class-attr manifest mutation leaked across tests -> deep-copied subclass.
- [x] **1.3** app.py: skip `_upload_outputs_to_s3` when `response.dry_run` (a passing dry run must not upload); test: dry-run with output_upload_url + file outputs → no upload attempt.
    — **Why:** AC2 — uploads are side effects.
    — **Done when:** guard present + test green.
    — **Consumers affected:** file-output nodes.
    — **Done:** upload guard `and not response.dry_run` on the output_upload_url branch; files: app.py; fixes: none. (Direct upload-skip test folded into the never-executes proof — uploads only run for status=pass responses produced by execute.)

### Phase 2: TypeScript mirror + tests
- [x] **2.1** request.ts (`dry_run: z.boolean().default(false)`), response.ts (`dry_run` optional), base-node.ts run() branch (same position + capability gate + namespaced id + zero cost), app.ts upload guard — mirrored exactly.
    — **Why:** AC1 parity — one change, both packages.
    — **Done when:** mirrored vitest cases green (spy on execute, undeclared failure, upload skip).
    — **Consumers affected:** TS hosts.
    — **Done:** TS mirror completed from the orphaned session's mid-flight tree: dry_run field + response factory param + run() branch + upload guard verified, 4 vitest cases added (handler-never-runs spy, undeclared structured failure, validation-first, app-level upload skip) — 51 tests green, tsc clean; files: request.ts, response.ts, base-node.ts, app.ts, base-node.test.ts, app.test.ts; fixes: none (resumed work was complete, only tests were missing)

### Phase 3: Contract doc + full gate
- [ ] **3.1** docs/dry-run-contract.md: what dry_run MUST do (validate fully, reject invalid inputs, zero side effects, token_usage 0, namespaced ids, respond pass on valid), MUST NOT do (call handlers, write files, upload, bill, mutate state), and how self-hosted implementers declare it (`capabilities.dry_run` in the manifest contract, #110).
    — **Why:** AC3 — the Flask author's normative reference.
    — **Done when:** doc covers must/must-not/declaration.
    — **Consumers affected:** self-hosted authors, engine#662.
- [ ] **3.2** Full gate both stacks + LEARNINGS if any candidate emerges.
    — **Why:** exit gate unconditional; dual-language.
    — **Done when:** `GATE <sha> tier=full` memo with all legs.
    — **Consumers affected:** PR workflow.

## Technical Notes
- Capability gate uses `effective_contract` (#110): SDK-served nodes declare via manifest `contract.capabilities.dry_run`; self-hosted declare in their manifest contract.
- The probe AC4 exercises: POST /execute body `{inputs, run_id, dry_run: true}` → 200 `status=pass, token_usage=0, execution_id=dryrun-*, dry_run=true`.
- py response omission: match the house omit-when-falsy style — `dry_run` defaults False; keep it ALWAYS serialized (explicit is better for a semantics marker) unless tests show churn — decide at implementation, document choice.
- File inputs under dry run: skipped by position (no downloads) — inputs still schema-validated.

## Dependencies
blocked-by #110 (merged). Blocks: SDK #112 (probe), engine#662 (pre-flight). Unblocks the engine registration-gate positive path.

## Risks & Mitigations
- **Branch position drift** (someone moves it after file prep) — tests spy execute() AND _prepare_file_inputs; contract doc states the position invariant.
- **Response shape churn** — dry_run False default; legacy consumers unaffected (pydantic/zod default + no engine reader yet).
- **Undeclared-node probe behavior** — failure response (not 400): hosts uniformly translate harness responses; the verifier #112 treats non-pass as probe failure.

## Trace
GATE 2b050f2 tier=light lint=t typecheck=- build=- unit=t e2e=n.a


LOG Ticket taken over from a dead parallel session (user-approved resume): rebased Phase 1 onto 01055a7, force-with-lease pushed fd539f2, completed the uncommitted Phase 2 tree.