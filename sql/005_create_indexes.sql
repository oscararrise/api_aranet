CREATE UNIQUE INDEX IF NOT EXISTS uq_sensor_sensor_code
    ON aranet.sensor (sensor_code)
    WHERE sensor_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_sensor_type ON aranet.sensor (sensor_type_id);
CREATE INDEX IF NOT EXISTS idx_sensor_active ON aranet.sensor (is_active) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_pairing_base ON aranet.sensor_base_pairing (base_station_id, removed_at);
CREATE INDEX IF NOT EXISTS idx_association_sensor ON aranet.asset_sensor_association (sensor_id, removed_at);
CREATE INDEX IF NOT EXISTS idx_point_asset ON aranet.measurement_point (asset_id);
CREATE INDEX IF NOT EXISTS idx_tag_assignment_entity ON aranet.tag_assignment (entity_type, entity_id);

CREATE INDEX IF NOT EXISTS idx_measurement_source_metric_time
    ON aranet.measurement (source_sensor_id, metric_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_measurement_subject_time
    ON aranet.measurement (subject_type, subject_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_measurement_asset_point_time
    ON aranet.measurement (asset_id, measurement_point_id, measured_at DESC)
    WHERE asset_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_measurement_time_brin
    ON aranet.measurement USING brin (measured_at);

CREATE INDEX IF NOT EXISTS idx_telemetry_sensor_time
    ON aranet.telemetry (sensor_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_metric_time
    ON aranet.telemetry (metric_id, measured_at DESC);
CREATE INDEX IF NOT EXISTS idx_telemetry_time_brin
    ON aranet.telemetry USING brin (measured_at);

CREATE INDEX IF NOT EXISTS idx_alarm_sensor_time ON aranet.alarm (sensor_id, alarmed_at DESC);
CREATE INDEX IF NOT EXISTS idx_alarm_active ON aranet.alarm (is_active) WHERE is_active;
CREATE INDEX IF NOT EXISTS idx_sync_run_started ON aranet.sync_run (started_at DESC);
CREATE INDEX IF NOT EXISTS idx_sync_gap_pending ON aranet.sync_gap (status, gap_from) WHERE status IN ('pending', 'failed');
CREATE INDEX IF NOT EXISTS idx_snapshot_resource ON aranet.resource_snapshot (resource_type, resource_id, captured_at DESC);

