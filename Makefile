PYTHON ?= .venv/bin/python
PIP ?= .venv/bin/pip

.PHONY: install install-dev lint test init-db check-api backfill sync-incremental

install:
	$(PIP) install -r requirements.txt

install-dev:
	$(PIP) install -r requirements-dev.txt

lint:
	.venv/bin/ruff format --check .
	.venv/bin/ruff check .

test:
	$(PYTHON) -m pytest -m "not integration"

init-db:
	$(PYTHON) main.py init-db

check-api:
	$(PYTHON) main.py check-api

backfill:
	$(PYTHON) main.py backfill

sync-incremental:
	$(PYTHON) main.py sync-incremental

