from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from psycopg import Connection, sql
from psycopg.types.json import Jsonb

from aranet_etl.utils import as_text, parse_datetime, payload_hash

_INACTIVATABLE_TABLES = {
    "base_station",
    "sensor_type",
    "sensor",
    "metric",
    "unit",
    "asset",
    "measurement_point",
    "tag",
    "attachment",
    "alarm_rule",
}

_REFERENCE_TABLES = {
    "base_station",
    "sensor_type",
    "sensor",
    "metric",
    "unit",
    "tag",
}


class CatalogRepository:
    def __init__(self, connection: Connection) -> None:
        self.connection = connection

    def mark_all_inactive(self, table_name: str) -> None:
        if table_name not in _INACTIVATABLE_TABLES:
            raise ValueError(f"Unsupported catalog table: {table_name}")
        with self.connection.cursor() as cursor:
            cursor.execute(
                sql.SQL("UPDATE aranet.{} SET is_active = false").format(sql.Identifier(table_name))
            )

    def ensure_reference(self, table_name: str, resource_id: str) -> None:
        """Create an inactive stub when Aranet returns a dangling relationship."""
        if table_name not in _REFERENCE_TABLES:
            raise ValueError(f"Unsupported reference table: {table_name}")
        with self.connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    """
                    INSERT INTO aranet.{} (id, raw_payload, is_active, synced_at)
                    VALUES (%s, '{}'::jsonb, false, CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO NOTHING
                    """
                ).format(sql.Identifier(table_name)),
                (resource_id,),
            )

    def snapshot(self, resource_type: str, resource_id: str, payload: dict[str, Any]) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.resource_snapshot
                    (resource_type, resource_id, payload_hash, payload)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (resource_type, resource_id, payload_hash) DO NOTHING
                """,
                (resource_type, resource_id, payload_hash(payload), Jsonb(payload)),
            )

    def upsert_base_station(self, item: dict[str, Any]) -> None:
        base_id = as_text(item.get("id"))
        if not base_id:
            return
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.base_station (
                    id, name, registered_at, firmware, product, board, region,
                    last_seen_at_source, paused_at, upgrade, configuration,
                    raw_payload, is_active, synced_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP
                )
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    registered_at = EXCLUDED.registered_at,
                    firmware = EXCLUDED.firmware,
                    product = EXCLUDED.product,
                    board = EXCLUDED.board,
                    region = EXCLUDED.region,
                    last_seen_at_source = EXCLUDED.last_seen_at_source,
                    paused_at = EXCLUDED.paused_at,
                    upgrade = EXCLUDED.upgrade,
                    configuration = EXCLUDED.configuration,
                    raw_payload = EXCLUDED.raw_payload,
                    is_active = true,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (
                    base_id,
                    item.get("name"),
                    parse_datetime(item.get("regdate")),
                    item.get("firmware"),
                    item.get("product"),
                    item.get("board"),
                    item.get("region"),
                    parse_datetime(item.get("lastSeen")),
                    parse_datetime(item.get("pausedate")),
                    item.get("upgrade"),
                    Jsonb(item.get("config") or {}),
                    Jsonb(item),
                ),
            )
        self.snapshot("base_station", base_id, item)

    def upsert_sensor_type(self, item: dict[str, Any]) -> None:
        item_id = as_text(item.get("id"))
        if not item_id:
            return
        conversion = item.get("conversionType") or {}
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.sensor_type
                    (
                        id, name, is_virtual, icon, conversion_type_id,
                        raw_payload, is_active, synced_at
                    )
                VALUES (%s, %s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    is_virtual = EXCLUDED.is_virtual,
                    icon = EXCLUDED.icon,
                    conversion_type_id = EXCLUDED.conversion_type_id,
                    raw_payload = EXCLUDED.raw_payload,
                    is_active = true,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (
                    item_id,
                    item.get("name"),
                    item.get("isVirtual"),
                    item.get("icon"),
                    as_text(conversion.get("id")),
                    Jsonb(item),
                ),
            )
        self.snapshot("sensor_type", item_id, item)

    def upsert_metric(self, item: dict[str, Any]) -> None:
        metric_id = as_text(item.get("id"))
        if not metric_id:
            return
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.metric
                    (id, name, kind, icon, sensor_count, raw_payload, is_active, synced_at)
                VALUES (%s, %s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    kind = EXCLUDED.kind,
                    icon = EXCLUDED.icon,
                    sensor_count = EXCLUDED.sensor_count,
                    raw_payload = EXCLUDED.raw_payload,
                    is_active = true,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (
                    metric_id,
                    item.get("name"),
                    item.get("kind"),
                    item.get("icon"),
                    item.get("sensors"),
                    Jsonb(item),
                ),
            )
        self.snapshot("metric", metric_id, item)

    def upsert_unit(self, item: dict[str, Any]) -> None:
        unit_id = as_text(item.get("id"))
        if not unit_id:
            return
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.unit
                    (id, name, precision_digits, raw_payload, is_active, synced_at)
                VALUES (%s, %s, %s, %s, true, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    precision_digits = COALESCE(
                        EXCLUDED.precision_digits,
                        aranet.unit.precision_digits
                    ),
                    raw_payload = EXCLUDED.raw_payload,
                    is_active = true,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (unit_id, item.get("name"), item.get("precision"), Jsonb(item)),
            )
        self.snapshot("unit", unit_id, item)

    def replace_metric_units(self, metric_id: str, units: Iterable[dict[str, Any]]) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute("DELETE FROM aranet.metric_unit WHERE metric_id = %s", (metric_id,))
            for unit in units:
                unit_id = as_text(unit.get("id"))
                if not unit_id:
                    continue
                cursor.execute(
                    """
                    INSERT INTO aranet.metric_unit
                        (metric_id, unit_id, is_default, is_selected, synced_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        metric_id,
                        unit_id,
                        bool(unit.get("default")),
                        bool(unit.get("selected")),
                    ),
                )

    def upsert_sensor(self, item: dict[str, Any]) -> None:
        sensor_id = as_text(item.get("id"))
        if not sensor_id:
            return
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.sensor
                    (id, sensor_code, name, sensor_type_id, raw_payload, is_active, synced_at)
                VALUES (%s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    sensor_code = EXCLUDED.sensor_code,
                    name = EXCLUDED.name,
                    sensor_type_id = EXCLUDED.sensor_type_id,
                    raw_payload = EXCLUDED.raw_payload,
                    is_active = true,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (
                    sensor_id,
                    as_text(item.get("sensorId")),
                    item.get("name"),
                    as_text(item.get("type")),
                    Jsonb(item),
                ),
            )
        self.snapshot("sensor", sensor_id, item)

    def replace_sensor_details(self, sensor_id: str, item: dict[str, Any]) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute("DELETE FROM aranet.sensor_probe WHERE sensor_id = %s", (sensor_id,))
            cursor.execute(
                "DELETE FROM aranet.sensor_capability WHERE sensor_id = %s",
                (sensor_id,),
            )

            for probe in item.get("probes") or []:
                probe_no = probe.get("probe")
                if probe_no is None:
                    continue
                cursor.execute(
                    """
                    INSERT INTO aranet.sensor_probe
                        (sensor_id, probe_no, name, label, color, raw_payload, synced_at)
                    VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    """,
                    (
                        sensor_id,
                        int(probe_no),
                        probe.get("name"),
                        probe.get("label"),
                        probe.get("color"),
                        Jsonb(probe),
                    ),
                )

            for skill in item.get("skills") or []:
                metric_id = as_text(skill.get("metric"))
                if not metric_id:
                    continue
                probes = skill.get("probes") or [{"probe": 0}]
                for probe in probes:
                    probe_no = int(probe.get("probe") or 0)
                    cursor.execute(
                        """
                        INSERT INTO aranet.sensor_capability
                            (sensor_id, metric_id, probe_no, is_active, raw_payload, synced_at)
                        VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        """,
                        (
                            sensor_id,
                            metric_id,
                            probe_no,
                            bool(skill.get("active", True)),
                            Jsonb(skill),
                        ),
                    )

            for pairing in item.get("pairing") or []:
                base_id = as_text(pairing.get("base"))
                if not base_id:
                    continue
                cursor.execute(
                    """
                    INSERT INTO aranet.sensor_base_pairing
                        (sensor_id, base_station_id, paired_at, removed_at, raw_payload, synced_at)
                    VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (sensor_id, base_station_id, paired_at)
                    DO UPDATE SET
                        removed_at = EXCLUDED.removed_at,
                        raw_payload = EXCLUDED.raw_payload,
                        synced_at = CURRENT_TIMESTAMP
                    """,
                    (
                        sensor_id,
                        base_id,
                        parse_datetime(pairing.get("paired")),
                        parse_datetime(pairing.get("removed")),
                        Jsonb(pairing),
                    ),
                )

    def upsert_asset(self, item: dict[str, Any]) -> None:
        asset_id = as_text(item.get("id"))
        if not asset_id:
            return
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.asset
                    (id, name, location, notes, raw_payload, is_active, synced_at)
                VALUES (%s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    location = EXCLUDED.location,
                    notes = EXCLUDED.notes,
                    raw_payload = EXCLUDED.raw_payload,
                    is_active = true,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (
                    asset_id,
                    item.get("name"),
                    item.get("location"),
                    item.get("notes"),
                    Jsonb(item),
                ),
            )
        self.snapshot("asset", asset_id, item)

    def replace_asset_details(self, asset_id: str, item: dict[str, Any]) -> None:
        point_ids = [as_text(p.get("id")) for p in item.get("points") or [] if p.get("id")]
        with self.connection.cursor() as cursor:
            if point_ids:
                cursor.execute(
                    """
                    UPDATE aranet.measurement_point
                    SET is_active = false
                    WHERE asset_id = %s AND NOT (id = ANY(%s))
                    """,
                    (asset_id, point_ids),
                )
            else:
                cursor.execute(
                    "UPDATE aranet.measurement_point SET is_active = false WHERE asset_id = %s",
                    (asset_id,),
                )

            for point in item.get("points") or []:
                point_id = as_text(point.get("id"))
                if not point_id:
                    continue
                cursor.execute(
                    """
                    INSERT INTO aranet.measurement_point
                        (id, asset_id, name, raw_payload, is_active, synced_at)
                    VALUES (%s, %s, %s, %s, true, CURRENT_TIMESTAMP)
                    ON CONFLICT (id) DO UPDATE SET
                        asset_id = EXCLUDED.asset_id,
                        name = EXCLUDED.name,
                        raw_payload = EXCLUDED.raw_payload,
                        is_active = true,
                        synced_at = CURRENT_TIMESTAMP
                    """,
                    (point_id, asset_id, point.get("name"), Jsonb(point)),
                )
                cursor.execute(
                    """
                    DELETE FROM aranet.measurement_point_capability
                    WHERE measurement_point_id = %s
                    """,
                    (point_id,),
                )
                for skill in point.get("skills") or []:
                    metric_id = as_text(skill.get("metric"))
                    if not metric_id:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO aranet.measurement_point_capability
                            (measurement_point_id, metric_id, is_active, raw_payload, synced_at)
                        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                        """,
                        (
                            point_id,
                            metric_id,
                            bool(skill.get("active", True)),
                            Jsonb(skill),
                        ),
                    )
                for association in point.get("associations") or []:
                    association_id = as_text(association.get("id"))
                    sensor_id = as_text(association.get("sensor"))
                    if not association_id or not sensor_id:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO aranet.asset_sensor_association (
                            id, asset_id, measurement_point_id, sensor_id, probe_no,
                            placed_at, removed_at, raw_payload, synced_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT (id) DO UPDATE SET
                            asset_id = EXCLUDED.asset_id,
                            measurement_point_id = EXCLUDED.measurement_point_id,
                            sensor_id = EXCLUDED.sensor_id,
                            probe_no = EXCLUDED.probe_no,
                            placed_at = EXCLUDED.placed_at,
                            removed_at = EXCLUDED.removed_at,
                            raw_payload = EXCLUDED.raw_payload,
                            synced_at = CURRENT_TIMESTAMP
                        """,
                        (
                            association_id,
                            asset_id,
                            point_id,
                            sensor_id,
                            int(association.get("probe") or 0),
                            parse_datetime(association.get("placed")),
                            parse_datetime(association.get("removed")),
                            Jsonb(association),
                        ),
                    )

    def upsert_tag(self, item: dict[str, Any]) -> None:
        tag_id = as_text(item.get("id"))
        if not tag_id:
            return
        tag_type = item.get("type") or {}
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.tag (
                    id, name, notes, type_id, type_name, type_color, type_icon,
                    raw_payload, is_active, synced_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    notes = EXCLUDED.notes,
                    type_id = EXCLUDED.type_id,
                    type_name = EXCLUDED.type_name,
                    type_color = EXCLUDED.type_color,
                    type_icon = EXCLUDED.type_icon,
                    raw_payload = EXCLUDED.raw_payload,
                    is_active = true,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (
                    tag_id,
                    item.get("name"),
                    item.get("notes"),
                    as_text(tag_type.get("id")),
                    tag_type.get("name"),
                    as_text(tag_type.get("color")),
                    as_text(tag_type.get("icon")),
                    Jsonb(item),
                ),
            )
        self.snapshot("tag", tag_id, item)

    def replace_tag_assignments(self, entity_type: str, entities: Iterable[dict[str, Any]]) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM aranet.tag_assignment WHERE entity_type = %s",
                (entity_type,),
            )
            for entity in entities:
                entity_id = as_text(entity.get("id"))
                if not entity_id:
                    continue
                for tag_id in entity.get("tags") or []:
                    normalized_tag_id = as_text(tag_id)
                    if not normalized_tag_id:
                        continue
                    cursor.execute(
                        """
                        INSERT INTO aranet.tag_assignment
                            (entity_type, entity_id, tag_id, synced_at)
                        VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
                        ON CONFLICT DO NOTHING
                        """,
                        (entity_type, entity_id, normalized_tag_id),
                    )

    def upsert_attachment(
        self,
        entity_type: str,
        entity_id: str,
        item: dict[str, Any],
    ) -> None:
        attachment_id = as_text(item.get("id"))
        if not attachment_id:
            return
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.attachment (
                    entity_type, entity_id, attachment_id, name, mime_type, size_bytes,
                    file_url, thumbnail_url, source_created_at, raw_payload,
                    is_active, synced_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP)
                ON CONFLICT (entity_type, entity_id, attachment_id) DO UPDATE SET
                    name = EXCLUDED.name,
                    mime_type = EXCLUDED.mime_type,
                    size_bytes = EXCLUDED.size_bytes,
                    file_url = EXCLUDED.file_url,
                    thumbnail_url = EXCLUDED.thumbnail_url,
                    source_created_at = EXCLUDED.source_created_at,
                    raw_payload = EXCLUDED.raw_payload,
                    is_active = true,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (
                    entity_type,
                    entity_id,
                    attachment_id,
                    item.get("name"),
                    item.get("mimeType"),
                    item.get("size"),
                    item.get("file"),
                    item.get("thumbnail"),
                    parse_datetime(item.get("createdAt")),
                    Jsonb(item),
                ),
            )
        self.snapshot(f"{entity_type}_attachment", f"{entity_id}:{attachment_id}", item)

    def upsert_alarm_rule(self, item: dict[str, Any]) -> None:
        rule_id = as_text(item.get("id"))
        if not rule_id:
            return
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO aranet.alarm_rule (
                    id, name, metric_id, notes, source_created_at,
                    raw_payload, is_active, synced_at
                ) VALUES (%s, %s, %s, %s, %s, %s, true, CURRENT_TIMESTAMP)
                ON CONFLICT (id) DO UPDATE SET
                    name = EXCLUDED.name,
                    metric_id = EXCLUDED.metric_id,
                    notes = EXCLUDED.notes,
                    source_created_at = EXCLUDED.source_created_at,
                    raw_payload = EXCLUDED.raw_payload,
                    is_active = true,
                    synced_at = CURRENT_TIMESTAMP
                """,
                (
                    rule_id,
                    item.get("name"),
                    as_text(item.get("metric")),
                    item.get("notes"),
                    parse_datetime(item.get("created")),
                    Jsonb(item),
                ),
            )
        self.snapshot("alarm_rule", rule_id, item)

    def sensor_ids(self) -> list[str]:
        with self.connection.cursor() as cursor:
            cursor.execute("SELECT id FROM aranet.sensor WHERE is_active ORDER BY id")
            return [row[0] for row in cursor.fetchall()]
