"""
CanvasTEKK Workflow Node SDK

A convenience SDK for building HTTP-based workflow nodes.
Handles all boilerplate (endpoints, validation, error handling)
so node authors can focus on business logic.

Quick Start:
    from canvastekk_workflow_sdk import BaseNode, WorkflowNodeManifest, ExecutionContext

    class MyNode(BaseNode):
        definition = WorkflowNodeManifest(
            slug="my-node",
            version="1.0.0",
            name="My Node",
            description="Does something useful",
            input_schema={"type": "object", "properties": {"input": {"type": "string"}}},
            output_schema={"type": "object", "properties": {"output": {"type": "string"}}},
        )

        def execute(self, inputs: dict, context: ExecutionContext) -> dict:
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
from canvastekk_workflow_sdk.base import BaseNode
from canvastekk_workflow_sdk.context import ExecutionContext
from canvastekk_workflow_sdk.contracts import (
    BaseContract,
    BoundingBox3D,
    Instance,
    InstanceSet,
    Measurement,
    MeasurementSet,
    NodeExecutionStatus,
    Plane,
    PlaneSet,
    Point3D,
    parse_node_execution_status,
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
from canvastekk_workflow_sdk.observability import ExecutionMetric, MetricsCollector
from canvastekk_workflow_sdk.request import NodeExecutionRequest
from canvastekk_workflow_sdk.response import HealthResponse, NodeExecutionResponse
from canvastekk_workflow_sdk.testing import LocalFileServer, serve_files
from canvastekk_workflow_sdk.uploads import (
    OutputUploader,
    S3PresignedUploader,
    UploadSession,
    UploadTarget,
    get_default_uploader,
)
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
    "BaseContract",
    "BaseNode",
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
    "ExecutionContext",
    "ExecutionMetric",
    "HealthResponse",
    "HttpExecutor",
    "InProcessExecutor",
    "Instance",
    "InstanceSet",
    "LocalFileServer",
    "LoggingMiddleware",
    "Measurement",
    "MeasurementSet",
    "MetricsCollector",
    "NodeAuth",
    "NodeConfigurationError",
    "WorkflowNodeManifestContract",
    "NodeExecutionError",
    "NodeExecutionRequest",
    "NodeExecutionResponse",
    "NodeExecutor",
    "NodeIOError",
    "NodeMiddleware",
    "NodeExecutionStatus",
    "NodeOutputValidationError",
    "NodeResult",
    "NodeTimeoutError",
    "NodeValidationError",
    "error_envelope",
    "parse_node_execution_status",
    "OutputUploader",
    "Plane",
    "PlaneSet",
    "Point3D",
    "WorkflowNodeRegistrationResult",
    "WorkflowNodeRegistrationError",
    "WorkflowNodeRetryConfig",
    "S3PresignedUploader",
    "UploadSession",
    "UploadTarget",
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
    "create_authed_app",
    "create_lambda_handler",
    "create_multi_node_app",
    "create_node_app",
    "mount_node",
    "export_workflow_node_manifest",
    "get_default_uploader",
    "get_node_logger",
    "register_workflow_node",
    "serve_files",
    "validate",
]

from canvastekk_workflow_sdk._version import RELEASE_DATE as RELEASE_DATE  # noqa: E402, F401
from canvastekk_workflow_sdk._version import __version__ as __version__  # noqa: E402, F401

_LAZY_SERVER_EXPORTS = {
    "create_node_app": "canvastekk_workflow_sdk.app",
    "create_multi_node_app": "canvastekk_workflow_sdk.router",
    "NodeAuth": "canvastekk_workflow_sdk.auth",
    "SDKVersionMiddleware": "canvastekk_workflow_sdk._server_middleware",
    "create_authed_app": "canvastekk_workflow_sdk.bootstrap",
    "mount_node": "canvastekk_workflow_sdk.bootstrap",
    "create_lambda_handler": "canvastekk_workflow_sdk.bootstrap",
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
        globals()[name] = value
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
