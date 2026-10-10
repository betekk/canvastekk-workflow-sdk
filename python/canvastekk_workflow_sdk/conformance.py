"""Node conformance verification — probes a deployed node's HTTP contract.

Framework-free (httpx + pydantic only): the verifier must be able to check
nodes that do NOT use the SDK's server, which is its whole purpose (#104).

Contract probed (mirrors what the engine calls):
  GET  /health    → 200
  GET  /manifest  → 200 + body validates as WorkflowNodeManifest
  POST /execute   → malformed payload must be rejected with a 4xx status
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from canvastekk_workflow_sdk.definition import WorkflowNodeManifest

__all__ = ["RouteCheck", "VerifyReport", "verify_node"]


@dataclass(frozen=True)
class RouteCheck:
    """Outcome of one probed route."""

    route: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class VerifyReport:
    """Aggregated conformance results for one node deployment."""

    base_url: str
    checks: list[RouteCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """True when every probed route conformed."""
        return all(c.ok for c in self.checks)

    def summary(self) -> str:
        """One line per check, PASS/FAIL prefixed."""
        lines = [f"{'PASS' if c.ok else 'FAIL'}  {c.route}  — {c.detail}" for c in self.checks]
        verdict = "CONFORMING" if self.ok else "NON-CONFORMING"
        return "\n".join([f"{self.base_url}: {verdict}"] + lines)


def verify_node(
    base_url: str,
    *,
    timeout: float = 10.0,
    api_key: str | None = None,
) -> VerifyReport:
    """Probe a deployed node's HTTP contract and report conformance.

    Args:
        base_url: Node base URL (e.g. ``http://localhost:8001``). Trailing
            slashes are stripped.
        timeout: Per-request timeout in seconds.
        api_key: Optional API key sent as ``X-API-Key`` on every probe.

    Returns:
        A :class:`VerifyReport` with one :class:`RouteCheck` per probed
        route; ``report.ok`` is True only when all routes conformed.
    """
    base = base_url.rstrip("/")
    headers = {"X-API-Key": api_key} if api_key else {}
    checks: list[RouteCheck] = []

    with httpx.Client(base_url=base, timeout=timeout, headers=headers) as client:
        # GET /health — must answer 200.
        try:
            r = client.get("/health")
            ok = r.status_code == 200
            checks.append(RouteCheck("GET /health", ok, f"status {r.status_code}"))
        except httpx.HTTPError as e:
            checks.append(RouteCheck("GET /health", False, f"unreachable: {e}"))

        # GET /manifest — must answer 200 with a valid manifest body.
        try:
            r = client.get("/manifest")
            if r.status_code != 200:
                checks.append(
                    RouteCheck("GET /manifest", False, f"status {r.status_code}")
                )
            else:
                try:
                    WorkflowNodeManifest.model_validate(r.json())
                    checks.append(
                        RouteCheck("GET /manifest", True, "valid WorkflowNodeManifest")
                    )
                except Exception as e:  # pydantic ValidationError or bad JSON
                    checks.append(
                        RouteCheck("GET /manifest", False, f"invalid manifest: {e}")
                    )
        except httpx.HTTPError as e:
            checks.append(RouteCheck("GET /manifest", False, f"unreachable: {e}"))

        # POST /execute — a malformed payload must be rejected (4xx).
        try:
            r = client.post("/execute", json={"unexpected": "probe"})
            ok = 400 <= r.status_code < 500
            detail = f"status {r.status_code} for malformed payload"
            checks.append(RouteCheck("POST /execute", ok, detail))
        except httpx.HTTPError as e:
            checks.append(RouteCheck("POST /execute", False, f"unreachable: {e}"))

    return VerifyReport(base_url=base, checks=checks)
