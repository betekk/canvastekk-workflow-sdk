"""DA-3359: support-horizon gate — frozen-clock coverage, both paths."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from canvastekk_workflow_sdk import _horizon
from canvastekk_workflow_sdk._horizon import (
    BREAK_GLASS_ENV,
    SUPPORT_HORIZON_DAYS,
    HorizonOutcome,
    SupportHorizonError,
    check_support_horizon,
    enforce_support_horizon,
    warn_support_horizon,
)

RELEASE = date.fromisoformat(_horizon.RELEASE_DATE)


def _freeze(monkeypatch: pytest.MonkeyPatch, day: date) -> None:
    monkeypatch.setattr(_horizon, "_today", lambda: day)


def test_normal_window_is_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, RELEASE + timedelta(days=30))
    assert check_support_horizon() is HorizonOutcome.OK
    # importing/Warning path stays silent in the OK window
    warn_support_horizon()  # does not raise


def test_warn_window_warns(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    import logging

    _freeze(monkeypatch, RELEASE + timedelta(days=SUPPORT_HORIZON_DAYS - 5))
    with caplog.at_level(logging.WARNING, logger="canvastekk_workflow_sdk.support"):
        assert warn_support_horizon() is HorizonOutcome.WARN
    assert any("end-of-support" in r.message for r in caplog.records)


def test_expired_warns_but_import_path_never_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, RELEASE + timedelta(days=SUPPORT_HORIZON_DAYS + 1))
    warn_support_horizon()  # log-only — the engine imports must never raise


def test_expired_raises_at_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, RELEASE + timedelta(days=SUPPORT_HORIZON_DAYS + 1))
    with pytest.raises(SupportHorizonError, match="support horizon"):
        enforce_support_horizon()


def test_expired_warn_window_does_not_raise_at_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    _freeze(monkeypatch, RELEASE + timedelta(days=SUPPORT_HORIZON_DAYS - 5))
    enforce_support_horizon()  # warn window is not an expiry


def test_break_glass_downgrades_to_critical(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    import logging

    _freeze(monkeypatch, RELEASE + timedelta(days=SUPPORT_HORIZON_DAYS + 1))
    monkeypatch.setenv(BREAK_GLASS_ENV, "1")
    with caplog.at_level(logging.CRITICAL, logger="canvastekk_workflow_sdk.support"):
        enforce_support_horizon()  # no raise
    assert any(r.levelno == logging.CRITICAL for r in caplog.records)
