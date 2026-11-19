"""Deprecated alias module — renamed to canvastekk_workflow_sdk.node_execution_request.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.node_execution_request"

warnings.warn(
    "canvastekk_workflow_sdk.request is deprecated; import"
    " canvastekk_workflow_sdk.node_execution_request instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.node_execution_request import *  # noqa: E402, F401, F403
