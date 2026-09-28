"""
Execution Context

Provides context to the node's execute() method including
run information, output directory, and logging.
"""

from __future__ import annotations

import logging
import os
import threading
from contextvars import ContextVar
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from canvastekk_workflow_sdk.logging import get_node_logger

if TYPE_CHECKING:
    from canvastekk_workflow_sdk.request import NodeExecutionRequest

logger = logging.getLogger(__name__)

# Max characters of a progress-ping message (engine payload cap, #495).
PROGRESS_MESSAGE_MAX_CHARS = 1000

# Per-ping timeout — a slow or hung engine must not hold threads (DA-3230).
PROGRESS_PING_TIMEOUT_S = 5.0

# Ambient per-run execution context (DA-3230).
#
# BaseNode.run() sets the run's ExecutionContext for the duration of
# execution, so BaseNode.report_progress() can resolve the current run
# without threading the context through node signatures. contextvars keep
# concurrent runs of one shared node instance isolated (asyncio.to_thread
# runs in a copy of the current context) — instance-held state would
# cross-run-race. Mirror of the TypeScript leg's executionContextStorage.
execution_context_var: ContextVar[ExecutionContext | None] = ContextVar(
    "canvastekk_execution_context", default=None
)


def _deliver_progress_ping(url: str, payload: dict[str, Any]) -> None:
    """POST a progress ping to the engine (runs on a daemon thread).

    Best-effort: any failure is swallowed and logged at warning level —
    progress reporting must never affect the node outcome (DA-2887
    philosophy). Module-level so tests can monkeypatch the delivery seam
    without real threads.

    Args:
        url: Full progress-route URL (``{callback_url}/progress``).
        payload: JSON body — ``{execution_id, percent[, message]}``.
    """
    try:
        httpx.post(url, json=payload, timeout=PROGRESS_PING_TIMEOUT_S)
    except Exception as exc:  # noqa: BLE001 — best-effort by contract
        logger.warning("Progress ping failed (best-effort, ignored): %s", exc)


class ExecutionContext:
    """
    Context provided to node execute() method.

    Provides access to:
    - Run and node identifiers
    - Output directory for temporary files
    - Downloads directory for auto-downloaded file inputs
    - Metadata dict for download tracking
    - Logger with context
    - Progress reporting (for long-running operations)
    - Cooperative cancellation (``cancel_event``) — set by the server when
      the request deadline expires; checked between download chunks.
      ``execute()`` itself cannot be interrupted.
    """

    def __init__(
        self,
        request: NodeExecutionRequest | None = None,
        output_dir: Path | None = None,
        *,
        run_id: str | None = None,
        node_id: str | None = None,
        cancel_event: threading.Event | None = None,
        execution_id: str | None = None,
    ) -> None:
        """Initialize execution context.

        Args:
            request: Node execution request (provides run_id, node_id).
            output_dir: Override output directory (defaults to temp or env var).
            run_id: Override workflow run ID.
            node_id: Override node instance ID.
            cancel_event: Cooperative cancellation event for downloads.
            execution_id: Execution ID minted by ``BaseNode.run()`` — carried
                so mid-run progress pings echo the same id the engine
                validated at dispatch time (DA-3230). ``None`` for
                locally constructed contexts (no run).
        """
        self._request = request
        resolved_run_id = run_id or (request.run_id if request else "local")
        resolved_node_id = node_id or (request.node_id if request else "unknown")

        if output_dir is not None:
            self._output_dir = output_dir
        else:
            base_dir = os.environ.get("CANVASTEKK_OUTPUT_DIR")
            if base_dir:
                self._output_dir = Path(base_dir) / resolved_run_id / resolved_node_id
            else:
                self._output_dir = Path("/tmp") / resolved_run_id / resolved_node_id
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._logger = get_node_logger(resolved_node_id)

        self._token_usage: dict[str, int] = {}
        self._metadata: dict[str, Any] = {}
        self._downloads_dir: Path | None = None
        self._cancel_event = cancel_event if cancel_event is not None else threading.Event()
        self._execution_id = execution_id

    @property
    def cancel_event(self) -> threading.Event:
        """Cooperative cancellation event — set when the request deadline expires."""
        return self._cancel_event

    @property
    def execution_id(self) -> str | None:
        """Execution ID minted by ``BaseNode.run()`` for this execution.

        Carried on the context so mid-run progress pings can echo the same
        ``execution_id`` the engine validated at dispatch time (DA-3230).
        ``None`` for locally constructed contexts (no run).
        """
        return self._execution_id

    @property
    def run_id(self) -> str:
        """Workflow run identifier."""
        if self._request is not None:
            return self._request.run_id
        return self._output_dir.parent.name

    @property
    def node_id(self) -> str:
        """Node instance ID in workflow."""
        if self._request is not None:
            return self._request.node_id
        return self._output_dir.name

    @property
    def account_id(self) -> int | None:
        """Active account ID asserted by the orchestrator (DA-2242).

        Engine-controlled routing identity (not an auth credential) — set
        exclusively from the ``X-Account-Id`` header on ``/execute``.
        ``None`` for local runs and request-less contexts.
        """
        if self._request is not None:
            return self._request.account_id
        return None

    @property
    def output_dir(self) -> Path:
        """Local temp directory for outputs."""
        return self._output_dir

    @property
    def logger(self) -> logging.Logger:
        """Pre-configured logger with context."""
        return self._logger

    def output_path(self, filename: str) -> Path:
        """
        Get path for an output file.

        Files written to output paths will be uploaded to storage
        by the SDK after execute() returns.

        Args:
            filename: Name of the output file

        Returns:
            Full path in the output directory

        Raises:
            ValueError: If the filename escapes the output directory
                (path traversal — absolute paths or ``..`` segments).
        """
        candidate = (self._output_dir / filename).resolve()
        if not candidate.is_relative_to(self._output_dir.resolve()):
            raise ValueError(
                f"Output filename '{filename}' escapes the output directory"
            )
        return candidate

    @property
    def downloads_dir(self) -> Path:
        """Directory for auto-downloaded file inputs.

        Created lazily on first access. Separate from ``output_dir``
        to keep downloaded inputs distinct from node-generated outputs.
        """
        if self._downloads_dir is None:
            self._downloads_dir = self._output_dir / "downloads"
            self._downloads_dir.mkdir(parents=True, exist_ok=True)
        return self._downloads_dir

    @property
    def metadata(self) -> dict[str, Any]:
        """Mutable metadata dict for tracking download info and other context.

        The SDK stores download metadata here (original URLs, local paths,
        file sizes). Node authors may also use this for custom metadata.
        """
        return self._metadata

    def report_progress(self, progress: float, message: str = "") -> None:
        """
        Report progress for long-running operations.

        Logs locally and, when running inside a workflow with a callback URL
        and execution ID (DA-3230), fires a best-effort progress ping to the
        engine. Local/dev contexts without a callback URL log exactly as
        before.

        Args:
            progress: Progress value from 0.0 to 1.0
            message: Optional progress message

        Note:
            The engine ping is fire-and-forget: transport failures are
            swallowed and logged, never raised into node logic.
        """
        percent = int(progress * 100)
        log_msg = f"Progress: {percent}%"
        if message:
            log_msg += f" - {message}"
        self._logger.info(log_msg)
        self._send_progress_ping(percent, message)

    def _send_progress_ping(self, percent: float = 0, message: str = "") -> None:
        """
        Fire-and-forget progress ping to the engine's progress route (DA-3230).

        POSTs ``{execution_id, percent, message}`` to
        ``{callback_url}/progress`` on a daemon thread (engine #495: the
        completion callback URL plus ``/progress``). Never raises into
        caller code — delivery failures are swallowed and logged inside
        :func:`_deliver_progress_ping`. Safe no-op when either the callback
        URL or the execution ID is missing (local dev, request-less
        contexts).

        Args:
            percent: Progress percentage; clamped to [0, 100].
            message: Optional message; truncated to ``PROGRESS_MESSAGE_MAX_CHARS``.
        """
        callback_url = self._request.callback_url if self._request is not None else None
        # Engine-issued orchestrator URL, deliberately NOT run through an
        # SSRF policy: the engine legitimately lives on private/loopback
        # addresses in-cluster.
        callback_url = callback_url.rstrip("/") if callback_url else None
        if not callback_url or not self._execution_id:
            return

        payload: dict[str, Any] = {
            "execution_id": self._execution_id,
            "percent": min(100, max(0, int(percent))),
        }
        capped = message[:PROGRESS_MESSAGE_MAX_CHARS]
        if capped:
            payload["message"] = capped

        threading.Thread(
            target=_deliver_progress_ping,
            args=(f"{callback_url}/progress", payload),
            daemon=True,
        ).start()

    def record_token_usage(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        total_tokens: int = 0,
    ) -> None:
        """
        Record actual token usage for this execution.

        Called by nodes that interact with LLM APIs to report
        real token counts instead of the static token_cost.

        Args:
            prompt_tokens: Number of tokens in the prompt
            completion_tokens: Number of tokens in the completion
            total_tokens: Total tokens used
        """
        self._token_usage = {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        }
        self._logger.info(
            "Token usage: prompt=%d, completion=%d, total=%d",
            prompt_tokens,
            completion_tokens,
            total_tokens,
        )

    @property
    def token_usage(self) -> dict[str, int]:
        """Token usage recorded during execution, if any."""
        return dict(self._token_usage)
