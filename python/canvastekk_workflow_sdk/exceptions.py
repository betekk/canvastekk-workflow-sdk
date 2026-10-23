"""
Structured Exception Hierarchy

Provides typed exceptions that the SDK and node authors can raise.
Each exception maps to a specific HTTP status code for consistent error handling.
"""

from __future__ import annotations

from typing import Any

ERROR_CATEGORIES: tuple[str, ...] = (
    "transport",
    "validation",
    "domain",
    "timeout",
    "lifecycle",
)

ERROR_ENVELOPE_KEYS: tuple[str, ...] = ("type", "message", "code")

IO_SUBCODE_DOWNLOAD_FAILED = "IO_DOWNLOAD_FAILED"
IO_SUBCODE_URL_POLICY_BLOCKED = "IO_URL_POLICY_BLOCKED"
IO_SUBCODE_SIZE_EXCEEDED = "IO_SIZE_EXCEEDED"


class NodeExecutionError(Exception):
    """Base exception for all node execution errors.

    Unclassified errors (a bare ``NodeExecutionError`` or an uncaught
    exception the app wraps) are ``domain`` — the node's own logic failed,
    not the transport, validation, timeout, or lifecycle machinery.
    """

    category: str = "domain"

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "EXECUTION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the exception with message and metadata.

        Args:
            message: Human-readable error message.
            error_code: Structured error code.
            details: Additional error context.
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        """Serialize the error to a JSON-friendly dict.

        Returns:
            Dict with ``error_code``, ``category``, ``message``, and
            ``details`` keys.
        """
        return {
            "error_code": self.error_code,
            "category": self.category,
            "message": self.message,
            "details": self.details,
        }


def error_envelope(error: NodeExecutionError) -> dict[str, str]:
    """Serialize an error to the S.3 envelope shape ``{type, message, code}``.

    Args:
        error: The exception to envelope.

    Returns:
        Dict with the ``ERROR_ENVELOPE_KEYS`` triple.
    """
    return {
        "type": error.category,
        "message": error.message,
        "code": error.error_code,
    }


class NodeTimeoutError(NodeExecutionError):
    """Raised when node execution exceeds the configured timeout."""
    category = "timeout"

    def __init__(
        self,
        timeout_seconds: int,
        *,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the timeout exception.

        Args:
            timeout_seconds: Timeout value in seconds.
            details: Additional error context.
        """
        super().__init__(
            f"Node execution timed out after {timeout_seconds}s",
            error_code="TIMEOUT",
            details=details or {"timeout_seconds": timeout_seconds},
        )
        self.timeout_seconds = timeout_seconds


class NodeValidationError(NodeExecutionError):
    """Raised when input validation against JSON Schema fails."""
    category = "validation"

    def __init__(
        self,
        message: str,
        *,
        errors: list[dict[str, Any]] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the validation exception.

        Args:
            message: Human-readable error message.
            errors: List of validation error details.
            details: Additional error context.
        """
        super().__init__(
            message,
            error_code="VALIDATION_ERROR",
            details=details or {},
        )
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        """Serialize with an additional ``errors`` list.

        Returns:
            Dict with ``error_code``, ``message``, ``details``, and ``errors``.
        """
        result = super().to_dict()
        result["errors"] = self.errors
        return result


class NodeIOError(NodeExecutionError):
    """Raised when file I/O operations fail."""
    category = "transport"

    def __init__(
        self,
        message: str,
        *,
        path: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the I/O exception.

        Args:
            message: Human-readable error message.
            path: File path that caused the error.
            details: Additional error context.
        """
        merged_details: dict[str, Any] = details or {}
        if path:
            merged_details["path"] = path
        super().__init__(
            message,
            error_code="IO_ERROR",
            details=merged_details,
        )
        self.path = path


class NodeConfigurationError(NodeExecutionError):
    """Raised when node configuration is invalid."""
    category = "lifecycle"

    def __init__(
        self,
        message: str,
        *,
        error_code: str = "CONFIGURATION_ERROR",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the configuration exception.

        Args:
            message: Human-readable error message.
            error_code: Structured error code (``NODE_SUNSET`` for
                post-sunset refusals, S.2).
            details: Additional error context.
        """
        super().__init__(
            message,
            error_code=error_code,
            details=details or {},
        )


class WorkflowExecutionError(NodeExecutionError):
    """Raised when local workflow execution fails."""
    category = "domain"

    def __init__(
        self,
        message: str,
        *,
        node_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the workflow execution exception.

        Args:
            message: Human-readable error message.
            node_id: Node ID that caused the error.
            details: Additional error context.
        """
        merged_details: dict[str, Any] = details or {}
        if node_id:
            merged_details["node_id"] = node_id
        super().__init__(
            message,
            error_code="WORKFLOW_EXECUTION_ERROR",
            details=merged_details,
        )
        self.node_id = node_id


class WorkflowValidationError(NodeExecutionError):
    """Raised when workflow spec validation fails."""
    category = "validation"

    def __init__(
        self,
        message: str,
        *,
        errors: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the workflow validation exception.

        Args:
            message: Human-readable error message.
            errors: List of validation error strings.
            details: Additional error context.
        """
        super().__init__(
            message,
            error_code="WORKFLOW_VALIDATION_ERROR",
            details=details or {},
        )
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        """Serialize with an additional ``errors`` list.

        Returns:
            Dict with ``error_code``, ``message``, ``details``, and ``errors``.
        """
        result = super().to_dict()
        result["errors"] = self.errors
        return result


class NodeOutputValidationError(NodeExecutionError):
    """Raised when output validation against JSON Schema fails."""
    category = "validation"

    def __init__(
        self,
        message: str,
        *,
        errors: list[dict[str, Any]] | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the output validation exception.

        Args:
            message: Human-readable error message.
            errors: List of validation error details.
            details: Additional error context.
        """
        super().__init__(
            message,
            error_code="OUTPUT_VALIDATION_ERROR",
            details=details or {},
        )
        self.errors = errors or []

    def to_dict(self) -> dict[str, Any]:
        """Serialize with an additional ``errors`` list.

        Returns:
            Dict with ``error_code``, ``message``, ``details``, and ``errors``.
        """
        result = super().to_dict()
        result["errors"] = self.errors
        return result


ERROR_CODE_TO_HTTP_STATUS: dict[str, int] = {
    "EXECUTION_ERROR": 500,
    "TIMEOUT": 408,
    "VALIDATION_ERROR": 422,
    "OUTPUT_VALIDATION_ERROR": 422,
    "IO_ERROR": 500,
    "CONFIGURATION_ERROR": 500,
    "WORKFLOW_EXECUTION_ERROR": 500,
    "WORKFLOW_VALIDATION_ERROR": 422,
}


def get_http_status_for_error(exc: NodeExecutionError) -> int:
    """Map a :class:`NodeExecutionError` to the appropriate HTTP status code.

    Args:
        exc: A structured node execution error.

    Returns:
        Integer HTTP status code (defaults to 500 for unknown error codes).
    """
    return ERROR_CODE_TO_HTTP_STATUS.get(exc.error_code, 500)
