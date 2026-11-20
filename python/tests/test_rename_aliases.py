"""Removed-alias guard tests (ADR 0001, #271 removal; 1.0.0, #272).

The deprecated module paths, public-name aliases, and the legacy `definition`
class attribute were removed in 1.0.0. These guards FAIL if any of them
returns: every old module path must raise ModuleNotFoundError, every old
public name must raise AttributeError, and `WorkflowNodeBase` must serve the
manifest only through `manifest`. The consumer-import freeze
(test_consumer_import_freeze.py) stays the consumer-surface oracle.
"""

from __future__ import annotations

import importlib

import pytest

# Old module paths — every one must now fail to import (1.0.0, #272).
REMOVED_MODULES = [
    # Phase 2 — manifest + registry
    "canvastekk_workflow_sdk.definition",
    "canvastekk_workflow_sdk.diff",
    "canvastekk_workflow_sdk.registry",
    "canvastekk_workflow_sdk.convergence",
    "canvastekk_workflow_sdk.conformance",
    # Phase 3 — node runtime + execution
    "canvastekk_workflow_sdk.base",
    "canvastekk_workflow_sdk.app",
    "canvastekk_workflow_sdk.router",
    "canvastekk_workflow_sdk.request",
    "canvastekk_workflow_sdk.response",
    "canvastekk_workflow_sdk.context",
    "canvastekk_workflow_sdk.protocol",
    "canvastekk_workflow_sdk.uploads",
    "canvastekk_workflow_sdk.multipart",
    "canvastekk_workflow_sdk.contracts",
    # Phase 4 — workflow manifest + run
    "canvastekk_workflow_sdk.workflow.models",
    "canvastekk_workflow_sdk.workflow.executor",
]

# Old public names that used to resolve from the package root via the lazy
# __getattr__ alias map — every one must now raise AttributeError.
REMOVED_ROOT_NAMES = {
    "export_definition", "NodeContract", "ContractCapabilities", "RetryConfig",
    "ColorPreset", "DeprecationInfo", "SDK_SERVED_CONTRACT_ROUTES",
    "RegisterNodeResult", "RegistrationError", "register_node",
    "build_registry_payload",
    "BaseNode", "ExecutionContext", "ExecutionMetric", "HealthResponse",
    "NodeExecutionStatus", "parse_node_execution_status", "OutputUploader",
    "S3PresignedUploader", "UploadSession", "UploadTarget",
    "get_default_uploader", "BaseContract",
    "create_node_app", "create_multi_node_app", "mount_node",
    "create_authed_app", "create_lambda_handler",
    "validate", "ValidationResult", "NodeResult", "NodeExecutor",
    "InProcessExecutor", "HttpExecutor", "WorkflowExecutionError",
    "WorkflowValidationError",
}

# Old names that lived in non-renamed modules behind a PEP 562 __getattr__ —
# module access must now raise AttributeError too.
REMOVED_IN_MODULE_NAMES = {
    "exceptions": ("WorkflowExecutionError", "WorkflowValidationError"),
    "bootstrap": ("mount_node", "create_authed_app", "create_lambda_handler"),
    "observability": ("ExecutionMetric", "MetricsCollector"),
    "workflow.validation": ("validate", "ValidationResult"),
    "workflow.runner": ("NodeResult", "ErrorPolicy"),
}


@pytest.mark.parametrize("old_path", REMOVED_MODULES)
def test_old_module_path_is_gone(old_path: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(old_path)


def test_old_root_names_are_gone() -> None:
    import canvastekk_workflow_sdk as sdk

    for old_name in sorted(REMOVED_ROOT_NAMES):
        with pytest.raises(AttributeError, match=old_name):
            getattr(sdk, old_name)


@pytest.mark.parametrize(("old_mod", "names"), sorted(REMOVED_IN_MODULE_NAMES.items()))
def test_in_module_old_names_are_gone(old_mod: str, names: tuple[str, ...]) -> None:
    module = importlib.import_module(f"canvastekk_workflow_sdk.{old_mod}")
    for old_name in names:
        with pytest.raises(AttributeError, match=old_name):
            getattr(module, old_name)


def test_no_deprecated_alias_maps_remain() -> None:
    """The alias tables themselves must not come back."""
    import inspect

    import canvastekk_workflow_sdk as sdk
    import canvastekk_workflow_sdk.bootstrap as bootstrap
    import canvastekk_workflow_sdk.exceptions as exceptions

    for obj in (sdk, bootstrap, exceptions):
        source = inspect.getsource(obj)
        assert "_DEPRECATED_NAME_ALIASES" not in source
        assert "_DEPRECATED_ALIASES" not in source


def test_manifest_attribute_only() -> None:
    """1.0.0 (#272): node classes carry the manifest as `manifest` only."""
    from canvastekk_workflow_sdk import WorkflowNodeBase, WorkflowNodeManifest

    class CanonicalNode(WorkflowNodeBase):
        manifest = WorkflowNodeManifest(
            slug="canonical-only",
            version="1.0.0",
            name="Canonical Only",
            description="manifest attribute only",
            input_schema={"type": "object"},
            output_schema={"type": "object"},
        )

        def execute(self, inputs, context):  # noqa: ANN001
            return {}

    node = CanonicalNode()
    assert node.manifest.slug == "canonical-only"
    with pytest.raises(AttributeError):
        _ = node.definition

    # A legacy class declaring `definition = ...` no longer satisfies the
    # contract: `__init_subclass__` must reject it (no silent migration).
    with pytest.raises(TypeError, match="manifest"):

        class LegacyAttrNode(WorkflowNodeBase):
            definition = WorkflowNodeManifest(  # noqa: N815 — deliberate legacy name
                slug="legacy-attr",
                version="1.0.0",
                name="Legacy Attr",
                description="legacy attribute must be rejected in 1.0.0",
                input_schema={"type": "object"},
                output_schema={"type": "object"},
            )

            def execute(self, inputs, context):  # noqa: ANN001
                return {}


def test_node_validation_error_split_preserves_catching() -> None:
    """ADR 0001: the split subclasses stay catchable via the old base name.

    `NodeValidationError` is kept by design in 1.0.0 (#272): it is the
    runtime base of both specific errors, not a deprecated alias.
    """
    from canvastekk_workflow_sdk.exceptions import (
        NodeInputValidationError,
        NodeValidationError,
        WorkflowNodeManifestValidationError,
    )

    for specific in (WorkflowNodeManifestValidationError, NodeInputValidationError):
        assert issubclass(specific, NodeValidationError)
        try:
            raise specific("x")
        except NodeValidationError:
            pass  # base-class except clauses keep catching both subclasses


def test_split_wire_names_unchanged() -> None:
    """ADR 0001: error_type on the wire keeps the historical names."""
    from canvastekk_workflow_sdk.exceptions import (
        NodeInputValidationError,
        WorkflowDefinitionValidationError,
        WorkflowNodeManifestValidationError,
        WorkflowRunError,
    )
    from canvastekk_workflow_sdk.workflow_node_base import _wire_error_type

    assert _wire_error_type(WorkflowNodeManifestValidationError("x")) == "NodeValidationError"
    assert _wire_error_type(NodeInputValidationError("x")) == "NodeValidationError"
    assert _wire_error_type(WorkflowRunError("x")) == "WorkflowExecutionError"
    assert _wire_error_type(WorkflowDefinitionValidationError("x")) == "WorkflowValidationError"
