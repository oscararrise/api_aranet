from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

import psycopg

from aranet_etl.config import DatabaseSettings
from aranet_etl.database.connection import database_connection
from aranet_etl.exceptions import DatabaseBootstrapError

LOGGER = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SQL_DIR = PROJECT_ROOT / "sql"


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    path: Path
    sql: str
    checksum: str


def discover_migrations(sql_dir: Path = DEFAULT_SQL_DIR) -> list[Migration]:
    migrations: list[Migration] = []
    for path in sorted(sql_dir.glob("[0-9][0-9][0-9]_*.sql")):
        if path.name.startswith("000_"):
            continue
        statement = path.read_text(encoding="utf-8")
        version, name = path.stem.split("_", 1)
        migrations.append(
            Migration(
                version=version,
                name=name,
                path=path,
                sql=statement,
                checksum=hashlib.sha256(statement.encode("utf-8")).hexdigest(),
            )
        )
    if not migrations:
        raise DatabaseBootstrapError(f"No SQL migrations found in {sql_dir}")
    return migrations


def apply_migrations(settings: DatabaseSettings, sql_dir: Path = DEFAULT_SQL_DIR) -> int:
    applied_count = 0
    migrations = discover_migrations(sql_dir)
    try:
        with database_connection(settings) as connection:
            for migration in migrations:
                with connection.transaction(), connection.cursor() as cursor:
                    cursor.execute("SELECT to_regclass('aranet.schema_migration')")
                    migration_table_exists = cursor.fetchone()[0] is not None
                    existing_checksum = None
                    if migration_table_exists:
                        cursor.execute(
                            "SELECT checksum FROM aranet.schema_migration WHERE version = %s",
                            (migration.version,),
                        )
                        row = cursor.fetchone()
                        existing_checksum = row[0] if row else None

                    if existing_checksum:
                        if existing_checksum != migration.checksum:
                            raise DatabaseBootstrapError(
                                f"Migration {migration.version} was modified after being applied"
                            )
                        LOGGER.debug("Migration already applied: %s", migration.path.name)
                        continue

                    LOGGER.info("Applying migration: %s", migration.path.name)
                    cursor.execute(migration.sql)
                    cursor.execute(
                        """
                            INSERT INTO aranet.schema_migration (version, name, checksum)
                            VALUES (%s, %s, %s)
                            ON CONFLICT (version) DO NOTHING
                            """,
                        (migration.version, migration.name, migration.checksum),
                    )
                    applied_count += 1
    except psycopg.Error as exc:
        raise DatabaseBootstrapError("PostgreSQL migration failed") from exc
    return applied_count
