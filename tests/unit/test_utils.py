from __future__ import annotations

from datetime import UTC, datetime

from aranet_etl.utils import chunked, parse_datetime, time_windows


def test_chunked_preserves_all_items() -> None:
    assert list(chunked(range(5), 2)) == [[0, 1], [2, 3], [4]]


def test_parse_datetime_accepts_zulu_and_rejects_invalid() -> None:
    assert parse_datetime("2026-08-13T10:30:00Z") == datetime(2026, 8, 13, 10, 30, tzinfo=UTC)
    assert parse_datetime("not-a-date") is None


def test_time_windows_do_not_exceed_end() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    end = datetime(2026, 1, 5, tzinfo=UTC)

    windows = list(time_windows(start, end, days=3))

    assert windows == [
        (datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 4, tzinfo=UTC)),
        (datetime(2026, 1, 4, tzinfo=UTC), datetime(2026, 1, 5, tzinfo=UTC)),
    ]
