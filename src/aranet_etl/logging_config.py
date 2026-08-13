from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path


class SecretRedactingFilter(logging.Filter):
    def __init__(self, secrets: list[str] | None = None) -> None:
        super().__init__()
        self._secrets = [secret for secret in (secrets or []) if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        rendered = record.getMessage()
        for secret in self._secrets:
            rendered = rendered.replace(secret, "***")
        record.msg = rendered
        record.args = ()
        return True


def configure_logging(
    level: str = "INFO", *, log_dir: Path | None = None, secrets: list[str] | None = None
) -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    redactor = SecretRedactingFilter(secrets)

    stream = logging.StreamHandler(sys.stdout)
    stream.setFormatter(formatter)
    stream.addFilter(redactor)
    root.addHandler(stream)

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_dir / "aranet_sync.log",
            maxBytes=10 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(redactor)
        root.addHandler(file_handler)
