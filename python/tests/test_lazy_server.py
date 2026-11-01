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
    sys.modules["starlette"] = None  # block: the starlette transitive too

    import canvastekk_workflow_sdk

    assert "create_node_app" in canvastekk_workflow_sdk.__all__
    assert "create_multi_node_app" in canvastekk_workflow_sdk.__all__
    assert "NodeAuth" in canvastekk_workflow_sdk.__all__
    assert "SDKVersionMiddleware" in canvastekk_workflow_sdk.__all__

    try:
        canvastekk_workflow_sdk.create_node_app
    except ImportError as exc:
        assert "[fastapi]" in str(exc), f"unguided error: {exc}"
    else:
        raise SystemExit("expected guided ImportError for create_node_app")

    try:
        canvastekk_workflow_sdk.SDKVersionMiddleware
    except ImportError as exc:
        assert "[fastapi]" in str(exc), f"unguided error: {exc}"
    else:
        raise SystemExit("expected guided ImportError for SDKVersionMiddleware")

    try:
        canvastekk_workflow_sdk.NodeAuth
    except ImportError as exc:
        assert "[fastapi]" in str(exc), f"unguided error: {exc}"
    else:
        raise SystemExit("expected guided ImportError for NodeAuth")

    # --- Wave 1 (#225): auth core is framework-free ----------------------
    import canvastekk_workflow_sdk.auth.core as auth_core

    assert callable(auth_core.TekkNodeAuth)
    assert callable(auth_core.TekkCentralAuth)
    assert issubclass(auth_core.TekkAuthUnavailable, auth_core.TekkAuthError)
    assert auth_core.TekkAuthUnavailable.status == 503

    # Tekk* eager at the root package too — no fastapi needed
    assert canvastekk_workflow_sdk.TekkNodeAuth is auth_core.TekkNodeAuth
    assert issubclass(canvastekk_workflow_sdk.TekkAuthError, Exception)

    # The auth package gate mirrors the root gate for adapter names
    import canvastekk_workflow_sdk.auth as auth_pkg

    try:
        auth_pkg.NodeAuth
    except ImportError as exc:
        assert "[fastapi]" in str(exc), f"unguided error: {exc}"
    else:
        raise SystemExit("expected guided ImportError for auth.NodeAuth")

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
    import canvastekk_workflow_sdk as sdk

    assert callable(sdk.create_node_app)
    assert callable(sdk.create_multi_node_app)
    assert callable(sdk.NodeAuth)


def test_auth_core_source_has_no_framework_imports() -> None:
    """Static CI enforcement: auth/core.py must not import fastapi/starlette."""
    import canvastekk_workflow_sdk.auth.core as auth_core

    source = auth_core.__file__
    assert source, "auth.core has no __file__"
    with open(source, encoding="utf-8") as handle:
        text = handle.read()
    for forbidden in ("import fastapi", "from fastapi", "import starlette", "from starlette"):
        assert forbidden not in text, f"auth/core.py must stay framework-free: found {forbidden!r}"
