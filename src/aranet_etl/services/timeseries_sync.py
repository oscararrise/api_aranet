from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from psycopg import Connection

from aranet_etl.api.client import AranetClient
from aranet_etl.config import Settings
from aranet_etl.database.catalog_repository import CatalogRepository
from aranet_etl.database.sync_repository import SyncRepository
from aranet_etl.database.timeseries_repository import TimeseriesRepository, UpsertResult
from aranet_etl.utils import chunked, isoformat_utc

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class RangeSyncResult:
    pages: int = 0
    received: int = 0
    inserted: int = 0
    updated: int = 0

    def add(self, upsert: UpsertResult) -> None:
        self.pages += 1
        self.received += upsert.received
        self.inserted += upsert.inserted
        self.updated += upsert.updated


class TimeseriesSyncService:
    def __init__(
        self,
        settings: Settings,
        client: AranetClient,
        connection: Connection,
        run_id: int,
    ) -> None:
        self.settings = settings
        self.client = client
        self.connection = connection
        self.run_id = run_id
        self.timeseries = TimeseriesRepository(connection)
        self.sync_repository = SyncRepository(connection)

    def _write(
        self,
        kind: Literal["measurement", "telemetry"],
        readings: list[dict],
    ) -> UpsertResult:
        with self.connection.transaction():
            if kind == "measurement":
                result = self.timeseries.upsert_measurements(readings)
            else:
                result = self.timeseries.upsert_telemetry(readings)
            self.sync_repository.add_progress(
                self.run_id,
                pages=1,
                received=result.received,
                inserted=result.inserted,
                updated=result.updated,
            )
        return result

    def sync_range(
        self,
        kind: Literal["measurement", "telemetry"],
        start: datetime,
        end: datetime,
        *,
        sensor_ids: list[str] | None = None,
        record_failures: bool = True,
    ) -> RangeSyncResult:
        endpoint = f"/api/v1/{'measurements' if kind == 'measurement' else 'telemetry'}/history"
        sensor_ids = sensor_ids or CatalogRepository(self.connection).sensor_ids()
        result = RangeSyncResult()
        for batch in chunked(sensor_ids, self.settings.aranet.sensor_batch_size):
            scope_key = f"sensor_batch:{','.join(batch)}"
            params = {
                "sensor": ",".join(batch),
                "from": isoformat_utc(start),
                "to": isoformat_utc(end),
                "limit": str(self.settings.aranet.page_limit),
                "links": "false",
            }
            try:
                for page in self.client.iter_pages(endpoint, params=params):
                    upsert = self._write(kind, page.payload.get("readings") or [])
                    result.add(upsert)
            except Exception as exc:
                if record_failures:
                    with self.connection.transaction():
                        self.sync_repository.record_gap(
                            endpoint,
                            start,
                            end,
                            str(exc),
                            scope_key=scope_key,
                        )
                raise
        LOGGER.info(
            "%s range synchronized: from=%s to=%s pages=%s received=%s inserted=%s updated=%s",
            kind,
            isoformat_utc(start),
            isoformat_utc(end),
            result.pages,
            result.received,
            result.inserted,
            result.updated,
        )
        return result

    def sync_latest(self) -> RangeSyncResult:
        result = RangeSyncResult()
        for kind, endpoint in (
            ("measurement", "/api/v1/measurements/last"),
            ("telemetry", "/api/v1/telemetry/last"),
        ):
            payload = self.client.get_json(endpoint, params={"links": "false"})
            upsert = self._write(kind, payload.get("readings") or [])
            result.add(upsert)
        return result

    def sync_alarm_history(self, start: datetime, end: datetime) -> UpsertResult:
        payload = self.client.get_json(
            "/api/v1/alarms/history",
            params={"from": isoformat_utc(start), "to": isoformat_utc(end)},
        )
        with self.connection.transaction():
            result = self.timeseries.upsert_alarms(payload.get("alarms") or [], actual=False)
            self.sync_repository.add_progress(
                self.run_id,
                pages=1,
                received=result.received,
                inserted=result.inserted,
                updated=result.updated,
            )
        return result

    def sync_actual_alarms(self) -> UpsertResult:
        payload = self.client.get_json("/api/v1/alarms/actual")
        with self.connection.transaction():
            result = self.timeseries.upsert_alarms(payload.get("alarms") or [], actual=True)
            self.sync_repository.add_progress(
                self.run_id,
                pages=1,
                received=result.received,
                inserted=result.inserted,
                updated=result.updated,
            )
        return result
