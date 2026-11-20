"""Rename-map guard tests (ADR 0001, #271; alias removal executed in 1.0.0, #272).

Two invariants, pinned permanently:
(a) py/ts name parity — every renamed symbol from the ADR map exists under
    its new name on BOTH sides (snake_case ↔ camelCase twins);
(b) the epic #4301 law — no node-level module or public name contains
    "definition" (workflow-level names are the only allowed users of the
    word; the deprecated shims that carried old names were removed in
    1.0.0, #272).
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
PY = REPO / "python" / "canvastekk_workflow_sdk"
TS = REPO / "typescript" / "src"

pytestmark = pytest.mark.skipif(not TS.is_dir(), reason="typescript/src absent (e.g. wheel-only checkout)")

# (new python name, new typescript name) — every ADR-0001 renamed symbol.
RENAME_PARITY: set[tuple[str, str]] = {
    # manifest cluster
    ("export_workflow_node_manifest", "exportWorkflowNodeManifest"),
    ("WorkflowNodeManifestContract", "WorkflowNodeManifestContract"),
    ("WorkflowNodeContractCapabilities", "WorkflowNodeContractCapabilities"),
    ("WorkflowNodeRetryConfig", "WorkflowNodeRetryConfig"),
    ("WorkflowNodeColorPreset", "WorkflowNodeColorPreset"),
    ("WorkflowNodeDeprecationInfo", "WorkflowNodeDeprecationInfo"),
    ("diff_workflow_node_manifests", "diffWorkflowNodeManifests"),
    ("WorkflowNodeManifestDiff", "WorkflowNodeManifestDiff"),
    ("register_workflow_node", "registerWorkflowNode"),
    ("WorkflowNodeRegistrationResult", "WorkflowNodeRegistrationResult"),
    ("WorkflowNodeRegistrationError", "WorkflowNodeRegistrationError"),
    ("build_workflow_node_registry_payload", "buildWorkflowNodeRegistryPayload"),
    # runtime cluster
    ("WorkflowNodeBase", "WorkflowNodeBase"),
    ("WorkflowNodeHealthResponse", "WorkflowNodeHealthResponse"),
    # execution / call cluster
    ("NodeExecutionContext", "NodeExecutionContext"),
    ("NodeExecutionMetric", "NodeExecutionMetric"),
    ("NodeExecutionMetricsCollector", "NodeExecutionMetricsCollector"),
    ("WorkflowNodeCallOutcome", "WorkflowNodeCallOutcome"),
    ("parse_workflow_node_call_outcome", "parseWorkflowNodeCallOutcome"),
    ("NODE_CALL_PROTOCOL_HEADER", "NODE_CALL_PROTOCOL_HEADER"),
    ("NODE_CALL_PROTOCOL_VERSION", "NODE_CALL_PROTOCOL_VERSION"),
    ("NODE_CALL_PROTOCOL_2_OUTCOMES", "NODE_CALL_PROTOCOL_2_OUTCOMES"),
    ("node_call_outcome_for_protocol", "nodeCallOutcomeForProtocol"),
    ("read_node_call_outcome", "readNodeCallOutcome"),
    ("requested_node_call_protocol", "requestedNodeCallProtocol"),
    # outputs cluster
    ("NodeOutputUploader", "NodeOutputUploader"),
    ("NodeOutputS3PresignedUploader", "NodeOutputS3PresignedUploader"),
    ("NodeOutputUploadSession", "NodeOutputUploadSessionDescriptor"),
    ("NodeOutputUploadTarget", "NodeOutputUploadTarget"),
    ("get_default_node_output_uploader", "getDefaultNodeOutputUploader"),
    ("upload_via_cds_multipart_session", "uploadViaCdsMultipartSession"),
    # I/O data cluster
    ("NodeIoDataContract", "NodeIoDataContractData"),
    ("NODE_IO_DATA_CONTRACT_VERSION", "NODE_IO_DATA_CONTRACT_VERSION"),
    # workflow definition + run cluster
# (app-factory pairs are py-lazy / TS-express-subpath by architecture — not index-level twins)
    ("validate_workflow_definition", "validateWorkflowDefinition"),
    ("WorkflowDefinitionValidationResult", "WorkflowDefinitionValidationResult"),
    ("WorkflowDefinitionValidationError", "WorkflowDefinitionValidationError"),
    ("WorkflowRunError", "WorkflowRunError"),
    ("WorkflowRunNodeResult", "WorkflowRunNodeResult"),
    ("WorkflowRunErrorPolicy", "WorkflowRunErrorPolicy"),
    ("WorkflowRunNodeExecutor", "WorkflowRunNodeExecutor"),
    ("InProcessNodeExecutor", "InProcessNodeExecutor"),
    ("HttpNodeExecutor", "HttpNodeExecutor"),
}

# Workflow-level names allowed to contain "definition" (epic glossary: the
# workflow definition IS a definition; node-level things are manifests).
WORKFLOW_DEFINITION_ALLOWLIST = {
    "WorkflowDefinitionNode",
    "WorkflowDefinitionSpec",
    "WorkflowEdgeDefinition",
    "WorkflowDefinitionValidationResult",
    "WorkflowDefinitionValidationError",
    "validate_workflow_definition",
}


def _py_new_names() -> set[str]:
    import canvastekk_workflow_sdk as sdk

    return set(sdk.__all__)


def _ts_index_names() -> set[str]:
    src = (TS / "index.ts").read_text()
    names: set[str] = set()
    for m in re.finditer(r"export\s+(?:type\s+)?(?:\{([^}]*)\}|const\s+(\w+)|class\s+(\w+)|function\s+(\w+))", src):
        if m.group(1):
            for part in m.group(1).split(","):
                part = part.strip()
                if part.startswith("type "):
                    part = part[5:].strip()
                if part and " as " not in part:
                    names.add(part.split(":")[0].strip())
        for g in m.groups()[1:]:
            if g:
                names.add(g)
    return names


@pytest.mark.parametrize(("py_name", "ts_name"), sorted(RENAME_PARITY))
def test_renamed_symbols_exist_on_both_sides(py_name: str, ts_name: str) -> None:
    import canvastekk_workflow_sdk as sdk

    # python side: resolvable from the package root or its cluster module
    py_ok = py_name in sdk.__all__ or hasattr(sdk, py_name)
    for module_name in (
        "workflow_node_manifest",
        "workflow_node_manifest_diff",
        "workflow_node_registry",
        "workflow_node_base",
        "workflow_node_app",
        "multi_node_router",
        "node_execution_context",
        "node_call_protocol",
        "node_output_uploads",
        "cds_multipart_upload",
        "node_io_data_contracts",
        "observability",
        "workflow.workflow_definition",
        "workflow.node_executor",
        "workflow.validation",
        "workflow.runner",
    ):
        if py_ok:
            break
        module = importlib.import_module(f"canvastekk_workflow_sdk.{module_name}")
        py_ok = hasattr(module, py_name)
    assert py_ok, f"python side lost renamed name: {py_name}"
    assert ts_name in _ts_index_names(), f"typescript index lost renamed name: {ts_name}"


def test_no_node_level_definition_in_py_module_names() -> None:
    for path in PY.glob("*.py"):
        if path.name == "__init__.py":
            continue
        assert "definition" not in path.stem, f"node-level module name contains 'definition': {path.name}"


def test_no_node_level_definition_in_public_names() -> None:
    offenders = [n for n in _py_new_names() if "definition" in n.lower() and n not in WORKFLOW_DEFINITION_ALLOWLIST]
    assert not offenders, f"node-level public names contain 'definition': {offenders}"


def test_workflow_definition_allowlist_names_still_exported() -> None:
    names = _py_new_names()
    for allowed in WORKFLOW_DEFINITION_ALLOWLIST:
        assert allowed in names, f"workflow-level name dropped from __all__: {allowed}"


def test_no_node_level_definition_in_ts_modules_or_exports() -> None:
    for path in TS.glob("*.ts"):
        assert "definition" not in path.stem, f"node-level TS module contains 'definition': {path.name}"
    offenders = [
        n
        for n in _ts_index_names()
        if "definition" in n.lower()
        and n
        not in {
            "WorkflowDefinitionNode",
            "WorkflowDefinitionSpec",
            "WorkflowEdgeDefinition",
            "WorkflowDefinitionValidationResult",
            "WorkflowDefinitionValidationError",
            "validateWorkflowDefinition",
        }
    ]
    assert not offenders, f"node-level TS exports contain 'definition': {offenders}"
