"""Conformance verifier + registration gate tests (#104).

All probes run against `httpx.MockTransport` — no network, no fastapi server
required (the verifier must be able to judge nodes built without the SDK).
"""

from __future__ import annotations

import httpx
import pytest

from canvastekk_workflow_sdk.conformance import verify_node
from canvastekk_workflow_sdk.definition import WorkflowNodeManifest
from canvastekk_workflow_sdk.registry import RegistrationError, register_node

MANIFEST = {
    "slug": "echo",
    "name": "echo",
    "version": "1.0.0",
    "description": "echo node",
    "input_schema": {"type": "object"},
    "output_schema": {"type": "object"},
}


def _transport(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://node.test")


def _patch_client(monkeypatch):
    """Point verify_node's httpx.Client at a MockTransport factory."""

    def _use(handler):
        client = _transport(handler)
        monkeypatch.setattr(httpx, "Client", lambda **kw: client)
        return client

    return _use


def _conforming_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "healthy"})
    if request.url.path == "/manifest":
        return httpx.Response(200, json=MANIFEST)
    if request.url.path == "/execute":
        return httpx.Response(422, json={"detail": "validation failed"})
    return httpx.Response(404)


def test_verify_node_conforming(monkeypatch) -> None:
    _patch_client(monkeypatch)(_conforming_handler)
    report = verify_node("http://node.test")
    assert report.ok
    assert len(report.checks) == 3
    assert all(c.ok for c in report.checks)


def test_verify_node_health_down(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(503)
        return _conforming_handler(request)

    _patch_client(monkeypatch)(handler)
    report = verify_node("http://node.test")
    assert not report.ok
    health = next(c for c in report.checks if c.route == "GET /health")
    assert not health.ok


def test_verify_node_invalid_manifest(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/manifest":
            return httpx.Response(200, json={"name": "missing-required-fields"})
        return _conforming_handler(request)

    _patch_client(monkeypatch)(handler)
    report = verify_node("http://node.test")
    manifest = next(c for c in report.checks if c.route == "GET /manifest")
    assert not manifest.ok
    assert "invalid manifest" in manifest.detail


def test_verify_node_execute_accepts_malformed(monkeypatch) -> None:
    """A node that 200s a garbage payload violates the contract."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/execute":
            return httpx.Response(200, json={"status": "pass"})
        return _conforming_handler(request)

    _patch_client(monkeypatch)(handler)
    report = verify_node("http://node.test")
    execute = next(c for c in report.checks if c.route == "POST /execute")
    assert not execute.ok


def test_register_node_verify_refuses_nonconforming(monkeypatch) -> None:
    probe_paths: list[str] = []
    post_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        probe_paths.append(request.url.path)
        if request.url.path == "/health":
            return httpx.Response(503)
        return httpx.Response(404)

    _patch_client(monkeypatch)(handler)
    monkeypatch.setattr(
        "canvastekk_workflow_sdk.registry.httpx.post",
        lambda url, **kw: post_urls.append(url) or httpx.Response(201, json={}, request=httpx.Request("POST", url)),
    )

    class FakeNode:
        definition = WorkflowNodeManifest.model_validate(MANIFEST)

        def export_definition(self) -> dict:
            return dict(MANIFEST)

    with pytest.raises(RegistrationError, match="conformance verification"):
        register_node(
            FakeNode(),  # type: ignore[arg-type]
            "https://engine.test/api/workflows/nodes/",
            invoke_url="http://node.test",
            invoke_type="http",
            api_key="k",
            verify=True,
        )
    # the probe hit the node's contract routes; the registry POST never fired
    assert probe_paths == ["/health", "/manifest", "/execute"]
    assert post_urls == []


def test_register_node_verify_accepts_conforming(monkeypatch) -> None:
    probe_calls: list[str] = []
    post_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        probe_calls.append(request.url.path)
        return _conforming_handler(request)

    client = _transport(handler)
    monkeypatch.setattr(httpx, "Client", lambda **kw: client)
    monkeypatch.setattr(
        "canvastekk_workflow_sdk.registry.httpx.post",
        lambda url, **kw: post_calls.append(url) or httpx.Response(
            201,
            json={**MANIFEST, "action": "created", "revision_id": "rev-1"},
            request=httpx.Request("POST", url),
        ),
    )

    class FakeNode:
        definition = WorkflowNodeManifest.model_validate(MANIFEST)

        def export_definition(self) -> dict:
            return dict(MANIFEST)

    result = register_node(
        FakeNode(),  # type: ignore[arg-type]
        "https://engine.test/api/workflows/nodes/",
        invoke_url="http://node.test",
        invoke_type="http",
        api_key="k",
        verify=True,
    )
    assert "/health" in probe_calls  # probe ran first
    assert result.action == "created"
    assert post_calls == ["https://engine.test/api/workflows/nodes/"]


def test_register_node_verify_requires_invoke_url(monkeypatch) -> None:
    _patch_client(monkeypatch)(_conforming_handler)

    class FakeNode:
        definition = WorkflowNodeManifest.model_validate(MANIFEST)

        def export_definition(self) -> dict:
            return dict(MANIFEST)

    with pytest.raises(ValueError, match="invoke_url"):
        register_node(
            FakeNode(),  # type: ignore[arg-type]
            "https://engine.test/api/workflows/nodes/",
            invoke_type="http",
            api_key="k",
            verify=True,
        )


def test_cli_verify_conforming(monkeypatch, capsys) -> None:
    _patch_client(monkeypatch)(_conforming_handler)
    from canvastekk_workflow_sdk.__main__ import main

    monkeypatch.setattr("sys.argv", ["canvastekk_workflow_sdk", "verify", "http://node.test"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "CONFORMING" in out


def test_cli_verify_nonconforming_exits_nonzero(monkeypatch, capsys) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    _patch_client(monkeypatch)(handler)
    from canvastekk_workflow_sdk.__main__ import main

    monkeypatch.setattr("sys.argv", ["canvastekk_workflow_sdk", "verify", "http://node.test"])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "NON-CONFORMING" in capsys.readouterr().out
