"""Deprecated alias module — renamed to canvastekk_workflow_sdk.node_execution_response.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.node_execution_response"

warnings.warn(
    "canvastekk_workflow_sdk.response is deprecated; import"
    " canvastekk_workflow_sdk.node_execution_response instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.node_execution_response import *  # noqa: E402, F401, F403
from canvastekk_workflow_sdk.node_execution_response import (  # noqa: E402
    MultiWorkflowNodeHealthResponse,
    WorkflowNodeHealthResponse,
    WorkflowNodeLivenessResponse,
    WorkflowNodeMetricsSummaryResponse,
    WorkflowNodeReadinessResponse,
)

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
HealthResponse = WorkflowNodeHealthResponse  # deprecated name (ADR 0001, #271)
LivenessResponse = WorkflowNodeLivenessResponse  # deprecated name (ADR 0001, #271)
ReadinessResponse = WorkflowNodeReadinessResponse  # deprecated name (ADR 0001, #271)
MetricsSummaryResponse = WorkflowNodeMetricsSummaryResponse  # deprecated name (ADR 0001, #271)
MultiNodeHealthResponse = MultiWorkflowNodeHealthResponse  # deprecated name (ADR 0001, #271)
