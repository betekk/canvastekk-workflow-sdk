"""
Node Executor Strategy

Defines how a node is executed: in-process (BaseNode.execute) or HTTP (POST /execute).
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import httpx

if TYPE_CHECKING:
    from canvastekk_workflow_sdk.base import BaseNode
    from canvastekk_workflow_sdk.context import ExecutionContext


class NodeExecutor(ABC):
    """Abstract strategy for executing a workflow node."""

    @abstractmethod
    async def execute(
        self,
        slug: str,
        inputs: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Execute a node and return its outputs."""

    @abstractmethod
    def has(self, slug: str) -> bool:
        """Check if this executor can handle the given slug."""


class InProcessExecutor(NodeExecutor):
    """Execute nodes by calling BaseNode.execute() directly via asyncio.to_thread.

    Example::

        executor = InProcessExecutor()
        executor.register("segmentation-v1.0.0", MySegmentNode())
        runner = WorkflowRunner(executor)
    """

    def __init__(self) -> None:
        """Initialize in-process executor with empty node registry."""
        self._registry: dict[str, BaseNode] = {}

    def register(self, slug: str, node: BaseNode) -> InProcessExecutor:
        """Register a BaseNode instance for a slug.

        Args:
            slug: Node type slug (e.g. ``"segmentation-v1.0.0"``).
            node: BaseNode instance.

        Returns:
            self for chaining.
        """
        self._registry[slug] = node
        return self

    async def execute(
        self,
        slug: str,
        inputs: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Execute a node by calling BaseNode.execute() in a thread.

        Args:
            slug: Node type slug.
            inputs: Input values for the node.
            context: Execution context.

        Returns:
            Output values from the node.
        """
        node = self._registry[slug]
        return await asyncio.to_thread(node.execute, inputs, context)

    def has(self, slug: str) -> bool:
        """Check if a slug is registered.

        Args:
            slug: Node type slug.

        Returns:
            True if slug is in the registry.
        """
        return slug in self._registry


class HttpExecutor(NodeExecutor):
    """Execute nodes by POSTing to their ``/execute`` endpoint.

    Posts a ``NodeExecutionRequest``-compatible payload:
    ``{"run_id": ..., "node_id": ..., "inputs": ...}``

    Example::

        executor = HttpExecutor()
        executor.register_url("segmentation-v1.0.0", "http://localhost:8001")
        runner = WorkflowRunner(executor)
    """

    def __init__(self, *, timeout: float = 300.0, retries: int = 2) -> None:
        """Initialize HTTP executor.

        Args:
            timeout: Request timeout in seconds.
            retries: Retry attempts for transient failures (connection
                errors, 502/503/504) with exponential backoff.
        """
        self._urls: dict[str, str] = {}
        self._timeout = timeout
        self._retries = retries
        self._client: httpx.AsyncClient | None = None

    def register_url(self, slug: str, url: str) -> HttpExecutor:
        """Register a base URL for a slug.

        Args:
            slug: Node type slug (e.g. ``"segmentation-v1.0.0"``).
            url: Base URL where the node is hosted (e.g. ``"http://localhost:8001"``).

        Returns:
            self for chaining.
        """
        self._urls[slug] = url.rstrip("/")
        return self

    async def execute(
        self,
        slug: str,
        inputs: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
        """Execute a node by POSTing to its HTTP endpoint.

        Args:
            slug: Node type slug.
            inputs: Input values for the node.
            context: Execution context.

        Returns:
            Output values from the node.

        Raises:
            RuntimeError: If the node returns failure status.
        """
        url = self._urls[slug]
        payload = {
            "run_id": context.run_id,
            "node_id": context.node_id,
            "inputs": inputs,
        }
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        client = self._client

        response: httpx.Response | None = None
        for attempt in range(self._retries + 1):
            try:
                response = await client.post(f"{url}/execute", json=payload)
                response.raise_for_status()
                break
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                transient = isinstance(exc, httpx.TransportError) or (exc.response.status_code in (502, 503, 504))
                if not transient or attempt == self._retries:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))

        assert response is not None
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError(f"Node '{slug}' returned malformed response (not an object)")
        if data.get("status") == "pass":
            outputs = data.get("outputs", {})
            if not isinstance(outputs, dict):
                raise RuntimeError(f"Node '{slug}' returned malformed outputs (not an object)")
            return outputs
        raise RuntimeError(f"Node '{slug}' returned failure: {data.get('error', 'unknown')}")

    def has(self, slug: str) -> bool:
        """Check if a slug is registered.

        Args:
            slug: Node type slug.

        Returns:
            True if slug is in the registry.
        """
        return slug in self._urls
