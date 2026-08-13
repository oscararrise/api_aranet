from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aranet_etl.config import Settings
from aranet_etl.exceptions import ConfigurationError


def test_settings_require_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ARANET_API_KEY", raising=False)
    with pytest.raises(ConfigurationError, match="ARANET_API_KEY"):
        Settings.load(require_api_key=True)


def test_settings_allow_database_only_command(monkeypatch) -> None:
    monkeypatch.delenv("ARANET_API_KEY", raising=False)
    monkeypatch.setenv("PGDATABASE", "agro_test")

    settings = Settings.load(require_api_key=False)

    assert settings.database.database == "agro_test"
    assert settings.aranet.api_key == ""
    assert settings.sync.reconciliation_lookback_days == 7
    assert settings.sync.reconciliation_interval_hours == 24


def test_backfill_date_is_normalized_to_utc(monkeypatch) -> None:
    monkeypatch.setenv("ARANET_API_KEY", "fake")
    monkeypatch.setenv("ARANET_BACKFILL_FROM", "2026-01-01T05:00:00-05:00")

    settings = Settings.load()

    assert settings.sync.backfill_from == datetime(2026, 1, 1, 10, tzinfo=UTC)


def test_invalid_integer_fails_early(monkeypatch) -> None:
    monkeypatch.setenv("ARANET_API_KEY", "fake")
    monkeypatch.setenv("ARANET_PAGE_LIMIT", "many")

    with pytest.raises(ConfigurationError, match="ARANET_PAGE_LIMIT must be an integer"):
        Settings.load()
