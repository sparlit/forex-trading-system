"""Test backtesting engine."""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_backtest_config():
    """Test backtest configuration."""
    from src.data.models import Timeframe
    from src.strategy.backtest.engine import BacktestConfig, BacktestMode

    config = BacktestConfig(
        mode=BacktestMode.VECTORIZED,
        initial_capital=Decimal(100000),
        commission_per_lot=Decimal("7.0"),
        spread_bps=10,
        slippage_bps=2,
        start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2024, 1, 1, tzinfo=timezone.utc),
        timeframe=Timeframe.H1,
    )

    assert config.initial_capital == Decimal(100000)
    assert config.mode == BacktestMode.VECTORIZED


def test_trade_creation():
    """Test trade creation."""
    from src.data.models import Direction
    from src.strategy.backtest.engine import Trade

    trade = Trade(
        strategy_id="test",
        symbol="EURUSD",
        direction=Direction.LONG,
        entry_time=datetime(2023, 1, 1, tzinfo=timezone.utc),
        exit_time=datetime(2023, 1, 1, 2, tzinfo=timezone.utc),
        entry_price=Decimal("1.0800"),
        exit_price=Decimal("1.0850"),
        volume=Decimal("1.0"),
        pnl=Decimal(500),
        commission=Decimal(7),
        net_pnl=Decimal(493),
        return_pct=0.00493,
        duration=timedelta(hours=2),
        exit_reason="tp",
    )

    assert trade.direction == Direction.LONG
    assert trade.net_pnl == Decimal(493)
    assert trade.exit_reason == "tp"


def test_backtest_metrics():
    """Test performance metrics calculation."""
    from src.data.models import Direction
    from src.strategy.backtest.engine import Trade
    from src.strategy.backtest.metrics import (
        calculate_advanced_metrics,
        generate_tear_sheet,
    )

    # Create equity curve
    start_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
    equity_curve = [
        (start_date + timedelta(days=i-1), Decimal(100000) + Decimal(str(i * 100)))
        for i in range(1, 100)
    ]

    # Create some trades
    trades = [
        Trade(
            strategy_id="test",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry_time=datetime(2023, 1, 1, tzinfo=timezone.utc),
            exit_time=datetime(2023, 1, 2, tzinfo=timezone.utc),
            entry_price=Decimal("1.0800"),
            exit_price=Decimal("1.0850"),
            volume=Decimal("1.0"),
            pnl=Decimal(500),
            commission=Decimal(7),
            net_pnl=Decimal(493),
            return_pct=0.00493,
            duration=timedelta(hours=2),
            exit_reason="tp",
        ),
        Trade(
            strategy_id="test",
            symbol="EURUSD",
            direction=Direction.SHORT,
            entry_time=datetime(2023, 1, 3, tzinfo=timezone.utc),
            exit_time=datetime(2023, 1, 4, tzinfo=timezone.utc),
            entry_price=Decimal("1.0900"),
            exit_price=Decimal("1.0850"),
            volume=Decimal("1.0"),
            pnl=Decimal(500),
            commission=Decimal(7),
            net_pnl=Decimal(493),
            return_pct=0.00493,
            duration=timedelta(hours=2),
            exit_reason="tp",
        ),
    ]

    metrics = calculate_advanced_metrics(equity_curve, trades)

    assert metrics.total_return > 0
    assert metrics.sharpe_ratio > 0
    assert metrics.total_trades == 2
    assert metrics.winning_trades == 2
    assert metrics.win_rate == 1.0

    # Test tear sheet generation
    tear_sheet = generate_tear_sheet(metrics)
    assert "PERFORMANCE TEAR SHEET" in tear_sheet
    assert "Sharpe Ratio" in tear_sheet


def test_strategy_comparison():
    """Test strategy comparison."""
    from src.data.models import Direction
    from src.strategy.backtest.engine import BacktestResult, Trade
    from src.strategy.backtest.metrics import compare_strategies

    # Create equity curve for strategy A and B
    start_date = datetime(2023, 1, 1, tzinfo=timezone.utc)
    equity_curve = [
        (start_date + timedelta(days=i-1), Decimal(100000) + Decimal(str(i * 200)))
        for i in range(1, 50)
    ]
    trades = [
        Trade(
            strategy_id="Strategy A",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry_time=datetime(2023, 1, 1, tzinfo=timezone.utc),
            exit_time=datetime(2023, 1, 2, tzinfo=timezone.utc),
            entry_price=Decimal("1.0800"),
            exit_price=Decimal("1.0850"),
            volume=Decimal("1.0"),
            pnl=Decimal(500),
            commission=Decimal(7),
            net_pnl=Decimal(493),
            return_pct=0.00493,
            duration=timedelta(hours=2),
            exit_reason="tp",
        ),
    ]
    result = BacktestResult(
        config=None,
        strategy_id="Strategy A",
        start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2023, 2, 20, tzinfo=timezone.utc),
        initial_capital=Decimal(100000),
        final_equity=Decimal(110000),
        total_return=10000,
        total_return_pct=10.0,
        annual_return=15.0,
        max_drawdown=1000,
        max_drawdown_pct=1.0,
        current_drawdown=0.5,
        sharpe_ratio=2.0,
        sortino_ratio=2.5,
        calmar_ratio=3.0,
        var_95=-1.0,
        var_99=-1.5,
        total_trades=10,
        winning_trades=7,
        losing_trades=3,
        win_rate=0.7,
        profit_factor=2.0,
        expectancy=100,
        avg_win=200,
        avg_loss=-100,
        largest_win=500,
        largest_loss=-200,
        avg_trade_duration=timedelta(hours=4),
        avg_bars_held=4,
        equity_curve=equity_curve,
        trades=trades,
    )
    results = {"Strategy A": result}

    # Strategy B
    equity_curve_b = [
        (start_date + timedelta(days=i-1), Decimal(100000) + Decimal(str(i * 150)))
        for i in range(1, 50)
    ]
    trades_b = [
        Trade(
            strategy_id="Strategy B",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry_time=datetime(2023, 1, 1, tzinfo=timezone.utc),
            exit_time=datetime(2023, 1, 2, tzinfo=timezone.utc),
            entry_price=Decimal("1.0800"),
            exit_price=Decimal("1.0850"),
            volume=Decimal("1.0"),
            pnl=Decimal(500),
            commission=Decimal(7),
            net_pnl=Decimal(493),
            return_pct=0.00493,
            duration=timedelta(hours=2),
            exit_reason="tp",
        ),
    ]
    result_b = BacktestResult(
        config=None,
        strategy_id="Strategy B",
        start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
        end_date=datetime(2023, 2, 20, tzinfo=timezone.utc),
        initial_capital=Decimal(100000),
        final_equity=Decimal(110000),
        total_return=10000,
        total_return_pct=10.0,
        annual_return=15.0,
        max_drawdown=1000,
        max_drawdown_pct=1.0,
        current_drawdown=0.5,
        sharpe_ratio=2.0,
        sortino_ratio=2.5,
        calmar_ratio=3.0,
        var_95=-1.0,
        var_99=-1.5,
        total_trades=10,
        winning_trades=7,
        losing_trades=3,
        win_rate=0.7,
        profit_factor=2.0,
        expectancy=100,
        avg_win=200,
        avg_loss=-100,
        largest_win=500,
        largest_loss=-200,
        avg_trade_duration=timedelta(hours=4),
        avg_bars_held=4,
        equity_curve=equity_curve_b,
        trades=trades_b,
    )
    results["Strategy B"] = result_b

    df = compare_strategies(results)
    assert len(df) == 2
    assert "Strategy" in df.columns
    assert "Sharpe" in df.columns


if __name__ == "__main__":
    test_backtest_config()
    test_trade_creation()
    test_backtest_metrics()
    test_strategy_comparison()
    print("All backtest tests passed!")