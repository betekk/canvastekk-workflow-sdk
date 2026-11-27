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
export { RunContextSchema, type RunContext } from "./run-context.js";
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
export {
  RESULT_FILE_VERSION,
  SUPPORTED_RESULT_FILE_VERSIONS,
  RESULT_FILE_OUTPUT_FIELD,
  RESULT_FILE_MARKER,
  RESULT_FILE_CONTENT_TYPE,
  RESULT_FILE_DEFAULT_NAME,
  RESULT_FILE_SUMMARY_MAX_BYTES,
  RESULT_FILE_HEADER_KEYS,
  RESULT_FILE_SCHEMA_1_0_0,
  RESULT_FILE_END_VALUE_SCHEMA_1_0_0,
  ResultFileFormatError,
  validateResultFileHeader,
  buildResultFileHeader,
  serializeResultFileHeaderPrefix,
  writeResultFile,
  resultFileOutputSchema,
  resultFileDeclarationErrors,
  RESULT_FILE_VERSION_1_1_0,
  RESULT_FILE_INPUTS_MAX_BYTES,
  RESULT_FILE_HEADER_KEYS_BY_VERSION,
  RESULT_FILE_OPTIONAL_HEADER_KEYS,
  RESULT_FILE_SCHEMA_1_1_0,
} from "./result-file.js";
export {
  VERDICT_MARK,
  CHECK_RESULT_SCHEMA,
  CHECK_RESULT_SCHEMA_VERSION,
  CHECK_RESULT_SCHEMA_VERSION_2_0_0,
  CHECK_RESULT_SCHEMA_VERSION_2_1_0,
  CHECK_RESULT_SCHEMA_VERSION_2_2_0,
  TekkCheckRoleEnum,
  TekkCheckOperatorEnum,
  TekkWorkflowRunVerdictEnum,
  TekkCheckRoundingEnum,
  VERDICT_PRECEDENCE,
  STATEMENT_PLACEHOLDERS,
  rollupVerdicts,
  CheckSpecSchema,
  MODEL_CHECK_CHECK_BODY_SCHEMA_1_0_0,
  MODEL_CHECK_CHECK_BODY_SCHEMA_2_0_0,
  MODEL_CHECK_CHECK_BODY_SCHEMA_2_1_0,
  MODEL_CHECK_CHECK_BODY_SCHEMA_2_2_0,
} from "./check-verdict.js";
export { MODEL_CHECK_FLOOR_GROUP_TEST_VECTORS } from "./model-check-floor-group-vectors.js";
export type { TekkCheckRole, TekkCheckOperator, TekkWorkflowRunVerdict, CheckSpec } from "./check-verdict.js";
export type {
  ResultFileHeader,
  ResultFileHeaderOptions,
  ResultFileSummaryValue,
  WriteResultFileOptions,
} from "./result-file.js";
