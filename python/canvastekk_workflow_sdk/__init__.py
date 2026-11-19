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
    WorkflowExecutionError,
    WorkflowValidationError,
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
from canvastekk_workflow_sdk.testing import LocalFileServer, serve_files
from canvastekk_workflow_sdk.workflow import (
    EdgeType,
    HttpExecutor,
    InProcessExecutor,
    NodeExecutor,
    NodeResult,
    ValidationResult,
    WorkflowBuilder,
    WorkflowDefinitionNode,
    WorkflowDefinitionSpec,
    WorkflowEdgeDefinition,
    WorkflowRunner,
    WorkflowRunResult,
    validate,
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
    "HttpExecutor",
    "InProcessExecutor",
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
    "NodeExecutor",
    "NodeIOError",
    "NodeMiddleware",
    "WorkflowNodeCallOutcome",
    "NodeOutputValidationError",
    "NodeResult",
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
    "ValidationResult",
    "WorkflowBuilder",
    "WorkflowDefinitionNode",
    "WorkflowDefinitionSpec",
    "WorkflowEdgeDefinition",
    "WorkflowExecutionError",
    "WorkflowNodeManifest",
    "WorkflowNodeRole",
    "WorkflowNodeStyles",
    "WorkflowRunResult",
    "WorkflowRunner",
    "WorkflowValidationError",
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
    "validate",
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

# Deprecated public-name aliases (ADR 0001, #271): old name -> (module, new
# name). Resolved lazily so new-name users never see a DeprecationWarning.
_DEPRECATED_NAME_ALIASES = {
    "export_definition": ("canvastekk_workflow_sdk.workflow_node_manifest", "export_workflow_node_manifest"),
    "NodeContract": ("canvastekk_workflow_sdk.workflow_node_manifest", "WorkflowNodeManifestContract"),
    "ContractCapabilities": ("canvastekk_workflow_sdk.workflow_node_manifest", "WorkflowNodeContractCapabilities"),
    "RetryConfig": ("canvastekk_workflow_sdk.workflow_node_manifest", "WorkflowNodeRetryConfig"),
    "ColorPreset": ("canvastekk_workflow_sdk.workflow_node_manifest", "WorkflowNodeColorPreset"),
    "DeprecationInfo": ("canvastekk_workflow_sdk.workflow_node_manifest", "WorkflowNodeDeprecationInfo"),
    "SDK_SERVED_CONTRACT_ROUTES": ("canvastekk_workflow_sdk.workflow_node_manifest", "WORKFLOW_NODE_MANIFEST_CONTRACT_ROUTES"),
    "RegisterNodeResult": ("canvastekk_workflow_sdk.workflow_node_registry", "WorkflowNodeRegistrationResult"),
    "RegistrationError": ("canvastekk_workflow_sdk.workflow_node_registry", "WorkflowNodeRegistrationError"),
    "register_node": ("canvastekk_workflow_sdk.workflow_node_registry", "register_workflow_node"),
    "build_registry_payload": ("canvastekk_workflow_sdk.workflow_node_registry", "build_workflow_node_registry_payload"),
    # Phase 3 (ADR 0001): node runtime + execution cluster
    "BaseNode": ("canvastekk_workflow_sdk.workflow_node_base", "WorkflowNodeBase"),
    "ExecutionContext": ("canvastekk_workflow_sdk.node_execution_context", "NodeExecutionContext"),
    "ExecutionMetric": ("canvastekk_workflow_sdk.observability", "NodeExecutionMetric"),
    "MetricsCollector": ("canvastekk_workflow_sdk.observability", "NodeExecutionMetricsCollector"),
    "HealthResponse": ("canvastekk_workflow_sdk.node_execution_response", "WorkflowNodeHealthResponse"),
    "NodeExecutionStatus": ("canvastekk_workflow_sdk.node_io_data_contracts", "WorkflowNodeCallOutcome"),
    "parse_node_execution_status": ("canvastekk_workflow_sdk.node_io_data_contracts", "parse_workflow_node_call_outcome"),
    "OutputUploader": ("canvastekk_workflow_sdk.node_output_uploads", "NodeOutputUploader"),
    "S3PresignedUploader": ("canvastekk_workflow_sdk.node_output_uploads", "NodeOutputS3PresignedUploader"),
    "UploadSession": ("canvastekk_workflow_sdk.node_output_uploads", "NodeOutputUploadSession"),
    "UploadTarget": ("canvastekk_workflow_sdk.node_output_uploads", "NodeOutputUploadTarget"),
    "get_default_uploader": ("canvastekk_workflow_sdk.node_output_uploads", "get_default_node_output_uploader"),
    "BaseContract": ("canvastekk_workflow_sdk.node_io_data_contracts", "NodeIoDataContract"),
    # FastAPI-backed server entry points (were in _LAZY_SERVER_EXPORTS; importing
    # the module without the fastapi extra raises ImportError, as before).
    "create_node_app": ("canvastekk_workflow_sdk.workflow_node_app", "create_workflow_node_app"),
    "create_multi_node_app": ("canvastekk_workflow_sdk.multi_node_router", "create_multi_workflow_node_app"),
    "mount_node": ("canvastekk_workflow_sdk.bootstrap", "mount_workflow_node"),
    "create_authed_app": ("canvastekk_workflow_sdk.bootstrap", "create_authed_workflow_node_app"),
    "create_lambda_handler": ("canvastekk_workflow_sdk.bootstrap", "create_workflow_node_lambda_handler"),
}


def __getattr__(name: str):
    alias = _DEPRECATED_NAME_ALIASES.get(name)
    if alias is not None:
        import importlib
        import warnings

        module_path, new_name = alias
        warnings.warn(
            f"{name!r} is deprecated; use {new_name!r} from {module_path} "
            "(ADR 0001; removal in 1.0.0).",
            DeprecationWarning,
            stacklevel=2,
        )
        value = getattr(importlib.import_module(module_path), new_name)
        # Deliberately NOT cached into globals(): old names must warn on every
        # access (ADR 0001) — caching would silence the signal after first use.
        return value
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
