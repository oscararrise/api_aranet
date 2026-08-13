from __future__ import annotations

import argparse
import json
import logging
from datetime import UTC, datetime
from typing import Any

from aranet_etl.api.client import AranetClient
from aranet_etl.config import Settings
from aranet_etl.database.bootstrap import ensure_database_exists
from aranet_etl.database.connection import check_database_connection, database_connection
from aranet_etl.database.migrations import apply_migrations
from aranet_etl.exceptions import AranetETLError, ConfigurationError
from aranet_etl.logging_config import configure_logging
from aranet_etl.services.orchestrator import SyncOrchestrator

LOGGER = logging.getLogger(__name__)


def _datetime_argument(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Use an ISO-8601 date or datetime") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Synchronize Aranet Cloud metadata and time series into PostgreSQL"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("init-db", help="Create the database, schema, tables, indexes, and views")
    subparsers.add_parser("check-db", help="Validate the PostgreSQL connection")
    subparsers.add_parser(
        "check-api", help="Validate the Aranet API key without printing sensor values"
    )
    subparsers.add_parser("sync-catalogs", help="Synchronize all metadata catalogs")

    backfill = subparsers.add_parser("backfill", help="Load all historical data in bounded windows")
    backfill.add_argument("--from", dest="start", type=_datetime_argument)
    backfill.add_argument("--to", dest="end", type=_datetime_argument)

    incremental = subparsers.add_parser(
        "sync-incremental", help="Synchronize new data with an overlap window; intended for cron"
    )
    incremental.add_argument(
        "--refresh-catalogs",
        action="store_true",
        help="Force a catalog refresh even when the catalog watermark is fresh",
    )
    subparsers.add_parser(
        "sync-all",
        help="Run a backfill on a fresh database; otherwise run an incremental synchronization",
    )
    gaps = subparsers.add_parser("reconcile-gaps", help="Retry historical ranges that failed")
    gaps.add_argument("--limit", type=int, default=10)
    return parser


def _prepare_database(settings: Settings) -> dict[str, Any]:
    created = ensure_database_exists(settings.database)
    migrations = apply_migrations(settings.database)
    connection = check_database_connection(settings.database)
    LOGGER.info(
        "Database ready: database=%s user=%s server_version=%s created=%s migrations=%s",
        connection["database"],
        connection["user"],
        connection["server_version"],
        created,
        migrations,
    )
    return {"created": created, "migrations_applied": migrations, **connection}


def _check_api(settings: Settings) -> dict[str, int]:
    endpoints = {
        "bases": ("/api/v1/bases", "bases"),
        "sensors": ("/api/v1/sensors", "sensors"),
        "assets": ("/api/v1/assets", "assets"),
        "metrics": ("/api/v1/metrics", "metrics"),
        "sensor_types": ("/api/v1/sensors/types", "sensorTypes"),
        "tags": ("/api/v1/tags", "tags"),
        "alarm_rules": ("/api/v1/alarms/rules", "rules"),
    }
    counts: dict[str, int] = {}
    with AranetClient(settings.aranet) as client:
        for name, (path, key) in endpoints.items():
            payload = client.get_json(path)
            counts[name] = len(payload.get(key) or [])
    LOGGER.info("Aranet API connection successful: %s", counts)
    return counts


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    require_api = args.command not in {"init-db", "check-db"}
    try:
        settings = Settings.load(require_api_key=require_api)
        configure_logging(
            settings.log_level,
            log_dir=settings.log_dir,
            secrets=[settings.aranet.api_key, settings.database.password],
        )

        if args.command == "init-db":
            print(json.dumps(_prepare_database(settings), default=str, indent=2))
            return 0
        if args.command == "check-db":
            print(json.dumps(check_database_connection(settings.database), default=str, indent=2))
            return 0
        if args.command == "check-api":
            print(json.dumps(_check_api(settings), indent=2))
            return 0

        _prepare_database(settings)
        with (
            AranetClient(settings.aranet) as client,
            database_connection(settings.database) as connection,
        ):
            orchestrator = SyncOrchestrator(settings, client, connection)
            if args.command == "sync-catalogs":
                result = orchestrator.sync_catalogs()
            elif args.command == "backfill":
                result = orchestrator.backfill(start=args.start, end=args.end)
            elif args.command == "sync-incremental":
                result = orchestrator.sync_incremental(
                    refresh_catalogs=True if args.refresh_catalogs else None
                )
            elif args.command == "sync-all":
                result = orchestrator.sync_all()
            elif args.command == "reconcile-gaps":
                result = orchestrator.reconcile_gaps(limit=args.limit)
            else:  # pragma: no cover
                raise RuntimeError(f"Unsupported command: {args.command}")
        print(json.dumps(result, default=str, indent=2))
        return 0
    except (AranetETLError, ConfigurationError, ValueError) as exc:
        logging.getLogger(__name__).error("%s", exc)
        return 1
    except KeyboardInterrupt:
        logging.getLogger(__name__).warning("Interrupted by user")
        return 130
