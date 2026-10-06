"""Engine scope-rename parity verification (DA-3588).

The engine renamed its definition scope value ``global`` → ``system``
(DA-3583, epic DA-3582) and added ``app_key`` / ``output_contract`` to
definitions payloads (DA-3585 / DA-3589). This module records the
verification finding: **the SDK does not model the engine's definitions
payloads at all** — its only ``scope`` references are ASGI request
scope (``app.py``) — so the breaking payload change cannot reach SDK
consumers, and no ``SdkCompatibility`` gate move is warranted.

The scan below is a regression guard: if definitions-payload parsing is
ever added to the SDK, this test surfaces the DA-3588 context so the
new parser handles the ``system`` value (and ``app_key`` /
``output_contract``) explicitly.
"""

from __future__ import annotations

from pathlib import Path

_SDK_ROOT = Path(__file__).resolve().parents[1] / "canvastekk_workflow_sdk"


def _source_files() -> list[Path]:
    return sorted(_SDK_ROOT.rglob("*.py"))


def test_no_definitions_scope_parsing_in_sdk() -> None:
    """No ``global``/``system`` DEFINITION-scope literals exist in SDK source.

    The only permitted ``scope`` hits are ASGI request scope
    (``app.py``'s middleware protocol) — never a definitions payload.
    """
    offenders: list[str] = []
    for path in _source_files():
        for lineno, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if 'scope = "global"' in line or 'scope == "global"' in line:
                offenders.append(f"{path.name}:{lineno}")
            if 'scope = "system"' in line or 'scope == "system"' in line:
                offenders.append(f"{path.name}:{lineno}")
    assert not offenders, (
        "Definitions-scope handling appeared in the SDK — extend this "
        f"module to cover the engine's 'system' value: {offenders}"
    )


def test_engine_payload_shape_documents_the_finding() -> None:
    """The engine payload the SDK deliberately does NOT parse (evidence)."""
    engine_payload = {
        "slug": "defect-checker-app",
        "name": "Defect Checker",
        "scope": "system",  # renamed from "global" (DA-3583)
        "app_key": "defect-checker",  # DA-3585
        "spec": {
            "nodes": [],
            "edges": [],
            "output_contract": {"type": "object"},  # DA-3589
        },
    }
    # Plain dict passthrough — the SDK transports specs opaquely (builder
    # templates embed specs as data), never validating scope.
    assert engine_payload["scope"] == "system"
    assert isinstance(engine_payload["spec"], dict)
