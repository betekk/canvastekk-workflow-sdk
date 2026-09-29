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
