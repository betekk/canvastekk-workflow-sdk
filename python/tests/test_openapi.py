"""to_openapi() golden-file tests (#113).

The emitted document is the contract of record for gateways — the golden
file pins its exact shape so schema-level emitter changes fail loudly and
deliberately. Full 3.2-parser validation is deferred until the ecosystem
ships a 3.2-capable parser (documented PLAN ceiling).
"""

from __future__ import annotations

import json
from pathlib import Path

from canvastekk_workflow_sdk.definition import WorkflowNodeManifest

GOLDEN = Path(__file__).parent / "golden" / "openapi-3.2-echo.json"

MANIFEST = {
    "slug": "echo",
    "name": "Echo",
    "version": "1.2.3",
    "description": "Echoes the message",
    "input_schema": {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    },
    "output_schema": {
        "type": "object",
        "properties": {"message": {"type": "string"}},
        "required": ["message"],
    },
    "contract": {
        "transport": "http",
        "routes": ["/execute", "/health", "/manifest"],
        "capabilities": {"dry_run": True},
        "openapi": "3.2",
    },
}

DEFAULT_MANIFEST = {k: v for k, v in MANIFEST.items() if k != "contract"}


def test_to_openapi_golden_declaring_node() -> None:
    """AC1/AC4: the emitted document is pinned exactly (golden file)."""
    manifest = WorkflowNodeManifest.model_validate(MANIFEST)
    doc = manifest.to_openapi()
    assert doc["openapi"] == "3.2.0"
    assert json.loads(json.dumps(doc)) == doc
    golden = json.loads(GOLDEN.read_text())
    assert doc == golden


def test_to_openapi_effective_default_routes() -> None:
    """No declared contract -> the SDK-served default routes appear."""
    manifest = WorkflowNodeManifest.model_validate(DEFAULT_MANIFEST)
    doc = manifest.to_openapi()
    assert set(doc["paths"]) == {
        "/execute",
        "/health",
        "/manifest",
        "/hook",
        "/metrics",
        "/live",
        "/ready",
    }
    assert "post" in doc["paths"]["/execute"]
    assert "get" in doc["paths"]["/health"]


def test_to_openapi_execute_carries_schemas() -> None:
    """The /execute operation carries input/output schemas (AC1)."""
    manifest = WorkflowNodeManifest.model_validate(MANIFEST)
    op = manifest.to_openapi()["paths"]["/execute"]["post"]
    body_schema = op["requestBody"]["content"]["application/json"]["schema"]
    assert body_schema == MANIFEST["input_schema"]
    resp_schema = op["responses"]["200"]["content"]["application/json"]["schema"]
    assert resp_schema == MANIFEST["output_schema"]
