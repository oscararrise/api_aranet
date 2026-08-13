from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from psycopg import Connection

from aranet_etl.api.client import AranetClient
from aranet_etl.database.catalog_repository import CatalogRepository
from aranet_etl.exceptions import AranetAPIError
from aranet_etl.utils import as_text

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class CatalogSyncResult:
    bases: int
    sensors: int
    assets: int
    metrics: int
    units: int
    sensor_types: int
    tags: int
    alarm_rules: int
    attachments: int
    attachment_scan_complete: bool

    @property
    def rows(self) -> int:
        return sum(
            (
                self.bases,
                self.sensors,
                self.assets,
                self.metrics,
                self.units,
                self.sensor_types,
                self.tags,
                self.alarm_rules,
                self.attachments,
            )
        )


class CatalogSyncService:
    def __init__(self, client: AranetClient, connection: Connection) -> None:
        self.client = client
        self.connection = connection

    def _details(
        self,
        collection: list[dict[str, Any]],
        *,
        path_template: str,
        response_key: str,
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for item in collection:
            item_id = as_text(item.get("id"))
            if not item_id:
                continue
            payload = self.client.get_json(path_template.format(id=quote(item_id, safe="")))
            result.append(payload.get(response_key) or item)
        return result

    def _attachment_metadata(
        self,
        entity_type: str,
        entities: list[dict[str, Any]],
    ) -> tuple[list[tuple[str, str, dict[str, Any]]], bool]:
        result: list[tuple[str, str, dict[str, Any]]] = []
        complete = True
        for entity in entities:
            entity_id = as_text(entity.get("id"))
            if not entity_id:
                continue
            for file_desc in entity.get("files") or []:
                href = file_desc.get("href")
                if not href:
                    continue
                try:
                    response = self.client.get_json(str(href))
                except AranetAPIError as exc:
                    complete = False
                    LOGGER.warning(
                        "Could not read %s attachment metadata for entity %s: %s",
                        entity_type,
                        entity_id,
                        exc,
                    )
                    continue
                metadata = response.get("attachment_info") or {}
                if metadata:
                    result.append((entity_type, entity_id, metadata))
        return result, complete

    def sync(self) -> CatalogSyncResult:
        sensor_type_list = self.client.get_json("/api/v1/sensors/types").get("sensorTypes") or []
        sensor_types = self._details(
            sensor_type_list,
            path_template="/api/v1/sensors/types/type/{id}",
            response_key="sensorType",
        )
        metric_list = self.client.get_json("/api/v1/metrics").get("metrics") or []
        metrics = self._details(
            metric_list,
            path_template="/api/v1/metrics/{id}",
            response_key="metric",
        )

        units_by_id: dict[str, dict[str, Any]] = {}
        for metric in metrics:
            for unit in metric.get("units") or []:
                unit_id = as_text(unit.get("id"))
                if unit_id:
                    units_by_id[unit_id] = {**units_by_id.get(unit_id, {}), **unit}
        for unit_id, unit in list(units_by_id.items()):
            try:
                detail = self.client.get_json(f"/api/v1/units/unit/{quote(unit_id, safe='')}")
                units_by_id[unit_id] = {**unit, **(detail.get("unit") or {})}
            except AranetAPIError as exc:
                LOGGER.warning("Could not enrich unit %s: %s", unit_id, exc)

        base_list = self.client.get_json("/api/v1/bases").get("bases") or []
        bases = self._details(
            base_list,
            path_template="/api/v1/bases/base/{id}",
            response_key="base",
        )

        sensor_list = self.client.get_json("/api/v1/sensors").get("sensors") or []
        sensors = self._details(
            sensor_list,
            path_template="/api/v1/sensors/sensor/{id}",
            response_key="sensor",
        )

        asset_list = self.client.get_json("/api/v1/assets").get("assets") or []
        assets = self._details(
            asset_list,
            path_template="/api/v1/assets/asset/{id}",
            response_key="asset",
        )
        tag_list = self.client.get_json("/api/v1/tags").get("tags") or []
        tags = self._details(
            tag_list,
            path_template="/api/v1/tags/tag/{id}",
            response_key="tag",
        )
        rule_list = self.client.get_json("/api/v1/alarms/rules").get("rules") or []
        rules = self._details(
            rule_list,
            path_template="/api/v1/alarms/rules/rule/{id}",
            response_key="rule",
        )

        sensor_attachments, sensor_attachments_complete = self._attachment_metadata(
            "sensor", sensors
        )
        asset_attachments, asset_attachments_complete = self._attachment_metadata("asset", assets)
        attachments = [*sensor_attachments, *asset_attachments]
        attachment_scan_complete = sensor_attachments_complete and asset_attachments_complete

        repository = CatalogRepository(self.connection)
        with self.connection.transaction():
            for table in (
                "sensor_type",
                "metric",
                "unit",
                "base_station",
                "sensor",
                "asset",
                "tag",
                "alarm_rule",
            ):
                repository.mark_all_inactive(table)
            if attachment_scan_complete:
                repository.mark_all_inactive("attachment")

            for item in sensor_types:
                repository.upsert_sensor_type(item)
            for item in sensors:
                sensor_type_id = as_text(item.get("type"))
                if sensor_type_id:
                    repository.ensure_reference("sensor_type", sensor_type_id)

            for item in metrics:
                repository.upsert_metric(item)
            for item in units_by_id.values():
                repository.upsert_unit(item)
            for metric in metrics:
                metric_id = as_text(metric.get("id"))
                if metric_id:
                    repository.replace_metric_units(metric_id, metric.get("units") or [])

            for item in bases:
                repository.upsert_base_station(item)
            for item in sensors:
                repository.upsert_sensor(item)
            for item in sensors:
                for pairing in item.get("pairing") or []:
                    base_id = as_text(pairing.get("base"))
                    if base_id:
                        repository.ensure_reference("base_station", base_id)
                for skill in item.get("skills") or []:
                    metric_id = as_text(skill.get("metric"))
                    if metric_id:
                        repository.ensure_reference("metric", metric_id)
                sensor_id = as_text(item.get("id"))
                if sensor_id:
                    repository.replace_sensor_details(sensor_id, item)

            for item in assets:
                repository.upsert_asset(item)
            for item in assets:
                for point in item.get("points") or []:
                    for skill in point.get("skills") or []:
                        metric_id = as_text(skill.get("metric"))
                        if metric_id:
                            repository.ensure_reference("metric", metric_id)
                    for association in point.get("associations") or []:
                        sensor_id = as_text(association.get("sensor"))
                        if sensor_id:
                            repository.ensure_reference("sensor", sensor_id)
                asset_id = as_text(item.get("id"))
                if asset_id:
                    repository.replace_asset_details(asset_id, item)

            for item in tags:
                repository.upsert_tag(item)
            for entity in [*bases, *sensors, *assets]:
                for tag_id in entity.get("tags") or []:
                    normalized_tag_id = as_text(tag_id)
                    if normalized_tag_id:
                        repository.ensure_reference("tag", normalized_tag_id)
            repository.replace_tag_assignments("base_station", bases)
            repository.replace_tag_assignments("sensor", sensors)
            repository.replace_tag_assignments("asset", assets)

            for entity_type, entity_id, item in attachments:
                repository.upsert_attachment(entity_type, entity_id, item)
            for item in rules:
                repository.upsert_alarm_rule(item)

        result = CatalogSyncResult(
            bases=len(bases),
            sensors=len(sensors),
            assets=len(assets),
            metrics=len(metrics),
            units=len(units_by_id),
            sensor_types=len(sensor_types),
            tags=len(tags),
            alarm_rules=len(rules),
            attachments=len(attachments),
            attachment_scan_complete=attachment_scan_complete,
        )
        LOGGER.info(
            "Catalog sync completed: bases=%s sensors=%s assets=%s metrics=%s units=%s "
            "sensor_types=%s tags=%s alarm_rules=%s attachments=%s attachment_scan_complete=%s",
            result.bases,
            result.sensors,
            result.assets,
            result.metrics,
            result.units,
            result.sensor_types,
            result.tags,
            result.alarm_rules,
            result.attachments,
            result.attachment_scan_complete,
        )
        return result
