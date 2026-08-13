from __future__ import annotations

import responses

from aranet_etl.api.client import AranetClient
from aranet_etl.exceptions import AranetAPIError


@responses.activate
def test_api_key_header_is_sent(api_settings) -> None:
    responses.get("https://aranet.example/api/v1/sensors", json={"sensors": []})

    with AranetClient(api_settings) as client:
        payload = client.get_json("/api/v1/sensors")

    assert payload == {"sensors": []}
    assert responses.calls[0].request.headers["ApiKey"] == "test-secret-key"


@responses.activate
def test_paginates_using_nextlink_header(api_settings) -> None:
    first_url = "https://aranet.example/api/v1/measurements/history?limit=1"
    second_url = "https://aranet.example/api/v1/measurements/history?next=token-2"
    responses.get(
        first_url,
        json={"readings": [{"value": 1}]},
        headers={"NextLink": second_url},
    )
    responses.get(second_url, json={"readings": [{"value": 2}]})

    with AranetClient(api_settings) as client:
        pages = list(client.iter_pages("/api/v1/measurements/history", params={"limit": "1"}))

    assert [page.payload["readings"][0]["value"] for page in pages] == [1, 2]


@responses.activate
def test_paginates_using_body_next_token(api_settings) -> None:
    first_url = "https://aranet.example/api/v1/telemetry/history?limit=1"
    second_url = "https://aranet.example/api/v1/telemetry/history?limit=1&next=abc"
    responses.get(first_url, json={"readings": [], "next": "abc"})
    responses.get(second_url, json={"readings": []})

    with AranetClient(api_settings) as client:
        pages = list(client.iter_pages("/api/v1/telemetry/history", params={"limit": "1"}))

    assert len(pages) == 2


@responses.activate
def test_treats_opaque_next_value_with_slash_as_a_token(api_settings) -> None:
    first_url = "https://aranet.example/api/v1/telemetry/history?limit=1"
    second_url = "https://aranet.example/api/v1/telemetry/history?limit=1&next=abc%2Fdef"
    responses.get(first_url, json={"readings": [], "next": "abc/def"})
    responses.get(second_url, json={"readings": []})

    with AranetClient(api_settings) as client:
        pages = list(client.iter_pages("/api/v1/telemetry/history", params={"limit": "1"}))

    assert len(pages) == 2


@responses.activate
def test_rejects_cross_origin_pagination(api_settings) -> None:
    responses.get(
        "https://aranet.example/api/v1/measurements/history",
        json={"readings": [], "next": "https://attacker.example/steal"},
    )

    with AranetClient(api_settings) as client:
        try:
            client.get_page("/api/v1/measurements/history")
        except AranetAPIError as exc:
            assert "leave the configured API origin" in str(exc)
        else:  # pragma: no cover
            raise AssertionError("Expected cross-origin pagination to fail")


@responses.activate
def test_surfaces_api_error_without_response_body_dump(api_settings) -> None:
    responses.get(
        "https://aranet.example/api/v1/measurements/history",
        status=400,
        json={"error": [{"message": "Sensor parameter required"}]},
    )

    with AranetClient(api_settings) as client:
        try:
            client.get_json("/api/v1/measurements/history")
        except AranetAPIError as exc:
            assert str(exc).endswith("Sensor parameter required")
            assert "test-secret-key" not in str(exc)
        else:  # pragma: no cover
            raise AssertionError("Expected HTTP 400 to fail")
