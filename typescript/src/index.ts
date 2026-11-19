/**
 * CanvasTEKK Workflow SDK for TypeScript.
 *
 * Provides:
 * - BaseNode abstract class for creating workflow nodes
 * - Express app creation with createNodeApp/createMultiNodeApp
 * - Authentication middleware (API key, JWT, Keycloak)
 * - Workflow builder and runner for local DAG execution
 * - Contract types for Point3D, Instance, Measurement, Plane
 * - Node registration with CanvasTEKK registry
 *
 * @see https://github.com/betekk/canvastekk-workflow-sdk
 */
export { VERSION } from "./version.js";

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
  WorkflowExecutionError,
  WorkflowValidationError,
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
} from "./request.js";
export {
  NodeExecutionResponseSchema,
  NodeExecutionStatusSchema,
  parseNodeExecutionStatus,
  NodeExecutionResponseFactory,
  HealthResponseSchema,
  type NodeExecutionResponse,
  type NodeExecutionStatus,
  type HealthResponse,
} from "./response.js";
export {
  NODE_PROTOCOL_HEADER,
  NODE_PROTOCOL_VERSION,
  PROTOCOL_2_OUTCOMES,
  outcomeForProtocol,
  readOutcome,
  requestedProtocol,
} from "./protocol.js";
export {
  StructuredJsonFormatter,
  HumanReadableFormatter,
  configureLogging,
  getNodeLogger,
  createLogger,
  type SdkLogger,
} from "./logging.js";
export { ExecutionContext } from "./context.js";
export {
  LoggingMiddleware,
  TimingMiddleware,
  SDKVersionMiddleware,
} from "./middleware.js";
export type { NodeMiddleware } from "./middleware.js";
export {
  MetricsCollector,
  createExecutionMetric,
  metricToDict,
  type ExecutionMetric,
} from "./observability.js";
export { BaseNode } from "./base-node.js";
export { NodeAuth, TekkNodeAuth, CANVASTEKK_AUTH_MARKER } from "./auth.js";
export type { AuthMiddleware, AuthResult } from "./auth.js";
export { NODE_TOKEN_PREFIX, isNodeToken } from "./node-token.js";
export type { NodeTokenClaims } from "./node-token.js";
export { S3PresignedUploader, getDefaultUploader, UploadSessionDescriptorSchema } from "./uploads.js";
export type { OutputUploader, UploadTarget, UploadSessionDescriptor } from "./uploads.js";
export { uploadViaSession } from "./multipart.js";
export {
  CONTRACT_VERSION,
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
} from "./contracts/index.js";
export type {
  BaseContractData,
  Point3D,
  BoundingBox3D,
  Instance,
  InstanceSetData,
  Measurement,
  MeasurementSetData,
  Plane,
  PlaneSetData,
} from "./contracts/index.js";
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
  InProcessExecutor,
  HttpExecutor,
  WorkflowRunner,
  computeLevels,
  resolveInputs,
  ResolverError,
  validate,
} from "./workflow/index.js";
export type {
  EdgeType,
  WorkflowEdgeDefinition,
  WorkflowDefinitionNode,
  WorkflowDefinitionSpec,
  NodeExecutor,
  ErrorPolicy,
  NodeResult,
  WorkflowRunResult,
  ValidationResult,
} from "./workflow/index.js";

import { warnSupportHorizon } from "./support-horizon.js";
warnSupportHorizon();
