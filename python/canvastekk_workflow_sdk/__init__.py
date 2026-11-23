"""
CanvasTEKK Workflow Node SDK

A convenience SDK for building HTTP-based workflow nodes.
Handles all boilerplate (endpoints, validation, error handling)
so node authors can focus on business logic.

Quick Start:
    from canvastekk_workflow_sdk import WorkflowNodeBase, WorkflowNodeManifest, NodeExecutionContext

    class MyNode(WorkflowNodeBase):
        definition = WorkflowNodeManifest(
            slug="my-node",
            version="1.0.0",
            name="My Node",
            description="Does something useful",
            input_schema={"type": "object", "properties": {"input": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"output": {"type": "string"}}},
        )

        def execute(self, inputs: dict, context: NodeExecutionContext) -> dict:
            return {"output": f"Processed: {inputs.get('input', '')}"}

    # Create FastAPI app
    app = MyNode().create_app()

Run with:
    uvicorn handler:app --port 8001

Endpoints:
    POST /execute    - Run the node
    GET /health      - Health check
    GET /manifest    - Node self-description
    POST /hook       - Webhook/callback handler

Philosophy:
    The SDK is a convenience layer, not a hard dependency.
    Nodes can "eject" by copying SDK code if true independence is needed.
"""

from canvastekk_workflow_sdk.auth.core import (
    TekkAuthError,
    TekkAuthInvalidCredential,
    TekkAuthMissingCredential,
    TekkAuthNotConfigured,
    TekkAuthTokenExpired,
    TekkAuthUnavailable,
    TekkNodeAuth,
)
from canvastekk_workflow_sdk.check_node_base import CheckNodeBase, check_node_conformance_errors
from canvastekk_workflow_sdk.check_result_reader import CheckResultReader, CheckResultReadError, open_check_result
from canvastekk_workflow_sdk.check_verdict import (
    VERDICT_MARK,
    CheckResolution,
    CheckSpec,
    CheckVerdictError,
    JudgedResult,
    Reading,
    Rule,
    TekkCheckOperatorEnum,
    TekkCheckRoleEnum,
    TekkCheckRoundingEnum,
    TekkWorkflowRunVerdictEnum,
    VerdictPolicy,
    judge,
    rollup,
    rules_from_inputs,
)
from canvastekk_workflow_sdk.exceptions import (
    ERROR_CATEGORIES,
    ERROR_ENVELOPE_KEYS,
    IO_SUBCODE_DOWNLOAD_FAILED,
    IO_SUBCODE_SIZE_EXCEEDED,
    IO_SUBCODE_URL_POLICY_BLOCKED,
    NodeConfigurationError,
    NodeExecutionError,
    NodeIOError,
    NodeOutputValidationError,
    NodeTimeoutError,
    NodeValidationError,
    WorkflowDefinitionValidationError,
    WorkflowRunError,
    error_envelope,
)
from canvastekk_workflow_sdk.logging import StructuredJsonFormatter, configure_logging, get_node_logger
from canvastekk_workflow_sdk.middleware import LoggingMiddleware, NodeMiddleware, TimingMiddleware
from canvastekk_workflow_sdk.node_execution_context import NodeExecutionContext
from canvastekk_workflow_sdk.node_execution_request import NodeExecutionRequest
from canvastekk_workflow_sdk.node_execution_response import NodeExecutionResponse, WorkflowNodeHealthResponse
from canvastekk_workflow_sdk.node_io_data_contracts import (
    BoundingBox3D,
    Instance,
    InstanceSet,
    Measurement,
    MeasurementSet,
    NodeIoDataContract,
    Plane,
    PlaneSet,
    Point3D,
    WorkflowNodeCallOutcome,
    parse_workflow_node_call_outcome,
)
from canvastekk_workflow_sdk.node_output_uploads import (
    NodeOutputS3PresignedUploader,
    NodeOutputUploader,
    NodeOutputUploadSession,
    NodeOutputUploadTarget,
    get_default_node_output_uploader,
)
from canvastekk_workflow_sdk.observability import NodeExecutionMetric, NodeExecutionMetricsCollector
from canvastekk_workflow_sdk.result_file import (
    RESULT_FILE_OUTPUT_FIELD,
    RESULT_FILE_VERSION,
    ResultFileFormatError,
    read_result_file_header,
    result_file_output_schema,
    validate_result_file_header,
    write_result_file,
)
from canvastekk_workflow_sdk.testing import LocalFileServer, serve_files
from canvastekk_workflow_sdk.workflow import (
    EdgeType,
    HttpNodeExecutor,
    InProcessNodeExecutor,
    WorkflowBuilder,
    WorkflowDefinitionNode,
    WorkflowDefinitionSpec,
    WorkflowDefinitionValidationResult,
    WorkflowEdgeDefinition,
    WorkflowRunner,
    WorkflowRunNodeExecutor,
    WorkflowRunNodeResult,
    WorkflowRunResult,
    validate_workflow_definition,
)
from canvastekk_workflow_sdk.workflow_node_base import WorkflowNodeBase
from canvastekk_workflow_sdk.workflow_node_manifest import (
    WorkflowNodeColorPreset,
    WorkflowNodeContractCapabilities,
    WorkflowNodeDeprecationInfo,
    WorkflowNodeManifest,
    WorkflowNodeManifestContract,
    WorkflowNodeRetryConfig,
    WorkflowNodeRole,
    WorkflowNodeStyles,
    export_workflow_node_manifest,
)
from canvastekk_workflow_sdk.workflow_node_registry import (
    WorkflowNodeRegistrationError,
    WorkflowNodeRegistrationResult,
    build_workflow_node_registry_payload,
    register_workflow_node,
)

__all__ = [
    "VERDICT_MARK",
    "CheckNodeBase",
    "CheckResolution",
    "CheckResultReadError",
    "CheckResultReader",
    "CheckSpec",
    "CheckVerdictError",
    "JudgedResult",
    "Reading",
    "Rule",
    "TekkCheckOperatorEnum",
    "TekkCheckRoleEnum",
    "TekkCheckRoundingEnum",
    "TekkWorkflowRunVerdictEnum",
    "VerdictPolicy",
    "check_node_conformance_errors",
    "judge",
    "open_check_result",
    "rollup",
    "rules_from_inputs",
    "RESULT_FILE_OUTPUT_FIELD",
    "RESULT_FILE_VERSION",
    "ResultFileFormatError",
    "read_result_file_header",
    "result_file_output_schema",
    "validate_result_file_header",
    "write_result_file",
    "NodeIoDataContract",
    "WorkflowNodeBase",
    "BoundingBox3D",
    "WorkflowNodeColorPreset",
    "ERROR_CATEGORIES",
    "ERROR_ENVELOPE_KEYS",
    "IO_SUBCODE_DOWNLOAD_FAILED",
    "IO_SUBCODE_SIZE_EXCEEDED",
    "IO_SUBCODE_URL_POLICY_BLOCKED",
    "WorkflowNodeContractCapabilities",
    "WorkflowNodeDeprecationInfo",
    "EdgeType",
    "NodeExecutionContext",
    "NodeExecutionMetric",
    "WorkflowNodeHealthResponse",
    "HttpNodeExecutor",
    "InProcessNodeExecutor",
    "Instance",
    "InstanceSet",
    "LocalFileServer",
    "LoggingMiddleware",
    "Measurement",
    "MeasurementSet",
    "NodeExecutionMetricsCollector",
    "NodeAuth",
    "NodeConfigurationError",
    "WorkflowNodeManifestContract",
    "NodeExecutionError",
    "NodeExecutionRequest",
    "NodeExecutionResponse",
    "WorkflowRunNodeExecutor",
    "NodeIOError",
    "NodeMiddleware",
    "WorkflowNodeCallOutcome",
    "NodeOutputValidationError",
    "WorkflowRunNodeResult",
    "NodeTimeoutError",
    "NodeValidationError",
    "error_envelope",
    "parse_workflow_node_call_outcome",
    "NodeOutputUploader",
    "Plane",
    "PlaneSet",
    "Point3D",
    "WorkflowNodeRegistrationResult",
    "WorkflowNodeRegistrationError",
    "WorkflowNodeRetryConfig",
    "NodeOutputS3PresignedUploader",
    "NodeOutputUploadSession",
    "NodeOutputUploadTarget",
    "SDKVersionMiddleware",
    "StructuredJsonFormatter",
    "TekkAuthError",
    "TekkAuthInvalidCredential",
    "TekkAuthMissingCredential",
    "TekkAuthNotConfigured",
    "TekkAuthTokenExpired",
    "TekkAuthUnavailable",
    "TekkNodeAuth",
    "TimingMiddleware",
    "WorkflowDefinitionValidationResult",
    "WorkflowBuilder",
    "WorkflowDefinitionNode",
    "WorkflowDefinitionSpec",
    "WorkflowEdgeDefinition",
    "WorkflowRunError",
    "WorkflowNodeManifest",
    "WorkflowNodeRole",
    "WorkflowNodeStyles",
    "WorkflowRunResult",
    "WorkflowRunner",
    "WorkflowDefinitionValidationError",
    "build_workflow_node_registry_payload",
    "configure_logging",
    "create_authed_workflow_node_app",
    "create_workflow_node_lambda_handler",
    "create_multi_workflow_node_app",
    "create_workflow_node_app",
    "mount_workflow_node",
    "export_workflow_node_manifest",
    "get_default_node_output_uploader",
    "get_node_logger",
    "register_workflow_node",
    "serve_files",
    "validate_workflow_definition",
]

from canvastekk_workflow_sdk._version import RELEASE_DATE as RELEASE_DATE  # noqa: E402, F401
from canvastekk_workflow_sdk._version import __version__ as __version__  # noqa: E402, F401

_LAZY_SERVER_EXPORTS = {
    "create_workflow_node_app": "canvastekk_workflow_sdk.workflow_node_app",
    "create_multi_workflow_node_app": "canvastekk_workflow_sdk.multi_node_router",
    "NodeAuth": "canvastekk_workflow_sdk.auth",
    "SDKVersionMiddleware": "canvastekk_workflow_sdk._server_middleware",
    "create_authed_workflow_node_app": "canvastekk_workflow_sdk.bootstrap",
    "mount_workflow_node": "canvastekk_workflow_sdk.bootstrap",
    "create_workflow_node_lambda_handler": "canvastekk_workflow_sdk.bootstrap",
}


def __getattr__(name: str):
    if name in _LAZY_SERVER_EXPORTS:
        try:
            import fastapi  # noqa: F401
        except ImportError as exc:
            raise ImportError(
                f"{name!r} requires the fastapi-backed server modules; "
                "install the extra: pip install canvastekk-workflow-sdk[fastapi]"
            ) from exc
        import importlib

        module = importlib.import_module(_LAZY_SERVER_EXPORTS[name])
        value = getattr(module, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
