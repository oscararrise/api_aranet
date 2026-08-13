CREATE TABLE IF NOT EXISTS aranet.measurement (
    subject_type text NOT NULL CHECK (subject_type IN ('sensor', 'asset_point')),
    subject_id text NOT NULL,
    source_sensor_id text NOT NULL,
    asset_id text,
    measurement_point_id text,
    metric_id text NOT NULL,
    unit_id text,
    probe_no integer NOT NULL DEFAULT 0,
    measured_at timestamptz NOT NULL,
    value double precision NOT NULL,
    novelty text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_ingested_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ingested_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (
        subject_type,
        subject_id,
        source_sensor_id,
        metric_id,
        probe_no,
        measured_at
    )
) PARTITION BY RANGE (measured_at);

CREATE TABLE IF NOT EXISTS aranet.telemetry (
    sensor_id text NOT NULL,
    metric_id text NOT NULL,
    unit_id text,
    probe_no integer NOT NULL DEFAULT 0,
    measured_at timestamptz NOT NULL,
    value double precision NOT NULL,
    novelty text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_ingested_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ingested_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sensor_id, metric_id, probe_no, measured_at)
) PARTITION BY RANGE (measured_at);

CREATE TABLE IF NOT EXISTS aranet.alarm_rule (
    id text PRIMARY KEY,
    name text,
    metric_id text,
    notes text,
    source_created_at timestamptz,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aranet.alarm (
    id text PRIMARY KEY,
    rule_id text,
    sensor_id text,
    metric_id text,
    unit_id text,
    alarmed_at timestamptz,
    resolved_at timestamptz,
    severity integer,
    threshold_direction text,
    threshold_value double precision,
    worst_value double precision,
    note text,
    is_active boolean NOT NULL DEFAULT false,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE OR REPLACE FUNCTION aranet.ensure_month_partition(
    p_table_name text,
    p_moment timestamptz
) RETURNS text
LANGUAGE plpgsql
AS $$
DECLARE
    month_start timestamptz;
    month_end timestamptz;
    partition_name text;
BEGIN
    IF p_table_name NOT IN ('measurement', 'telemetry') THEN
        RAISE EXCEPTION 'Unsupported partitioned table: %', p_table_name;
    END IF;

    month_start := date_trunc('month', p_moment AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
    month_end := month_start + interval '1 month';
    partition_name := format(
        '%s_y%sm%s',
        p_table_name,
        to_char(month_start, 'YYYY'),
        to_char(month_start, 'MM')
    );

    EXECUTE format(
        'CREATE TABLE IF NOT EXISTS aranet.%I PARTITION OF aranet.%I FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        p_table_name,
        month_start,
        month_end
    );
    RETURN partition_name;
END;
$$;

SELECT aranet.ensure_month_partition('measurement', CURRENT_TIMESTAMP);
SELECT aranet.ensure_month_partition('measurement', CURRENT_TIMESTAMP + interval '1 month');
SELECT aranet.ensure_month_partition('telemetry', CURRENT_TIMESTAMP);
SELECT aranet.ensure_month_partition('telemetry', CURRENT_TIMESTAMP + interval '1 month');

COMMENT ON TABLE aranet.measurement IS 'Environmental, agricultural, and asset-point measurements';
COMMENT ON TABLE aranet.telemetry IS 'Device health metrics such as RSSI, battery, and power supply';

