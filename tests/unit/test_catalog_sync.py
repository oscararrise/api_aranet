from __future__ import annotations

from contextlib import nullcontext
from unittest.mock import MagicMock, call

from aranet_etl.exceptions import AranetAPIError
from aranet_etl.services import catalog_sync
from aranet_etl.services.catalog_sync import CatalogSyncService


def _api_payloads() -> dict[str, dict]:
    return {
        "/api/v1/sensors/types": {"sensorTypes": [{"id": "type-1"}]},
        "/api/v1/sensors/types/type/type-1": {"sensorType": {"id": "type-1"}},
        "/api/v1/metrics": {"metrics": [{"id": "metric-1"}]},
        "/api/v1/metrics/metric-1": {"metric": {"id": "metric-1", "units": [{"id": "unit-1"}]}},
        "/api/v1/units/unit/unit-1": {"unit": {"id": "unit-1", "precision": 2}},
        "/api/v1/bases": {"bases": [{"id": "base-1"}]},
        "/api/v1/bases/base/base-1": {"base": {"id": "base-1", "tags": ["tag-1"]}},
        "/api/v1/sensors": {"sensors": [{"id": "sensor-1"}]},
        "/api/v1/sensors/sensor/sensor-1": {
            "sensor": {
                "id": "sensor-1",
                "type": "type-1",
                "pairing": [{"base": "base-1"}],
                "skills": [{"metric": "metric-1"}],
                "tags": ["tag-1"],
                "files": [{"href": "/attachment/sensor-1/file-1"}],
            }
        },
        "/api/v1/assets": {"assets": [{"id": "asset-1"}]},
        "/api/v1/assets/asset/asset-1": {
            "asset": {
                "id": "asset-1",
                "tags": ["tag-1"],
                "points": [
                    {
                        "id": "point-1",
                        "skills": [{"metric": "metric-1"}],
                        "associations": [{"id": "assoc-1", "sensor": "sensor-1"}],
                    }
                ],
            }
        },
        "/api/v1/tags": {"tags": [{"id": "tag-1"}]},
        "/api/v1/tags/tag/tag-1": {"tag": {"id": "tag-1"}},
        "/api/v1/alarms/rules": {"rules": [{"id": "rule-1"}]},
        "/api/v1/alarms/rules/rule/rule-1": {"rule": {"id": "rule-1"}},
        "/attachment/sensor-1/file-1": {
            "attachment_info": {"id": "file-1", "mimeType": "image/jpeg"}
        },
    }


class FakeClient:
    def __init__(self, payloads: dict[str, dict], *, broken_attachment: bool = False) -> None:
        self.payloads = payloads
        self.broken_attachment = broken_attachment
        self.calls: list[str] = []

    def get_json(self, path: str) -> dict:
        self.calls.append(path)
        if self.broken_attachment and path.startswith("/attachment/"):
            raise AranetAPIError("attachment temporarily unavailable")
        return self.payloads[path]


def _run_catalog_sync(monkeypatch, *, broken_attachment: bool = False):
    repository = MagicMock()
    monkeypatch.setattr(catalog_sync, "CatalogRepository", lambda _connection: repository)
    connection = MagicMock()
    connection.transaction.return_value = nullcontext()
    client = FakeClient(_api_payloads(), broken_attachment=broken_attachment)

    result = CatalogSyncService(client, connection).sync()
    return result, client, repository


def test_catalog_sync_reads_every_json_detail_endpoint(monkeypatch) -> None:
    result, client, repository = _run_catalog_sync(monkeypatch)

    assert result.rows == 9
    assert result.attachment_scan_complete is True
    assert set(client.calls) == set(_api_payloads())
    assert repository.mark_all_inactive.call_args_list[-1] == call("attachment")
    assert call("sensor_type", "type-1") in repository.ensure_reference.call_args_list
    assert call("base_station", "base-1") in repository.ensure_reference.call_args_list
    assert call("metric", "metric-1") in repository.ensure_reference.call_args_list
    assert call("sensor", "sensor-1") in repository.ensure_reference.call_args_list
    assert call("tag", "tag-1") in repository.ensure_reference.call_args_list


def test_incomplete_attachment_scan_does_not_inactivate_existing_rows(monkeypatch) -> None:
    result, _, repository = _run_catalog_sync(monkeypatch, broken_attachment=True)

    assert result.attachment_scan_complete is False
    assert call("attachment") not in repository.mark_all_inactive.call_args_list
