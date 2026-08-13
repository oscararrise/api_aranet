from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from psycopg import Connection
from psycopg.types.json import Jsonb

from aranet_etl.database.partitions import ensure_month_partitions
from aranet_etl.utils import as_text, parse_datetime


@dataclass(frozen=True, slots=True)
class UpsertResult:
    received: int = 0
    inserted: int = 0
    updated: int = 0


def _link_id(value: Any) -> str | None:
    if isinstance(value, dict):
        return as_text(value.get("id"))
    return as_text(value)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class TimeseriesRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def upsert_measurements(self, readings: list[dict[str, Any]]) -> UpsertResult:
        rows: dict[tuple[Any, ...], tuple[Any, ...]] = {}
        moments = set()
        for reading in readings:
            sensor_id = _link_id(reading.get("sensor"))
            metric_id = _link_id(reading.get("metric"))
            measured_at = parse_datetime(reading.get("time"))
            value = _number(reading.get("value"))
            if not sensor_id or not metric_id or measured_at is None or value is None:
                continue
            asset_id = _link_id(reading.get("asset"))
            point_id = _link_id(reading.get("point"))
            subject_type = "asset_point" if asset_id and point_id else "sensor"
            subject_id = point_id if subject_type == "asset_point" else sensor_id
            probe_no = int(reading.get("probe") or 0)
            key = (subject_type, subject_id, sensor_id, metric_id, probe_no, measured_at)
            rows[key] = (
                subject_type,
                subject_id,
                sensor_id,
                asset_id,
                point_id,
                metric_id,
                _link_id(reading.get("unit")),
                probe_no,
                measured_at,
                value,
                reading.get("novelty"),
                Jsonb(reading),
            )
            moments.add(measured_at)
        if not rows:
            return UpsertResult(received=len(readings))

        ensure_month_partitions(self.connection, "measurement", moments)
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS pg_temp.stage_aranet_measurement")
            cursor.execute(
                "CREATE TEMP TABLE stage_aranet_measurement "
                "(LIKE aranet.measurement INCLUDING DEFAULTS) ON COMMIT DROP"
            )
            with cursor.copy(
                """
                COPY stage_aranet_measurement (
                    subject_type, subject_id, source_sensor_id, asset_id,
                    measurement_point_id, metric_id, unit_id, probe_no,
                    measured_at, value, novelty, raw_payload
                ) FROM STDIN
                """
            ) as copy:
                for row in rows.values():
                    copy.write_row(row)
            cursor.execute(
                """
                WITH inserted AS (
                    INSERT INTO aranet.measurement (
                        subject_type, subject_id, source_sensor_id, asset_id,
                        measurement_point_id, metric_id, unit_id, probe_no,
                        measured_at, value, novelty, raw_payload
                    )
                    SELECT
                        subject_type, subject_id, source_sensor_id, asset_id,
                        measurement_point_id, metric_id, unit_id, probe_no,
                        measured_at, value, novelty, raw_payload
                    FROM stage_aranet_measurement
                    ON CONFLICT (
                        subject_type, subject_id, source_sensor_id,
                        metric_id, probe_no, measured_at
                    ) DO NOTHING
                    RETURNING 1
                )
                SELECT COUNT(*) FROM inserted
                """
            )
            inserted = cursor.fetchone()[0]
            cursor.execute(
                """
                WITH updated AS (
                    UPDATE aranet.measurement AS target SET
                        asset_id = source.asset_id,
                        measurement_point_id = source.measurement_point_id,
                        unit_id = source.unit_id,
                        value = source.value,
                        novelty = COALESCE(source.novelty, target.novelty),
                        raw_payload = target.raw_payload || source.raw_payload,
                        ingested_at = CURRENT_TIMESTAMP
                    FROM stage_aranet_measurement AS source
                    WHERE target.subject_type = source.subject_type
                      AND target.subject_id = source.subject_id
                      AND target.source_sensor_id = source.source_sensor_id
                      AND target.metric_id = source.metric_id
                      AND target.probe_no = source.probe_no
                      AND target.measured_at = source.measured_at
                      AND (
                          target.asset_id IS DISTINCT FROM source.asset_id
                          OR target.measurement_point_id
                              IS DISTINCT FROM source.measurement_point_id
                          OR target.unit_id IS DISTINCT FROM source.unit_id
                          OR target.value IS DISTINCT FROM source.value
                          OR (
                              source.novelty IS NOT NULL
                              AND target.novelty IS DISTINCT FROM source.novelty
                          )
                          OR target.raw_payload IS DISTINCT FROM (
                              target.raw_payload || source.raw_payload
                          )
                      )
                    RETURNING 1
                )
                SELECT COUNT(*) FROM updated
                """
            )
            updated = cursor.fetchone()[0]
        return UpsertResult(len(readings), int(inserted or 0), int(updated or 0))

    def upsert_telemetry(self, readings: list[dict[str, Any]]) -> UpsertResult:
        rows: dict[tuple[Any, ...], tuple[Any, ...]] = {}
        moments = set()
        for reading in readings:
            sensor_id = _link_id(reading.get("sensor"))
            metric_id = _link_id(reading.get("metric"))
            measured_at = parse_datetime(reading.get("time"))
            value = _number(reading.get("value"))
            if not sensor_id or not metric_id or measured_at is None or value is None:
                continue
            probe_no = int(reading.get("probe") or 0)
            key = (sensor_id, metric_id, probe_no, measured_at)
            rows[key] = (
                sensor_id,
                metric_id,
                _link_id(reading.get("unit")),
                probe_no,
                measured_at,
                value,
                reading.get("novelty"),
                Jsonb(reading),
            )
            moments.add(measured_at)
        if not rows:
            return UpsertResult(received=len(readings))

        ensure_month_partitions(self.connection, "telemetry", moments)
        with self.connection.transaction(), self.connection.cursor() as cursor:
            cursor.execute("DROP TABLE IF EXISTS pg_temp.stage_aranet_telemetry")
            cursor.execute(
                "CREATE TEMP TABLE stage_aranet_telemetry "
                "(LIKE aranet.telemetry INCLUDING DEFAULTS) ON COMMIT DROP"
            )
            with cursor.copy(
                """
                COPY stage_aranet_telemetry (
                    sensor_id, metric_id, unit_id, probe_no,
                    measured_at, value, novelty, raw_payload
                ) FROM STDIN
                """
            ) as copy:
                for row in rows.values():
                    copy.write_row(row)
            cursor.execute(
                """
                WITH inserted AS (
                    INSERT INTO aranet.telemetry (
                        sensor_id, metric_id, unit_id, probe_no,
                        measured_at, value, novelty, raw_payload
                    )
                    SELECT
                        sensor_id, metric_id, unit_id, probe_no,
                        measured_at, value, novelty, raw_payload
                    FROM stage_aranet_telemetry
                    ON CONFLICT (sensor_id, metric_id, probe_no, measured_at)
                    DO NOTHING
                    RETURNING 1
                )
                SELECT COUNT(*) FROM inserted
                """
            )
            inserted = cursor.fetchone()[0]
            cursor.execute(
                """
                WITH updated AS (
                    UPDATE aranet.telemetry AS target SET
                        unit_id = source.unit_id,
                        value = source.value,
                        novelty = COALESCE(source.novelty, target.novelty),
                        raw_payload = target.raw_payload || source.raw_payload,
                        ingested_at = CURRENT_TIMESTAMP
                    FROM stage_aranet_telemetry AS source
                    WHERE target.sensor_id = source.sensor_id
                      AND target.metric_id = source.metric_id
                      AND target.probe_no = source.probe_no
                      AND target.measured_at = source.measured_at
                      AND (
                          target.unit_id IS DISTINCT FROM source.unit_id
                          OR target.value IS DISTINCT FROM source.value
                          OR (
                              source.novelty IS NOT NULL
                              AND target.novelty IS DISTINCT FROM source.novelty
                          )
                          OR target.raw_payload IS DISTINCT FROM (
                              target.raw_payload || source.raw_payload
                          )
                      )
                    RETURNING 1
                )
                SELECT COUNT(*) FROM updated
                """
            )
            updated = cursor.fetchone()[0]
        return UpsertResult(len(readings), int(inserted or 0), int(updated or 0))

    def upsert_alarms(self, alarms: list[dict[str, Any]], *, actual: bool) -> UpsertResult:
        valid = [alarm for alarm in alarms if alarm.get("id") is not None]
        if not valid:
            return UpsertResult(received=len(alarms))
        inserted = 0
        updated = 0
        with self.connection.cursor() as cursor:
            if actual:
                cursor.execute("UPDATE aranet.alarm SET is_active = false WHERE is_active")
            for alarm in valid:
                cursor.execute(
                    """
                    INSERT INTO aranet.alarm (
                        id, rule_id, sensor_id, metric_id, unit_id, alarmed_at,
                        resolved_at, severity, threshold_direction, threshold_value,
                        worst_value, note, is_active, raw_payload, synced_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT (id) DO UPDATE SET
                        rule_id = EXCLUDED.rule_id,
                        sensor_id = EXCLUDED.sensor_id,
                        metric_id = EXCLUDED.metric_id,
                        unit_id = EXCLUDED.unit_id,
                        alarmed_at = EXCLUDED.alarmed_at,
                        resolved_at = EXCLUDED.resolved_at,
                        severity = EXCLUDED.severity,
                        threshold_direction = EXCLUDED.threshold_direction,
                        threshold_value = EXCLUDED.threshold_value,
                        worst_value = EXCLUDED.worst_value,
                        note = EXCLUDED.note,
                        is_active = CASE
                            WHEN EXCLUDED.resolved_at IS NOT NULL THEN false
                            WHEN EXCLUDED.is_active THEN true
                            ELSE aranet.alarm.is_active
                        END,
                        raw_payload = EXCLUDED.raw_payload,
                        synced_at = CURRENT_TIMESTAMP
                    RETURNING (xmax = 0)
                    """,
                    (
                        as_text(alarm.get("id")),
                        as_text(alarm.get("rule")),
                        as_text(alarm.get("sensor")),
                        as_text(alarm.get("metric")),
                        as_text(alarm.get("unit")),
                        parse_datetime(alarm.get("alarmed")),
                        parse_datetime(alarm.get("resolved")),
                        alarm.get("severity"),
                        alarm.get("threshold"),
                        _number(alarm.get("value")),
                        _number(alarm.get("worst")),
                        alarm.get("note"),
                        actual and alarm.get("resolved") is None,
                        Jsonb(alarm),
                    ),
                )
                if cursor.fetchone()[0]:
                    inserted += 1
                else:
                    updated += 1
        return UpsertResult(len(alarms), inserted, updated)
