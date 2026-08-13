#!/usr/bin/env python3
"""Validate both PostgreSQL and Aranet Cloud connectivity."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aranet_etl.cli import main  # noqa: E402

if __name__ == "__main__":
    database_result = main(["check-db"])
    if database_result:
        raise SystemExit(database_result)
    raise SystemExit(main(["check-api"]))
