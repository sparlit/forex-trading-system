# Repository Guidelines

## Project Structure & Module Organization

Application code lives in `src/`. Keep domain work within its owning package: `strategy/` for trading logic and models, `infra/` for messaging and monitoring, `trading/` for paper trading, and `web/`, `ui/`, or `viz/` for presentation. Add tests in `tests/` using the matching `test_*.py` naming pattern. Runtime configuration is in `config/`; deployment files are in `deployment/`; utility scripts are in `scripts/`. Treat `models/`, `data/`, `logs/`, and local databases as runtime artifacts unless a change explicitly requires versioning them. MetaTrader expert-advisor sources live in `ea/`.

## Build, Test, and Development Commands

Use Python 3.11 or 3.12 and Poetry:

```bash
poetry install --with dev,ml,viz,trading  # install development dependencies
make docker-up                            # start local infrastructure
make test                                 # pytest with coverage (minimum 70%)
make lint                                 # Ruff checks for src/ and tests/
make typecheck                            # strict mypy checks
make format                               # apply Ruff formatting and safe fixes
```

Run a focused suite with `poetry run pytest tests/test_backtest.py -v`. Start components with `make run-api`, `make run-strategy`, or `make run-dashboard` after required services are available.

## Coding Style & Naming Conventions

Use four-space indentation, type annotations, and double-quoted Python strings. Ruff, Black, and isort use a 100-character line length; format before committing. Name modules and functions in `snake_case`, classes in `PascalCase`, and constants in `UPPER_SNAKE_CASE`. Keep async interfaces consistently `async def`; strict mypy settings require fully typed definitions.

## Testing Guidelines

Pytest discovers `tests/test_*.py`, `Test*` classes, and `test_*` functions. Mark suites with `unit`, `integration`, or `slow` as appropriate, then run `make test-unit`, `make test-integration`, or `make test-slow`. Add regression tests for behavioral fixes and avoid live broker credentials or external-service dependence in unit tests.

## Commit & Pull Request Guidelines

Git history is unavailable in this checkout, so use concise imperative commits such as `Add risk-limit validation`. Keep each commit focused. Pull requests should explain the behavior and risk impact, link the issue when applicable, list validation commands, and include screenshots for UI/dashboard changes. Never commit `.env` values, broker keys, or production credentials; start from `.env.example` instead.
