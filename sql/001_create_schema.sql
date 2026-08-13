CREATE SCHEMA IF NOT EXISTS aranet;

CREATE TABLE IF NOT EXISTS aranet.schema_migration (
    version text PRIMARY KEY,
    name text NOT NULL,
    checksum text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON SCHEMA aranet IS 'Aranet Cloud metadata, measurements, telemetry, alarms, and ETL state';

