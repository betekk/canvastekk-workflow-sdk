# PLAN: RunContext on the node execution context

**Branch**: feat/281
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/281
**Base**: dev (6ebeb56)

CWE will send a versioned `run_context` object with every `/execute` call
(betekk/canvastekk-workflow-engine#1443 builds the engine side). The SDK
exposes it on the node execution context, Python and TypeScript in parity,
and the result-file writer prefers `run_context.workflow_run_id` over the
bare wire `run_id`. Ships before the engine change: absent `run_context`
behaves exactly as today, and old SDKs ignore the new body key
(`extra="ignore"` / zod passthrough-by-default).

## Acceptance Criteria

- [ ] AC1 `ctx.run_context` populated from a request carrying
  `run_context`, None without it (Python and TypeScript tests).
- [ ] AC2 Result-file header uses `run_context.workflow_run_id` when
  present and `context.run_id` otherwise (tests for both, both legs).
- [ ] AC3 Docs updated (`docs/RESULT-FILE.md`, `docs/GLOSSARY.md`);
  minor release published (label-driven by release.yml on merge).
- [ ] AC4 No forced node change: node services adopt when they next bump
  the SDK (no breaking API change — additive field + additive property).

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|---|---|---|---|
| `python/…/run_context.py` (NEW `RunContext` model) | — | request model, context property, writer | low |
| `python/…/node_execution_request.py` (`run_context` field) | RunContext | engine wire (sender: CWE#1443), context | low (additive, `extra="ignore"`) |
| `python/…/node_execution_context.py` (`run_context` property) | request field | node `execute()` bodies, writer | low |
| `python/…/result_file.py:300` (header id choice) | context property | result-file header consumers (CWE run-end check, FE reader) | med (header contract) |
| `typescript/src/run-context.ts` (NEW schema+type) | — | request schema, context getter, writer | low |
| `typescript/src/node-execution-request.ts` (schema field) | run-context | express parse path | low (zod optional) |
| `typescript/src/node-execution-context.ts` (`runContext` getter) | request field | node bodies, writer | low |
| `typescript/src/result-file.ts:296` (header id choice) | context getter | same as python writer | med |
| `docs/RESULT-FILE.md`, `docs/GLOSSARY.md` | implementation | node authors | low |

## Implementation Phases

### Phase 1: Python leg

- [ ] **1.1** New `python/canvastekk_workflow_sdk/run_context.py`:
  `RunContext(BaseModel)` with `run_context_version: str`,
  `workflow_run_id: str` (required); `workflow_definition_id`,
  `workflow_definition_slug`, `workflow_definition_version`,
  `account_id: int | None`, `started_at: str | None` (optional,
  default None); field descriptions naming the sender (CWE executor,
  #1443) and the versioning rule (additive keys bump the minor).
  — **Why:** one wire model both legs mirror; identity fields required so
  the header fallback can never read a half-built context.
  — **Done when:** model imports, validates the v1 sample from the epic,
  rejects missing `workflow_run_id`.
  — **Consumers affected:** request model, context, writer.
- [ ] **1.2** `NodeExecutionRequest.run_context: RunContext | None = None`
  (after `account_id`); `NodeExecutionContext.run_context` property
  delegating to `self._request.run_context` (None without a request),
  docstring noting the engine sender and None-when-absent.
  — **Why:** the context is the single surface nodes read identity from.
  — **Done when:** AC1 Python half green.
  — **Consumers affected:** node bodies; writer.
- [ ] **1.3** `result_file.py:300`:
  `workflow_run_id=context.run_context.workflow_run_id if context.run_context else context.run_id`.
  — **Why:** AC2 — the header must carry the workflow run id once the
  engine sends the context; identical behavior until then.
  — **Done when:** AC2 Python half green (header equals run_context id
  when present, run_id otherwise).
  — **Consumers affected:** result-file readers (CWE run-end check, FE).
- [ ] **1.4** Tests `python/tests/test_run_context.py`: request with/without
  `run_context` (parse + context property), writer header both ways
  (extend the existing result-file test pattern).
  — **Why:** AC1/AC2 are checkable only at these seams.
  — **Done when:** pytest green.
  — **Consumers affected:** none (tests).

### Phase 2: TypeScript leg (parity)

- [ ] **2.1** New `typescript/src/run-context.ts`: zod schema
  (`run_context_version`, `workflow_run_id` required; definition fields,
  `account_id`, `started_at` optional) + inferred type + JSDoc mirroring
  the Python model; export from `index.ts` per the existing export
  pattern.
  — **Why:** wire parity is the ticket's contract.
  — **Done when:** schema parses the same v1 sample; rejects missing
  `workflow_run_id`.
  — **Consumers affected:** request schema, context.
- [ ] **2.2** `NodeExecutionRequestSchema` gains
  `run_context: RunContextSchema.nullish()`; context gets a
  `get runContext()` following the `runId` getter pattern (request first,
  null otherwise).
  — **Why:** AC1 TS half.
  — **Done when:** AC1 TS half green.
  — **Consumers affected:** node bodies; writer.
- [ ] **2.3** `result-file.ts:296`:
  `context.runContext?.workflow_run_id ?? context.runId`; tests in
  `typescript/tests/run-context.test.ts` (parse ±, header both ways).
  — **Why:** AC2 TS half.
  — **Done when:** AC2 TS half green.
  — **Consumers affected:** result-file readers.

### Phase 3: docs + release label

- [ ] **3.1** `docs/RESULT-FILE.md`: header `workflow_run_id` is the
  workflow run id; the writer prefers `run_context.workflow_run_id` and
  falls back to the wire `run_id`; note the wire `run_id` equals the
  workflow run id once CWE#1440 is live. `docs/GLOSSARY.md`: entries for
  `run_context`, `workflow run id` (cross-ref CWE #1440/#1443).
  — **Why:** AC3 — node authors must know which id lands in the header.
  — **Done when:** both docs mention the rule and the versioning rule.
  — **Consumers affected:** node authors.
- [ ] **3.2** Exit gate (full tier): python pytest + ruff/mypy if
  configured + `npm test` (typescript) per repo manifests; `minor` label
  on the PR (release.yml bumps versions on merge to dev).
  — **Why:** AC3's release half is label-driven; the gate is the PR's
  citation.
  — **Done when:** gates green, `GATE <sha> tier=full` memo appended.
  — **Consumers affected:** PR creation.

## Technical Notes

- Wire format is snake_case on both legs (existing request contract).
- `NodeExecutionRequest` Python uses `extra="ignore"` (`:119`) — old SDK
  versions ignore the new body key; TS zod strips unknown keys by default.
- Python context fallback when no request: `run_context` returns None
  (there is nothing to derive; the writer then uses `run_id`, which itself
  falls back to the output-dir name).
- Versions: NOT bumped in the PR — `release.yml` runs
  `scripts/bump_versions.py` on merge to dev, driven by the semver label.
- Test commands: python `pytest` from `python/` (venv in
  `python/.venv` if present — else repo CI shape); typescript `npm test`
  in `typescript/`.

## Dependencies

- None (engine side is CWE#1443, blocked-by #1441; ships after this).

## Risks & Mitigations

- **Header contract drift between legs** — parity tests assert the same
  v1 sample both sides; the writer fallback is one expression per leg.
- **Premature engine assumptions** — the SDK only reads what the ticket
  fixes (RC3 v1 fields); unknown keys are ignored (py extra=ignore /
  zod strip), so engine additions stay non-breaking.

## Trace

(populated by execution; final line must be `GATE <short-sha> tier=full` for the pushed SHA)
