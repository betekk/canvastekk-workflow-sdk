"""Deprecated alias module — renamed to canvastekk_workflow_sdk.workflow_node_registry_convergence.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.workflow_node_registry_convergence"

warnings.warn(
    "canvastekk_workflow_sdk.convergence is deprecated; import"
    " canvastekk_workflow_sdk.workflow_node_registry_convergence instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.workflow_node_registry_convergence import *  # noqa: E402, F401, F403
