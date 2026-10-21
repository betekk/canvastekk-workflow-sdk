# PLAN: SDK contract release — array file inputs, error taxonomy, envelope, status enum, capability passthrough

**Branch**: feat/SDK-161
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/161
**Base**: dev

## Acceptance Criteria

From ticket #161:

- [ ] AC1: All six S-items shipped in python AND typescript
- [ ] AC2: Version floor stamped X-SDK-Version; tagged per two-lane standard
- [ ] AC3: No CDS client code in the SDK

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/exceptions.py` + `typescript/src/exceptions.ts` (S.2 taxonomy + S.3 envelope) | — | every node repo (error shape), CWE#852 (D.2 envelope synthesis), the four D.4 deletions (nodes raise typed errors against this taxonomy) | med — additive fields/props; existing error_code values unchanged |
| `python/.../contracts.py` + `typescript/src/contracts/*` (S.5 `NodeExecutionStatus`) | S.2 (validation-class fail on unknown) | CWE#852 strict-status flip (the flip IS the engine pin-bump to this release); CWN#548; CFN#2080 (ERROR rows) | med — new enum, strict parser; consumers only affected when they bump pins |
| `python/.../base.py::_prepare_file_inputs` + `typescript/src/base-node.ts::prepareFileInputs` (S.1 array inputs) | — | CISA#307 (`ifc_parts` array), CWE#851 (array presign), every node accepting file lists | high — core execution path; per-element download+cleanup |
| `python/.../request.py`/`context.py` + `typescript/src/request.ts`/`context.ts` (S.4 `capability` field) | — | CWE#851 (mint, `X-Node-Capability` header — name defined HERE, the contract PR), CWN#548 (client presents it) | low — optional passthrough, header-exclusive (DA-2242 mirror) |
| `python/.../app.py` (X-SDK-Version response header parity) | — | engine version-floor enforcement (F-track standing check) | low — TS already stamps it (middleware.ts:163); python adds parity |
| IO_* sub-codes (S.6) in exceptions + download paths | S.2 | node error reporting; CFN#2080 envelope rows | low |

Cross-module consumers: EVERY node repo + the engine consume this SDK via pinned release assets; nothing here changes existing wire behavior for pinned v0.54.0 consumers — the contract is additive until consumers bump.

## Implementation Phases

### Phase 1: S.2 taxonomy + S.3 envelope (both languages)

- [x] **1.1** Add `ERROR_CATEGORIES = ("transport", "validation", "domain", "timeout", "lifecycle")` and a `category` property to `NodeExecutionError` (subclass mapping: `NodeIOError`→transport, `NodeValidationError`/`NodeOutputValidationError`/`WorkflowValidationError`→validation, `NodeTimeoutError`→timeout, `NodeConfigurationError`→lifecycle; uncaught/bare exceptions the app wraps → domain); include `category` in `to_dict()`; sunset refusal (`_check_deprecation_lifecycle`) raises with structured `error_code="NODE_SUNSET"` + `details={"sunset_date", "replacement_slug"}`; add `error_envelope(exc) -> {"type","message","code"}` + `ERROR_ENVELOPE_KEYS` constant
    — **Why:** the epic's error architecture needs one taxonomy registry and one envelope shape shared by engine (D.2), nodes (D.4), and frontend (envelope rows)
    — **Done when:** python tests assert the five category mappings, bare-Exception→domain wrap, the envelope triple, and the structured sunset code; ruff green
    — **Done:** taxonomy+envelope+sunset+IO_* constants+exports; 37 tests green, ruff clean; files: exceptions.py, base.py, __init__.py, tests; fixes: category-before-docstring stamp bug (fixed pre-gate), 2 stale to_dict expectations updated
    — **Consumers affected:** CWE#852, CWN#549/CISA#308/CRS#175/CPCA#309, CFN#2080
- [x] **1.2** Mirror 1.1 in TypeScript (`exceptions.ts`: `ERROR_CATEGORIES`, `category` getter, envelope helper, sunset structure in the deprecation pipeline)
    — **Why:** AC1 — both languages, one contract
    — **Done when:** vitest mirrors the python assertions; eslint + tsc green
    — **Done:** mirrored constants/getters/envelope/sunset; 34 tests green, eslint+tsc×2 clean; files: exceptions.ts, base-node.ts, index.ts, tests; fixes: 1 stale toDict expectation updated
    — **Consumers affected:** same as 1.1 (CISA apps/node consumes TS)

### Phase 2: S.5 NodeExecutionStatus + S.6 IO_* sub-codes (both languages)

- [ ] **2.1** Add `NodeExecutionStatus` enum (wire values lowercase: `success`, `failed`, `skipped`, `timeout`) + `parse_node_execution_status(value)` that is STRICT by default (missing/unknown → validation-class error) — the engine's flip is its pin-bump to this release (CWE#852, gated on F.4)
    — **Why:** strict status is the epic's honest-failure backbone; the SDK ships it ARMED so the engine's adoption is a single version bump
    — **Done when:** python+TS tests assert enum values, strict rejection of unknown/missing, and the validation-class category
    — **Consumers affected:** CWE#852 (flip), engine run status agreement (epic AC)
- [ ] **2.2** Add IO_* sub-codes (`IO_DOWNLOAD_FAILED`, `IO_URL_POLICY_BLOCKED`, `IO_SIZE_EXCEEDED`) carried in `details["sub_code"]` by the download paths (`_download_one`/`downloadOne`, URL-policy block, size validation) in both languages
    — **Why:** S.6 — transport-class failures need machine-readable sub-codes for the frontend's envelope rows and the incident-replay gate
    — **Done when:** tests assert each sub-code surfaces on its failure path
    — **Consumers affected:** CFN#2080, incident replay (G.4)

### Phase 3: S.1 array file inputs (both languages)

- [ ] **3.1** `_prepare_file_inputs` (python) accepts lists per file field: iterate elements, download URL strings element-wise, validate per-element, replace with local paths, record `context.metadata[field]` as a list of per-element entries; non-URL elements pass through; failure mid-list cleans every downloaded file of the run (existing cleanup invariant)
    — **Why:** `ifc_parts: [s3://…]` cannot flow today — the presign walk (CWE#851) delivers arrays and the SDK must materialize them
    — **Done when:** python tests cover URL-array→paths, mixed elements, empty list, mid-list failure cleanup; single-value behavior unchanged (existing tests green)
    — **Consumers affected:** CISA#307, CWE#851, model-checker group runs
- [ ] **3.2** Mirror 3.1 in `prepareFileInputs` (TS)
    — **Why:** AC1 — CISA's node side is TypeScript
    — **Done when:** vitest mirrors 3.1's cases
    — **Consumers affected:** same as 3.1

### Phase 4: S.4 capability field + X-SDK-Version parity

- [ ] **4.1** `NodeExecutionRequest.capability: str | None` + `ExecutionContext.capability` accessor (python + TS), header-exclusive via `X-Node-Capability` (DA-2242 account_id mirror: body-supplied value stripped before validation, header is the only source; opaque string, no parsing) — the header name is DEFINED here as the contract; CWE#851's mint writes it
    — **Why:** the #833 run-scoped CDS capability must reach nodes without touching CDS code in the SDK
    — **Done when:** tests assert header→context, body-only→None, both languages
    — **Consumers affected:** CWE#851 (mint), CWN#548 (client presents)
- [ ] **4.2** Python app sets the `X-SDK-Version` response header (TS middleware.ts:163 parity)
    — **Why:** AC2 — the version floor stamp must be observable on both stacks' responses
    — **Done when:** python test asserts the header on a node response
    — **Consumers affected:** engine floor enforcement (F-track CI check)

### Phase 5: verification gate (full tier — ticket exit gate, BOTH languages)

- [ ] **5.1** Full gate: python (pytest + ruff) AND typescript (vitest + eslint + `tsc --noEmit` + `tsc --noEmit -p tsconfig.tests.json` + `tsup` build); grep proves zero CDS-client code (AC3); append `tier=full` memo. Tagging rides the two-lane release workflow on merge (dev counter → prod final) — no hand-bump in this PR
    — **Why:** the exit gate is unconditional; AC3 needs a mechanical check, not a claim
    — **Done when:** all gates green on the final tree; `grep -ri "cds" python/canvastekk_workflow_sdk typescript/src` shows no client surface (only doc mentions if any); memo recorded
    — **Consumers affected:** none (verification)

## Technical Notes

- Existing `error_code` values (EXECUTION_ERROR, TIMEOUT, VALIDATION_ERROR, IO_ERROR, CONFIGURATION_ERROR) are UNCHANGED — the taxonomy is an additive classification layer, so pinned consumers see no drift.
- `X-Node-Capability` is an opaque HMAC token per #833 §1: `{run_id, node_id, account_id, scope, exp}` — the SDK transports it, never parses/validates it (CDS-side verification is authlib#65).
- `NodeExecutionStatus` strict parsing ARMED in the SDK does NOT flip the engine — the engine's behavior changes only when it bumps its pin (CWE#852, after F.4 floor confirmation).
- Sunset structure: `_check_deprecation_lifecycle` currently raises `NodeConfigurationError` message-only; it gains the structured code without changing the raise type.
- No CDS client, no ErrorOutputNode in this release (CWE#850-amended #833 migration table row: contract-only).

## Dependencies

- blocked-by: canvastekk-workflow-engine#850 (MERGED — PR #855, 6802b0de). Parent epic: betekk/canvastekk-tracker#3953 (S track).
- Unblocks: CWN#548 (+authlib#65), CISA#307, CWE#851, CWN#549, CISA#308, CRS#175, CPCA#309 (all pinned on this release).

## Risks & Mitigations

- **Core-path regression (S.1)** → per-element cleanup rides the existing try/except invariant; full suite both languages each phase.
- **Contract drift python↔TS** → every S-item lands as a mirrored pair with mirrored tests in the same phase.
- **Name collision on `X-Node-Capability`** → defined here once, cross-referenced in CWE#851/CWN#548 PLANs at their authoring.

## Trace

| Phase | Commit | Gate |
|-------|--------|------|
