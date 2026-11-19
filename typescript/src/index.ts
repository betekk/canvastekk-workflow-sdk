/**
 * CanvasTEKK Workflow SDK for TypeScript.
 *
 * Provides:
 * - WorkflowNodeBase abstract class for creating workflow nodes
 * - Express app creation with createWorkflowNodeApp/createMultiWorkflowNodeApp
 * - Authentication middleware (API key, JWT, Keycloak)
 * - Workflow builder and runner for local DAG execution
 * - Contract types for Point3D, Instance, Measurement, Plane
 * - Node registration with CanvasTEKK registry
 *
 * @see https://github.com/betekk/canvastekk-workflow-sdk
 */
export { VERSION } from "./version.js";
// --- Deprecated name aliases, phase 3 (ADR 0001, #271; removal in 1.0.0, #272) ---
/** @deprecated use WorkflowNodeBase */
export { WorkflowNodeBase as BaseNode } from "./workflow-node-base.js";
/** @deprecated use createWorkflowNodeApp */
export { createWorkflowNodeApp as createNodeApp } from "./workflow-node-app.js";
/** @deprecated use createMultiWorkflowNodeApp */
export { createMultiWorkflowNodeApp as createMultiNodeApp } from "./workflow-node-app.js";
/** @deprecated use NodeExecutionContext */
export { NodeExecutionContext as ExecutionContext } from "./node-execution-context.js";
/** @deprecated use WorkflowNodeHealthResponse */
export { WorkflowNodeHealthResponseSchema as HealthResponseSchema, type WorkflowNodeHealthResponse as HealthResponse } from "./node-execution-response.js";
/** @deprecated use WorkflowNodeCallOutcome / parseWorkflowNodeCallOutcome */
export { WorkflowNodeCallOutcomeSchema as NodeExecutionStatusSchema, parseWorkflowNodeCallOutcome as parseNodeExecutionStatus, type WorkflowNodeCallOutcome as NodeExecutionStatus } from "./node-execution-response.js";
/** @deprecated use NODE_CALL_PROTOCOL_HEADER etc. */
export { NODE_CALL_PROTOCOL_HEADER as NODE_PROTOCOL_HEADER, NODE_CALL_PROTOCOL_VERSION as NODE_PROTOCOL_VERSION, NODE_CALL_PROTOCOL_2_OUTCOMES as PROTOCOL_2_OUTCOMES, nodeCallOutcomeForProtocol as outcomeForProtocol, readNodeCallOutcome as readOutcome, requestedNodeCallProtocol as requestedProtocol } from "./node-call-protocol.js";
/** @deprecated use NodeExecutionMetric / NodeExecutionMetricsCollector */
export { NodeExecutionMetricsCollector as MetricsCollector, createNodeExecutionMetric as createExecutionMetric, nodeExecutionMetricToDict as metricToDict, type NodeExecutionMetric as ExecutionMetric } from "./observability.js";
/** @deprecated use NodeOutput* names */
export { NodeOutputS3PresignedUploader as S3PresignedUploader, getDefaultNodeOutputUploader as getDefaultUploader, NodeOutputUploadSessionDescriptorSchema as UploadSessionDescriptorSchema, type NodeOutputUploader as OutputUploader, type NodeOutputUploadTarget as UploadTarget, type NodeOutputUploadSessionDescriptor as UploadSessionDescriptor } from "./node-output-uploads.js";
/** @deprecated use uploadViaCdsMultipartSession */
export { uploadViaCdsMultipartSession as uploadViaSession } from "./cds-multipart-upload.js";
/** @deprecated use NODE_IO_DATA_CONTRACT_VERSION */
export { NODE_IO_DATA_CONTRACT_VERSION as CONTRACT_VERSION, type NodeIoDataContractData as BaseContractData } from "./node-io-data-contracts/index.js";
// --- end phase-3 deprecated aliases ---
// --- Deprecated name aliases, phase 4 (ADR 0001, #271; removal in 1.0.0, #272) ---
/** @deprecated use validateWorkflowDefinition */
export { validateWorkflowDefinition as validate } from "./workflow/index.js";
/** @deprecated use WorkflowDefinitionValidationResult */
export { type WorkflowDefinitionValidationResult as ValidationResult } from "./workflow/index.js";
/** @deprecated use WorkflowRunNodeResult */
export { type WorkflowRunNodeResult as NodeResult } from "./workflow/index.js";
/** @deprecated use WorkflowRunErrorPolicy */
export { type WorkflowRunErrorPolicy as ErrorPolicy } from "./workflow/index.js";
/** @deprecated use WorkflowRunNodeExecutor / InProcessNodeExecutor / HttpNodeExecutor */
export { type WorkflowRunNodeExecutor as NodeExecutor, InProcessNodeExecutor as InProcessExecutor, HttpNodeExecutor as HttpExecutor } from "./workflow/index.js";
/** @deprecated use WorkflowRunError */
export { WorkflowRunError as WorkflowExecutionError } from "./exceptions.js";
/** @deprecated use WorkflowDefinitionValidationError */
export { WorkflowDefinitionValidationError as WorkflowValidationError } from "./exceptions.js";
// --- end phase-4 deprecated aliases ---

// --- Deprecated name aliases (ADR 0001, #271; removal in 1.0.0, #272) ---
/** @deprecated use WorkflowNodeColorPreset */
export { WorkflowNodeColorPresetSchema as ColorPresetSchema, type WorkflowNodeColorPreset as ColorPreset } from "./workflow-node-manifest.js";
/** @deprecated use WorkflowNodeRetryConfig */
export { WorkflowNodeRetryConfigSchema as RetryConfigSchema, type WorkflowNodeRetryConfig as RetryConfig } from "./workflow-node-manifest.js";
/** @deprecated use WorkflowNodeDeprecationInfo */
export { WorkflowNodeDeprecationInfoSchema as DeprecationInfoSchema, type WorkflowNodeDeprecationInfo as DeprecationInfo } from "./workflow-node-manifest.js";
/** @deprecated use WorkflowNodeManifestContract */
export { type WorkflowNodeManifestContract as NodeContract } from "./workflow-node-manifest.js";
/** @deprecated use WorkflowNodeContractCapabilities */
export { type WorkflowNodeContractCapabilities as ContractCapabilities } from "./workflow-node-manifest.js";
/** @deprecated use getWorkflowNodeManifestId */
export { getWorkflowNodeManifestId as getNodeId } from "./workflow-node-manifest.js";
/** @deprecated use diffWorkflowNodeManifests / WorkflowNodeManifestDiff */
export { diffWorkflowNodeManifests as diffManifests, type WorkflowNodeManifestDiff as ManifestDiff } from "./workflow-node-manifest-diff.js";
/** @deprecated use registerWorkflowNode */
export { registerWorkflowNode as registerNode } from "./workflow-node-registry.js";
/** @deprecated use WorkflowNodeRegistrationResult */
export { type WorkflowNodeRegistrationResult as RegisterNodeResult } from "./workflow-node-registry.js";
/** @deprecated use WorkflowNodeRegistrationError */
export { WorkflowNodeRegistrationError as RegistrationError } from "./exceptions.js";
/** @deprecated use buildWorkflowNodeRegistryPayload */
export { buildWorkflowNodeRegistryPayload as buildRegistryPayload } from "./workflow-node-registry.js";
/** @deprecated use exportWorkflowNodeManifest */
export { exportWorkflowNodeManifest as exportDefinition } from "./workflow-node-registry.js";
// --- end deprecated aliases ---
export {
  WorkflowNodeColorPresetSchema,
  WorkflowNodeStylesSchema,
  WorkflowNodeRetryConfigSchema,
  WorkflowNodeManifestSchema,
  WorkflowNodeRoleSchema,
  WorkflowNodeDeprecationInfoSchema,
  getWorkflowNodeManifestId,
  getFileInputFields,
  getFileOutputFields,
  validateFileInput,
  effectiveRuntimeSeconds,
  type WorkflowNodeColorPreset,
  type WorkflowNodeStyles,
  type WorkflowNodeRetryConfig,
  type WorkflowNodeManifest,
  type WorkflowNodeRole,
  type WorkflowNodeDeprecationInfo,
} from "./workflow-node-manifest.js";
export {
  NodeExecutionError,
  NodeTimeoutError,
  NodeValidationError,
  NodeOutputValidationError,
  NodeIOError,
  NodeConfigurationError,
  WorkflowRunError,
  WorkflowDefinitionValidationError,
  WorkflowNodeRegistrationError,
  ERROR_CODE_TO_HTTP_STATUS,
  getHttpStatusForError,
  ERROR_CATEGORIES,
  ERROR_ENVELOPE_KEYS,
  IO_SUBCODE_DOWNLOAD_FAILED,
  IO_SUBCODE_SIZE_EXCEEDED,
  IO_SUBCODE_URL_POLICY_BLOCKED,
  errorEnvelope,
} from "./exceptions.js";
export type { ErrorCategory } from "./exceptions.js";
export {
  NodeExecutionRequestSchema,
  type NodeExecutionRequest,
} from "./node-execution-request.js";
export {
  NodeExecutionResponseSchema,
  WorkflowNodeCallOutcomeSchema,
  parseWorkflowNodeCallOutcome,
  NodeExecutionResponseFactory,
  WorkflowNodeHealthResponseSchema,
  type NodeExecutionResponse,
  type WorkflowNodeCallOutcome,
  type WorkflowNodeHealthResponse,
} from "./node-execution-response.js";
export {
  NODE_CALL_PROTOCOL_HEADER,
  NODE_CALL_PROTOCOL_VERSION,
  NODE_CALL_PROTOCOL_2_OUTCOMES,
  nodeCallOutcomeForProtocol,
  readNodeCallOutcome,
  requestedNodeCallProtocol,
} from "./node-call-protocol.js";
export {
  StructuredJsonFormatter,
  HumanReadableFormatter,
  configureLogging,
  getNodeLogger,
  createLogger,
  type SdkLogger,
} from "./logging.js";
export { NodeExecutionContext } from "./node-execution-context.js";
export {
  LoggingMiddleware,
  TimingMiddleware,
  SDKVersionMiddleware,
} from "./middleware.js";
export type { NodeMiddleware } from "./middleware.js";
export {
  NodeExecutionMetricsCollector,
  createNodeExecutionMetric,
  nodeExecutionMetricToDict,
  type NodeExecutionMetric,
} from "./observability.js";
export { WorkflowNodeBase } from "./workflow-node-base.js";
export { TekkNodeAuth, CANVASTEKK_AUTH_MARKER } from "./auth.js";
/** @deprecated use TekkNodeAuth (ADR 0001, #271) */
export { NodeAuth } from "./auth.js";
export type { AuthMiddleware, AuthResult } from "./auth.js";
export { NODE_TOKEN_PREFIX, isNodeToken } from "./node-token.js";
export type { NodeTokenClaims } from "./node-token.js";
export { NodeOutputS3PresignedUploader, getDefaultNodeOutputUploader, NodeOutputUploadSessionDescriptorSchema } from "./node-output-uploads.js";
export type { NodeOutputUploader, NodeOutputUploadTarget, NodeOutputUploadSessionDescriptor } from "./node-output-uploads.js";
export { uploadViaCdsMultipartSession } from "./cds-multipart-upload.js";
export {
  NODE_IO_DATA_CONTRACT_VERSION,
  saveJson,
  loadJson,
  point3DToList,
  point3DFromList,
  boundingBoxCenter,
  boundingBoxSize,
  instanceNumPoints,
  getInstancesByClass,
  getInstancesByClassId,
  getMeasurement,
  getValue,
  getPlaneByLabel,
  STANDARD_CLASSES,
  STANDARD_CLASS_NAMES,
} from "./node-io-data-contracts/index.js";
export type {
  NodeIoDataContractData,
  Point3D,
  BoundingBox3D,
  Instance,
  InstanceSetData,
  Measurement,
  MeasurementSetData,
  Plane,
  PlaneSetData,
} from "./node-io-data-contracts/index.js";
export {
  buildWorkflowNodeRegistryPayload,
  registerWorkflowNode,
  exportWorkflowNodeManifest,
  extractNodeData,
  registerNodeResultGet,
  registerNodeResultHas,
} from "./workflow-node-registry.js";
export type { InvokeType, WorkflowNodeRegistrationResult } from "./workflow-node-registry.js";
export { diffWorkflowNodeManifests } from "./workflow-node-manifest-diff.js";
export type { WorkflowNodeManifestDiff } from "./workflow-node-manifest-diff.js";
export {
  WorkflowBuilder,
  InProcessNodeExecutor,
  HttpNodeExecutor,
  WorkflowRunner,
  computeLevels,
  resolveInputs,
  ResolverError,
  validateWorkflowDefinition,
} from "./workflow/index.js";
export type {
  EdgeType,
  WorkflowEdgeDefinition,
  WorkflowDefinitionNode,
  WorkflowDefinitionSpec,
  WorkflowRunNodeExecutor,
  WorkflowRunErrorPolicy,
  WorkflowRunNodeResult,
  WorkflowRunResult,
  WorkflowDefinitionValidationResult,
} from "./workflow/index.js";

import { warnSupportHorizon } from "./support-horizon.js";
warnSupportHorizon();
