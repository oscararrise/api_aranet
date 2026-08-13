from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv

from aranet_etl.exceptions import ConfigurationError


def _env_int(name: str, default: int, *, minimum: int = 1) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigurationError(f"{name} must be at least {minimum}")
    return value


def _optional_datetime(name: str) -> datetime | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ConfigurationError(
            f"{name} must use ISO-8601 format, for example 2026-01-01T00:00:00+00:00"
        ) from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    host: str
    port: int
    database: str
    user: str
    password: str
    sslmode: str
    connect_timeout: int
    admin_database: str

    @property
    def connection_kwargs(self) -> dict[str, str | int]:
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.database,
            "user": self.user,
            "password": self.password,
            "sslmode": self.sslmode,
            "connect_timeout": self.connect_timeout,
            "application_name": "api_aranet",
        }

    @property
    def admin_connection_kwargs(self) -> dict[str, str | int]:
        values = self.connection_kwargs.copy()
        values["dbname"] = self.admin_database
        values["application_name"] = "api_aranet_bootstrap"
        return values

    @property
    def safe_dsn(self) -> str:
        return (
            f"postgresql://{quote_plus(self.user)}:***@{self.host}:{self.port}/"
            f"{quote_plus(self.database)}?sslmode={quote_plus(self.sslmode)}"
        )


@dataclass(frozen=True, slots=True)
class AranetSettings:
    base_url: str
    api_key: str
    timeout_seconds: int
    retries: int
    page_limit: int
    sensor_batch_size: int


@dataclass(frozen=True, slots=True)
class SyncSettings:
    backfill_from: datetime | None
    backfill_window_days: int
    incremental_overlap_minutes: int
    initial_lookback_hours: int
    catalog_refresh_hours: int
    reconciliation_lookback_days: int
    reconciliation_interval_hours: int


@dataclass(frozen=True, slots=True)
class Settings:
    database: DatabaseSettings
    aranet: AranetSettings
    sync: SyncSettings
    log_level: str
    log_dir: Path | None

    @classmethod
    def load(cls, *, require_api_key: bool = True) -> Settings:
        load_dotenv(override=False)

        api_key = os.getenv("ARANET_API_KEY", "").strip()
        if require_api_key and not api_key:
            raise ConfigurationError("ARANET_API_KEY is required for this command")

        database = DatabaseSettings(
            host=os.getenv("PGHOST", "localhost"),
            port=_env_int("PGPORT", 5432),
            database=os.getenv("PGDATABASE", "agro_platform"),
            user=os.getenv("PGUSER", "postgres"),
            password=os.getenv("PGPASSWORD", ""),
            sslmode=os.getenv("PGSSLMODE", "prefer"),
            connect_timeout=_env_int("PGCONNECT_TIMEOUT", 10),
            admin_database=os.getenv("PGADMIN_DATABASE", "postgres"),
        )
        aranet = AranetSettings(
            base_url=os.getenv("ARANET_API_BASE_URL", "https://aranet.cloud").rstrip("/"),
            api_key=api_key,
            timeout_seconds=_env_int("ARANET_HTTP_TIMEOUT_SECONDS", 30),
            retries=_env_int("ARANET_HTTP_RETRIES", 5, minimum=0),
            page_limit=_env_int("ARANET_PAGE_LIMIT", 10_000),
            sensor_batch_size=_env_int("ARANET_SENSOR_BATCH_SIZE", 10),
        )
        sync = SyncSettings(
            backfill_from=_optional_datetime("ARANET_BACKFILL_FROM"),
            backfill_window_days=_env_int("ARANET_BACKFILL_WINDOW_DAYS", 30),
            incremental_overlap_minutes=_env_int("ARANET_INCREMENTAL_OVERLAP_MINUTES", 30),
            initial_lookback_hours=_env_int("ARANET_INITIAL_LOOKBACK_HOURS", 24),
            catalog_refresh_hours=_env_int("ARANET_CATALOG_REFRESH_HOURS", 6),
            reconciliation_lookback_days=_env_int("ARANET_RECONCILIATION_LOOKBACK_DAYS", 7),
            reconciliation_interval_hours=_env_int("ARANET_RECONCILIATION_INTERVAL_HOURS", 24),
        )

        raw_log_dir = os.getenv("LOG_DIR", "logs").strip()
        return cls(
            database=database,
            aranet=aranet,
            sync=sync,
            log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
            log_dir=Path(raw_log_dir) if raw_log_dir else None,
        )
