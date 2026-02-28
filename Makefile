.PHONY: help install test test-unit test-integration lint serve
.DEFAULT_GOAL := help

help:
	@awk 'BEGIN {FS = ":.*##"}; \
		/^[a-zA-Z0-9_-]+:.*?##/ { printf "  %-20s %s\n", $$1, $$2 } \
		/^##@/ { printf "\n%s\n", substr($$0, 5) }' $(MAKEFILE_LIST)

##@ Setup
install: ## Install dependencies
	uv sync

##@ Testing
test: ## Run unit tests
	uv run pytest tests/unit/

test-unit: ## Run unit tests with verbose output
	uv run pytest tests/unit/ -v

test-integration: ## Run integration tests
	uv run pytest tests/integration/ -v -m integration

##@ Development
lint: ## Lint source and tests
	uv run ruff check src/ tests/

serve: ## Start the server
	uv run python -m alaya.server
