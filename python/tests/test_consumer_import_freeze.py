"""Consumer-import freeze — the Wave-2 zero-change contract (#225).

Every consumer import statement enumerated by the 2026-11-01 audit
(CWN, CLS, canvastekk-workflow-engine, ifc-equivalent python names) must
keep resolving from the SDK surface. The auth split must be invisible to
these rows; removing or renaming any frozen symbol fails here before it
can reach a consumer.
"""

from __future__ import annotations

import importlib

# (module, frozen attribute names)
FREEZE: list[tuple[str, tuple[str, ...]]] = [
    # CWN — 43+ files (apps/python/**)
    (
        "canvastekk_workflow_sdk",
        (
            "BaseNode",
            "ExecutionContext",
            "WorkflowNodeManifest",
            "NodeExecutionRequest",
            "NodeAuth",  # lazy fastapi-gated; CI installs -E fastapi
            "create_authed_app",
        ),
    ),
    ("canvastekk_workflow_sdk.exceptions", ("NodeExecutionError", "NodeValidationError", "NodeIOError")),
    (
        "canvastekk_workflow_sdk.definition",
        ("WorkflowNodeStyles", "RetryConfig", "WorkflowNodeManifest", "SDK_SERVED_CONTRACT_ROUTES"),
    ),
    ("canvastekk_workflow_sdk.testing", ("LocalFileServer",)),
    ("canvastekk_workflow_sdk.contracts", ("InstanceSet", "Instance")),
    # CLS — both app surfaces (opencode_app/node/app.py, fastapi_gateway_app/node/app.py)
    ("canvastekk_workflow_sdk.app", ("create_node_app",)),
    ("canvastekk_workflow_sdk", ("mount_node", "create_lambda_handler")),
    # canvastekk-workflow-engine — framework-free consumer (unchanged by Wave 1/2)
    ("canvastekk_workflow_sdk.registry", ("build_registry_payload",)),
    (
        "canvastekk_workflow_sdk.node_token",
        ("NODE_TOKEN_PREFIX", "NodeTokenClaims", "mint_node_token", "verify_node_token", "is_node_token"),
    ),
    ("canvastekk_workflow_sdk._version", ("__version__",)),  # engine imports the private module — never move
    # SDK canonical auth surface (new, additive — frozen from day one)
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
    "canvastekk_workflow_sdk.workflow.models",
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
