"""Deprecated alias module — renamed to canvastekk_workflow_sdk.workflow.workflow_definition.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.workflow.workflow_definition"

warnings.warn(
    "canvastekk_workflow_sdk.workflow.models is deprecated; import"
    " canvastekk_workflow_sdk.workflow.workflow_definition instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.workflow.workflow_definition import *  # noqa: E402, F401, F403

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
