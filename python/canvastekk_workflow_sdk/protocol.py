"""Deprecated alias module — renamed to canvastekk_workflow_sdk.node_call_protocol.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.node_call_protocol"

warnings.warn(
    "canvastekk_workflow_sdk.protocol is deprecated; import"
    " canvastekk_workflow_sdk.node_call_protocol instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.node_call_protocol import *  # noqa: E402, F401, F403
from canvastekk_workflow_sdk.node_call_protocol import (  # noqa: E402
    NODE_CALL_PROTOCOL_2_OUTCOMES,
    NODE_CALL_PROTOCOL_HEADER,
    NODE_CALL_PROTOCOL_VERSION,
    node_call_outcome_for_protocol,
    read_node_call_outcome,
    requested_node_call_protocol,
)

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
NODE_PROTOCOL_HEADER = NODE_CALL_PROTOCOL_HEADER  # deprecated name (ADR 0001, #271)
NODE_PROTOCOL_VERSION = NODE_CALL_PROTOCOL_VERSION  # deprecated name (ADR 0001, #271)
PROTOCOL_2_OUTCOMES = NODE_CALL_PROTOCOL_2_OUTCOMES  # deprecated name (ADR 0001, #271)
outcome_for_protocol = node_call_outcome_for_protocol  # deprecated name (ADR 0001, #271)
read_outcome = read_node_call_outcome  # deprecated name (ADR 0001, #271)
requested_protocol = requested_node_call_protocol  # deprecated name (ADR 0001, #271)
