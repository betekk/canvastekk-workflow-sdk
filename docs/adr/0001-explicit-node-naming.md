# ADR 0001: Explicit node naming — "definition" means workflow definition only

**Status:** Accepted · **Date:** 2026-11-19 · **Ticket:** [#271](https://github.com/betekk/canvastekk-workflow-sdk/issues/271) · **Epic:** [betekk/canvastekk-tracker#4301](https://github.com/betekk/canvastekk-tracker/issues/4301)

## Context

"Definition" means two different things across the CanvasTEKK stack: in CWE
and FE a **workflow definition** is the graph a user saves, while this SDK's
`definition.py` / `definition.ts` hold the **node manifest**
(`WorkflowNodeManifest`, `NodeContract`, `export_definition`); the actual
workflow definition lives in `workflow/models.py`. Many SDK modules and public
names (`base`, `app`, `context`, `registry`, `BaseNode`, `ExecutionContext`,
`NodeResult`, `validate`, `NodeExecutionStatus`) do not say which object they
belong to.

## Decision

1. Adopt the [glossary](../GLOSSARY.md) as vocabulary law: **"definition"
   only ever means a workflow definition; node-level things say "manifest";
   every module, type, class, function and constant names the object it
   belongs to.**
2. Rename modules and public names per the complete map below, **Python and
   TypeScript in the same commit per cluster** (py-ts parity rule).
3. Keep every old Python module path and every old public name (Python and
   the TypeScript index) working as a deprecated alias. Removal is 1.0.0
   (#272), after every consumer repo has migrated.
4. **Ambiguity-driven renaming** (the interpretive rule for names the ticket
   left open): rename when the name does not say which object it belongs to
   (`getNodeId` reads as "id of a node" but returns the manifest id); keep
   when the name is already unambiguous in SDK scope (`NodeExecutionRequest`,
   `Measurement`, `WorkflowNodeManifest`). Cluster coherence extends an
   epic-decided rename to its direct twins (`HealthResponse` →
   `WorkflowNodeHealthResponse` also carries `LivenessResponse`,
   `ReadinessResponse`, `MetricsSummaryResponse`, `MultiNodeHealthResponse`;
   `ExecutionMetric` → `NodeExecutionMetric` also carries
   `MetricsCollector`, `createExecutionMetric`, `metricToDict`).

### Alias mechanism

- **Python old module paths** (e.g. `definition.py`) become shim modules:
  they re-export the *entire* new module surface, carry
  `_deprecated_alias_of = "<new dotted module>"` (machine-checkable marker
  for guards and alias tests), and emit a module-import `DeprecationWarning`
  naming the new path.
- **Python old public names** (e.g. `BaseNode`) resolve from the package root
  through a lazy `__getattr__` (extending the existing `_LAZY_SERVER_EXPORTS`
  pattern) that warns on access — new-name users never see warnings. Where the
  old name lives in a non-renamed module (`exceptions.py`), a module-level
  `__getattr__` (PEP 562) does the same job there.
- **TypeScript old paths** (e.g. `definition.ts`) stay as shim files
  re-exporting the new module; every re-export carries `/** @deprecated */`.
  The index re-exports old names as `/** @deprecated */` aliases of the new
  ones.
- Internal SDK code never routes through a shim: each rename phase retargets
  every internal import repo-wide. Phase-5 verification greps pin this.
- **Compatibility is behavioral, not just syntactic**: the
  `NodeValidationError` split keeps the old name as the *base class* of both
  new specific errors, so any consumer `except NodeValidationError` keeps
  catching both.

### Resolutions of the two open names

- **`NodeAuth` vs `TekkNodeAuth`** — not a duplicate, two different shapes:
  - TypeScript: `TekkNodeAuth` is literally `export const TekkNodeAuth =
    NodeAuth` (`auth.ts:476`). Canonical name: **`TekkNodeAuth`**; `NodeAuth`
    becomes a `/** @deprecated */` alias.
  - Python: two distinct classes — `TekkNodeAuth` (`auth/core.py:587`, the
    credential object) and `NodeAuth` (`auth/fastapi.py:113`, the FastAPI
    dependency). **Both kept**, documented as distinct; no rename.
- **`NodeValidationError`** — raised for both manifest validation
    (`definition.py:553`) and input validation (`base.py:181`,
    `contracts.py:90`). Split by what failed, preserving the old name as the
    common base so existing `except` clauses keep catching both:
    - `WorkflowNodeManifestValidationError(NodeValidationError)` — manifest
      validation failures.
    - `NodeInputValidationError(NodeValidationError)` — input payload
      validation failures.
    - `NodeValidationError` itself: deprecated alias for catching (still the
      runtime base class); SDK raise-sites move to the specific subclasses.
    - TypeScript twins identical (subclass split in `exceptions.ts`).

### Complete module map

| Python old | Python new | TypeScript old | TypeScript new |
|---|---|---|---|
| `definition.py` | `workflow_node_manifest.py` | `definition.ts` | `workflow-node-manifest.ts` |
| `diff.py` | `workflow_node_manifest_diff.py` | `diff.ts` | `workflow-node-manifest-diff.ts` |
| `registry.py` | `workflow_node_registry.py` | `registry.ts` | `workflow-node-registry.ts` |
| `convergence.py` | `workflow_node_registry_convergence.py` | — | — |
| `conformance.py` | `workflow_node_conformance.py` | — | — |
| `base.py` | `workflow_node_base.py` | `base-node.ts` | `workflow-node-base.ts` |
| `app.py` | `workflow_node_app.py` | `app.ts` | `workflow-node-app.ts` |
| `router.py` | `multi_node_router.py` | (TS `createMultiNodeApp` lives in `app.ts`) | — |
| `request.py` | `node_execution_request.py` | `request.ts` | `node-execution-request.ts` |
| `response.py` | `node_execution_response.py` | `response.ts` | `node-execution-response.ts` |
| `context.py` | `node_execution_context.py` | `context.ts` | `node-execution-context.ts` |
| `protocol.py` | `node_call_protocol.py` | `protocol.ts` | `node-call-protocol.ts` |
| `uploads.py` | `node_output_uploads.py` | `uploads.ts` | `node-output-uploads.ts` |
| `multipart.py` | `cds_multipart_upload.py` | `multipart.ts` | `cds-multipart-upload.ts` |
| `contracts.py` | `node_io_data_contracts.py` | `contracts/` | `node-io-data-contracts/` |
| `workflow/models.py` | `workflow/workflow_definition.py` | `workflow/models.ts` | `workflow/workflow-definition.ts` |
| `workflow/executor.py` | `workflow/node_executor.py` | `workflow/executor.ts` | `workflow/node-executor.ts` |

Not renamed (already explicit): `exceptions`, `logging`, `middleware`,
`observability`, `testing`, `bootstrap`, `auth/`, `node_token`, `url_policy`,
`schema_dialect`, `support-horizon`, `version`, `index`, `cli`, `express`, and
the `workflow/` helpers (`builder`, `runner`, `resolver`, `validation`,
`level`, `control-flow`).

### Complete symbol map — renamed

Every row: Python old → new · TypeScript old → new (`—` = not present in that
language). `*Schema` twins rename with their type (`RetryConfig` →
`WorkflowNodeRetryConfig` carries `RetryConfigSchema` →
`WorkflowNodeRetryConfigSchema`).

**Manifest cluster**

| Python | TypeScript |
|---|---|
| `export_definition` → `export_workflow_node_manifest` | `exportDefinition` → `exportWorkflowNodeManifest` |
| `NodeContract` → `WorkflowNodeManifestContract` | `NodeContract` → `WorkflowNodeManifestContract` |
| `ContractCapabilities` → `WorkflowNodeContractCapabilities` | `ContractCapabilities` → `WorkflowNodeContractCapabilities` |
| `RetryConfig` → `WorkflowNodeRetryConfig` | `RetryConfig` → `WorkflowNodeRetryConfig` |
| `ColorPreset` → `WorkflowNodeColorPreset` | `ColorPreset` → `WorkflowNodeColorPreset` |
| `DeprecationInfo` → `WorkflowNodeDeprecationInfo` | `DeprecationInfo` → `WorkflowNodeDeprecationInfo` |
| `SDK_SERVED_CONTRACT_ROUTES` → `WORKFLOW_NODE_MANIFEST_CONTRACT_ROUTES` | — |
| `diff_manifests` → `diff_workflow_node_manifests` | `diffManifests` → `diffWorkflowNodeManifests` |
| `ManifestDiff` → `WorkflowNodeManifestDiff` | `ManifestDiff` → `WorkflowNodeManifestDiff` |
| `fetch_published_definition` → `fetch_published_workflow_node_manifest` | — |
| `diff_against_published` → `diff_against_published_workflow_node_manifest` | — |

**Registry cluster**

| Python | TypeScript |
|---|---|
| `register_node` → `register_workflow_node` | `registerNode` → `registerWorkflowNode` |
| `RegisterNodeResult` → `WorkflowNodeRegistrationResult` | `RegisterNodeResult` → `WorkflowNodeRegistrationResult` |
| `RegistrationError` → `WorkflowNodeRegistrationError` | `RegistrationError` → `WorkflowNodeRegistrationError` |
| `build_registry_payload` → `build_workflow_node_registry_payload` | `buildRegistryPayload` → `buildWorkflowNodeRegistryPayload` |

**Node runtime cluster**

| Python | TypeScript |
|---|---|
| `BaseNode` → `WorkflowNodeBase` | `BaseNode` → `WorkflowNodeBase` |
| `create_node_app` → `create_workflow_node_app` | `createNodeApp` → `createWorkflowNodeApp` |
| `create_multi_node_app` → `create_multi_workflow_node_app` | `createMultiNodeApp` → `createMultiWorkflowNodeApp` |
| `mount_node` → `mount_workflow_node` | — |
| `create_authed_app` → `create_authed_workflow_node_app` | — |
| `create_lambda_handler` → `create_workflow_node_lambda_handler` | — |
| `HealthResponse` → `WorkflowNodeHealthResponse` | `HealthResponse` → `WorkflowNodeHealthResponse` |
| `LivenessResponse` → `WorkflowNodeLivenessResponse` | `LivenessResponse` → `WorkflowNodeLivenessResponse` |
| `ReadinessResponse` → `WorkflowNodeReadinessResponse` | `ReadinessResponse` → `WorkflowNodeReadinessResponse` |
| `MetricsSummaryResponse` → `WorkflowNodeMetricsSummaryResponse` | `MetricsSummaryResponse` → `WorkflowNodeMetricsSummaryResponse` |
| `MultiNodeHealthResponse` → `MultiWorkflowNodeHealthResponse` | `MultiNodeHealthResponse` → `MultiWorkflowNodeHealthResponse` |
| — | `NodeAuth` → deprecated alias of `TekkNodeAuth` (no rename) |

**Node execution / call cluster**

| Python | TypeScript |
|---|---|
| `ExecutionContext` → `NodeExecutionContext` | `ExecutionContext` → `NodeExecutionContext` |
| `ExecutionMetric` → `NodeExecutionMetric` | `ExecutionMetric` → `NodeExecutionMetric` |
| `MetricsCollector` → `NodeExecutionMetricsCollector` | `MetricsCollector` → `NodeExecutionMetricsCollector` |
| — | `createExecutionMetric` → `createNodeExecutionMetric` |
| — | `metricToDict` → `nodeExecutionMetricToDict` |
| `NodeExecutionStatus` → `WorkflowNodeCallOutcome` (matches CWE `TekkWorkflowNodeCallOutcomeEnum`) | `NodeExecutionStatus` → `WorkflowNodeCallOutcome` |
| `parse_node_execution_status` → `parse_workflow_node_call_outcome` | `parseNodeExecutionStatus` → `parseWorkflowNodeCallOutcome` |
| `NODE_PROTOCOL_HEADER` → `NODE_CALL_PROTOCOL_HEADER` | `NODE_PROTOCOL_HEADER` → `NODE_CALL_PROTOCOL_HEADER` |
| `NODE_PROTOCOL_VERSION` → `NODE_CALL_PROTOCOL_VERSION` | `NODE_PROTOCOL_VERSION` → `NODE_CALL_PROTOCOL_VERSION` |
| `PROTOCOL_2_OUTCOMES` → `NODE_CALL_PROTOCOL_2_OUTCOMES` | `PROTOCOL_2_OUTCOMES` → `NODE_CALL_PROTOCOL_2_OUTCOMES` |
| `outcome_for_protocol` → `node_call_outcome_for_protocol` | `outcomeForProtocol` → `nodeCallOutcomeForProtocol` |
| `read_outcome` → `read_node_call_outcome` | `readOutcome` → `readNodeCallOutcome` |
| `requested_protocol` → `requested_node_call_protocol` | `requestedProtocol` → `requestedNodeCallProtocol` |

**Node output / uploads cluster**

| Python | TypeScript |
|---|---|
| `OutputUploader` → `NodeOutputUploader` | `OutputUploader` → `NodeOutputUploader` |
| `S3PresignedUploader` → `NodeOutputS3PresignedUploader` | `S3PresignedUploader` → `NodeOutputS3PresignedUploader` |
| `UploadSession` → `NodeOutputUploadSession` | — |
| `UploadTarget` → `NodeOutputUploadTarget` | `UploadTarget` → `NodeOutputUploadTarget` |
| `get_default_uploader` → `get_default_node_output_uploader` | `getDefaultUploader` → `getDefaultNodeOutputUploader` |
| — | `UploadSessionDescriptor` → `NodeOutputUploadSessionDescriptor` |
| `upload_via_session` → `upload_via_cds_multipart_session` | `uploadViaSession` → `uploadViaCdsMultipartSession` |

**Node I/O data cluster**

| Python | TypeScript |
|---|---|
| `BaseContract` → `NodeIoDataContract` | `BaseContractData` → `NodeIoDataContractData` |
| `CONTRACT_VERSION` → `NODE_IO_DATA_CONTRACT_VERSION` | `CONTRACT_VERSION` → `NODE_IO_DATA_CONTRACT_VERSION` |

**Workflow definition / run cluster**

| Python | TypeScript |
|---|---|
| `validate` → `validate_workflow_definition` | `validate` → `validateWorkflowDefinition` |
| `ValidationResult` → `WorkflowDefinitionValidationResult` | `ValidationResult` → `WorkflowDefinitionValidationResult` |
| `WorkflowValidationError` → `WorkflowDefinitionValidationError` | `WorkflowValidationError` → `WorkflowDefinitionValidationError` |
| `WorkflowExecutionError` → `WorkflowRunError` | `WorkflowExecutionError` → `WorkflowRunError` |
| `NodeResult` → `WorkflowRunNodeResult` | `NodeResult` → `WorkflowRunNodeResult` |
| `ErrorPolicy` → `WorkflowRunErrorPolicy` | `ErrorPolicy` → `WorkflowRunErrorPolicy` |
| `NodeExecutor` → `WorkflowRunNodeExecutor` | `NodeExecutor` → `WorkflowRunNodeExecutor` |
| `InProcessExecutor` → `InProcessNodeExecutor` | `InProcessExecutor` → `InProcessNodeExecutor` |
| `HttpExecutor` → `HttpNodeExecutor` | `HttpExecutor` → `HttpNodeExecutor` |

**Exceptions split** (`NodeValidationError` resolution, both languages):
`WorkflowNodeManifestValidationError(NodeValidationError)` +
`NodeInputValidationError(NodeValidationError)` added; raise-sites move to the
specific subclasses; `NodeValidationError` remains the importable, catchable
base (deprecated for *raising*, never for catching).

**TypeScript `*Schema` twins (literal enumeration)** — renamed with their
type: `ColorPresetSchema` → `WorkflowNodeColorPresetSchema`,
`DeprecationInfoSchema` → `WorkflowNodeDeprecationInfoSchema`,
`RetryConfigSchema` → `WorkflowNodeRetryConfigSchema`,
`WorkflowNodeManifestSchema` → kept (type kept),
`HealthResponseSchema` → `WorkflowNodeHealthResponseSchema`,
`NodeExecutionStatusSchema` → `WorkflowNodeCallOutcomeSchema`,
`UploadSessionDescriptorSchema` → `NodeOutputUploadSessionDescriptorSchema`.
Kept (type kept): `WorkflowNodeRoleSchema`, `WorkflowNodeStylesSchema`,
`NodeExecutionRequestSchema`, `NodeExecutionResponseSchema`. Kept auth types
(module-scoped): `AuthMiddleware`, `AuthResult`.

### Complete symbol map — kept (already explicit)

`WorkflowNodeManifest`, `WorkflowNodeRole`, `WorkflowNodeStyles` (+
`*Schema`), `WorkflowNodeManifestSchema`, `NodeExecutionRequest` (+`Schema`),
`NodeExecutionResponse` (+`Schema`), `NodeExecutionResponseFactory`,
`NodeExecutionError`, `NodeTimeoutError`, `NodeIOError`,
`NodeConfigurationError`, `NodeOutputValidationError`, `TekkNodeAuth` (py),
`NodeAuth` (py, distinct FastAPI class), `TekkAuthError`,
`TekkAuthInvalidCredential`, `TekkAuthMissingCredential`,
`TekkAuthNotConfigured`, `TekkAuthTokenExpired`, `TekkAuthUnavailable`,
`CANVASTEKK_AUTH_MARKER`, `NODE_TOKEN_PREFIX`, `isNodeToken`, `NodeTokenClaims`,
`Point3D`, `BoundingBox3D`, `Instance`, `InstanceSet` (TS `InstanceSetData`),
`Measurement`, `MeasurementSet` (TS `MeasurementSetData`), `Plane`,
`PlaneSet` (TS `PlaneSetData`), `STANDARD_CLASSES`, `STANDARD_CLASS_NAMES`,
`DEFAULT_CHECK_VERDICTS`, `build_check_output_schema`,
`validate_verdict_fields`, `saveJson`/`save_json`, `loadJson`/`load_json`,
`point3DToList`, `point3DFromList`, `boundingBoxCenter`, `boundingBoxSize`,
`instanceNumPoints`, `getInstancesByClass`, `getInstancesByClassId`,
`getMeasurement`, `getValue`, `getPlaneByLabel`, `getFileInputFields`,
`getFileOutputFields`, `validateFileInput`, `effectiveRuntimeSeconds`,
`VERSION`, `__version__`, `RELEASE_DATE`, `StructuredJsonFormatter`,
`HumanReadableFormatter`, `configure_logging`/`configureLogging`,
`get_node_logger`/`getNodeLogger`, `createLogger`, `SdkLogger`,
`LoggingMiddleware`, `TimingMiddleware`, `SDKVersionMiddleware`,
`NodeMiddleware`, `LocalFileServer`, `serve_files`/`serveFiles`,
`error_envelope`/`errorEnvelope`, `ERROR_CATEGORIES`, `ERROR_ENVELOPE_KEYS`,
`ERROR_CODE_TO_HTTP_STATUS`, `getHttpStatusForError`, `ErrorCategory`,
`IO_SUBCODE_DOWNLOAD_FAILED`, `IO_SUBCODE_SIZE_EXCEEDED`,
`IO_SUBCODE_URL_POLICY_BLOCKED`, `CTK_PREFIX`, `CTK_BODY_ALPHABET`,
`CTK_BODY_LENGTH`, `invalid_ctk_reason`/`invalidCtkReason`,
`registry_auth_header`/`registryAuthHeader`, `VALID_INVOKE_TYPES`,
`UNSUPPORTED_INVOKE_TYPES`, `InvokeType`, `extractNodeData`,
`registerNodeResultGet`, `registerNodeResultHas`,
`diff_against_published`-side constants (`VERSION_BUMPS`,
`ENGINE_NON_COMPARISON_FIELDS`, `MINIMUM_CONTRACT_ROUTES`,
`CONTRACT_ROUTE_VOCABULARY`, `ENVELOPE_RESERVED_OUTPUT_FIELDS`),
`DEFAULT_MAX_BODY_BYTES`, `PROGRESS_MESSAGE_MAX_CHARS`,
`PROGRESS_PING_TIMEOUT_S`, `WorkflowBuilder`, `WorkflowRunner`,
`WorkflowRunResult`, `EdgeType`, `WorkflowDefinitionNode`,
`WorkflowDefinitionSpec`, `WorkflowEdgeDefinition`, `computeLevels`/
`compute_levels`, `resolveInputs`/`resolve_inputs`, `ResolverError`,
`verify_node`, `RouteCheck`, `VerifyReport`, convergence internals
(`drain`, `compute_drain`, `fetch_actives`, `history_slugs`,
`load_declared`, `load_declared_from_text`, `assert_staged`,
`canonical_from_invoke_url`, `PAGE_SIZE`, `main`).

## Versioning

Released as **0.67.0** (non-breaking: new names + deprecated aliases).
Version files are never hand-bumped — the release pipeline stamps all five
sources tag-derived at publish. **N1 tickets stay pinned to exactly v0.66.0**
(user directive, 2026-11-19): releasing 0.67.0 does not switch any N1 PR;
CLS (#809) and IFC (#553) migrate to the new protocol-helper names on their
own tickets, and the old names (`outcome_for_protocol` /
`outcomeForProtocol` et al.) keep working via aliases for any consumer that
later upgrades.

## Verification (step 1.3 — enumeration cross-check)

Machine-checked 2026-11-19 against `python/canvastekk_workflow_sdk/__init__.py`
`__all__` (85 names), the `typescript/src/index.ts` export surface (122
names), and the module-level publics of all 17 renamed Python modules:
**zero missing in both directions after the Schema-twin enumeration** (11
`*Schema`/auth names added on first pass). Python `ErrorPolicy` lives in
`workflow/runner.py` (renames in place there). The Phase-5 guard test
re-pins this invariant permanently.

## Consequences

- Public surface says which object every name belongs to; the
  "definition" ambiguity is gone (node-level = manifest, workflow-level =
  workflow definition).
- Consumers (CWE, FE, node-hosts) keep working unchanged on 0.66.0 and on
  0.67.0 via aliases; they migrate on epic tickets R2–R10; 1.0.0 (#272)
  removes the aliases.
- No wire change: manifest/registry/payload JSON keys are untouched — only
  Python/TS identifiers move.
- Guard tests pin py↔ts name parity and the no-node-level-"definition"
  invariant permanently (shim-aware via `_deprecated_alias_of` markers).
