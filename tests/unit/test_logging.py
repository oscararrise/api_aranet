from __future__ import annotations

import logging

from aranet_etl.logging_config import SecretRedactingFilter


def test_secret_filter_redacts_message_and_arguments() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="request key=%s",
        args=("super-secret",),
        exc_info=None,
    )

    assert SecretRedactingFilter(["super-secret"]).filter(record)
    assert record.getMessage() == "request key=***"
