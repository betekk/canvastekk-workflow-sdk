"""Lazy server-symbol exports: core imports (and works) without fastapi.

The `[fastapi]` extra gates `create_node_app`, `create_multi_node_app`, and
`NodeAuth`. These tests run the package in a subprocess with fastapi import
blocked (`sys.modules["fastapi"] = None`), proving no module-level fastapi
dependency remains in the core import path (#104).
"""

from __future__ import annotations

import subprocess
import sys
import textwrap

_PROBE = textwrap.dedent(
    """
    import sys

    sys.modules["fastapi"] = None  # block: any `import fastapi` raises

    import canvastekk_workflow_sdk

    assert "create_node_app" in canvastekk_workflow_sdk.__all__
    assert "create_multi_node_app" in canvastekk_workflow_sdk.__all__
    assert "NodeAuth" in canvastekk_workflow_sdk.__all__

    try:
        canvastekk_workflow_sdk.create_node_app
    except ImportError as exc:
        assert "[fastapi]" in str(exc), f"unguided error: {exc}"
    else:
        raise SystemExit("expected guided ImportError for create_node_app")

    try:
        canvastekk_workflow_sdk.NodeAuth
    except ImportError as exc:
        assert "[fastapi]" in str(exc), f"unguided error: {exc}"
    else:
        raise SystemExit("expected guided ImportError for NodeAuth")

    print("ok")
    """
)


def test_core_import_succeeds_without_fastapi() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _PROBE],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_lazy_symbols_resolve_with_fastapi_installed() -> None:
    # The normal (fastapi-installed) path: attribute access resolves and
    # caches the real callable.
    import canvastekk_workflow_sdk as sdk

    assert callable(sdk.create_node_app)
    assert callable(sdk.create_multi_node_app)
    assert callable(sdk.NodeAuth)
