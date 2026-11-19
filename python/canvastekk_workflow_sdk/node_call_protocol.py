"""Node protocol version negotiation (N1, betekk/canvastekk-workflow-engine#1300).

Protocol 2 renames the node call outcomes: ``pass`` -> ``SUCCEEDED``,
``fail`` -> ``FAILED``, ``pending`` -> ``ACCEPTED``. The engine advertises the
protocol it reads with the ``X-Node-Protocol`` request header; a node answers
in the new words only when that header says 2 or more, so a node on this SDK
keeps answering ``pass`` / ``fail`` to an engine that has not moved yet.

Node code never sees the new words: it keeps building ``pass`` / ``fail``
responses and ``/execute`` translates on the way out.
"""

from __future__ import annotations

NODE_CALL_PROTOCOL_HEADER = "x-node-protocol"
"""Request header carrying the engine's node protocol version."""

NODE_CALL_PROTOCOL_VERSION = 2
"""Highest node protocol this SDK speaks."""

_TO_PROTOCOL_2 = {"pass": "SUCCEEDED", "fail": "FAILED", "pending": "ACCEPTED"}
_FROM_PROTOCOL_2 = {new.casefold(): old for old, new in _TO_PROTOCOL_2.items()}

NODE_CALL_PROTOCOL_2_OUTCOMES: dict[str, str] = {new: old for old, new in _TO_PROTOCOL_2.items()}
"""Exact protocol-2 words mapped to their protocol-1 equivalents (strict readers)."""


def requested_node_call_protocol(header_value: str | None) -> int:
    """The protocol a request asks for; 1 when the header is absent or malformed.

    Args:
        header_value: Raw ``X-Node-Protocol`` header value.

    Returns:
        The requested protocol version, capped at :data:`NODE_CALL_PROTOCOL_VERSION`.
    """
    if header_value is None:
        return 1
    try:
        version = int(header_value.strip())
    except ValueError:
        return 1
    return max(1, min(version, NODE_CALL_PROTOCOL_VERSION))


def node_call_outcome_for_protocol(status: str, protocol: int) -> str:
    """Wire outcome for ``status`` under ``protocol``.

    Args:
        status: The outcome node code produced (``pass`` / ``fail`` / ``pending``).
        protocol: The negotiated protocol version.

    Returns:
        The protocol-2 word when ``protocol >= 2``, else ``status`` unchanged.
    """
    if protocol >= 2:
        return _TO_PROTOCOL_2.get(status, status)
    return status


def read_node_call_outcome(value: object) -> str | None:
    """Read an outcome in either protocol as ``pass`` / ``fail`` / ``pending``.

    Args:
        value: Wire outcome from a node response or callback.

    Returns:
        The protocol-1 word, or None when absent or unknown.
    """
    if not isinstance(value, str) or not value:
        return None
    folded = value.strip().casefold()
    if folded in _TO_PROTOCOL_2:
        return folded
    return _FROM_PROTOCOL_2.get(folded)
