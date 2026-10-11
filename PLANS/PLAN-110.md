# PLAN: Manifest declares its serving contract (ContractSpec)

**Branch**: feat/110
**Issue**: https://github.com/betekk/canvastekk-workflow-sdk/issues/110
**Base**: main

## Acceptance Criteria
- [ ] AC1: contract block validated by pydantic AND zod with identical accept/reject behavior — both validator loops + parity tests land in ONE change (repo learning: validator loops must cover new fields)
- [ ] AC2: closed route vocabulary enforced; manifests missing execute/health/manifest rejected with a named-field error
- [ ] AC3: fastapi and express adapters stamp ContractSpec with zero author input
- [ ] AC4: `build_registry_payload` includes the contract; TestBuildRegistryPayload pins it

## Dependency & Consumer Map

| Node (file/module) | Depends on (must precede) | Consumers (who depends on this) | Change risk |
|--------------------|---------------------------|---------------------------------|-------------|
| `python/canvastekk_workflow_sdk/definition.py` (NodeContract + `contract` field) | — | to_dict/`/manifest` body; build_registry_payload; every manifest consumer (34-caller blast on registry.py alone) | med — additive optional field; serializer omits when None (byte-identical legacy shape) |
| `typescript/src/definition.ts` (zod ContractSchema + field) | mirror of py design | 10 callers incl. cli.ts probeManifest, base-node.ts, index.ts | med — same additive shape |
| `python/canvastekk_workflow_sdk/app.py` (fastapi stamp) | NodeContract | `/manifest` response (engine reads at gate time, #658) | low — stamp-if-unset |
| `typescript/src/app.ts` (express stamp) | zod schema | `/manifest` response | low |
| `python/canvastekk_workflow_sdk/registry.py` (constraints carry) | NodeContract | engine RegisterWorkflowNodeRequest wire (extra=forbid TODAY — contract rides inside `constraints`, so the current engine accepts it; engine #658 reads it) | med — wire-compat preserved by placement |
| `typescript/src/cli.ts` (mirror carry in buildEngineRequest) | zod schema | probeManifest engine-request mirror | low |

External consumers: engine#658 (registration gate — reads `constraints["contract"]` + `/manifest.contract`); SDK verifier #112 and OpenAPI #113 build on the declared routes; engine#662 pre-flight reads capabilities. None exist yet — additive until they land.

**Wire decision (D8/D11 + repo learning "parity ports must widen the wire schema"):** the engine's `RegisterWorkflowNodeRequest` is `extra="forbid"` and has no `contract` field today. Emitting contract at the payload TOP LEVEL would 422 every registration against the current engine. Placement: `constraints["contract"]` (constraints is a declared free-form dict on both sides, already whitelisted in TS `ENGINE_REQUEST_ALLOWED`) — carried now, read by engine#658, promotable to a top-level field by the ENGINE when it adds the field (its widening, its release).

## Implementation Phases

### Phase 1: Python ContractSpec + tests
- [ ] **1.1** Add `ContractCapabilities` (dry_run: bool = False) and `NodeContract` (transport: Literal["http"] = "http"; routes: list[str]; capabilities: ContractCapabilities = default; openapi: Literal["3.2"] = "3.2") models in definition.py, plus `contract: NodeContract | None = Field(default=None)` on WorkflowNodeManifest; add `"contract"` to `_drop_optional_when_none`'s optional-key tuple.
    — **Why:** D8 — the manifest must declare HOW a node serves; None-default + omit-when-None keeps legacy serialization byte-identical (protects the /manifest comparers called out in the model_serializer docstring).
    — **Done when:** manifest without contract serializes identically to pre-change (regression test proves it); with contract, it round-trips.
    — **Consumers affected:** to_dict, /manifest body, build_registry_payload (later phases).
- [ ] **1.2** Validators on NodeContract: routes must be a subset of the closed vocabulary {"/execute","/health","/manifest","/hook","/metrics","/live","/ready"}; must contain the minimum {"/execute","/health","/manifest"}; no duplicates; error messages name the offending field and value.
    — **Why:** AC2 — the vocabulary is the contract the engine gate (#658) and verifier (#112) derive probes from; a lying or partial declaration must fail at validation, not at run time.
    — **Done when:** accept/reject tests cover: valid subset, unknown route rejected (named), missing each minimum rejected (named), duplicate rejected (named).
    — **Consumers affected:** all manifest validators (py side).
- [ ] **1.3** Python unit tests (test_definition.py): the accept/reject matrix above + serialization omission + round-trip + the pre-change byte-identity regression.
    — **Why:** AC1's pydantic half + the repo learning that validator loops must cover new fields IN THE SAME CHANGE.
    — **Done when:** `pytest python/tests/test_definition.py` green with the new cases present.
    — **Consumers affected:** none (tests).

### Phase 2: TypeScript ContractSpec + tests (SAME change — parity rule)
- [ ] **2.1** Mirror in typescript/src/definition.ts: `ContractCapabilitiesSchema`, `NodeContractSchema` (zod) with the SAME closed vocabulary, minimum-set, duplicate, and literal constraints; `contract: NodeContractSchema.nullable().default(null)` on WorkflowNodeManifestObjectSchema.
    — **Why:** AC1 — identical accept/reject behavior both languages; the parity learning exists because a one-sided validator loop once shipped.
    — **Done when:** schema parses the same fixture set as pydantic (same cases pass/fail).
    — **Consumers affected:** 10 zod callers inherit the field (additive, nullable default).
- [ ] **2.2** TS unit tests (definition.test.ts): the same accept/reject matrix + nullable default.
    — **Why:** AC1's zod half; identical matrix = the parity test.
    — **Done when:** `vitest run typescript/tests/definition.test.ts` green with mirrored cases.
    — **Consumers affected:** none (tests).

### Phase 3: Adapters stamp the contract
- [ ] **3.1** fastapi `create_node_app`: serve the contract on `/manifest` via a derived property — `WorkflowNodeManifest.effective_contract` (returns the declared `contract` when set, else the SDK-served default: transport http, the 7 mounted routes, dry_run False, openapi 3.2). The adapter MUTATES nothing; the property is the stamp (arch fold: single-writer discipline, matches `effective_runtime_seconds` precedent at definition.py:299).
    — **Why:** AC3 — SDK-served authors get the contract with zero input; the stamped list must equal what the adapter ACTUALLY mounts (it is the source of truth D8 names).
    — **Done when:** app test — create_node_app on a bare node → GET /manifest shows contract.routes == the 7 mounted paths; a node with a DECLARED subset keeps its declaration.
    — **Consumers affected:** /manifest consumers (registry cross-check, future gate).
- [ ] **3.2** express `createNodeApp`: same derived-property stamp on the TS side (`effectiveContract` getter on the manifest type via the schema's exported helper, or the adapter's manifest response composes it) with the same 7 paths (TS constant).
    — **Why:** AC3 parity of adapters.
    — **Done when:** ts app test — /manifest body carries contract with the 7 routes; declared subset wins.
    — **Consumers affected:** same, TS side.

### Phase 4: Registry payload carries the contract
- [ ] **4.1** `build_registry_payload`: when `definition.contract is not None` (the DECLARED contract — not the effective default; self-hosted registrations reflect the author's declaration), set `resolved_constraints["contract"] = definition.contract.model_dump(mode="json")` (caller-supplied constraints win, per the existing merge rule); docstring notes the wire decision (constraints placement vs extra=forbid engine).
    — **Why:** AC4 — the engine registration path must receive the contract; constraints placement keeps TODAY's engine accepting the payload (engine #658 reads + promotes it).
    — **Done when:** TestBuildRegistryPayload: definition with contract → payload["constraints"]["contract"] present and shape-pinned; definition without → key absent.
    — **Consumers affected:** register_node, export_definition, TS mirror.
- [ ] **4.2** TS `buildEngineRequest` mirror: same constraints merge behavior; cli.test.ts case for both presence and absence.
    — **Why:** AC4 parity — the CLI's offline engine-request mirror must not drift from the py payload builder.
    — **Done when:** cli.test.ts green with mirrored cases.
    — **Consumers affected:** probeManifest (mirror probe), CLI register.

### Phase 5: Full gate + LEARNINGS
- [ ] **5.1** Full gate: python (ruff + pytest) and typescript (eslint + tsc --noEmit + tsc tests + vitest) — all green on the same tree.
    — **Why:** ticket exit gate is unconditionally full; dual-language change needs both stacks gated.
    — **Done when:** `GATE <sha> tier=full` memo with all six legs true.
    — **Consumers affected:** PR workflow cites it.
- [ ] **5.2** LEARNINGS capture if anything non-obvious surfaced (candidate: wire-placement rule — additive manifest fields that must cross an extra=forbid request ride an existing free-form dict until the receiver widens).
    — **Why:** the constraints-placement decision is a reusable pattern for the engine-gate tickets ahead.
    — **Done when:** entries + index rows written (swept in the end-of-ticket commit).
    — **Consumers affected:** engine#658 implementers.

## Technical Notes
- Closed vocabulary (both languages, identical): "/execute", "/health", "/manifest", "/hook", "/metrics", "/live", "/ready" — exactly the routes both adapters mount today (app.py :334/:497/:530/:571/:608/:623/:633; app.ts :119/:200/:229/:269/:283/:288/:293). "/hook" is unconditional (501 unless overridden).
- Minimum set: {"/execute", "/health", "/manifest"} (D8).
- capabilities.dry_run is DECLARED here; semantics + verifier probe land in #111/#112 — this ticket only adds the flag.
- openapi: "3.2" is the declared document dialect stamp; emission is #113.
- Serializer: `"contract"` joins the omit-when-None tuple (model_serializer at definition.py) so legacy nodes serialize byte-identically.
- py fields live after changelog_url; ts field after changelog_url (mirror order).
- Trust rule (arch fold 2): the declared contract is ADVISORY until the engine gate (#658) probes the live node — declaration never substitutes for verification; the SDK stamps what it actually mounts, authors declare what they actually serve, the gate cross-checks.

## Dependencies
None (root of the SDK slice). Blocks: SDK #111/#112/#113 (consume contract shape), engine#658 (gate reads constraints["contract"] + /manifest.contract).

## Risks & Mitigations
- **Validator drift py↔ts** — Phases 1+2 land in one PR with mirrored matrices; the parity learning is the named precedent.
- **Engine 422 on registration** — contract rides `constraints` (declared dict both sides; TS whitelist already allows it); top-level promotion happens engine-side (#658).
- **Serialization churn for existing nodes** — omit-when-None + a byte-identity regression test.
- **Stamped routes lying about what's mounted** — the stamp constant sits beside the mounts and a test pins the 7 paths; #112's probe-derivation then has a truthful source.
