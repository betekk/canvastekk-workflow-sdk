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
export {
  ColorPresetSchema,
  WorkflowNodeStylesSchema,
  RetryConfigSchema,
  WorkflowNodeManifestSchema,
  WorkflowNodeRoleSchema,
  DeprecationInfoSchema,
  getNodeId,
  getFileInputFields,
  getFileOutputFields,
  validateFileInput,
  effectiveRuntimeSeconds,
  type ColorPreset,
  type WorkflowNodeStyles,
  type RetryConfig,
  type WorkflowNodeManifest,
  type WorkflowNodeRole,
  type DeprecationInfo,
} from "./definition.js";
export {
  NodeExecutionError,
  NodeTimeoutError,
  NodeValidationError,
  NodeOutputValidationError,
  NodeIOError,
  NodeConfigurationError,
  WorkflowExecutionError,
  WorkflowValidationError,
  RegistrationError,
  ERROR_CODE_TO_HTTP_STATUS,
  getHttpStatusForError,
} from "./exceptions.js";
export {
  NodeExecutionRequestSchema,
  type NodeExecutionRequest,
} from "./request.js";
export {
  NodeExecutionResponseSchema,
  NodeExecutionResponseFactory,
  HealthResponseSchema,
  type NodeExecutionResponse,
  type HealthResponse,
} from "./response.js";
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
export { createNodeApp, createMultiNodeApp } from "./app.js";
export type { CreateNodeAppOptions } from "./app.js";
export { NodeAuth, CANVASTEKK_AUTH_MARKER } from "./auth.js";
export type { AuthMiddleware, AuthResult } from "./auth.js";
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
  buildRegistryPayload,
  registerNode,
  exportDefinition,
  extractNodeData,
  registerNodeResultGet,
  registerNodeResultHas,
} from "./registry.js";
export type { InvokeType, RegisterNodeResult } from "./registry.js";
export { diffManifests } from "./diff.js";
export type { ManifestDiff } from "./diff.js";
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

// DA-3359: package import warns (log only) once the support horizon nears/passes.
import { warnSupportHorizon } from "./support-horizon.js";
warnSupportHorizon();
