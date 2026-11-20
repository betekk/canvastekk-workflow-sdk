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
export type { WorkflowNodeManifestContract, WorkflowNodeContractCapabilities } from "./workflow-node-manifest.js";
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
