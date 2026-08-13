from __future__ import annotations

from datetime import datetime
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb


class SyncRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def start_run(self, command: str, *, details: dict[str, Any] | None = None) -> int:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.sync_run (command, status, details)
                VALUES (%s, 'running', %s)
                RETURNING id
                """,
                (command, Jsonb(details or {})),
            )
            return int(cursor.fetchone()[0])

    def add_progress(
        self,
        run_id: int,
        *,
        pages: int = 0,
        received: int = 0,
        inserted: int = 0,
        updated: int = 0,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE aranet.sync_run SET
                    pages_read = pages_read + %s,
                    rows_received = rows_received + %s,
                    rows_inserted = rows_inserted + %s,
                    rows_updated = rows_updated + %s
                WHERE id = %s
                """,
                (pages, received, inserted, updated, run_id),
            )

    def finish_run(self, run_id: int, *, details: dict[str, Any] | None = None) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE aranet.sync_run SET
                    status = 'succeeded',
                    finished_at = CURRENT_TIMESTAMP,
                    details = details || %s
                WHERE id = %s
                """,
                (Jsonb(details or {}), run_id),
            )

    def fail_run(self, run_id: int, error_message: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE aranet.sync_run SET
                    status = 'failed',
                    finished_at = CURRENT_TIMESTAMP,
                    error_message = %s
                WHERE id = %s
                """,
                (error_message[:4000], run_id),
            )

    def get_watermark(self, endpoint: str, scope_key: str = "all") -> datetime | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT watermark FROM aranet.sync_state WHERE endpoint = %s AND scope_key = %s",
                (endpoint, scope_key),
            )
            row = cursor.fetchone()
            return row[0] if row else None

    def set_watermark(
        self,
        endpoint: str,
        watermark: datetime,
        *,
        scope_key: str = "all",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.sync_state (
                    endpoint, scope_key, watermark, last_success_at, metadata, updated_at
                ) VALUES (%s, %s, %s, CURRENT_TIMESTAMP, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (endpoint, scope_key) DO UPDATE SET
                    watermark = EXCLUDED.watermark,
                    last_success_at = CURRENT_TIMESTAMP,
                    metadata = aranet.sync_state.metadata || EXCLUDED.metadata,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (endpoint, scope_key, watermark, Jsonb(metadata or {})),
            )

    def record_gap(
        self,
        endpoint: str,
        gap_from: datetime,
        gap_to: datetime,
        error: str,
        *,
        scope_key: str = "all",
    ) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.sync_gap (
                    endpoint, scope_key, gap_from, gap_to, status, attempts,
                    last_error, updated_at
                ) VALUES (%s, %s, %s, %s, 'failed', 1, %s, CURRENT_TIMESTAMP)
                ON CONFLICT (endpoint, scope_key, gap_from, gap_to) DO UPDATE SET
                    status = 'failed',
                    attempts = aranet.sync_gap.attempts + 1,
                    last_error = EXCLUDED.last_error,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (endpoint, scope_key, gap_from, gap_to, error[:4000]),
            )

    def infer_backfill_start(self) -> datetime | None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT MIN(value) FROM (
                    SELECT MIN(registered_at) AS value FROM aranet.base_station
                    UNION ALL
                    SELECT MIN(paired_at) AS value FROM aranet.sensor_base_pairing
                    UNION ALL
                    SELECT MIN(placed_at) AS value FROM aranet.asset_sensor_association
                ) candidates
                """
            )
            return cursor.fetchone()[0]

    def pending_gaps(self, limit: int = 10) -> list[dict[str, Any]]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, endpoint, scope_key, gap_from, gap_to, attempts
                FROM aranet.sync_gap
                WHERE status IN ('pending', 'failed')
                ORDER BY gap_from
                LIMIT %s
                """,
                (limit,),
            )
            return [
                {
                    "id": row[0],
                    "endpoint": row[1],
                    "scope_key": row[2],
                    "gap_from": row[3],
                    "gap_to": row[4],
                    "attempts": row[5],
                }
                for row in cursor.fetchall()
            ]

    def mark_gap_processing(self, gap_id: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE aranet.sync_gap SET
                    status = 'processing',
                    attempts = attempts + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (gap_id,),
            )

    def resolve_gap(self, gap_id: int) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE aranet.sync_gap SET
                    status = 'resolved',
                    last_error = NULL,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (gap_id,),
            )

    def fail_gap(self, gap_id: int, error: str) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE aranet.sync_gap SET
                    status = 'failed',
                    last_error = %s,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = %s
                """,
                (error[:4000], gap_id),
            )
