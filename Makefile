# Common developer commands. Run `make help` to list them.
VENV ?= .intergrate_venv
PY   := $(VENV)/bin/python

.PHONY: help install install-dev lint format typecheck test cov check run clean

help:  ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'

install:  ## Install app with vision models
	$(PY) -m pip install -e ".[vision]"

install-dev:  ## Install app, vision models and dev tools, plus git hooks
	$(PY) -m pip install -e ".[vision,dev]"
	$(VENV)/bin/pre-commit install

lint:  ## Check style and likely bugs (ruff)
	$(VENV)/bin/ruff check src tests
	$(VENV)/bin/ruff format --check src tests

format:  ## Auto-fix style (ruff)
	$(VENV)/bin/ruff check --fix src tests
	$(VENV)/bin/ruff format src tests

typecheck:  ## Static type check (mypy)
	$(VENV)/bin/mypy

test:  ## Run unit tests
	$(PY) -m pytest

cov:  ## Run tests with coverage report
	$(PY) -m pytest --cov --cov-report=term-missing

check: lint typecheck test  ## Everything CI runs

run:  ## Start the system
	$(PY) -m fall_detector

clean:  ## Remove caches
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
