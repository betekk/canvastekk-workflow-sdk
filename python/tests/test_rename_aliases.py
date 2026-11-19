"""Deprecated-alias tests (ADR 0001, #271).

Old module paths and old public names keep working and warn as deprecated.
Phase-scoped: grows with each rename phase (manifest+registry here; runtime,
workflow clusters follow). The consumer-import freeze
(test_consumer_import_freeze.py) stays the consumer-surface oracle; this file
asserts the deprecation contract on top.
"""

from __future__ import annotations

import importlib
import warnings

import pytest

# Old module path -> new module path (both must import; old must warn).
SHIMMED_MODULES = {
    "canvastekk_workflow_sdk.definition": "canvastekk_workflow_sdk.workflow_node_manifest",
    "canvastekk_workflow_sdk.diff": "canvastekk_workflow_sdk.workflow_node_manifest_diff",
    "canvastekk_workflow_sdk.registry": "canvastekk_workflow_sdk.workflow_node_registry",
    "canvastekk_workflow_sdk.convergence": "canvastekk_workflow_sdk.workflow_node_registry_convergence",
    "canvastekk_workflow_sdk.conformance": "canvastekk_workflow_sdk.workflow_node_conformance",
}

# Old public name -> (old module path, new name). Package-root access goes
# through the lazy __getattr__; module access through the shim assignments.
ALIASED_NAMES = {
    "export_definition": ("definition", "export_workflow_node_manifest"),
    "NodeContract": ("definition", "WorkflowNodeManifestContract"),
    "ContractCapabilities": ("definition", "WorkflowNodeContractCapabilities"),
    "RetryConfig": ("definition", "WorkflowNodeRetryConfig"),
    "ColorPreset": ("definition", "WorkflowNodeColorPreset"),
    "DeprecationInfo": ("definition", "WorkflowNodeDeprecationInfo"),
    "SDK_SERVED_CONTRACT_ROUTES": ("definition", "WORKFLOW_NODE_MANIFEST_CONTRACT_ROUTES"),
    "diff_manifests": ("diff", "diff_workflow_node_manifests"),
    "ManifestDiff": ("diff", "WorkflowNodeManifestDiff"),
    "register_node": ("registry", "register_workflow_node"),
    "RegisterNodeResult": ("registry", "WorkflowNodeRegistrationResult"),
    "RegistrationError": ("registry", "WorkflowNodeRegistrationError"),
    "build_registry_payload": ("registry", "build_workflow_node_registry_payload"),
    "fetch_published_definition": ("registry", "fetch_published_workflow_node_manifest"),
    "diff_against_published": ("registry", "diff_against_published_workflow_node_manifest"),
}


@pytest.mark.parametrize(("old_path", "new_path"), SHIMMED_MODULES.items())
def test_old_module_path_imports_and_warns(old_path: str, new_path: str) -> None:
    import sys

    sys.modules.pop(old_path, None)  # re-execute the shim body: the warning fires at import
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        module = importlib.import_module(old_path)
    assert any(
        w.category is DeprecationWarning and new_path in str(w.message) for w in caught
    ), f"{old_path} import did not warn pointing at {new_path}"
    assert module._deprecated_alias_of == new_path


@pytest.mark.parametrize(("old_name", "old_mod_new_name"), sorted(ALIASED_NAMES.items()))
def test_old_public_name_resolves_from_old_module(old_name: str, old_mod_new_name: tuple[str, str]) -> None:
    old_mod, new_name = old_mod_new_name
    module = importlib.import_module(f"canvastekk_workflow_sdk.{old_mod}")
    new_module = importlib.import_module(module._deprecated_alias_of)
    assert getattr(module, old_name) is getattr(new_module, new_name)


# Names the old package root actually exported (old __all__) — these must
# resolve (with warning) from the package root too. The rest were
# module-level publics only and keep resolving from their old modules.
ROOT_EXPORTED_NAMES = {
    "export_definition",
    "NodeContract",
    "ContractCapabilities",
    "RetryConfig",
    "ColorPreset",
    "DeprecationInfo",
    "RegisterNodeResult",
    "RegistrationError",
    "register_node",
    "build_registry_payload",
}


def test_old_public_names_resolve_from_package_root() -> None:
    import canvastekk_workflow_sdk as sdk

    for old_name in ROOT_EXPORTED_NAMES:
        old_mod, new_name = ALIASED_NAMES[old_name]
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            value = getattr(sdk, old_name)
        assert any(w.category is DeprecationWarning for w in caught), old_name
        new_module = importlib.import_module(SHIMMED_MODULES[f"canvastekk_workflow_sdk.{old_mod}"])
        assert value is getattr(new_module, new_name), old_name
