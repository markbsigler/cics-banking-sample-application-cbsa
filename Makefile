.DEFAULT_GOAL := help

.PHONY: help setup test lint fmt format-check typecheck check clean

## List the available targets.
help:
	@printf '%s\n' \
		'Usage: make <target>' \
		'' \
		'Targets:' \
		'  setup         Install Python development dependencies with uv' \
		'  test          Run the Python test suite with coverage' \
		'  lint          Lint the Python utility and tests' \
		'  fmt           Auto-fix and format the Python code' \
		'  format-check  Check Python formatting' \
		'  typecheck     Type-check with strict mypy' \
		'  check         Run lint, format check, typecheck, and tests' \
		'  clean         Remove Python caches and coverage output'

## Install Python development dependencies.
setup:
	uv sync

## Run the Python test suite with coverage.
test:
	uv run pytest

## Lint the Python utility and tests.
lint:
	uv run ruff check bankdata_setup.py tests

## Auto-fix and format the Python code.
fmt:
	uv run ruff check --fix bankdata_setup.py tests
	uv run ruff format bankdata_setup.py tests

## Check Python formatting.
format-check:
	uv run ruff format --check bankdata_setup.py tests

## Type-check with strict mypy.
typecheck:
	uv run mypy

## Run all Python checks.
check: lint format-check typecheck test

## Remove Python caches and coverage output.
clean:
	rm -rf .mypy_cache .pytest_cache .ruff_cache .coverage htmlcov
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
