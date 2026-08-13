from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from psycopg import Connection

from aranet_etl.config import DatabaseSettings


@contextmanager
def database_connection(settings: DatabaseSettings) -> Iterator[Connection]:
    connection = psycopg.connect(**settings.connection_kwargs)
    try:
        yield connection
    finally:
        connection.close()


def check_database_connection(settings: DatabaseSettings) -> dict[str, str | int]:
    with database_connection(settings) as connection, connection.cursor() as cursor:
        cursor.execute("SELECT current_database(), current_user, current_setting('server_version')")
        database, user, version = cursor.fetchone()
    return {"database": database, "user": user, "server_version": version}
