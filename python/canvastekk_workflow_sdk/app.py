"""Deprecated alias module — renamed to canvastekk_workflow_sdk.workflow_node_app.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.workflow_node_app"

warnings.warn(
    "canvastekk_workflow_sdk.app is deprecated; import"
    " canvastekk_workflow_sdk.workflow_node_app instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.workflow_node_app import *  # noqa: E402, F401, F403
from canvastekk_workflow_sdk.workflow_node_app import (  # noqa: E402
    create_workflow_node_app,
)

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
create_node_app = create_workflow_node_app  # deprecated name (ADR 0001, #271)
