CREATE OR REPLACE VIEW aranet.v_latest_measurements AS
SELECT DISTINCT ON (subject_type, subject_id, source_sensor_id, metric_id, probe_no)
    subject_type,
    subject_id,
    source_sensor_id,
    asset_id,
    measurement_point_id,
    metric_id,
    unit_id,
    probe_no,
    measured_at,
    value,
    novelty,
    ingested_at
FROM aranet.measurement
ORDER BY subject_type, subject_id, source_sensor_id, metric_id, probe_no, measured_at DESC;

CREATE OR REPLACE VIEW aranet.v_latest_telemetry AS
SELECT DISTINCT ON (sensor_id, metric_id, probe_no)
    sensor_id,
    metric_id,
    unit_id,
    probe_no,
    measured_at,
    value,
    novelty,
    ingested_at
FROM aranet.telemetry
ORDER BY sensor_id, metric_id, probe_no, measured_at DESC;

CREATE OR REPLACE VIEW aranet.v_sensor_status AS
SELECT
    s.id AS sensor_id,
    s.sensor_code,
    s.name AS sensor_name,
    s.sensor_type_id,
    s.is_active,
    MAX(t.measured_at) AS last_telemetry_at,
    MAX(t.value) FILTER (WHERE t.metric_id = '61') AS rssi_dbm,
    MAX(t.value) FILTER (WHERE t.metric_id = '62') AS battery_value,
    MAX(t.unit_id) FILTER (WHERE t.metric_id = '62') AS battery_unit_id,
    MAX(t.value) FILTER (WHERE t.metric_id = '63') AS power_supply
FROM aranet.sensor s
LEFT JOIN aranet.v_latest_telemetry t ON t.sensor_id = s.id
GROUP BY s.id, s.sensor_code, s.name, s.sensor_type_id, s.is_active;

CREATE OR REPLACE VIEW aranet.v_active_alarms AS
SELECT
    a.*,
    s.name AS sensor_name,
    m.name AS metric_name,
    u.name AS unit_name,
    r.name AS rule_name
FROM aranet.alarm a
LEFT JOIN aranet.sensor s ON s.id = a.sensor_id
LEFT JOIN aranet.metric m ON m.id = a.metric_id
LEFT JOIN aranet.unit u ON u.id = a.unit_id
LEFT JOIN aranet.alarm_rule r ON r.id = a.rule_id
WHERE a.is_active;

