"""Deprecated alias module — renamed to canvastekk_workflow_sdk.node_io_data_contracts.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.node_io_data_contracts"

warnings.warn(
    "canvastekk_workflow_sdk.contracts is deprecated; import"
    " canvastekk_workflow_sdk.node_io_data_contracts instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.node_io_data_contracts import *  # noqa: E402, F401, F403
from canvastekk_workflow_sdk.node_io_data_contracts import (  # noqa: E402
    NODE_IO_DATA_CONTRACT_VERSION,
    NodeIoDataContract,
    WorkflowNodeCallOutcome,
    parse_workflow_node_call_outcome,
)

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
BaseContract = NodeIoDataContract  # deprecated name (ADR 0001, #271)
CONTRACT_VERSION = NODE_IO_DATA_CONTRACT_VERSION  # deprecated name (ADR 0001, #271)
NodeExecutionStatus = WorkflowNodeCallOutcome  # deprecated name (ADR 0001, #271)
parse_node_execution_status = parse_workflow_node_call_outcome  # deprecated name (ADR 0001, #271)
