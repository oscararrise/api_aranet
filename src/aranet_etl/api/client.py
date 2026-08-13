from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from aranet_etl.config import AranetSettings
from aranet_etl.exceptions import AranetAPIError

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AranetPage:
    payload: dict[str, Any]
    next_url: str | None
    url: str
    status_code: int


class AranetClient:
    def __init__(
        self,
        settings: AranetSettings,
        *,
        session: requests.Session | None = None,
    ) -> None:
        self.settings = settings
        self.session = session or self._build_session()
        self._base_origin = self._origin(settings.base_url)

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        retry = Retry(
            total=self.settings.retries,
            connect=self.settings.retries,
            read=self.settings.retries,
            status=self.settings.retries,
            backoff_factor=0.8,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset({"GET"}),
            respect_retry_after_header=True,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=10, pool_maxsize=10)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        session.headers.update(
            {
                "ApiKey": self.settings.api_key,
                "Accept": "application/json",
                "User-Agent": "api-aranet/0.1",
            }
        )
        return session

    @staticmethod
    def _origin(url: str) -> tuple[str, str, int | None]:
        parsed = urlparse(url)
        return parsed.scheme, parsed.hostname or "", parsed.port

    def _validate_url(self, url: str) -> str:
        absolute = urljoin(f"{self.settings.base_url}/", url)
        if self._origin(absolute) != self._base_origin:
            raise AranetAPIError("Aranet pagination attempted to leave the configured API origin")
        return absolute

    def _next_url(self, response: requests.Response, payload: dict[str, Any]) -> str | None:
        raw_next = payload.get("next") or response.headers.get("NextLink")
        if not raw_next:
            return None
        raw_next = str(raw_next)
        if raw_next.startswith(("http://", "https://", "/")):
            return self._validate_url(raw_next)

        parsed = urlparse(response.url)
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["next"] = raw_next
        return self._validate_url(urlunparse(parsed._replace(query=urlencode(query, doseq=True))))

    def get_page(
        self,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> AranetPage:
        url = self._validate_url(path_or_url)
        LOGGER.debug("GET %s", urlparse(url).path)
        try:
            response = self.session.get(
                url,
                params=dict(params) if params else None,
                timeout=self.settings.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise AranetAPIError(f"Aranet request failed for {urlparse(url).path}") from exc

        if not 200 <= response.status_code < 300:
            message = f"Aranet returned HTTP {response.status_code} for {urlparse(url).path}"
            try:
                error_payload = response.json()
                warnings = (
                    (error_payload.get("error") or []) if isinstance(error_payload, dict) else []
                )
                descriptions = [
                    str(item.get("message"))
                    for item in warnings
                    if isinstance(item, Mapping) and item.get("message")
                ]
                if descriptions:
                    message = f"{message}: {'; '.join(descriptions)}"
            except (ValueError, AttributeError):
                pass
            raise AranetAPIError(message)

        try:
            payload = response.json()
        except ValueError as exc:
            raise AranetAPIError(
                f"Aranet returned non-JSON content for {urlparse(url).path}"
            ) from exc
        if not isinstance(payload, dict):
            raise AranetAPIError(
                f"Aranet returned an unexpected JSON shape for {urlparse(url).path}"
            )

        warnings = payload.get("error") or []
        for warning in warnings:
            message = (
                warning.get("message", "unknown warning")
                if isinstance(warning, Mapping)
                else "unknown warning"
            )
            LOGGER.warning("Aranet warning: %s", message)

        return AranetPage(
            payload=payload,
            next_url=self._next_url(response, payload),
            url=response.url,
            status_code=response.status_code,
        )

    def get_json(
        self,
        path_or_url: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.get_page(path_or_url, params=params).payload

    def iter_pages(
        self,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
    ) -> Iterator[AranetPage]:
        next_url: str | None = path
        next_params = params
        visited: set[str] = set()
        while next_url:
            page = self.get_page(next_url, params=next_params)
            next_params = None
            yield page
            if not page.next_url:
                return
            if page.next_url in visited:
                raise AranetAPIError("Aranet returned a repeating pagination link")
            visited.add(page.next_url)
            next_url = page.next_url

    def close(self) -> None:
        self.session.close()

    def __enter__(self) -> AranetClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
