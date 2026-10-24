"""Node conformance verification — probes a deployed node's HTTP contract.

Framework-free (httpx + pydantic only): the verifier must be able to check
nodes that do NOT use the SDK's server, which is its whole purpose (#104).

The probe set is DERIVED from the node's own served manifest (#113): the
verifier fetches GET /manifest, validates the body, and probes every route
the manifest's effective contract declares (author-declared routes, or the
SDK-served default — D8/#110). No route list is hardcoded here; a broken or
missing manifest fails the verification under its own route name.

Probe expectations by family (the contract route vocabulary is closed, D8):
  GET  /health, /live, /ready, /metrics → must answer: 404 or 5xx FAIL
  GET  /manifest                        → 200 + body validates as WorkflowNodeManifest
  POST /execute                         → malformed payload must be rejected (4xx)
  POST other (e.g. /hook)               → must answer: 404 or 5xx FAIL

An auth-guarded route (401/403) counts as present: mounted and routing, just
protected. The X-API-Key header is sent on every probe when provided.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import httpx

from canvastekk_workflow_sdk.definition import WorkflowNodeManifest

__all__ = ["RouteCheck", "VerifyReport", "verify_node"]

_POST_ROUTES = frozenset({"/execute", "/hook"})


def _presence_ok(status: int) -> bool:
    """Mounted-and-routing: not 404 (absent) and not 5xx (broken)."""
    return status < 500 and status != 404


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
    dry_run: bool = False,
) -> VerifyReport:
    """Probe a deployed node's HTTP contract and report conformance.

    Args:
        base_url: Node base URL (e.g. ``http://localhost:8001``). Trailing
            slashes are stripped.
        timeout: Per-request timeout in seconds.
        api_key: Optional API key sent as ``X-API-Key`` on every probe.
        dry_run: Opt in to the positive ``POST /execute`` probe. It fires
            only when the manifest ALSO declares
            ``contract.capabilities.dry_run``; otherwise it is recorded as
            skipped (never a failure). Registration-time verification keeps
            the default (``False``) so unattended verifies stay passive
            against production nodes.

    Returns:
        A :class:`VerifyReport` with one :class:`RouteCheck` per probed
        route; ``report.ok`` is True only when all routes conformed.
    """
    base = base_url.rstrip("/")
    headers = {"X-API-Key": api_key} if api_key else {}
    checks: list[RouteCheck] = []

    with httpx.Client(base_url=base, timeout=timeout, headers=headers) as client:
        manifest: WorkflowNodeManifest | None = None
        try:
            r = client.get("/manifest")
            if r.status_code != 200:
                checks.append(RouteCheck("GET /manifest", False, f"status {r.status_code}"))
            else:
                try:
                    manifest = WorkflowNodeManifest.model_validate(r.json())
                    checks.append(RouteCheck("GET /manifest", True, "valid WorkflowNodeManifest"))
                except Exception as e:
                    checks.append(RouteCheck("GET /manifest", False, f"invalid manifest: {e}"))
        except httpx.HTTPError as e:
            checks.append(RouteCheck("GET /manifest", False, f"unreachable: {e}"))

        if manifest is None:
            return VerifyReport(base_url=base, checks=checks)

        for route in manifest.effective_contract.routes:
            if route == "/manifest":
                continue

            if route == "/execute":
                try:
                    r = client.post("/execute", json={"unexpected": "probe"})
                    ok = 400 <= r.status_code < 500
                    detail = f"status {r.status_code} for malformed payload"
                    checks.append(RouteCheck("POST /execute", ok, detail))
                except httpx.HTTPError as e:
                    checks.append(RouteCheck("POST /execute", False, f"unreachable: {e}"))

                name = "POST /execute (dry-run)"
                capability = manifest.effective_contract.capabilities.dry_run
                if not dry_run or not capability:
                    why = "capability not declared" if not capability else "--dry-run not passed"
                    checks.append(RouteCheck(name, True, f"skipped: {why}"))
                    continue
                payload = {"dry_run": True, "inputs": _seed_inputs(manifest)}
                try:
                    r = client.post("/execute", json=payload)
                    ok = 200 <= r.status_code < 300
                    checks.append(RouteCheck(name, ok, f"status {r.status_code} for dry-run payload"))
                except httpx.HTTPError as e:
                    checks.append(RouteCheck(name, False, f"unreachable: {e}"))
                continue

            method = "POST" if route in _POST_ROUTES else "GET"
            try:
                if method == "POST":
                    r = client.post(route, json={})
                else:
                    r = client.get(route)
                ok = _presence_ok(r.status_code)
                checks.append(RouteCheck(f"{method} {route}", ok, f"status {r.status_code}"))
            except httpx.HTTPError as e:
                checks.append(RouteCheck(f"{method} {route}", False, f"unreachable: {e}"))

    return VerifyReport(base_url=base, checks=checks)


def _seed_inputs(manifest: WorkflowNodeManifest) -> dict:
    """Type-seeded dummy values for the manifest's required input fields.

    The positive dry-run probe needs a payload that passes input validation;
    cross-field or semantic validation that rejects dummies surfaces as a
    documented FAIL with the node's own 4xx detail.
    """
    schema = manifest.input_schema if isinstance(manifest.input_schema, dict) else {}
    properties = schema.get("properties", {})
    required = schema.get("required", properties.keys())
    seeds: dict = {"string": "", "number": 0, "integer": 0, "boolean": False, "array": [], "object": {}}
    return {name: seeds.get((properties.get(name) or {}).get("type", "object"), "") for name in required}
