"""Conformance verifier + registration gate tests (#104).

All probes run against `httpx.MockTransport` — no network, no fastapi server
required (the verifier must be able to judge nodes built without the SDK).
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from canvastekk_workflow_sdk import BaseNode
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

    def _use(handler, *args, **kwargs):
        if args or kwargs:
            client = _transport(lambda req: handler(req, *args, **kwargs))
        else:
            client = _transport(handler)
        monkeypatch.setattr(httpx, "Client", lambda **kw: client)
        return client

    return _use


def _conforming_handler(request: httpx.Request) -> httpx.Response:
    """Serves the full SDK-served default contract (7 routes)."""
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "healthy"})
    if request.url.path == "/manifest":
        return httpx.Response(200, json=MANIFEST)
    if request.url.path == "/execute":
        body = request.read()
        return httpx.Response(200, json={"ok": True}) if b"dry_run" in body else httpx.Response(
            422, json={"detail": "validation failed"}
        )
    if request.url.path in ("/hook", "/metrics", "/live", "/ready"):
        return httpx.Response(200, json={})
    return httpx.Response(404)


def test_verify_node_conforming(monkeypatch) -> None:
    _patch_client(monkeypatch)(_conforming_handler)
    report = verify_node("http://node.test")
    assert report.ok
    # derived: /manifest + 6 remaining SDK-served routes + the dry-run skip line
    assert len(report.checks) == 8
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
    # /manifest 404s -> the probe set cannot be derived; the registry POST never fired
    assert probe_paths == ["/manifest"]
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


# --- #113: manifest-derived probe set -------------------------------

DERIVED_MANIFEST = {
    **MANIFEST,
    "contract": {
        "transport": "http",
        "routes": ["/execute", "/health", "/manifest", "/metrics"],
        "capabilities": {"dry_run": False},
        "openapi": "3.2",
    },
}


def _derived_handler(request: httpx.Request, metrics_status: int = 200) -> httpx.Response:
    if request.url.path == "/manifest":
        return httpx.Response(200, json=DERIVED_MANIFEST)
    if request.url.path == "/metrics":
        return httpx.Response(metrics_status, json={})
    if request.url.path == "/execute":
        return httpx.Response(422, json={"detail": "validation failed"})
    return httpx.Response(200, json={"status": "healthy"})


def test_verify_node_derives_declared_routes(monkeypatch) -> None:
    """Probe list = declared routes; no hardcoded list (#113 AC1)."""
    _patch_client(monkeypatch)(_derived_handler)
    report = verify_node("http://node.test")
    names = [c.route for c in report.checks]
    assert names == [
        "GET /manifest",
        "POST /execute",
        "POST /execute (dry-run)",
        "GET /health",
        "GET /metrics",
    ]
    assert report.ok


def test_verify_node_broken_declared_route_fails_at_its_name(monkeypatch) -> None:
    """A deliberately broken declared route FAILs under its own name (#113 AC4)."""
    _patch_client(monkeypatch)(_derived_handler, metrics_status=404)
    report = verify_node("http://node.test")
    metrics = next(c for c in report.checks if c.route == "GET /metrics")
    assert not metrics.ok
    assert not report.ok


# --- #113: capability-gated dry-run positive probe -------------------

DRY_RUN_MANIFEST = {
    **DERIVED_MANIFEST,
    "contract": {**DERIVED_MANIFEST["contract"], "capabilities": {"dry_run": True}},
}


def _dry_run_handler(request: httpx.Request, dry_status: int = 200) -> httpx.Response:
    if request.url.path == "/manifest":
        return httpx.Response(200, json=DRY_RUN_MANIFEST)
    if request.url.path == "/execute":
        body = request.read()
        if b"dry_run" in body:
            return httpx.Response(dry_status, json={"status": "pass", "token_cost": 0})
        return httpx.Response(422, json={"detail": "validation failed"})
    return httpx.Response(200, json={})


def test_dry_run_positive_probe_fires_when_flagged_and_declared(monkeypatch) -> None:
    _patch_client(monkeypatch)(_dry_run_handler)
    report = verify_node("http://node.test", dry_run=True)
    probe = next(c for c in report.checks if c.route == "POST /execute (dry-run)")
    assert probe.ok
    assert report.ok


def test_dry_run_positive_probe_fails_at_its_name_on_5xx(monkeypatch) -> None:
    _patch_client(monkeypatch)(_dry_run_handler, dry_status=500)
    report = verify_node("http://node.test", dry_run=True)
    probe = next(c for c in report.checks if c.route == "POST /execute (dry-run)")
    assert not probe.ok
    assert not report.ok


def test_dry_run_positive_probe_skipped_without_flag(monkeypatch) -> None:
    """Capability declared but no --dry-run -> skipped, never failed."""
    _patch_client(monkeypatch)(_dry_run_handler)
    report = verify_node("http://node.test")
    probe = next(c for c in report.checks if c.route == "POST /execute (dry-run)")
    assert probe.ok
    assert "skipped" in probe.detail


def test_dry_run_positive_probe_skipped_without_capability(monkeypatch) -> None:
    """--dry-run passed but capability absent -> skipped, never failed (#113 AC2)."""
    _patch_client(monkeypatch)(_derived_handler)
    report = verify_node("http://node.test", dry_run=True)
    probe = next(c for c in report.checks if c.route == "POST /execute (dry-run)")
    assert probe.ok
    assert "skipped" in probe.detail


def test_cli_verify_dry_run_flag_threads_through(monkeypatch, capsys) -> None:
    """--dry-run reaches verify_node as dry_run=True (#113 AC3)."""
    captured: dict = {}

    def fake_verify(url, **kw):
        captured.update(kw)

        class _R:
            ok = True

            def summary(self):
                return "CONFORMING"

        return _R()

    _patch_client(monkeypatch)(_dry_run_handler)
    import canvastekk_workflow_sdk.conformance as conf

    monkeypatch.setattr(conf, "verify_node", fake_verify)
    from canvastekk_workflow_sdk.__main__ import main

    monkeypatch.setattr(
        "sys.argv", ["canvastekk_workflow_sdk", "verify", "http://node.test", "--dry-run"]
    )
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 0
    assert captured.get("dry_run") is True


class _CentralEchoNode(BaseNode):
    """Echo node used to probe central-mode authentication end to end."""

    definition = WorkflowNodeManifest(
        slug="echo",
        version="1.0.0",
        name="Echo",
        description="Returns input unchanged",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
        token_cost=0.0,
    )

    def execute(self, inputs: dict, context: Any) -> dict:
        return {"message": inputs.get("message", "")}


def _start_cwe_stub(key: str):
    """Serve the verify endpoint with real token verification."""
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from canvastekk_workflow_sdk.node_token import verify_node_token

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802 - http.server API
            if self.path != "/api/nodes/verify-token":
                self.send_response(404)
                self.end_headers()
                return
            body = _json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            claims = verify_node_token(body.get("token", ""), key)
            payload = (
                {"valid": True, "run_id": claims.run_id, "node_id": claims.node_id, "exp": claims.exp}
                if claims
                else {"valid": False}
            )
            encoded = _json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(encoded)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def test_verify_node_central_mode_with_valid_token(monkeypatch) -> None:
    """A central-mode node passes conformance when probed with a real token.

    End to end over real code paths: verify_node → ASGI app →
    _CentralAuth → local CWE stub → verify_node_token (#3825).
    """
    from canvastekk_workflow_sdk.app import create_node_app
    from canvastekk_workflow_sdk.auth import NodeAuth
    from canvastekk_workflow_sdk.node_token import mint_node_token

    key = "conformance-signing-key-0123456789abcdef"
    server = _start_cwe_stub(key)
    try:
        monkeypatch.setenv("CWE_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
        app = create_node_app(_CentralEchoNode(), auth=NodeAuth.central(timeout=2.0))

        def fake_client(**kw: Any) -> TestClient:
            return TestClient(app, base_url=kw.get("base_url"), headers=kw.get("headers", {}))

        monkeypatch.setattr(httpx, "Client", fake_client)

        token = mint_node_token("run-c1", "echo", key, ttl_seconds=300)
        report = verify_node("http://node.test", api_key=token)
        assert report.ok, [c.route for c in report.checks if not c.ok]
        assert all(c.ok for c in report.checks)
        assert len(report.checks) >= 6  # manifest + derived route probes
    finally:
        server.shutdown()


def test_verify_node_central_mode_without_token_fails_at_manifest(monkeypatch) -> None:
    """Without a token the manifest fetch cannot succeed — report not ok."""
    from canvastekk_workflow_sdk.app import create_node_app
    from canvastekk_workflow_sdk.auth import NodeAuth

    key = "conformance-signing-key-0123456789abcdef"
    server = _start_cwe_stub(key)
    try:
        monkeypatch.setenv("CWE_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
        app = create_node_app(_CentralEchoNode(), auth=NodeAuth.central(timeout=2.0))

        def fake_client(**kw: Any) -> TestClient:
            return TestClient(app, base_url=kw.get("base_url"), headers=kw.get("headers", {}))

        monkeypatch.setattr(httpx, "Client", fake_client)

        report = verify_node("http://node.test")
        assert not report.ok
        assert any("manifest" in c.route for c in report.checks if not c.ok)
    finally:
        server.shutdown()
