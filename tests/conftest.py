from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from aranet_etl.config import AranetSettings, DatabaseSettings


@pytest.fixture
def api_settings() -> AranetSettings:
    return AranetSettings(
        base_url="https://aranet.example",
        api_key="test-secret-key",
        timeout_seconds=5,
        retries=0,
        page_limit=100,
        sensor_batch_size=10,
    )


@pytest.fixture
def postgres_settings() -> Iterator[DatabaseSettings]:
    if os.getenv("RUN_POSTGRES_TESTS") != "1":
        pytest.skip("Set RUN_POSTGRES_TESTS=1 to run PostgreSQL integration tests")
    yield DatabaseSettings(
        host=os.getenv("PGHOST", "localhost"),
        port=int(os.getenv("PGPORT", "5432")),
        database=os.getenv("PGDATABASE", "agro_platform"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "postgres"),
        sslmode=os.getenv("PGSSLMODE", "disable"),
        connect_timeout=10,
        admin_database=os.getenv("PGADMIN_DATABASE", "postgres"),
    )
