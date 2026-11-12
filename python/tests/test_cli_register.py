"""DA-2603: register CLI + offline probe harness tests."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import patch

import pytest

from canvastekk_workflow_sdk.__main__ import (
    _build_engine_request,
    _probe_definition,
    _run_register,
    main,
)
from canvastekk_workflow_sdk.definition import WorkflowNodeManifest


def _manifest(**overrides) -> WorkflowNodeManifest:
    defaults = dict(
        slug="echo",
        version="1.0.0",
        name="Echo",
        description="Echo node",
        input_schema={"type": "object"},
        output_schema={"type": "object"},
    )
    defaults.update(overrides)
    return WorkflowNodeManifest(**defaults)


class TestBuildEngineRequest:
    def test_vocabulary_adapter_mapping(self) -> None:
        payload = _build_engine_request(_manifest())
        assert payload["name"] == "echo"
        assert payload["label"] == "Echo"
        assert payload["description"] == "Echo node"
        assert "slug" not in payload

    def test_keys_within_engine_whitelist(self) -> None:
        manifest = _manifest(
            minimum_sdk_version="0.27.0",
            docs_url="https://docs.example.com/echo",
            styles=None,
        )
        payload = _build_engine_request(manifest)
        allowed = {
            "name",
            "version",
            "label",
            "description",
            "input_schema",
            "output_schema",
            "invoke_type",
            "invoke_url",
            "invoke_config",
            "category",
            "tags",
            "styles",
            "constraints",
            "token_cost",
            "timeout_seconds",
            "deprecation",
        }
        assert set(payload) <= allowed
        assert payload["constraints"] == {
            "docs_url": "https://docs.example.com/echo",
            "sdk_version": manifest.sdk_version,
        }

    def test_invoke_url_and_suffix(self) -> None:
        payload = _build_engine_request(
            _manifest(), invoke_url="https://nodes.example.com/echo/execute", name_suffix="-lambda"
        )
        assert payload["name"] == "echo-lambda"
        assert payload["invoke_type"] == "http"
        assert payload["invoke_url"] == "https://nodes.example.com/echo/execute"


class TestProbeDefinition:
    def test_valid_manifest_passes_with_engine_mirror(self) -> None:
        report = _probe_definition(_manifest())
        assert report["valid"], report["errors"]
        assert report["probes"] == ["manifest", "engine-request-mirror", "host-ceiling"]

    def test_broken_schema_fails(self) -> None:
        report = _probe_definition(_manifest(input_schema={"type": "not-a-real-type", "enum": 3}))
        assert not report["valid"]
        assert report["errors"]


class TestRunRegister:
    def _run(self, argv, token="ctk_" + "t" * 43, environ=None):
        env = {"CANVASTEKK_NODE_REGISTRATION_KEY": token, **(environ or {})}
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", env), redirect_stdout(buf_out), redirect_stderr(buf_err):
            code = _run_register(argv)
        return code, buf_out.getvalue(), buf_err.getvalue()

    def test_missing_token_is_usage_error(self) -> None:
        code, _, err = self._run(["m:d", "--engine-url", "https://eng"], token="")
        assert code == 2
        assert "CANVASTEKK_NODE_REGISTRATION_KEY" in err

    def test_non_ctk_token_is_rotation_error(self) -> None:
        """#239: legacy credentials fail locally (exit 2, rotation message) —
        no network call."""
        code, _, err = self._run(["m:d", "--engine-url", "https://eng"], token="t0ps3cret")
        assert code == 2
        assert "ctk_" in err and "rotate" in err

    def test_malformed_ctk_token_is_usage_error(self) -> None:
        """#239: truncated ctk_ keys fail locally with the shape hint."""
        code, _, err = self._run(["m:d", "--engine-url", "https://eng"], token="ctk_short")
        assert code == 2
        assert "truncated" in err

    def test_missing_engine_url_is_usage_error(self) -> None:
        assert self._run(["m:d"])[0] == 2

    def _post_response(self, status=201, body=b"{}"):
        response = io.BytesIO(body)
        response.status = status
        return response

    def test_success_registers_and_verifies(self) -> None:
        responses = [
            self._post_response(201),
            self._post_response(200, json.dumps({"id": "node-1"}).encode()),
        ]
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append((req.method, req.full_url))
            return responses.pop(0)

        with patch("urllib.request.urlopen", side_effect=fake_urlopen):
            code, out, _ = self._run(
                ["tests.test_cli_register:_manifest_module_marker", "--engine-url", "https://eng", "--json"]
            )
        assert code == 0, out
        data = json.loads(out)
        assert data["ok"] is True and data["id"] == "node-1"
        assert calls[0][1] == "https://eng/api/workflows/nodes/"
        assert calls[1][1] == "https://eng/api/workflows/nodes/by-name/echo"

    def test_auth_failure_exit_code(self) -> None:
        import urllib.request

        err = urllib.error.HTTPError("u", 401, "Unauthorized", hdrs=None, fp=io.BytesIO(b"{}"))
        with patch("urllib.request.urlopen", side_effect=err):
            code, _, out = self._run(["tests.test_cli_register:_manifest_module_marker", "--engine-url", "https://eng"])
        assert code == 3
        assert "t0ps3cret" not in out

    def test_client_error_exit_code(self) -> None:
        import urllib.request

        err = urllib.error.HTTPError("u", 422, "Unprocessable", hdrs=None, fp=io.BytesIO(b'{"detail": "slug"}'))
        with patch("urllib.request.urlopen", side_effect=err):
            code, _, _ = self._run(["tests.test_cli_register:_manifest_module_marker", "--engine-url", "https://eng"])
        assert code == 4

    def test_network_error_exit_code(self) -> None:
        import urllib.request

        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("refused")):
            code, _, _ = self._run(["tests.test_cli_register:_manifest_module_marker", "--engine-url", "https://eng"])
        assert code == 6


_manifest_module_marker = _manifest()


class TestProbeValueDomain:
    """DA-2603 review: probe mirrors the engine's value domain, not just key shape."""

    def test_rejects_category_outside_engine_enum(self) -> None:
        report = _probe_definition(_manifest(category="transform"))
        assert not report["valid"]
        assert any("category" in e for e in report["errors"])

    def test_rejects_timeout_over_engine_ceiling(self) -> None:
        report = _probe_definition(_manifest(timeout_seconds=100_000))
        assert not report["valid"]
        assert any("timeout_seconds" in e for e in report["errors"])

    def test_build_delegates_to_shipped_builder(self) -> None:
        from canvastekk_workflow_sdk.registry import build_registry_payload

        m = _manifest(minimum_sdk_version="0.27.0", docs_url="https://docs.example.com")
        assert _build_engine_request(m) == build_registry_payload(m, invoke_url=None)


class TestRegisterManifestFileInput:
    """DA-2604: register --manifest <file|URL> — parity with the ts CLI."""

    def test_manifest_file_registers(self, tmp_path) -> None:

        path = tmp_path / "manifest.json"
        path.write_text(
            json.dumps(
                {
                    "slug": "echo",
                    "version": "1.0.0",
                    "name": "Echo",
                    "description": "Echo node",
                    "input_schema": {"type": "object"},
                    "output_schema": {"type": "object"},
                    "id": "echo-v1.0.0",
                    "sdk_version": "0.28.0",
                    "mode": "production",
                    "code_digest": "ab" * 32,
                }
            )
        )
        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append((req.method, req.full_url))
            response = io.BytesIO(json.dumps({"id": "node-1"}).encode())
            response.status = 201
            if req.method == "GET":
                response = io.BytesIO(json.dumps({"id": "node-1"}).encode())
                response.status = 200
            return response

        with (
            patch.dict("os.environ", {"CANVASTEKK_NODE_REGISTRATION_KEY": "ctk_" + "t" * 43}),
            patch("urllib.request.urlopen", side_effect=fake_urlopen),
        ):
            code = _run_register(["--manifest", str(path), "--engine-url", "https://eng", "--json"])
        assert code == 0
        assert calls[0][1] == "https://eng/api/workflows/nodes/"

    def test_manifest_missing_file_is_usage_error(self, tmp_path) -> None:
        with patch.dict("os.environ", {"CANVASTEKK_NODE_REGISTRATION_KEY": "ctk_" + "t" * 43}):
            assert _run_register(["--manifest", str(tmp_path / "nope.json"), "--engine-url", "https://eng"]) == 2


class TestRegistryConvergenceCommand:
    """DA-3086: the registry-convergence subcommand routes to convergence.main."""

    def test_help_exits_zero(self, capsys) -> None:
        from canvastekk_workflow_sdk.convergence import main as convergence_main

        with pytest.raises(SystemExit) as exc:
            convergence_main(["--help"])
        assert exc.value.code == 0
        assert "--registry-base" in capsys.readouterr().out

    def test_missing_required_args_exit_2(self) -> None:
        from canvastekk_workflow_sdk.convergence import main as convergence_main

        with pytest.raises(SystemExit) as exc:
            convergence_main([])
        assert exc.value.code == 2

    def test_dispatch_delegates_with_argv(self, capsys) -> None:
        from unittest.mock import patch

        with patch("sys.argv", ["prog", "registry-convergence", "--help"]):
            with pytest.raises(SystemExit) as exc:
                main()
        assert exc.value.code == 0
        assert "--registry-base" in capsys.readouterr().out


class TestRegisterRetry:
    """#242: bounded retry on engine 5xx + transport errors; 4xx fails fast."""

    def _run(self, argv, token="ctk_" + "t" * 43, environ=None):
        env = {"CANVASTEKK_NODE_REGISTRATION_KEY": token, **(environ or {})}
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with patch.dict("os.environ", env), redirect_stdout(buf_out), redirect_stderr(buf_err):
            code = _run_register(argv)
        return code, buf_out.getvalue(), buf_err.getvalue()

    @staticmethod
    def _post_response(status=201, body=b"{}"):
        response = io.BytesIO(body)
        response.status = status
        return response

    @staticmethod
    def _http_error(code_):
        import urllib.error

        return urllib.error.HTTPError("u", code_, "Error", hdrs=None, fp=io.BytesIO(b"{}"))

    def _retry_run(self, side_effects):
        import urllib.error

        calls = []

        def fake_urlopen(req, timeout=None):
            calls.append(req.method)
            effect = side_effects.pop(0)
            if isinstance(effect, (urllib.error.HTTPError, urllib.error.URLError, OSError)):
                raise effect
            return effect

        sleeps = []
        with patch("urllib.request.urlopen", side_effect=fake_urlopen), patch(
            "canvastekk_workflow_sdk.__main__.time.sleep", side_effect=sleeps.append
        ):
            code, out, err = self._run(
                ["tests.test_cli_register:_manifest_module_marker", "--engine-url", "https://eng", "--json"]
            )
        return code, out, err, calls, sleeps

    def test_502s_then_success_retries(self) -> None:
        code, out, err, calls, sleeps = self._retry_run(
            [self._http_error(502), self._http_error(503), self._post_response(201), self._post_response(200)]
        )
        assert code == 0, out
        assert calls.count("POST") == 3
        assert sleeps == [2, 4]
        assert "attempt 1/4 failed (HTTP 502)" in err
        assert "attempt 2/4 failed (HTTP 503)" in err

    def test_client_error_fails_fast(self) -> None:
        code, out, err, calls, sleeps = self._retry_run([self._http_error(409)])
        assert code == 4
        assert len(calls) == 1
        assert sleeps == []
        assert "retrying" not in err

    def test_persistent_502_exhausts_attempts(self) -> None:
        code, out, err, calls, sleeps = self._retry_run(
            [self._http_error(502)] * 4
        )
        assert code == 5
        assert len(calls) == 4
        assert sleeps == [2, 4, 8]
        assert "Engine error (HTTP 502)" in out

    def test_transport_error_then_success(self) -> None:
        import urllib.error

        code, out, err, calls, sleeps = self._retry_run(
            [urllib.error.URLError("conn refused"), self._post_response(201), self._post_response(200)]
        )
        assert code == 0, out
        assert calls.count("POST") == 2
        assert sleeps == [2]
        assert "attempt 1/4 failed (URLError" in err
