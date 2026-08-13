from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

from psycopg import Connection

from aranet_etl.api.client import AranetClient
from aranet_etl.config import Settings
from aranet_etl.database.sync_repository import SyncRepository
from aranet_etl.exceptions import ConcurrentSyncError
from aranet_etl.services.catalog_sync import CatalogSyncService
from aranet_etl.services.timeseries_sync import TimeseriesSyncService
from aranet_etl.utils import time_windows, utc_now

LOGGER = logging.getLogger(__name__)
ADVISORY_LOCK_NAME = "api_aranet_global_sync"


class SyncOrchestrator:
    def __init__(self, settings: Settings, client: AranetClient, connection: Connection) -> None:
        self.settings = settings
        self.client = client
        self.connection = connection
        self.connection.autocommit = True
        self.state = SyncRepository(connection)

    @contextmanager
    def _exclusive_lock(self) -> Iterator[None]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_try_advisory_lock(hashtext(%s))",
                (ADVISORY_LOCK_NAME,),
            )
            acquired = bool(cursor.fetchone()[0])
        if not acquired:
            raise ConcurrentSyncError("Another Aranet synchronization is already running")
        try:
            yield
        finally:
            with self.connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_unlock(hashtext(%s))",
                    (ADVISORY_LOCK_NAME,),
                )

    def _run(self, command: str, operation: Any) -> dict[str, Any]:
        with self._exclusive_lock():
            run_id = self.state.start_run(command)
            LOGGER.info("Starting synchronization command=%s run_id=%s", command, run_id)
            try:
                details = operation(run_id) or {}
                self.state.finish_run(run_id, details=details)
                LOGGER.info("Synchronization succeeded command=%s run_id=%s", command, run_id)
                return {"run_id": run_id, **details}
            except Exception as exc:
                self.state.fail_run(run_id, str(exc))
                LOGGER.exception("Synchronization failed command=%s run_id=%s", command, run_id)
                raise

    def sync_catalogs(self) -> dict[str, Any]:
        def operation(run_id: int) -> dict[str, Any]:
            result = CatalogSyncService(self.client, self.connection).sync()
            self.state.add_progress(run_id, pages=1, received=result.rows, inserted=result.rows)
            now = utc_now()
            self.state.set_watermark("catalogs", now)
            return {
                "catalog_rows": result.rows,
                "attachment_scan_complete": result.attachment_scan_complete,
            }

        return self._run("sync-catalogs", operation)

    def _catalogs_are_stale(self, now: datetime) -> bool:
        watermark = self.state.get_watermark("catalogs")
        if watermark is None:
            return True
        return watermark < now - timedelta(hours=self.settings.sync.catalog_refresh_hours)

    def backfill(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        refresh_catalogs: bool = True,
    ) -> dict[str, Any]:
        if refresh_catalogs:
            self.sync_catalogs()

        def operation(run_id: int) -> dict[str, Any]:
            finish = (end or utc_now()).astimezone(UTC)
            inferred = self.state.infer_backfill_start()
            begin = start or self.settings.sync.backfill_from or inferred
            if begin is None:
                raise ValueError(
                    "Backfill start could not be inferred. Set ARANET_BACKFILL_FROM explicitly."
                )
            begin = begin.astimezone(UTC)
            if begin >= finish:
                raise ValueError("Backfill start must be earlier than its end")

            service = TimeseriesSyncService(self.settings, self.client, self.connection, run_id)
            windows = 0
            for window_start, window_end in time_windows(
                begin, finish, self.settings.sync.backfill_window_days
            ):
                service.sync_range("measurement", window_start, window_end)
                service.sync_range("telemetry", window_start, window_end)
                service.sync_alarm_history(window_start, window_end)
                windows += 1
            service.sync_latest()
            service.sync_actual_alarms()
            self.state.set_watermark("measurements", finish, metadata={"mode": "backfill"})
            self.state.set_watermark("telemetry", finish, metadata={"mode": "backfill"})
            self.state.set_watermark("alarms", finish, metadata={"mode": "backfill"})
            return {
                "backfill_from": begin.isoformat(),
                "backfill_to": finish.isoformat(),
                "windows": windows,
            }

        return self._run("backfill", operation)

    def sync_incremental(self, *, refresh_catalogs: bool | None = None) -> dict[str, Any]:
        now = utc_now()
        should_refresh = (
            self._catalogs_are_stale(now) if refresh_catalogs is None else refresh_catalogs
        )
        if should_refresh:
            self.sync_catalogs()

        def operation(run_id: int) -> dict[str, Any]:
            service = TimeseriesSyncService(self.settings, self.client, self.connection, run_id)
            overlap = timedelta(minutes=self.settings.sync.incremental_overlap_minutes)
            fallback = now - timedelta(hours=self.settings.sync.initial_lookback_hours)
            starts = {
                endpoint: (self.state.get_watermark(endpoint) or fallback) - overlap
                for endpoint in ("measurements", "telemetry", "alarms")
            }
            service.sync_range("measurement", starts["measurements"], now)
            service.sync_range("telemetry", starts["telemetry"], now)
            service.sync_alarm_history(starts["alarms"], now)
            service.sync_latest()
            service.sync_actual_alarms()
            reconciliation_watermark = self.state.get_watermark("reconciliation")
            reconciliation_due = reconciliation_watermark is None or reconciliation_watermark < (
                now - timedelta(hours=self.settings.sync.reconciliation_interval_hours)
            )
            if reconciliation_due:
                reconciliation_start = now - timedelta(
                    days=self.settings.sync.reconciliation_lookback_days
                )
                service.sync_range("measurement", reconciliation_start, now)
                service.sync_range("telemetry", reconciliation_start, now)
                self.state.set_watermark(
                    "reconciliation",
                    now,
                    metadata={"lookback_days": self.settings.sync.reconciliation_lookback_days},
                )
            for endpoint in starts:
                self.state.set_watermark(endpoint, now, metadata={"mode": "incremental"})
            return {
                "incremental_to": now.isoformat(),
                "catalogs_refreshed": should_refresh,
                "overlap_minutes": self.settings.sync.incremental_overlap_minutes,
                "reconciliation_performed": reconciliation_due,
            }

        return self._run("sync-incremental", operation)

    def reconcile_gaps(self, *, limit: int = 10) -> dict[str, Any]:
        def operation(run_id: int) -> dict[str, Any]:
            gaps = self.state.pending_gaps(limit)
            service = TimeseriesSyncService(self.settings, self.client, self.connection, run_id)
            resolved = 0
            failed = 0
            for gap in gaps:
                self.state.mark_gap_processing(gap["id"])
                kind = "measurement" if "/measurements/" in gap["endpoint"] else "telemetry"
                scope = gap["scope_key"]
                sensor_ids = None
                if scope.startswith("sensor_batch:"):
                    sensor_ids = [
                        value for value in scope.removeprefix("sensor_batch:").split(",") if value
                    ]
                try:
                    service.sync_range(
                        kind,
                        gap["gap_from"],
                        gap["gap_to"],
                        sensor_ids=sensor_ids,
                        record_failures=False,
                    )
                    self.state.resolve_gap(gap["id"])
                    resolved += 1
                except Exception as exc:
                    self.state.fail_gap(gap["id"], str(exc))
                    failed += 1
            return {"gaps_checked": len(gaps), "gaps_resolved": resolved, "gaps_failed": failed}

        return self._run("reconcile-gaps", operation)

    def sync_all(self) -> dict[str, Any]:
        measurement_watermark = self.state.get_watermark("measurements")
        if measurement_watermark is None:
            return self.backfill(refresh_catalogs=True)
        return self.sync_incremental()
