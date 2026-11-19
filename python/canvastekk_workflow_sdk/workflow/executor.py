"""Deprecated alias module — renamed to canvastekk_workflow_sdk.workflow.node_executor.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.workflow.node_executor"

warnings.warn(
    "canvastekk_workflow_sdk.workflow.executor is deprecated; import"
    " canvastekk_workflow_sdk.workflow.node_executor instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.workflow.node_executor import *  # noqa: E402, F401, F403
from canvastekk_workflow_sdk.workflow.node_executor import (  # noqa: E402
    HttpNodeExecutor,
    InProcessNodeExecutor,
    WorkflowRunNodeExecutor,
)

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
NodeExecutor = WorkflowRunNodeExecutor  # deprecated name (ADR 0001, #271)
InProcessExecutor = InProcessNodeExecutor  # deprecated name (ADR 0001, #271)
HttpExecutor = HttpNodeExecutor  # deprecated name (ADR 0001, #271)
