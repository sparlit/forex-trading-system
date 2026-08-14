#!/usr/bin/env python3
"""
Forex Trading System - Main Entry Point
Run different components of the trading system.
"""

import asyncio
import sys
import typer
from typing import Optional
from loguru import logger

app = typer.Typer(help="Forex Trading System - Innovative Trading Platform")


@app.command()
def data(
    config: str = typer.Option("development", help="Config environment"),
):
    """Run data ingestion worker."""
    from src.data.runner import run_data_ingestion
    logger.info("Starting data ingestion worker...")
    asyncio.run(run_data_ingestion())


@app.command()
def strategy(
    config: str = typer.Option("development", help="Config environment"),
):
    """Run strategy engine worker."""
    from src.strategy.runner import run_strategy_worker
    logger.info("Starting strategy engine worker...")
    asyncio.run(run_strategy_worker())


@app.command()
def risk(
    config: str = typer.Option("development", help="Config environment"),
):
    """Run risk management worker."""
    from src.risk.runner import run_risk_worker
    logger.info("Starting risk management worker...")
    asyncio.run(run_risk_worker())


@app.command()
def execution(
    config: str = typer.Option("development", help="Config environment"),
):
    """Run execution engine worker."""
    from src.execution.runner import run_execution_worker
    logger.info("Starting execution engine worker...")
    asyncio.run(run_execution_worker())


@app.command()
def api(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8000, help="Port to bind"),
    reload: bool = typer.Option(False, help="Enable auto-reload"),
    workers: int = typer.Option(1, help="Number of workers"),
):
    """Run REST API server."""
    import uvicorn
    logger.info(f"Starting API server on {host}:{port}...")
    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=reload,
        workers=workers,
    )


@app.command()
def dashboard(
    host: str = typer.Option("0.0.0.0", help="Host to bind"),
    port: int = typer.Option(8501, help="Port to bind"),
):
    """Run Streamlit dashboard."""
    import subprocess
    logger.info(f"Starting dashboard on {host}:{port}...")
    subprocess.run([
        "streamlit", "run", "src/portfolio/dashboard/app.py",
        "--server.address", host,
        "--server.port", str(port),
    ])


@app.command()
def backtest(
    strategy: str = typer.Option("ensemble", help="Strategy to backtest"),
    start: str = typer.Option("2023-01-01", help="Start date"),
    end: str = typer.Option("2024-01-01", help="End date"),
    symbols: str = typer.Option("EURUSD,GBPUSD,XAUUSD", help="Comma-separated symbols"),
    timeframe: str = typer.Option("H1", help="Timeframe"),
    capital: float = typer.Option(100000, help="Initial capital"),
):
    """Run backtest."""
    from src.strategy.backtest.engine import VectorizedBacktestEngine, BacktestConfig
    from src.strategy.base.strategy import StrategyConfig
    from src.strategy.ml.strategies import EnsembleStrategy, MeanReversionStrategy, TrendFollowingStrategy, BreakoutStrategy
    from src.data.storage.timescale import timescaledb
    from datetime import datetime
    from decimal import Decimal

    async def run_backtest():
        await timescaledb.connect()

        # Load data
        data = {}
        for symbol in symbols.split(","):
            bars = await timescaledb.get_bars_polars(
                symbol=symbol.strip(),
                timeframe=timeframe,
                start_time=datetime.fromisoformat(start),
                end_time=datetime.fromisoformat(end),
            )
            data[symbol.strip()] = bars

        # Create strategy
        strategy_map = {
            "ensemble": EnsembleStrategy,
            "mean_reversion": MeanReversionStrategy,
            "trend_following": TrendFollowingStrategy,
            "breakout": BreakoutStrategy,
        }

        strategy_class = strategy_map.get(strategy)
        if not strategy_class:
            logger.error(f"Unknown strategy: {strategy}")
            return

        strat_config = StrategyConfig(
            strategy_id=f"backtest_{strategy}",
            name=strategy,
            parameters={},
        )
        strat = strategy_class(strat_config)
        await strat.initialize()

        # Run backtest
        config = BacktestConfig(
            start_date=datetime.fromisoformat(start),
            end_date=datetime.fromisoformat(end),
            initial_capital=Decimal(str(capital)),
            timeframe=timeframe,
        )

        engine = VectorizedBacktestEngine(config)
        result = await engine.run(strat, data)

        # Print results
        from src.strategy.backtest.metrics import generate_tear_sheet, calculate_advanced_metrics
        metrics = calculate_advanced_metrics(result.equity_curve, result.trades)
        print(generate_tear_sheet(metrics, result))

        await timescaledb.disconnect()

    logger.info(f"Running backtest for {strategy}...")
    asyncio.run(run_backtest())


@app.command()
def init_db():
    """Initialize database schema."""
    import subprocess
    logger.info("Initializing database...")
    subprocess.run([
        "docker-compose", "exec", "-T", "timescaledb",
        "psql", "-U", "trader", "-d", "market_data", "-f", "/docker-entrypoint-initdb.d/init-timescaledb.sql"
    ])


@app.command()
def test(
    path: str = typer.Option("tests", help="Test path"),
    coverage: bool = typer.Option(False, help="Run with coverage"),
    verbose: bool = typer.Option(True, help="Verbose output"),
):
    """Run tests."""
    import subprocess
    cmd = ["pytest"]
    if verbose:
        cmd.append("-v")
    if coverage:
        cmd.extend(["--cov=src", "--cov-report=term-missing"])
    cmd.append(path)
    subprocess.run(cmd)


@app.command()
def lint():
    """Run linting."""
    import subprocess
    subprocess.run(["ruff", "check", "src"])
    subprocess.run(["ruff", "format", "--check", "src"])
    subprocess.run(["mypy", "src"])


@app.command()
def format():
    """Format code."""
    import subprocess
    subprocess.run(["ruff", "format", "src"])
    subprocess.run(["ruff", "check", "--fix", "src"])


@app.command()
def migrate(
    message: str = typer.Option("", help="Migration message"),
):
    """Create database migration."""
    import subprocess
    cmd = ["alembic", "revision", "--autogenerate"]
    if message:
        cmd.extend(["-m", message])
    subprocess.run(cmd)


@app.command()
def upgrade():
    """Apply database migrations."""
    import subprocess
    subprocess.run(["alembic", "upgrade", "head"])


@app.command()
def docker_up(
    detach: bool = typer.Option(True, help="Run in background"),
    build: bool = typer.Option(False, help="Build images first"),
):
    """Start with Docker Compose."""
    import subprocess
    cmd = ["docker-compose", "up"]
    if detach:
        cmd.append("-d")
    if build:
        cmd.append("--build")
    subprocess.run(cmd)


@app.command()
def docker_down(
    volumes: bool = typer.Option(False, help="Remove volumes"),
):
    """Stop Docker Compose."""
    import subprocess
    cmd = ["docker-compose", "down"]
    if volumes:
        cmd.append("-v")
    subprocess.run(cmd)


@app.command()
def version():
    """Show version."""
    from src import __version__
    print(f"Forex Trading System v{__version__}")


if __name__ == "__main__":
    app()