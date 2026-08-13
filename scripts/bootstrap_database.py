#!/usr/bin/env python3
"""Convenience wrapper for `python main.py init-db`."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from aranet_etl.cli import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main(["init-db"]))
