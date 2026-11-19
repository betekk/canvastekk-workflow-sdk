"""Deprecated alias module — renamed to canvastekk_workflow_sdk.workflow_node_registry.

ADR 0001 (explicit node naming, #271): every old module path keeps working
and warns as deprecated; removed in 1.0.0 (#272).
"""

from __future__ import annotations

import warnings

_deprecated_alias_of = "canvastekk_workflow_sdk.workflow_node_registry"

warnings.warn(
    "canvastekk_workflow_sdk.registry is deprecated; import"
    " canvastekk_workflow_sdk.workflow_node_registry instead (ADR 0001; removal in 1.0.0).",
    DeprecationWarning,
    stacklevel=2,
)

from canvastekk_workflow_sdk.workflow_node_registry import *  # noqa: E402, F401, F403
from canvastekk_workflow_sdk.workflow_node_registry import (  # noqa: E402
    WorkflowNodeRegistrationError,
    WorkflowNodeRegistrationResult,
    build_workflow_node_registry_payload,
    diff_against_published_workflow_node_manifest,
    fetch_published_workflow_node_manifest,
    register_workflow_node,
)

# Deprecated public names (ADR 0001, #271) — old name -> renamed symbol.
register_node = register_workflow_node  # deprecated name (ADR 0001, #271)
RegisterNodeResult = WorkflowNodeRegistrationResult  # deprecated name (ADR 0001, #271)
RegistrationError = WorkflowNodeRegistrationError  # deprecated name (ADR 0001, #271)
build_registry_payload = build_workflow_node_registry_payload  # deprecated name (ADR 0001, #271)
fetch_published_definition = fetch_published_workflow_node_manifest  # deprecated name (ADR 0001, #271)
diff_against_published = diff_against_published_workflow_node_manifest  # deprecated name (ADR 0001, #271)
