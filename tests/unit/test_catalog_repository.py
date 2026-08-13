from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from aranet_etl.database.catalog_repository import CatalogRepository


def test_ensure_reference_builds_dynamic_table_query() -> None:
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value

    CatalogRepository(connection).ensure_reference("sensor_type", "type-1")

    query, parameters = cursor.execute.call_args.args
    rendered = query.as_string()
    assert 'INSERT INTO aranet."sensor_type"' in rendered
    assert parameters == ("type-1",)


def test_ensure_reference_rejects_unknown_table() -> None:
    with pytest.raises(ValueError, match="Unsupported reference table"):
        CatalogRepository(MagicMock()).ensure_reference("not_allowed", "value")
