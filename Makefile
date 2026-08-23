.DEFAULT_GOAL := help

.PHONY: help setup services-up services-down observability-up observability-down up down health test lint format security \
	data-download data-generate data-validate data-status ingest reindex reindex-docs \
	reindex-graph reset-indexes eval eval-live notebooks api ui

help: ## Show available commands
	@awk 'BEGIN {FS = ":.*## "; printf "\nCivil Engineering Copilot commands:\n\n"} /^[a-zA-Z0-9_-]+:.*## / {printf "  %-20s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Install the pinned Python environment
	uv sync --all-groups

services-up: ## Start PostgreSQL, Qdrant, and Neo4j
	docker compose up -d postgres qdrant neo4j

services-down: ## Stop local data services without deleting data
	docker compose down

observability-up: ## Start the self-hosted Langfuse observability stack
	docker compose -f compose.observability.yaml up -d

observability-down: ## Stop self-hosted Langfuse without deleting traces
	docker compose -f compose.observability.yaml down

up: services-up ## Start all backend services and print app commands
	@echo "Run 'make api' and 'make ui' in separate terminals."

down: services-down ## Stop the local stack without deleting data

health: ## Verify databases and application dependencies
	uv run python scripts/check_services.py

test: ## Run the test suite
	uv run pytest -q

lint: ## Check formatting and Python quality
	uv run ruff format --check .
	uv run ruff check .

format: ## Format Python project code
	uv run ruff format src tests scripts
	uv run ruff check --fix src tests scripts

security: ## Scan project code and installed dependencies
	uv run bandit -c pyproject.toml -r src scripts
	uv run pip-audit

data-download: ## Refresh only permitted public source material
	uv run python scripts/download_public_data.py

data-generate: ## Deterministically rebuild the synthetic demo project
	uv run python scripts/generate_synthetic_data.py

data-validate: ## Validate provenance, revisions, checksums, and relationships
	uv run python scripts/generate_synthetic_data.py --check

data-status: ## Show source, record, chunk, relationship, and index counts
	uv run python scripts/ingest.py --status

ingest: ## Idempotently ingest new or changed source records
	uv run python scripts/ingest.py

reindex: ## Safely rebuild document and graph indexes from authoritative data
	uv run python scripts/ingest.py --reindex all

reindex-docs: ## Safely rebuild the Qdrant document index
	uv run python scripts/ingest.py --reindex documents

reindex-graph: ## Safely rebuild the Neo4j project graph
	uv run python scripts/ingest.py --reindex graph

reset-indexes: ## DESTRUCTIVE: require CONFIRM=reset-local-indexes before clearing local indexes
	@test "$(CONFIRM)" = "reset-local-indexes" || (echo "Refusing. Re-run with CONFIRM=reset-local-indexes"; exit 1)
	uv run python scripts/ingest.py --reset-indexes --confirm "$(CONFIRM)"

eval: ## Run the reproducible offline RAG and agent evaluation baseline
	uv run python -m civil_copilot.evals.runner

eval-live: ## Run the same evaluation through configured live model and services
	uv run python -m civil_copilot.evals.runner --live

notebooks: ## Execute all teaching notebooks headlessly
	uv run jupyter nbconvert --execute --to notebook --inplace notebooks/*.ipynb

api: ## Start the FastAPI backend on port 8001
	uv run uvicorn civil_copilot.api.main:app --reload --port 8001

ui: ## Start the Streamlit UI on port 8501
	uv run streamlit run src/civil_copilot/ui/app.py --server.port 8501
