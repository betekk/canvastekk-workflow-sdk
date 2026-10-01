"""Support-horizon gate (DA-3359): warn at import, raise at node entrypoints.

The sunset is ``RELEASE_DATE + SUPPORT_HORIZON_DAYS``. The package-import
path LOGS ONLY — the engine lazy-imports this package during seeding and
discovery, and an import-time raise would silently disable both. The hard
raise lives at the node entrypoints (``create_node_app``, ``BaseNode.run``).

``CANVASTEKK_SDK_ALLOW_UNSUPPORTED=1`` is the break-glass: past-sunset
executions downgrade the raise to a CRITICAL log.
"""

from __future__ import annotations

import logging
import os
from datetime import date, timedelta
from enum import StrEnum
from functools import lru_cache

from canvastekk_workflow_sdk._version import RELEASE_DATE

SUPPORT_HORIZON_DAYS = 180
WARN_WINDOW_DAYS = 30

BREAK_GLASS_ENV = "CANVASTEKK_SDK_ALLOW_UNSUPPORTED"

_logger = logging.getLogger("canvastekk_workflow_sdk.support")


def _logger_or_none():
    return _logger


class HorizonOutcome(StrEnum):
    OK = "ok"
    WARN = "warn"
    EXPIRED = "expired"


def _today() -> date:
    """Clock seam — tests monkeypatch this for frozen-clock coverage."""
    return date.today()


@lru_cache(maxsize=1)
def _sunset() -> date:
    return date.fromisoformat(RELEASE_DATE) + timedelta(days=SUPPORT_HORIZON_DAYS)


def check_support_horizon(today: date | None = None) -> HorizonOutcome:
    """Classify today against the support horizon (no side effects)."""
    day = today or _today()
    if day >= _sunset():
        return HorizonOutcome.EXPIRED
    if day >= _sunset() - timedelta(days=WARN_WINDOW_DAYS):
        return HorizonOutcome.WARN
    return HorizonOutcome.OK


def warn_support_horizon(today: date | None = None) -> HorizonOutcome:
    """Import-time path: LOG ONLY (never raises)."""
    outcome = check_support_horizon(today)
    log = _logger_or_none()
    if outcome is HorizonOutcome.EXPIRED:
        log.warning(
            "support horizon expired: this SDK (%s) passed end-of-support on %s; "
            "node entrypoints will raise unless %s=1",
            RELEASE_DATE,
            _sunset().isoformat(),
            BREAK_GLASS_ENV,
        )
    elif outcome is HorizonOutcome.WARN:
        log.warning(
            "support horizon warning: this SDK (%s) reaches end-of-support on %s",
            RELEASE_DATE,
            _sunset().isoformat(),
        )
    return outcome


def enforce_support_horizon(today: date | None = None) -> None:
    """Entrypoint path: raise once the horizon has passed (break-glass honored)."""
    outcome = check_support_horizon(today)
    if outcome is not HorizonOutcome.EXPIRED:
        return
    log = _logger_or_none()
    if os.environ.get(BREAK_GLASS_ENV) == "1":
        log.critical(
            "support horizon expired for SDK %s (sunset %s); continuing via "
            "%s=1 — upgrade the SDK",
            RELEASE_DATE,
            _sunset().isoformat(),
            BREAK_GLASS_ENV,
        )
        return
    raise SupportHorizonError(
        f"canvastekk-workflow-sdk {RELEASE_DATE} passed its support horizon "
        f"on {_sunset().isoformat()}; upgrade the SDK or set "
        f"{BREAK_GLASS_ENV}=1 to continue unsupported"
    )


class SupportHorizonError(RuntimeError):
    """Raised at node entrypoints once the SDK's support horizon has passed."""
