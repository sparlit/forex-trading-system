# Forex Trading System - Makefile
# Common development tasks

.PHONY: help install test lint format typecheck clean docker-build docker-up docker-down db-init run-data run-strategy run-risk run-execution run-api run-dashboard

# Default target
help:
	@echo "Forex Trading System - Development Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install          - Install dependencies with Poetry"
	@echo "  make install-dev      - Install with dev dependencies"
	@echo "  make pre-commit       - Install pre-commit hooks"
	@echo ""
	@echo "Testing:"
	@echo "  make test             - Run all tests with coverage"
	@echo "  make test-unit        - Run unit tests only"
	@echo "  make test-integration - Run integration tests only"
	@echo "  make test-slow        - Run slow tests"
	@echo ""
	@echo "Code Quality:"
	@echo "  make lint             - Run ruff linter"
	@echo "  make format           - Format code with ruff"
	@echo "  make typecheck        - Run mypy type checking"
	@echo "  make security         - Run security scans (bandit, pip-audit)"
	@echo ""
	@echo "Database:"
	@echo "  make db-init          - Initialize TimescaleDB schema"
	@echo "  make db-migrate       - Create new migration"
	@echo "  make db-upgrade       - Apply migrations"
	@echo ""
	@echo "Docker:"
	@echo "  make docker-build     - Build Docker images"
	@echo "  make docker-up        - Start services with docker-compose"
	@echo "  make docker-down      - Stop services"
	@echo "  make docker-logs      - View service logs"
	@echo ""
	@echo "Running Components:"
	@echo "  make run-data         - Run data ingestion worker"
	@echo "  make run-strategy     - Run strategy engine"
	@echo "  make run-risk         - Run risk management"
	@echo "  make run-execution    - Run execution engine"
	@echo "  make run-api          - Run REST API server"
	@echo "  make run-dashboard    - Run Streamlit dashboard"
	@echo "  make run-all          - Run all workers (background)"
	@echo ""
	@echo "Maintenance:"
	@echo "  make clean            - Clean build artifacts"
	@echo "  make update-deps      - Update dependencies"

# Installation
install:
	poetry install --only main

install-dev:
	poetry install --with dev,ml,viz,trading

pre-commit:
	poetry run pre-commit install
	poetry run pre-commit run --all-files

# Testing
test:
	poetry run pytest tests/ -v --cov=src --cov-report=term-missing --cov-fail-under=70

test-unit:
	poetry run pytest tests/ -m "unit" -v

test-integration:
	poetry run pytest tests/ -m "integration" -v

test-slow:
	poetry run pytest tests/ -m "slow" -v

# Code Quality
lint:
	poetry run ruff check src tests

format:
	poetry run ruff format src tests
	poetry run ruff check --fix src tests

typecheck:
	poetry run mypy src --strict

security:
	poetry run bandit -r src -f json -o bandit-report.json
	poetry run pip-audit --desc --format=json --output=audit-results.json

# Database
db-init:
	python scripts/init_db.py

db-migrate:
	poetry run alembic revision --autogenerate -m "$(MSG)"

db-upgrade:
	poetry run alembic upgrade head

# Docker
docker-build:
	docker-compose build

docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

docker-down-volumes:
	docker-compose down -v

docker-logs:
	docker-compose logs -f

docker-ps:
	docker-compose ps

# Running Components
run-data:
	python -m src.data.runner

run-strategy:
	python -m src.strategy.runner

run-risk:
	python -m src.risk.runner

run-execution:
	python -m src.execution.runner

run-api:
	python -m src.api.main

run-dashboard:
	streamlit run src/portfolio/dashboard/app.py

run-all:
	@echo "Starting all workers in background..."
	@python -m src.data.runner &
	@python -m src.strategy.runner &
	@python -m src.risk.runner &
	@python -m src.execution.runner &
	@echo "All workers started. Check logs for output."

# Production
docker-prod-build:
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml build

docker-prod-up:
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

docker-prod-down:
	docker-compose -f docker-compose.yml -f docker-compose.prod.yml down

# Maintenance
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name ".coverage" -delete
	find . -type f -name "coverage.xml" -delete
	find . -type f -name "bandit-report.json" -delete
	find . -type f -name "audit-results.json" -delete
	rm -rf build/ dist/ *.egg-info/

update-deps:
	poetry update
	poetry lock

# Development workflow
dev-setup: install-dev pre-commit db-init docker-up
	@echo "Development environment ready!"
	@echo "Run 'make run-api' to start the API server"
	@echo "Run 'make run-dashboard' to start the dashboard"

ci: lint typecheck test security
	@echo "CI pipeline passed!"

# Quick commands
logs:
	tail -f logs/forex-trading-system.log

shell:
	poetry shell