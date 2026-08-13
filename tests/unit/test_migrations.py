from __future__ import annotations

from aranet_etl.database.migrations import discover_migrations


def test_migrations_are_ordered_and_database_script_is_excluded() -> None:
    migrations = discover_migrations()

    assert [migration.version for migration in migrations] == [
        "001",
        "002",
        "003",
        "004",
        "005",
        "006",
    ]
    assert all(len(migration.checksum) == 64 for migration in migrations)
