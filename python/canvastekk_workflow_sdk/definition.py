"""Deprecated alias module — renamed to canvastekk_workflow_sdk.workflow_node_manifest.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.workflow_node_manifest"

warnings.warn(
    "canvastekk_workflow_sdk.definition is deprecated; import"
    " canvastekk_workflow_sdk.workflow_node_manifest instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.workflow_node_manifest import *  # noqa: E402, F401, F403
from canvastekk_workflow_sdk.workflow_node_manifest import (  # noqa: E402
    WORKFLOW_NODE_MANIFEST_CONTRACT_ROUTES,
    WorkflowNodeColorPreset,
    WorkflowNodeContractCapabilities,
    WorkflowNodeDeprecationInfo,
    WorkflowNodeManifestContract,
    WorkflowNodeRetryConfig,
    export_workflow_node_manifest,
)

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
RetryConfig = WorkflowNodeRetryConfig  # deprecated name (ADR 0001, #271)
ColorPreset = WorkflowNodeColorPreset  # deprecated name (ADR 0001, #271)
DeprecationInfo = WorkflowNodeDeprecationInfo  # deprecated name (ADR 0001, #271)
NodeContract = WorkflowNodeManifestContract  # deprecated name (ADR 0001, #271)
ContractCapabilities = WorkflowNodeContractCapabilities  # deprecated name (ADR 0001, #271)
SDK_SERVED_CONTRACT_ROUTES = WORKFLOW_NODE_MANIFEST_CONTRACT_ROUTES  # deprecated name (ADR 0001, #271)
export_definition = export_workflow_node_manifest  # deprecated name (ADR 0001, #271)
