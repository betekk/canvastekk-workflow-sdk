"""Deprecated-alias tests (ADR 0001, #271).

Old module paths and old public names keep working and warn as deprecated.
Grew with each rename phase (manifest+registry: Phase 2; runtime+execution:
Phase 3). The consumer-import freeze (test_consumer_import_freeze.py) stays
the consumer-surface oracle; this file asserts the deprecation contract.
"""

from __future__ import annotations

import importlib
import sys
import warnings

import pytest

# Old module path -> new module path (both must import; old must warn).
SHIMMED_MODULES = {
    # Phase 2 — manifest + registry
    "canvastekk_workflow_sdk.definition": "canvastekk_workflow_sdk.workflow_node_manifest",
    "canvastekk_workflow_sdk.diff": "canvastekk_workflow_sdk.workflow_node_manifest_diff",
    "canvastekk_workflow_sdk.registry": "canvastekk_workflow_sdk.workflow_node_registry",
    "canvastekk_workflow_sdk.convergence": "canvastekk_workflow_sdk.workflow_node_registry_convergence",
    "canvastekk_workflow_sdk.conformance": "canvastekk_workflow_sdk.workflow_node_conformance",
    # Phase 3 — node runtime + execution
    "canvastekk_workflow_sdk.base": "canvastekk_workflow_sdk.workflow_node_base",
    "canvastekk_workflow_sdk.app": "canvastekk_workflow_sdk.workflow_node_app",
    "canvastekk_workflow_sdk.router": "canvastekk_workflow_sdk.multi_node_router",
    "canvastekk_workflow_sdk.request": "canvastekk_workflow_sdk.node_execution_request",
    "canvastekk_workflow_sdk.response": "canvastekk_workflow_sdk.node_execution_response",
    "canvastekk_workflow_sdk.context": "canvastekk_workflow_sdk.node_execution_context",
    "canvastekk_workflow_sdk.protocol": "canvastekk_workflow_sdk.node_call_protocol",
    "canvastekk_workflow_sdk.uploads": "canvastekk_workflow_sdk.node_output_uploads",
    "canvastekk_workflow_sdk.multipart": "canvastekk_workflow_sdk.cds_multipart_upload",
    "canvastekk_workflow_sdk.contracts": "canvastekk_workflow_sdk.node_io_data_contracts",
}

# Old public name -> (old module path, new module path, new name). Module
# access resolves through the shim (or the renamed module itself for
# non-renamed modules like observability); root access via __getattr__.
ALIASED_NAMES: dict[str, tuple[str, str, str]] = {
    # Phase 2 — manifest + registry
    "export_definition": ("definition", "workflow_node_manifest", "export_workflow_node_manifest"),
    "NodeContract": ("definition", "workflow_node_manifest", "WorkflowNodeManifestContract"),
    "ContractCapabilities": ("definition", "workflow_node_manifest", "WorkflowNodeContractCapabilities"),
    "RetryConfig": ("definition", "workflow_node_manifest", "WorkflowNodeRetryConfig"),
    "ColorPreset": ("definition", "workflow_node_manifest", "WorkflowNodeColorPreset"),
    "DeprecationInfo": ("definition", "workflow_node_manifest", "WorkflowNodeDeprecationInfo"),
    "SDK_SERVED_CONTRACT_ROUTES": ("definition", "workflow_node_manifest", "WORKFLOW_NODE_MANIFEST_CONTRACT_ROUTES"),
    "diff_manifests": ("diff", "workflow_node_manifest_diff", "diff_workflow_node_manifests"),
    "ManifestDiff": ("diff", "workflow_node_manifest_diff", "WorkflowNodeManifestDiff"),
    "register_node": ("registry", "workflow_node_registry", "register_workflow_node"),
    "RegisterNodeResult": ("registry", "workflow_node_registry", "WorkflowNodeRegistrationResult"),
    "RegistrationError": ("registry", "workflow_node_registry", "WorkflowNodeRegistrationError"),
    "build_registry_payload": ("registry", "workflow_node_registry", "build_workflow_node_registry_payload"),
    "fetch_published_definition": ("registry", "workflow_node_registry", "fetch_published_workflow_node_manifest"),
    "diff_against_published": ("registry", "workflow_node_registry", "diff_against_published_workflow_node_manifest"),
    # Phase 3 — node runtime + execution
    "BaseNode": ("base", "workflow_node_base", "WorkflowNodeBase"),
    "create_node_app": ("app", "workflow_node_app", "create_workflow_node_app"),
    "create_multi_node_app": ("router", "multi_node_router", "create_multi_workflow_node_app"),
    "mount_node": ("bootstrap", "bootstrap", "mount_workflow_node"),
    "create_authed_app": ("bootstrap", "bootstrap", "create_authed_workflow_node_app"),
    "create_lambda_handler": ("bootstrap", "bootstrap", "create_workflow_node_lambda_handler"),
    "ExecutionContext": ("context", "node_execution_context", "NodeExecutionContext"),
    "HealthResponse": ("response", "node_execution_response", "WorkflowNodeHealthResponse"),
    "LivenessResponse": ("response", "node_execution_response", "WorkflowNodeLivenessResponse"),
    "ReadinessResponse": ("response", "node_execution_response", "WorkflowNodeReadinessResponse"),
    "MetricsSummaryResponse": ("response", "node_execution_response", "WorkflowNodeMetricsSummaryResponse"),
    "MultiNodeHealthResponse": ("response", "node_execution_response", "MultiWorkflowNodeHealthResponse"),
    "ExecutionMetric": ("observability", "observability", "NodeExecutionMetric"),
    "MetricsCollector": ("observability", "observability", "NodeExecutionMetricsCollector"),
    "NODE_PROTOCOL_HEADER": ("protocol", "node_call_protocol", "NODE_CALL_PROTOCOL_HEADER"),
    "NODE_PROTOCOL_VERSION": ("protocol", "node_call_protocol", "NODE_CALL_PROTOCOL_VERSION"),
    "PROTOCOL_2_OUTCOMES": ("protocol", "node_call_protocol", "NODE_CALL_PROTOCOL_2_OUTCOMES"),
    "outcome_for_protocol": ("protocol", "node_call_protocol", "node_call_outcome_for_protocol"),
    "read_outcome": ("protocol", "node_call_protocol", "read_node_call_outcome"),
    "requested_protocol": ("protocol", "node_call_protocol", "requested_node_call_protocol"),
    "OutputUploader": ("uploads", "node_output_uploads", "NodeOutputUploader"),
    "S3PresignedUploader": ("uploads", "node_output_uploads", "NodeOutputS3PresignedUploader"),
    "UploadSession": ("uploads", "node_output_uploads", "NodeOutputUploadSession"),
    "UploadTarget": ("uploads", "node_output_uploads", "NodeOutputUploadTarget"),
    "get_default_uploader": ("uploads", "node_output_uploads", "get_default_node_output_uploader"),
    "upload_via_session": ("multipart", "cds_multipart_upload", "upload_via_cds_multipart_session"),
    "BaseContract": ("contracts", "node_io_data_contracts", "NodeIoDataContract"),
    "CONTRACT_VERSION": ("contracts", "node_io_data_contracts", "NODE_IO_DATA_CONTRACT_VERSION"),
    "NodeExecutionStatus": ("contracts", "node_io_data_contracts", "WorkflowNodeCallOutcome"),
    "parse_node_execution_status": ("contracts", "node_io_data_contracts", "parse_workflow_node_call_outcome"),
}

# Names the old package root actually exported (old __all__) — these must
# also resolve (with warning) from the package root.
ROOT_EXPORTED_NAMES = {
    "export_definition", "NodeContract", "ContractCapabilities", "RetryConfig",
    "ColorPreset", "DeprecationInfo", "RegisterNodeResult", "RegistrationError",
    "register_node", "build_registry_payload",
    "BaseNode", "ExecutionContext", "ExecutionMetric", "HealthResponse",
    "NodeExecutionStatus", "parse_node_execution_status", "OutputUploader",
    "S3PresignedUploader", "UploadSession", "UploadTarget",
    "get_default_uploader", "BaseContract",
    "create_node_app", "create_multi_node_app", "mount_node",
    "create_authed_app", "create_lambda_handler",
}


def _new_module(new_path: str):
    return importlib.import_module(new_path)


@pytest.mark.parametrize(("old_path", "new_path"), SHIMMED_MODULES.items())
def test_old_module_path_imports_and_warns(old_path: str, new_path: str) -> None:
    sys.modules.pop(old_path, None)  # re-execute the shim body: the warning fires at import
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module = importlib.import_module(old_path)
    assert any(
        w.category is DeprecationWarning and new_path in str(w.message) for w in caught
    ), f"{old_path} import did not warn pointing at {new_path}"
    assert module._deprecated_alias_of == new_path


@pytest.mark.parametrize("old_name", sorted(ALIASED_NAMES))
def test_old_public_name_resolves_from_old_module(old_name: str) -> None:
    old_mod, new_path, new_name = ALIASED_NAMES[old_name]
    if old_mod in {"bootstrap", "observability"}:
        pytest.skip(f"{old_mod} was not renamed; {old_name} aliased in-module")
    module = importlib.import_module(f"canvastekk_workflow_sdk.{old_mod}")
    assert getattr(module, old_name) is getattr(_new_module(module._deprecated_alias_of), new_name)


@pytest.mark.parametrize("old_mod", ["bootstrap", "observability"])
def test_in_module_old_names_resolve_and_warn(old_mod: str) -> None:
    module = importlib.import_module(f"canvastekk_workflow_sdk.{old_mod}")
    for old_name, (mod, new_path, new_name) in ALIASED_NAMES.items():
        if mod != old_mod:
            continue
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = getattr(module, old_name)
        assert any(w.category is DeprecationWarning for w in caught), old_name
        assert value is getattr(_new_module(f"canvastekk_workflow_sdk.{new_path}"), new_name)


def test_old_public_names_resolve_from_package_root() -> None:
    import canvastekk_workflow_sdk as sdk

    for old_name in ROOT_EXPORTED_NAMES:
        old_mod, new_path, new_name = ALIASED_NAMES[old_name]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = getattr(sdk, old_name)
        assert any(w.category is DeprecationWarning for w in caught), old_name
        assert value is getattr(_new_module(f"canvastekk_workflow_sdk.{new_path}"), new_name), old_name
