"""Consumer-import freeze — the post-1.0.0 consumer contract (#225 → #272).

Every consumer import the migrated repos actually perform (verified by the
#272 AC-1 cross-repo search, recorded on the ticket) must keep resolving
from the SDK surface. The 1.0.0 alias removal (#272) retargeted the
original 2026-11-01 audit rows to the explicit names — a deliberate,
separately reviewed staleness change (LEARNINGS:
consumer-import-freeze-is-rename-oracle): consumers migrated on their epic
tickets (CWN #697, CLS #809, ML #196, audio #308, IFC #553, PC #407,
RSV #256, CWE #1329), all merged before this retarget. Removing or
renaming any frozen symbol fails here before it can reach a consumer.
"""

from __future__ import annotations

import importlib

# (module, frozen attribute names)
FREEZE: list[tuple[str, tuple[str, ...]]] = [
    # CWN / ML / audio / IFC / PC / RSV — node hosts (apps/python/**)
    (
        "canvastekk_workflow_sdk",
        (
            "WorkflowNodeBase",
            "NodeExecutionContext",
            "WorkflowNodeManifest",
            "NodeExecutionRequest",
            "NodeAuth",  # lazy fastapi-gated; CI installs -E fastapi
        ),
    ),
    ("canvastekk_workflow_sdk.exceptions", ("NodeExecutionError", "NodeValidationError", "NodeIOError")),
    (
        "canvastekk_workflow_sdk.workflow_node_manifest",
        ("WorkflowNodeStyles", "WorkflowNodeRetryConfig", "WorkflowNodeManifest", "WORKFLOW_NODE_MANIFEST_CONTRACT_ROUTES"),
    ),
    ("canvastekk_workflow_sdk.testing", ("LocalFileServer",)),
    ("canvastekk_workflow_sdk.node_io_data_contracts", ("InstanceSet", "Instance")),
    # CLS — both app surfaces (opencode_app/node/app.py, fastapi_gateway_app/node/app.py)
    ("canvastekk_workflow_sdk.workflow_node_app", ("create_workflow_node_app",)),
    ("canvastekk_workflow_sdk", ("mount_workflow_node", "create_workflow_node_lambda_handler")),
    # canvastekk-workflow-engine — framework-free consumer (migrated on #1329)
    ("canvastekk_workflow_sdk.workflow_node_registry", ("build_workflow_node_registry_payload",)),
    (
        "canvastekk_workflow_sdk.node_token",
        ("NODE_TOKEN_PREFIX", "NodeTokenClaims", "mint_node_token", "verify_node_token", "is_node_token"),
    ),
    ("canvastekk_workflow_sdk._version", ("__version__",)),  # engine imports the private module — never move
    # SDK canonical auth surface (additive — frozen from day one)
    (
        "canvastekk_workflow_sdk.auth.core",
        (
            "TekkNodeAuth",
            "TekkApiKeyAuth",
            "TekkCentralAuth",
            "TekkJwtAuth",
            "TekkKeycloakAuth",
            "TekkAuthError",
            "TekkAuthNotConfigured",
            "TekkAuthMissingCredential",
            "TekkAuthInvalidCredential",
            "TekkAuthTokenExpired",
            "TekkAuthUnavailable",
        ),
    ),
]

# Raw submodule imports consumers perform (import machinery level)
FREEZE_MODULES = (
    "canvastekk_workflow_sdk.workflow.workflow_definition",  # CWE (#1329)
    "canvastekk_workflow_sdk.node_execution_context",  # CLS (#809)
    "canvastekk_workflow_sdk.auth.core",
    "canvastekk_workflow_sdk.auth.fastapi",  # adapter importable when fastapi present (CI: -E fastapi)
)


def test_frozen_consumer_imports_resolve() -> None:
    for module_name, names in FREEZE:
        module = importlib.import_module(module_name)
        missing = [n for n in names if not hasattr(module, n)]
        assert not missing, f"{module_name} lost frozen names: {missing}"


def test_frozen_submodules_import() -> None:
    for module_name in FREEZE_MODULES:
        importlib.import_module(module_name)
