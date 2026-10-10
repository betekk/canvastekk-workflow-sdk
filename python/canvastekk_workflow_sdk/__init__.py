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

from canvastekk_workflow_sdk.base import BaseNode
from canvastekk_workflow_sdk.context import ExecutionContext
from canvastekk_workflow_sdk.contracts import (
    BaseContract,
    BoundingBox3D,
    Instance,
    InstanceSet,
    Measurement,
    MeasurementSet,
    Plane,
    PlaneSet,
    Point3D,
)
from canvastekk_workflow_sdk.definition import (
    ColorPreset,
    DeprecationInfo,
    RetryConfig,
    WorkflowNodeManifest,
    WorkflowNodeRole,
    WorkflowNodeStyles,
    export_definition,
)
from canvastekk_workflow_sdk.exceptions import (
    NodeConfigurationError,
    NodeExecutionError,
    NodeIOError,
    NodeOutputValidationError,
    NodeTimeoutError,
    NodeValidationError,
    WorkflowExecutionError,
    WorkflowValidationError,
)
from canvastekk_workflow_sdk.logging import StructuredJsonFormatter, configure_logging, get_node_logger
from canvastekk_workflow_sdk.middleware import LoggingMiddleware, NodeMiddleware, SDKVersionMiddleware, TimingMiddleware
from canvastekk_workflow_sdk.observability import ExecutionMetric, MetricsCollector
from canvastekk_workflow_sdk.registry import (
    RegisterNodeResult,
    RegistrationError,
    build_registry_payload,
    register_node,
)
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

__all__ = [
    "BaseContract",
    "BaseNode",
    "BoundingBox3D",
    "ColorPreset",
    "DeprecationInfo",
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
    "NodeExecutionError",
    "NodeExecutionRequest",
    "NodeExecutionResponse",
    "NodeExecutor",
    "NodeIOError",
    "NodeMiddleware",
    "NodeOutputValidationError",
    "NodeResult",
    "NodeTimeoutError",
    "NodeValidationError",
    "OutputUploader",
    "Plane",
    "PlaneSet",
    "Point3D",
    "RegisterNodeResult",
    "RegistrationError",
    "RetryConfig",
    "S3PresignedUploader",
    "UploadSession",
    "UploadTarget",
    "SDKVersionMiddleware",
    "StructuredJsonFormatter",
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
    "build_registry_payload",
    "configure_logging",
    "create_multi_node_app",
    "create_node_app",
    "export_definition",
    "get_default_uploader",
    "get_node_logger",
    "register_node",
    "serve_files",
    "validate",
]

# DA-3359: single source of truth lives in _version.py (leaf module — no
# import cycle); re-exported for backwards compatibility.
from canvastekk_workflow_sdk._version import RELEASE_DATE as RELEASE_DATE  # noqa: E402, F401
from canvastekk_workflow_sdk._version import __version__ as __version__  # noqa: E402, F401

# Server symbols live behind lazily-imported fastapi-backed modules; the
# core package imports (and installs) without fastapi. Access raises a
# guided ImportError when the `[fastapi]` extra is missing.
_LAZY_SERVER_EXPORTS = {
    "create_node_app": "canvastekk_workflow_sdk.app",
    "create_multi_node_app": "canvastekk_workflow_sdk.router",
    "NodeAuth": "canvastekk_workflow_sdk.auth",
}


def __getattr__(name: str):  # PEP 562
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
        globals()[name] = value  # cache: subsequent lookups skip this hook
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
