from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aranet_etl.database.bootstrap import ensure_database_exists
from aranet_etl.database.connection import database_connection
from aranet_etl.database.migrations import apply_migrations
from aranet_etl.database.timeseries_repository import TimeseriesRepository

pytestmark = pytest.mark.integration


def test_bootstrap_is_idempotent_and_timeseries_upserts(postgres_settings) -> None:
    ensure_database_exists(postgres_settings)
    with database_connection(postgres_settings) as connection:
        connection.autocommit = True
        with connection.cursor() as cursor:
            cursor.execute("DROP SCHEMA IF EXISTS aranet CASCADE")

    assert apply_migrations(postgres_settings) == 6
    assert apply_migrations(postgres_settings) == 0

    measured_at = datetime(2026, 8, 13, 12, tzinfo=UTC)
    measurement = {
        "sensor": "sensor-1",
        "metric": "1",
        "unit": "1",
        "time": measured_at.isoformat(),
        "value": 20.5,
    }
    telemetry = {
        "sensor": "sensor-1",
        "metric": "61",
        "unit": "11",
        "time": measured_at.isoformat(),
        "value": -70,
    }

    with database_connection(postgres_settings) as connection:
        connection.autocommit = True
        repository = TimeseriesRepository(connection)
        first_measurement = repository.upsert_measurements([measurement])
        first_telemetry = repository.upsert_telemetry([telemetry])
        updated_measurement = {**measurement, "value": 21.25, "novelty": "new"}
        updated_telemetry = {**telemetry, "value": -68, "novelty": "new"}
        second_measurement = repository.upsert_measurements([updated_measurement])
        second_telemetry = repository.upsert_telemetry([updated_telemetry])
        unchanged_measurement = repository.upsert_measurements([updated_measurement])
        unchanged_telemetry = repository.upsert_telemetry([updated_telemetry])

        assert (first_measurement.inserted, first_measurement.updated) == (1, 0)
        assert (first_telemetry.inserted, first_telemetry.updated) == (1, 0)
        assert (second_measurement.inserted, second_measurement.updated) == (0, 1)
        assert (second_telemetry.inserted, second_telemetry.updated) == (0, 1)
        assert (unchanged_measurement.inserted, unchanged_measurement.updated) == (0, 0)
        assert (unchanged_telemetry.inserted, unchanged_telemetry.updated) == (0, 0)

        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*), MAX(value) FROM aranet.measurement")
            assert cursor.fetchone() == (1, 21.25)
            cursor.execute("SELECT COUNT(*), MAX(value) FROM aranet.telemetry")
            assert cursor.fetchone() == (1, -68.0)
            cursor.execute(
                """
                SELECT COUNT(*) FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'aranet'
                  AND c.relname IN ('measurement_y2026m08', 'telemetry_y2026m08')
                """
            )
            assert cursor.fetchone()[0] == 2


def test_asset_point_measurement_has_a_distinct_natural_key(postgres_settings) -> None:
    with database_connection(postgres_settings) as connection:
        connection.autocommit = True
        repository = TimeseriesRepository(connection)
        reading = {
            "sensor": "sensor-2",
            "asset": "asset-1",
            "point": "point-1",
            "metric": "8",
            "unit": "115",
            "time": "2026-08-13T13:00:00Z",
            "value": 34.5,
        }
        result = repository.upsert_measurements([reading])
        assert result.inserted == 1
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT subject_type, subject_id, source_sensor_id
                FROM aranet.measurement
                WHERE source_sensor_id = 'sensor-2'
                """
            )
            assert cursor.fetchone() == ("asset_point", "point-1", "sensor-2")
