CREATE TABLE IF NOT EXISTS aranet.base_station (
    id text PRIMARY KEY,
    name text,
    registered_at timestamptz,
    firmware text,
    product text,
    board text,
    region text,
    last_seen_at_source timestamptz,
    paused_at timestamptz,
    upgrade text,
    configuration jsonb NOT NULL DEFAULT '{}'::jsonb,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    first_seen_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aranet.sensor_type (
    id text PRIMARY KEY,
    name text,
    is_virtual boolean,
    icon text,
    conversion_type_id text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aranet.sensor (
    id text PRIMARY KEY,
    sensor_code text,
    name text,
    sensor_type_id text REFERENCES aranet.sensor_type(id),
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    first_seen_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aranet.sensor_base_pairing (
    pairing_pk bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sensor_id text NOT NULL REFERENCES aranet.sensor(id),
    base_station_id text NOT NULL REFERENCES aranet.base_station(id),
    paired_at timestamptz,
    removed_at timestamptz,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE NULLS NOT DISTINCT (sensor_id, base_station_id, paired_at)
);

CREATE TABLE IF NOT EXISTS aranet.sensor_probe (
    sensor_id text NOT NULL REFERENCES aranet.sensor(id),
    probe_no integer NOT NULL,
    name text,
    label text,
    color text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sensor_id, probe_no)
);

CREATE TABLE IF NOT EXISTS aranet.metric (
    id text PRIMARY KEY,
    name text,
    kind text,
    icon text,
    sensor_count integer,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aranet.unit (
    id text PRIMARY KEY,
    name text,
    precision_digits integer,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aranet.metric_unit (
    metric_id text NOT NULL REFERENCES aranet.metric(id),
    unit_id text NOT NULL REFERENCES aranet.unit(id),
    is_default boolean NOT NULL DEFAULT false,
    is_selected boolean NOT NULL DEFAULT false,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (metric_id, unit_id)
);

CREATE TABLE IF NOT EXISTS aranet.sensor_capability (
    sensor_id text NOT NULL REFERENCES aranet.sensor(id),
    metric_id text NOT NULL REFERENCES aranet.metric(id),
    probe_no integer NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sensor_id, metric_id, probe_no)
);

CREATE TABLE IF NOT EXISTS aranet.asset (
    id text PRIMARY KEY,
    name text,
    location text,
    notes text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    first_seen_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aranet.measurement_point (
    id text PRIMARY KEY,
    asset_id text NOT NULL REFERENCES aranet.asset(id),
    name text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aranet.asset_sensor_association (
    id text PRIMARY KEY,
    asset_id text NOT NULL REFERENCES aranet.asset(id),
    measurement_point_id text NOT NULL REFERENCES aranet.measurement_point(id),
    sensor_id text NOT NULL REFERENCES aranet.sensor(id),
    probe_no integer NOT NULL DEFAULT 0,
    placed_at timestamptz,
    removed_at timestamptz,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aranet.measurement_point_capability (
    measurement_point_id text NOT NULL REFERENCES aranet.measurement_point(id),
    metric_id text NOT NULL REFERENCES aranet.metric(id),
    is_active boolean NOT NULL DEFAULT true,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (measurement_point_id, metric_id)
);

CREATE TABLE IF NOT EXISTS aranet.tag (
    id text PRIMARY KEY,
    name text,
    notes text,
    type_id text,
    type_name text,
    type_color text,
    type_icon text,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS aranet.tag_assignment (
    entity_type text NOT NULL CHECK (entity_type IN ('base_station', 'sensor', 'asset')),
    entity_id text NOT NULL,
    tag_id text NOT NULL REFERENCES aranet.tag(id),
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entity_type, entity_id, tag_id)
);

CREATE TABLE IF NOT EXISTS aranet.attachment (
    entity_type text NOT NULL CHECK (entity_type IN ('sensor', 'asset')),
    entity_id text NOT NULL,
    attachment_id text NOT NULL,
    name text,
    mime_type text,
    size_bytes bigint,
    file_url text,
    thumbnail_url text,
    source_created_at timestamptz,
    raw_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    is_active boolean NOT NULL DEFAULT true,
    synced_at timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entity_type, entity_id, attachment_id)
);

COMMENT ON COLUMN aranet.sensor.sensor_code IS 'Identifier shown on the physical device; API filters use sensor.id instead';
COMMENT ON COLUMN aranet.sensor_capability.probe_no IS 'Zero means the metric is not tied to a numbered probe';
COMMENT ON TABLE aranet.attachment IS 'Attachment metadata only; binary files are deliberately not stored in PostgreSQL';
