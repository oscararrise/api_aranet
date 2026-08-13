from __future__ import annotations

from datetime import datetime

from psycopg import Connection


def ensure_month_partitions(
    connection: Connection,
    table_name: str,
    moments: set[datetime],
) -> None:
    if not moments:
        return
    with connection.cursor() as cursor:
        for moment in sorted(moments):
            cursor.execute(
                "SELECT aranet.ensure_month_partition(%s, %s)",
                (table_name, moment),
            )
