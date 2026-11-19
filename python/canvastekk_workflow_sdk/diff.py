"""Deprecated alias module — renamed to canvastekk_workflow_sdk.workflow_node_manifest_diff.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.workflow_node_manifest_diff"

warnings.warn(
    "canvastekk_workflow_sdk.diff is deprecated; import"
    " canvastekk_workflow_sdk.workflow_node_manifest_diff instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.workflow_node_manifest_diff import *  # noqa: E402, F401, F403
from canvastekk_workflow_sdk.workflow_node_manifest_diff import (  # noqa: E402
    WorkflowNodeManifestDiff,
    diff_workflow_node_manifests,
)

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
diff_manifests = diff_workflow_node_manifests  # deprecated name (ADR 0001, #271)
ManifestDiff = WorkflowNodeManifestDiff  # deprecated name (ADR 0001, #271)
