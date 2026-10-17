"""Tests for authentication module (Phase 2)."""

from typing import Any

import pytest
from fastapi import HTTPException

from canvastekk_workflow_sdk.auth import NodeAuth, _ApiKeyAuth, _is_dev_mode, _JwtAuth, _KeycloakAuth


def _raise_import_error(message: str):
    def _raiser(*args: Any, **kwargs: Any) -> Any:
        raise ImportError(message)

    return _raiser


class TestIsDevMode:
    """Tests for _is_dev_mode helper function."""

    def test_dev_mode_true_with_true_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "true")
        assert _is_dev_mode() is True

    def test_dev_mode_true_with_one_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "1")
        assert _is_dev_mode() is True

    def test_dev_mode_true_with_yes_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "yes")
        assert _is_dev_mode() is True

    def test_dev_mode_false_with_false_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "false")
        assert _is_dev_mode() is False

    def test_dev_mode_false_with_zero_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "0")
        assert _is_dev_mode() is False

    def test_dev_mode_false_with_no_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CANVASTEKK_DEV_MODE", raising=False)
        assert _is_dev_mode() is False

    def test_dev_mode_case_insensitive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "TRUE")
        assert _is_dev_mode() is True
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "True")
        assert _is_dev_mode() is True
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "TrUe")
        assert _is_dev_mode() is True


class TestApiKeyAuth:
    """Tests for _ApiKeyAuth backend."""

    def test_valid_api_key_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_API_KEY", "secret-key-123")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()
        request.headers["X-API-Key"] = "secret-key-123"

        result = auth.authenticate(request)
        assert result == {"auth_mode": "api_key"}

    def test_invalid_api_key_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_API_KEY", "correct-key")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()
        request.headers["X-API-Key"] = "wrong-key"

        with pytest.raises(Exception) as exc_info:
            auth.authenticate(request)
        assert "Invalid API key" in str(exc_info.value)
        assert exc_info.value.status_code == 401

    def test_missing_api_key_header_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_API_KEY", "correct-key")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()

        with pytest.raises(Exception) as exc_info:
            auth.authenticate(request)
        assert "Invalid API key" in str(exc_info.value)
        assert exc_info.value.status_code == 401

    def test_missing_env_var_rejected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CANVASTEKK_API_KEY", raising=False)

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()
        request.headers["X-API-Key"] = "any-key"

        with pytest.raises(Exception) as exc_info:
            auth.authenticate(request)
        assert "Authentication not configured" in str(exc_info.value)
        assert exc_info.value.status_code == 401

    def test_dev_mode_bypasses_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "true")
        monkeypatch.delenv("CANVASTEKK_API_KEY", raising=False)

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()

        result = auth.authenticate(request)
        assert result == {"auth_mode": "dev_bypass"}

    def test_custom_env_var_name(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MY_CUSTOM_KEY", "custom-secret")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth(key_env_var="MY_CUSTOM_KEY")
        request = MockRequest()
        request.headers["X-API-Key"] = "custom-secret"

        result = auth.authenticate(request)
        assert result == {"auth_mode": "api_key"}

    def test_as_dependency_returns_depends(self) -> None:
        auth = _ApiKeyAuth()
        depends = auth.as_dependency()
        assert depends is not None

    def test_next_key_accepted_during_rotation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_API_KEY", "current-key")
        monkeypatch.setenv("CANVASTEKK_API_KEY_NEXT", "new-key")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()
        request.headers["X-API-Key"] = "new-key"

        result = auth.authenticate(request)
        assert result == {"auth_mode": "api_key"}

    def test_current_key_still_accepted_with_next_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_API_KEY", "current-key")
        monkeypatch.setenv("CANVASTEKK_API_KEY_NEXT", "new-key")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()
        request.headers["X-API-Key"] = "current-key"

        result = auth.authenticate(request)
        assert result == {"auth_mode": "api_key"}

    def test_empty_next_key_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_API_KEY", "current-key")
        monkeypatch.setenv("CANVASTEKK_API_KEY_NEXT", "")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()
        request.headers["X-API-Key"] = "current-key"

        result = auth.authenticate(request)
        assert result == {"auth_mode": "api_key"}

    def test_unknown_key_rejected_when_next_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_API_KEY", "current-key")
        monkeypatch.setenv("CANVASTEKK_API_KEY_NEXT", "new-key")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()
        request.headers["X-API-Key"] = "neither-key"

        with pytest.raises(HTTPException) as exc_info:
            auth.authenticate(request)
        assert exc_info.value.status_code == 401

    def test_next_only_configured_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Edge case: NEXT set while current is empty (mid-rotation misconfig still authenticates NEXT holders)."""
        monkeypatch.setenv("CANVASTEKK_API_KEY", "")
        monkeypatch.setenv("CANVASTEKK_API_KEY_NEXT", "new-key")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()
        request.headers["X-API-Key"] = "new-key"

        result = auth.authenticate(request)
        assert result == {"auth_mode": "api_key"}

    def test_callable_invokes_authenticate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_API_KEY", "test-key")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _ApiKeyAuth()
        request = MockRequest()
        request.headers["X-API-Key"] = "test-key"

        result = auth(request)
        assert result == {"auth_mode": "api_key"}


class TestJwtAuth:
    """Tests for _JwtAuth backend."""

    def test_import_error_without_jwt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_JWT_SECRET", "test-secret")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _JwtAuth()
        auth._jwt_module = None
        monkeypatch.setattr(auth, "_get_jwt", _raise_import_error("PyJWT is required for JWT authentication"))

        request = MockRequest()
        request.headers["Authorization"] = "Bearer test-token"

        with pytest.raises(ImportError, match="PyJWT is required for JWT authentication"):
            auth.authenticate(request)

    def test_missing_secret_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CANVASTEKK_JWT_SECRET", raising=False)

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _JwtAuth()
        request = MockRequest()
        request.headers["Authorization"] = "Bearer test-token"

        with pytest.raises(Exception) as exc_info:
            auth.authenticate(request)
        assert "JWT authentication not configured" in str(exc_info.value)
        assert exc_info.value.status_code == 401

    def test_missing_bearer_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_JWT_SECRET", "test-secret")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _JwtAuth()
        request = MockRequest()
        request.headers["Authorization"] = "Basic some-credential"

        with pytest.raises(Exception) as exc_info:
            auth.authenticate(request)
        assert "Missing Bearer token" in str(exc_info.value)
        assert exc_info.value.status_code == 401

    def test_empty_auth_header(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_JWT_SECRET", "test-secret")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _JwtAuth()
        request = MockRequest()

        with pytest.raises(Exception) as exc_info:
            auth.authenticate(request)
        assert "Missing Bearer token" in str(exc_info.value)
        assert exc_info.value.status_code == 401

    def test_dev_mode_bypasses_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "true")
        monkeypatch.delenv("CANVASTEKK_JWT_SECRET", raising=False)

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _JwtAuth()
        request = MockRequest()

        result = auth.authenticate(request)
        assert result == {"auth_mode": "dev_bypass"}

    def test_custom_algorithm(self) -> None:
        auth = _JwtAuth(algorithm="HS512")
        assert auth._algorithm == "HS512"

    def test_custom_audience(self) -> None:
        auth = _JwtAuth(audience="my-app")
        assert auth._audience == "my-app"

    def test_custom_secret_env_var(self) -> None:
        auth = _JwtAuth(secret_env_var="MY_JWT_SECRET")
        assert auth._secret_env_var == "MY_JWT_SECRET"

    def test_as_dependency_returns_depends(self) -> None:
        auth = _JwtAuth()
        depends = auth.as_dependency()
        assert depends is not None

    def test_callable_invokes_authenticate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_JWT_SECRET", "test-secret")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _JwtAuth()
        auth._jwt_module = None
        monkeypatch.setattr(auth, "_get_jwt", _raise_import_error("PyJWT is required"))

        request = MockRequest()
        request.headers["Authorization"] = "Bearer test-token"

        with pytest.raises(ImportError):
            auth(request)


class TestKeycloakAuth:
    """Tests for _KeycloakAuth backend."""

    def test_import_error_without_jwt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class MockRequest:
            headers: dict[str, str] = {}

        auth = _KeycloakAuth()
        auth._jwt_module = None
        monkeypatch.setattr(
            auth, "_get_jwt", _raise_import_error("PyJWT and cryptography are required for Keycloak authentication")
        )

        request = MockRequest()
        request.headers["Authorization"] = "Bearer test-token"

        with pytest.raises(ImportError, match="PyJWT and cryptography are required"):
            auth.authenticate(request)

    def test_missing_bearer_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class MockRequest:
            headers: dict[str, str] = {}

        auth = _KeycloakAuth()
        request = MockRequest()
        request.headers["Authorization"] = "Basic some-credential"

        with pytest.raises(HTTPException) as exc_info:
            auth.authenticate(request)
        assert exc_info.value.status_code == 401

    def test_dev_mode_bypasses_auth(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "true")

        class MockRequest:
            headers: dict[str, str] = {}

        auth = _KeycloakAuth()
        request = MockRequest()

        result = auth.authenticate(request)
        assert result == {"auth_mode": "dev_bypass"}

    def test_custom_server_url(self) -> None:
        auth = _KeycloakAuth(server_url="https://auth.example.com")
        assert auth._server_url == "https://auth.example.com"

    def test_custom_realm(self) -> None:
        auth = _KeycloakAuth(realm="my-realm")
        assert auth._realm == "my-realm"

    def test_custom_audience(self) -> None:
        auth = _KeycloakAuth(audience="my-app")
        assert auth._audience == "my-app"

    def test_custom_algorithm(self) -> None:
        auth = _KeycloakAuth(algorithm="RS512")
        assert auth._algorithm == "RS512"

    def test_config_from_env_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_KEYCLOAK_SERVER_URL", "https://auth.example.com")
        monkeypatch.setenv("CANVASTEKK_KEYCLOAK_REALM", "test-realm")
        monkeypatch.setenv("CANVASTEKK_KEYCLOAK_AUDIENCE", "test-audience")

        auth = _KeycloakAuth()
        assert auth._server_url == "https://auth.example.com"
        assert auth._realm == "test-realm"
        assert auth._audience == "test-audience"

    def test_as_dependency_returns_depends(self) -> None:
        auth = _KeycloakAuth()
        depends = auth.as_dependency()
        assert depends is not None

    def test_callable_invokes_authenticate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class MockRequest:
            headers: dict[str, str] = {}

        auth = _KeycloakAuth()
        auth._jwt_module = None
        monkeypatch.setattr(auth, "_get_jwt", _raise_import_error("PyJWT and cryptography are required"))

        request = MockRequest()
        request.headers["Authorization"] = "Bearer test-token"

        with pytest.raises(ImportError):
            auth(request)


class TestNodeAuthFactory:
    """Tests for NodeAuth factory class."""

    def test_api_key_factory_returns_api_key_auth(self) -> None:
        auth = NodeAuth.api_key()
        assert isinstance(auth, _ApiKeyAuth)

    def test_api_key_factory_with_custom_env_var(self) -> None:
        auth = NodeAuth.api_key(key_env_var="MY_KEY")
        assert isinstance(auth, _ApiKeyAuth)
        assert auth._key_env_var == "MY_KEY"

    def test_jwt_factory_returns_jwt_auth(self) -> None:
        auth = NodeAuth.jwt()
        assert isinstance(auth, _JwtAuth)

    def test_jwt_factory_with_custom_params(self) -> None:
        auth = NodeAuth.jwt(secret_env_var="MY_SECRET", algorithm="HS512", audience="my-app")
        assert isinstance(auth, _JwtAuth)
        assert auth._secret_env_var == "MY_SECRET"
        assert auth._algorithm == "HS512"
        assert auth._audience == "my-app"

    def test_keycloak_factory_returns_keycloak_auth(self) -> None:
        auth = NodeAuth.keycloak()
        assert isinstance(auth, _KeycloakAuth)

    def test_keycloak_factory_with_custom_params(self) -> None:
        auth = NodeAuth.keycloak(
            server_url="https://auth.example.com", realm="my-realm", audience="my-app", algorithm="RS512"
        )
        assert isinstance(auth, _KeycloakAuth)
        assert auth._server_url == "https://auth.example.com"
        assert auth._realm == "my-realm"
        assert auth._audience == "my-app"
        assert auth._algorithm == "RS512"


class TestCentralAuth:
    """Tests for the _CentralAuth backend (#3825)."""

    VALID_CLAIMS = {"run_id": "run-7", "node_id": "node-a", "exp": 9_999_999_999}

    def _auth(self, **kwargs: Any):
        from canvastekk_workflow_sdk.auth import _CentralAuth

        defaults: dict[str, Any] = {"cache_ttl": 60.0, "timeout": 1.0}
        defaults.update(kwargs)
        return _CentralAuth(**defaults)

    @staticmethod
    def _request_with_key(key: str) -> Any:
        class MockRequest:
            headers = {"X-API-Key": key}

        return MockRequest()

    @staticmethod
    def _stub_verify(verdicts: list[Any], counter: dict[str, int]) -> Any:
        """Replace _remote_verify with a queue of verdicts/exceptions."""

        def _stub(self: Any, token: str, base_url: str) -> Any:
            counter["calls"] = counter.get("calls", 0) + 1
            result = verdicts.pop(0) if verdicts else verdicts
            if isinstance(result, Exception):
                raise result
            return result

        return _stub

    def test_valid_token_accepted_and_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CWE_API_BASE_URL", "http://engine.example")
        auth = self._auth()
        counter: dict[str, int] = {}
        monkeypatch.setattr(
            type(auth),
            "_remote_verify",
            self._stub_verify([(True, dict(self.VALID_CLAIMS))], counter),
        )
        result = auth.authenticate(self._request_with_key("cwnt_v1.abc.def"))
        assert result["auth_mode"] == "central"
        assert result["run_id"] == "run-7"
        assert result["node_id"] == "node-a"
        # Second call must hit the cache — stub sees exactly one call.
        auth.authenticate(self._request_with_key("cwnt_v1.abc.def"))
        assert counter["calls"] == 1

    def test_invalid_verdict_rejected_and_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CWE_API_BASE_URL", "http://engine.example")
        auth = self._auth()
        counter: dict[str, int] = {}
        monkeypatch.setattr(
            type(auth), "_remote_verify", self._stub_verify([(False, None)], counter)
        )
        with pytest.raises(HTTPException) as first:
            auth.authenticate(self._request_with_key("cwnt_v1.abc.def"))
        assert first.value.status_code == 401
        with pytest.raises(HTTPException):
            auth.authenticate(self._request_with_key("cwnt_v1.abc.def"))
        assert counter["calls"] == 1

    def test_transport_failure_fails_closed_503_not_cached(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CWE_API_BASE_URL", "http://engine.example")
        from canvastekk_workflow_sdk.auth import _VerifyUnavailableError

        auth = self._auth()
        counter: dict[str, int] = {}
        monkeypatch.setattr(
            type(auth),
            "_remote_verify",
            self._stub_verify([_VerifyUnavailableError("boom")], counter),
        )
        with pytest.raises(HTTPException) as first:
            auth.authenticate(self._request_with_key("cwnt_v1.abc.def"))
        assert first.value.status_code == 503
        # Not cached: a retry after recovery re-queries (stub would be
        # exhausted otherwise — provide a good verdict next).
        monkeypatch.setattr(
            type(auth),
            "_remote_verify",
            self._stub_verify([(True, dict(self.VALID_CLAIMS))], counter),
        )
        result = auth.authenticate(self._request_with_key("cwnt_v1.abc.def"))
        assert result["auth_mode"] == "central"

    def test_legacy_key_accepted_when_env_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_API_KEY", "legacy-secret")
        auth = self._auth()
        result = auth.authenticate(self._request_with_key("legacy-secret"))
        assert result == {"auth_mode": "legacy_api_key"}

    def test_legacy_rotation_next_key_accepted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CANVASTEKK_API_KEY", "")
        monkeypatch.setenv("CANVASTEKK_API_KEY_NEXT", "rotating-secret")
        auth = self._auth()
        result = auth.authenticate(self._request_with_key("rotating-secret"))
        assert result == {"auth_mode": "legacy_api_key"}

    def test_legacy_leg_inert_when_env_unset(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CWE_API_BASE_URL", "http://engine.example")
        monkeypatch.delenv("CANVASTEKK_API_KEY", raising=False)
        monkeypatch.delenv("CANVASTEKK_API_KEY_NEXT", raising=False)
        auth = self._auth()
        counter: dict[str, int] = {}
        monkeypatch.setattr(
            type(auth), "_remote_verify", self._stub_verify([(False, None)], counter)
        )
        with pytest.raises(HTTPException) as exc:
            auth.authenticate(self._request_with_key("legacy-secret"))
        assert exc.value.status_code == 401
        assert counter["calls"] == 1

    def test_missing_base_url_and_no_legacy_match_is_401(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("CWE_API_BASE_URL", raising=False)
        monkeypatch.delenv("CANVASTEKK_API_KEY", raising=False)
        auth = self._auth()
        with pytest.raises(HTTPException) as exc:
            auth.authenticate(self._request_with_key("cwnt_v1.abc.def"))
        assert exc.value.status_code == 401
        assert exc.value.detail == "Authentication not configured"

    def test_missing_header_is_401(self) -> None:
        auth = self._auth()

        class MockRequest:
            headers: dict[str, str] = {}

        with pytest.raises(HTTPException) as exc:
            auth.authenticate(MockRequest())
        assert exc.value.status_code == 401

    def test_dev_mode_bypasses(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CANVASTEKK_DEV_MODE", "true")
        auth = self._auth()
        assert auth.authenticate(self._request_with_key("anything")) == {
            "auth_mode": "dev_bypass"
        }

    def test_real_http_stub_valid_verdict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        calls = {"count": 0}

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server API
                calls["count"] += 1
                body = json.dumps({"valid": True, **TestCentralAuth.VALID_CLAIMS})
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body.encode())

            def log_message(self, *args: Any) -> None:
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            monkeypatch.setenv("CWE_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
            auth = self._auth()
            first = auth.authenticate(self._request_with_key("cwnt_v1.real.http"))
            second = auth.authenticate(self._request_with_key("cwnt_v1.real.http"))
            assert first["auth_mode"] == "central"
            assert second["run_id"] == "run-7"
            assert calls["count"] == 1  # cache honored over real urllib path
        finally:
            server.shutdown()

    def test_real_http_unreachable_fails_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import socket

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
        sock.close()  # nothing listens here
        monkeypatch.setenv("CWE_API_BASE_URL", f"http://127.0.0.1:{port}")
        auth = self._auth(timeout=0.5)
        with pytest.raises(HTTPException) as exc:
            auth.authenticate(self._request_with_key("cwnt_v1.dead.port"))
        assert exc.value.status_code == 503

    def test_malformed_verify_response_fails_closed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - http.server API
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(b"<not-json>")

            def log_message(self, *args: Any) -> None:
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            monkeypatch.setenv("CWE_API_BASE_URL", f"http://127.0.0.1:{server.server_port}")
            auth = self._auth()
            with pytest.raises(HTTPException) as exc:
                auth.authenticate(self._request_with_key("cwnt_v1.abc.def"))
            assert exc.value.status_code == 503
        finally:
            server.shutdown()

    def test_cache_expiry_bounded_by_token_exp(self) -> None:
        import time as time_mod

        auth = self._auth(cache_ttl=60.0)
        soon = time_mod.time() + 2.0
        expiry = auth._cache_expiry(True, {"exp": soon})
        assert expiry <= time_mod.monotonic() + 2.5
        invalid_expiry = auth._cache_expiry(False, None)
        assert invalid_expiry > time_mod.monotonic() + 55.0

    def test_cache_clears_on_overflow(self, monkeypatch: pytest.MonkeyPatch) -> None:
        auth = self._auth()
        # Fill the cache to capacity with expired junk entries.
        auth._verdict_cache.update(
            {f"k{i}": (False, None, 0.0) for i in range(auth._CACHE_MAX_ENTRIES)}
        )
        counter: dict[str, int] = {}
        monkeypatch.setattr(
            type(auth), "_remote_verify", self._stub_verify([(True, dict(self.VALID_CLAIMS))], counter)
        )
        monkeypatch.setenv("CWE_API_BASE_URL", "http://engine.example")
        auth._validated_claims("cwnt_v1.overflow.token")
        assert len(auth._verdict_cache) <= auth._CACHE_MAX_ENTRIES

    def test_central_factory_defaults(self) -> None:
        auth = NodeAuth.central()
        from canvastekk_workflow_sdk.auth import _CentralAuth

        assert isinstance(auth, _CentralAuth)
        assert auth._verify_base_url_env_var == "CWE_API_BASE_URL"
        assert auth._verify_path == "/api/nodes/verify-token"
        assert auth._cache_ttl == 60.0
        assert auth._legacy_key_env_var == "CANVASTEKK_API_KEY"

    def test_central_factory_central_only(self) -> None:
        auth = NodeAuth.central(legacy_key_env_var=None)
        assert auth._legacy_key_env_var is None
        assert auth._legacy_matches("anything") is False
