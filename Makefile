.PHONY: install test test-unit test-integration lint serve

install:
	uv sync

test:
	uv run pytest tests/unit/

test-unit:
	uv run pytest tests/unit/ -v

test-integration:
	uv run pytest tests/integration/ -v -m integration

lint:
	uv run ruff check src/ tests/

serve:
	uv run python -m alaya.server
