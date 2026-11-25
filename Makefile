.PHONY: help install test test-unit test-integration eval lint serve publish
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

LME_DATA := tests/eval/longmemeval/data/longmemeval_s_cleaned.json
LME_URL := https://huggingface.co/datasets/xiaowu0162/longmemeval-cleaned/resolve/main/longmemeval_s_cleaned.json

eval-data: $(LME_DATA) ## Download LongMemEval-S (~280 MB, not committed)

$(LME_DATA):
	mkdir -p $(dir $@)
	curl -fL --retry 3 -o $@.part $(LME_URL) && mv $@.part $@

eval: $(LME_DATA) ## Retrieval eval on LongMemEval-S (opt-in; EVAL_ARGS="--per-type 5")
	uv run python -m tests.eval.longmemeval.run $(EVAL_ARGS)

##@ Development
lint: ## Lint source and tests
	uv run ruff check src/ tests/

serve: ## Start the server
	uv run alaya

##@ Publishing
publish: ## Build distribution and check with twine
	uv build
	uv tool run twine check dist/*
