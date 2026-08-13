from __future__ import annotations

import logging

import psycopg
from psycopg import sql

from aranet_etl.config import DatabaseSettings
from aranet_etl.exceptions import DatabaseBootstrapError

LOGGER = logging.getLogger(__name__)


def ensure_database_exists(settings: DatabaseSettings) -> bool:
    """Create the target database when absent. Returns True when it was created."""
    try:
        with (
            psycopg.connect(**settings.admin_connection_kwargs, autocommit=True) as connection,
            connection.cursor() as cursor,
        ):
            cursor.execute(
                "SELECT EXISTS (SELECT 1 FROM pg_database WHERE datname = %s)",
                (settings.database,),
            )
            if cursor.fetchone()[0]:
                LOGGER.info("Target database already exists: %s", settings.database)
                return False
            cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(settings.database)))
            LOGGER.info("Created target database: %s", settings.database)
            return True
    except psycopg.Error as exc:
        raise DatabaseBootstrapError(
            "Could not create or inspect the target database. Verify PGADMIN_DATABASE and "
            "that PGUSER has CONNECT and CREATEDB privileges."
        ) from exc
