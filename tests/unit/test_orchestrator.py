from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, call

import pytest

from aranet_etl.config import Settings
from aranet_etl.exceptions import ConcurrentSyncError
from aranet_etl.services import orchestrator as orchestrator_module
from aranet_etl.services.orchestrator import SyncOrchestrator


def _settings(monkeypatch) -> Settings:
    monkeypatch.setenv("ARANET_API_KEY", "fake")
    monkeypatch.setenv("LOG_DIR", "")
    return Settings.load()


def test_incremental_run_performs_periodic_late_data_reconciliation(monkeypatch) -> None:
    now = datetime(2026, 8, 13, 14, tzinfo=UTC)
    monkeypatch.setattr(orchestrator_module, "utc_now", lambda: now)
    service = MagicMock()
    monkeypatch.setattr(
        orchestrator_module,
        "TimeseriesSyncService",
        lambda *_args: service,
    )

    instance = SyncOrchestrator(_settings(monkeypatch), MagicMock(), MagicMock())
    instance.state = MagicMock()
    watermarks = {
        "measurements": now - timedelta(minutes=10),
        "telemetry": now - timedelta(minutes=10),
        "alarms": now - timedelta(minutes=10),
        "reconciliation": None,
    }
    instance.state.get_watermark.side_effect = watermarks.get
    instance._run = lambda _command, operation: operation(42)  # type: ignore[method-assign]

    result = instance.sync_incremental(refresh_catalogs=False)

    overlap_start = now - timedelta(minutes=40)
    reconciliation_start = now - timedelta(days=7)
    assert service.sync_range.call_args_list == [
        call("measurement", overlap_start, now),
        call("telemetry", overlap_start, now),
        call("measurement", reconciliation_start, now),
        call("telemetry", reconciliation_start, now),
    ]
    service.sync_alarm_history.assert_called_once_with(overlap_start, now)
    service.sync_latest.assert_called_once_with()
    service.sync_actual_alarms.assert_called_once_with()
    assert result["reconciliation_performed"] is True
    assert (
        call("reconciliation", now, metadata={"lookback_days": 7})
        in instance.state.set_watermark.call_args_list
    )


def test_incremental_run_skips_reconciliation_until_interval_is_due(monkeypatch) -> None:
    now = datetime(2026, 8, 13, 14, tzinfo=UTC)
    monkeypatch.setattr(orchestrator_module, "utc_now", lambda: now)
    service = MagicMock()
    monkeypatch.setattr(
        orchestrator_module,
        "TimeseriesSyncService",
        lambda *_args: service,
    )

    instance = SyncOrchestrator(_settings(monkeypatch), MagicMock(), MagicMock())
    instance.state = MagicMock()
    instance.state.get_watermark.side_effect = lambda endpoint: {
        "measurements": now,
        "telemetry": now,
        "alarms": now,
        "reconciliation": now - timedelta(hours=1),
    }[endpoint]
    instance._run = lambda _command, operation: operation(7)  # type: ignore[method-assign]

    result = instance.sync_incremental(refresh_catalogs=False)

    assert service.sync_range.call_count == 2
    assert result["reconciliation_performed"] is False


def test_database_advisory_lock_rejects_overlapping_run(monkeypatch) -> None:
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.return_value = (False,)
    instance = SyncOrchestrator(_settings(monkeypatch), MagicMock(), connection)

    with pytest.raises(ConcurrentSyncError, match="already running"), instance._exclusive_lock():
        raise AssertionError("lock body must not execute")
