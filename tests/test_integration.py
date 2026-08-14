"""Integration test for the complete trading system."""

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import polars as pl
import pytest

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


@pytest.fixture
def mock_mt5():
    """Mock MT5 module."""
    with patch('src.data.ingest.mt5_connector.mt5') as mock:
        mock.initialize.return_value = True
        mock.terminal_info.return_value = MagicMock(connected=True)
        mock.symbols_get.return_value = [
            MagicMock(
                name="EURUSD",
                visible=True,
                currency_base="EUR",
                currency_profit="USD",
                exchange="MT5",
                description="Euro vs US Dollar",
                path="Forex/Majors",
                trade_contract_size=100000,
                trade_tick_size=0.00001,
                trade_tick_value=1.0,
                volume_min=0.01,
                volume_max=100.0,
                volume_step=0.01,
                swap_long=-1.0,
                swap_short=-0.5,
                currency_margin="USD",
                margin_initial=0.01,
                spread=10,
                digits=5,
                trade_mode=0,
            )
        ]
        # Set up timeframe constants
        mock.TIMEFRAME_TICK = 0
        mock.TIMEFRAME_S1 = 1
        mock.TIMEFRAME_S5 = 5
        mock.TIMEFRAME_S15 = 15
        mock.TIMEFRAME_S30 = 30
        mock.TIMEFRAME_M1 = 60
        mock.TIMEFRAME_M2 = 120
        mock.TIMEFRAME_M3 = 180
        mock.TIMEFRAME_M4 = 240
        mock.TIMEFRAME_M5 = 300
        mock.TIMEFRAME_M6 = 360
        mock.TIMEFRAME_M10 = 600
        mock.TIMEFRAME_M12 = 720
        mock.TIMEFRAME_M15 = 900
        mock.TIMEFRAME_M20 = 1200
        mock.TIMEFRAME_M30 = 1800
        mock.TIMEFRAME_H1 = 3600
        mock.TIMEFRAME_H2 = 7200
        mock.TIMEFRAME_H3 = 10800
        mock.TIMEFRAME_H4 = 14400
        mock.TIMEFRAME_H6 = 21600
        mock.TIMEFRAME_H8 = 28800
        mock.TIMEFRAME_H12 = 43200
        mock.TIMEFRAME_D1 = 86400
        mock.TIMEFRAME_W1 = 604800
        mock.TIMEFRAME_MN1 = 2592000
        mock.copy_rates_range.return_value = [
            {'time': 1704067200, 'open': 1.0800, 'high': 1.0850, 'low': 1.0780, 'close': 1.0820, 'tick_volume': 1000, 'spread': 10, 'real_volume': 1000}
        ]
        mock.copy_rates_from_pos.return_value = [
            {'time': 1704067200, 'open': 1.0800, 'high': 1.0850, 'low': 1.0780, 'close': 1.0820, 'tick_volume': 1000, 'spread': 10, 'real_volume': 1000},
            {'time': 1704070800, 'open': 1.0820, 'high': 1.0870, 'low': 1.0810, 'close': 1.0840, 'tick_volume': 1200, 'spread': 10, 'real_volume': 1200},
        ]
        mock.symbol_info_tick.return_value = MagicMock(
            bid=1.0820,
            ask=1.0821,
            last=1.08205,
            volume=100,
            time=1704067200,
            time_msc=0,
            flags=0,
        )
        mock.last_error.return_value = (0, "OK")
        mock.shutdown.return_value = None
        yield mock


@pytest.fixture
def mock_ccxt():
    """Mock CCXT module."""
    with patch('src.data.ingest.ccxt_connector.ccxt') as mock:
        # Create mock exchange
        mock_exchange = AsyncMock()
        mock_exchange.load_markets = AsyncMock()
        mock_exchange.markets = {
            "BTC/USDT": {
                "symbol": "BTC/USDT",
                "base": "BTC",
                "quote": "USDT",
                "active": True,
                "precision": {"price": 0.01, "amount": 0.00001},
                "limits": {"amount": {"min": 0.0001, "max": 100}},
                "contractSize": 1,
                "type": "spot",
                "spot": True,
            }
        }
        mock_exchange.fetch_ohlcv = AsyncMock(return_value=[
            [1704067200000, 43000, 43500, 42800, 43200, 100],
        ])
        mock_exchange.fetch_ticker = AsyncMock(return_value={
            "symbol": "BTC/USDT",
            "bid": 43200,
            "ask": 43210,
            "last": 43205,
            "baseVolume": 1000,
            "timestamp": 1704067200000,
        })
        mock_exchange.create_order = AsyncMock(return_value={
            "id": "order_123",
            "status": "closed",
            "filled": 0.1,
            "average": 43200,
            "fee": {"cost": 10},
            "timestamp": 1704067200000,
        })
        mock_exchange.cancel_order = AsyncMock(return_value={"status": "canceled"})
        mock_exchange.fetch_order = AsyncMock(return_value={
            "id": "order_123",
            "status": "closed",
            "filled": 0.1,
            "average": 43200,
        })
        mock_exchange.fetch_open_orders = AsyncMock(return_value=[])
        mock_exchange.fetch_balance = AsyncMock(return_value={
            "USDT": {"free": 10000, "used": 0, "total": 10000},
        })
        mock_exchange.fetch_positions = AsyncMock(return_value=[])
        mock_exchange.close = AsyncMock()
        mock_exchange.fetch_time = AsyncMock(return_value=1704067200000)

        mock.binance = lambda config: mock_exchange
        mock.bybit = lambda config: mock_exchange
        mock.kraken = lambda config: mock_exchange

        yield mock


@pytest.fixture
def sample_bars():
    """Create sample bar data."""
    import numpy as np
    dates = [datetime(2023, 1, 1, tzinfo=timezone.utc) + timedelta(days=i) for i in range(100)]
    base_price = 1.0800

    data = {
        "timestamp": dates,
        "open": [float(base_price + np.random.randn() * 0.001) for _ in dates],
        "high": [float(base_price + abs(np.random.randn()) * 0.002) for _ in dates],
        "low": [float(base_price - abs(np.random.randn()) * 0.002) for _ in dates],
        "close": [float(base_price + np.random.randn() * 0.001) for _ in dates],
        "volume": [float(1000 + np.random.randn() * 100) for _ in dates],
        "spread": [0.0001] * len(dates),
    }
    return pl.DataFrame(data)


class TestDataIngestion:
    """Test data ingestion layer."""

    @pytest.mark.asyncio
    async def test_mt5_connector_initialization(self, mock_mt5):
        """Test MT5 connector initializes correctly."""
        from src.data.ingest.mt5_connector import MT5Provider

        provider = MT5Provider(
            login=12345,
            password="password",
            server="TestServer",
        )

        await provider.connect()
        assert provider.connected
        assert len(provider._symbol_cache) > 0

        await provider.disconnect()
        assert not provider.connected

    @pytest.mark.asyncio
    async def test_ccxt_connector_initialization(self, mock_ccxt):
        """Test CCXT connector initializes correctly."""
        from src.data.ingest.ccxt_connector import CCXTProvider

        provider = CCXTProvider(
            exchanges=["binance"],
            api_keys={},
        )

        await provider.connect()
        assert provider.connected
        assert "binance" in provider._exchanges

        await provider.disconnect()
        assert not provider.connected


class TestStrategyEngine:
    """Test strategy engine."""

    @pytest.mark.asyncio
    async def test_mean_reversion_strategy(self, sample_bars):
        """Test mean reversion strategy generates signals."""
        from src.data.models import Bar, Timeframe
        from src.strategy.base.strategy import StrategyConfig
        from src.strategy.ml.strategies import MeanReversionStrategy

        config = StrategyConfig(
            strategy_id="test_mr",
            name="Test Mean Reversion",
            parameters={},
            timeframes=[Timeframe.H1],
        )
        strategy = MeanReversionStrategy(config)
        await strategy.initialize()

        # Feed bars
        for i, row in enumerate(sample_bars.iter_rows(named=True)):
            bar = Bar(
                symbol_id=0,
                symbol="EURUSD",
                timestamp=row["timestamp"],
                timeframe=Timeframe.H1,
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
                spread=Decimal(str(row["spread"])),
            )
            signals = await strategy.on_bar(bar)
            # Strategy should not error
            assert isinstance(signals, list)

    @pytest.mark.asyncio
    async def test_ensemble_strategy(self, sample_bars):
        """Test ensemble strategy."""
        from src.data.models import Bar, Timeframe
        from src.strategy.base.strategy import StrategyConfig
        from src.strategy.ml.strategies import EnsembleStrategy

        config = StrategyConfig(
            strategy_id="test_ensemble",
            name="Test Ensemble",
            parameters={
                "model_type": "lstm",
                "lookback": 50,
            },
            timeframes=[Timeframe.H1],
        )
        strategy = EnsembleStrategy(config)
        await strategy.initialize()

        # Feed bars (need enough for lookback)
        for i, row in enumerate(sample_bars.iter_rows(named=True)):
            bar = Bar(
                symbol_id=0,
                symbol="EURUSD",
                timestamp=row["timestamp"],
                timeframe=Timeframe.H1,
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
                spread=Decimal(str(row["spread"])),
            )
            signals = await strategy.on_bar(bar)
            assert isinstance(signals, list)


class TestRiskManagement:
    """Test risk management."""

    def test_position_sizer(self):
        """Test position sizing methods."""
        from src.data.models import AssetClass, Direction, Symbol, Timeframe
        from src.risk.position_sizer import (
            PositionSizer,
            PositionSizingConfig,
            PositionSizingMethod,
        )
        from src.strategy.base.signal import Signal

        sizer = PositionSizer(PositionSizingConfig(
            method=PositionSizingMethod.VOLATILITY_TARGET,
            risk_per_trade=0.02,
        ))

        signal = Signal.create_entry(
            strategy_id="test",
            strategy_name="Test",
            symbol="EURUSD",
            direction=Direction.LONG,
            entry_price=Decimal("1.0800"),
            stop_loss=Decimal("1.0750"),
            take_profit=Decimal("1.0900"),
            strength=0.7,
            confidence=0.6,
            timeframe=Timeframe.H1,
        )

        symbol = Symbol(
            symbol_id=1,
            symbol="EURUSD",
            base_currency="EUR",
            quote_currency="USD",
            asset_class=AssetClass.FOREX,
            contract_size=Decimal(100000),
            tick_size=Decimal("0.00001"),
            min_volume=Decimal("0.01"),
            max_volume=Decimal(100),
            volume_step=Decimal("0.01"),
            margin_rate=Decimal("0.01"),
        )

        result = sizer.calculate_position_size(
            signal=signal,
            symbol=symbol,
            equity=Decimal(100000),
            current_positions={},
            account_balance=Decimal(100000),
            free_margin=Decimal(100000),
        )

        assert result.size > 0
        assert result.risk_amount > 0

    def test_portfolio_risk_manager(self):
        """Test portfolio risk manager."""
        from src.risk.portfolio_risk import PortfolioRiskManager, RiskLimits

        risk_manager = PortfolioRiskManager(RiskLimits(
            max_portfolio_risk=0.02,
            max_drawdown=0.10,
        ))

        equity = Decimal(100000)
        risk_manager.update_equity(equity)

        dd_current, dd_max = risk_manager.calculate_drawdown(equity)
        assert dd_current == 0.0
        assert dd_max == 0.0

        # Simulate drawdown
        risk_manager.update_equity(Decimal(95000))
        dd_current, dd_max = risk_manager.calculate_drawdown(Decimal(95000))
        assert dd_current > 0
        assert dd_max > 0

    def test_circuit_breaker(self):
        """Test circuit breaker."""
        from src.risk.risk_circuit_breaker import CircuitBreakerManager, CircuitBreakerType

        manager = CircuitBreakerManager()

        # Check daily loss
        metrics = {"daily_loss": 0.03, "drawdown": 0.05, "consecutive_losses": 2}
        triggered = manager.check_all(metrics)
        assert len(triggered) == 0  # Below threshold

        metrics = {"daily_loss": 0.06, "drawdown": 0.05, "consecutive_losses": 2}
        triggered = manager.check_all(metrics)
        assert CircuitBreakerType.DAILY_LOSS in triggered

    def test_drawdown_guard(self):
        """Test drawdown guard."""
        from src.risk.risk_circuit_breaker import DrawdownGuard

        guard = DrawdownGuard(
            max_drawdown=0.10,
            warning_drawdown=0.05,
            reduce_at_drawdown=0.07,
            stop_at_drawdown=0.10,
        )

        # Normal equity
        status = guard.update(Decimal(100000))
        assert not status["warning"]
        assert not status["reduce_position"]
        assert not status["stop_trading"]
        assert status["position_multiplier"] == 1.0

        # Drawdown warning
        status = guard.update(Decimal(96000))  # 4% drawdown
        assert not status["warning"]

        status = guard.update(Decimal(94000))  # 6% drawdown
        assert status["warning"]

        status = guard.update(Decimal(92000))  # 8% drawdown
        assert status["reduce_position"]
        assert status["position_multiplier"] < 1.0


class TestExecutionEngine:
    """Test execution engine."""

    @pytest.mark.asyncio
    async def test_order_manager(self):
        """Test order manager."""
        from uuid import uuid4

        from src.execution.order_manager import (
            BrokerType,
            OrderManager,
            OrderSide,
            OrderStatus,
            OrderType,
        )

        manager = OrderManager()

        order = manager.create_order(
            strategy_id="test",
            signal_id=uuid4(),
            symbol="EURUSD",
            symbol_id=1,
            broker=BrokerType.MT5,
            order_type=OrderType.MARKET,
            side=OrderSide.BUY,
            volume=Decimal("1.0"),
            price=Decimal("1.0800"),
        )

        assert order.status == OrderStatus.PENDING
        assert order.volume == Decimal("1.0")

        retrieved = manager.get_order(order.order_id)
        assert retrieved is not None
        assert retrieved.client_order_id == order.client_order_id


class TestBacktesting:
    """Test backtesting engine."""

    @pytest.mark.asyncio
    async def test_vectorized_backtest(self, sample_bars):
        """Test vectorized backtest engine."""
        from src.data.models import Timeframe
        from src.strategy.backtest.engine import BacktestConfig, VectorizedBacktestEngine
        from src.strategy.base.strategy import StrategyConfig
        from src.strategy.ml.strategies import MeanReversionStrategy

        config = BacktestConfig(
            start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2023, 4, 10, tzinfo=timezone.utc),
            initial_capital=Decimal(100000),
            timeframe=Timeframe.H1,
        )

        data = {"EURUSD": sample_bars}

        strat_config = StrategyConfig(
            strategy_id="test_mr",
            name="Test MR",
            parameters={},
        )
        strategy = MeanReversionStrategy(strat_config)
        await strategy.initialize()

        engine = VectorizedBacktestEngine(config)
        result = await engine.run(strategy, data)

        assert result.final_equity >= 0
        assert result.total_trades >= 0
        assert isinstance(result.equity_curve, list)

    @pytest.mark.asyncio
    async def test_walk_forward_optimizer(self, sample_bars):
        """Test walk-forward optimizer."""
        from src.data.models import Timeframe
        from src.strategy.backtest.engine import BacktestConfig, WalkForwardOptimizer
        from src.strategy.ml.strategies import MeanReversionStrategy

        optimizer = WalkForwardOptimizer(
            train_window=30,
            test_window=10,
            step_size=5,
        )

        param_grid = {
            "bb_period": [20, 30],
            "rsi_period": [14, 21],
        }

        config = BacktestConfig(
            start_date=datetime(2023, 1, 1, tzinfo=timezone.utc),
            end_date=datetime(2023, 4, 10, tzinfo=timezone.utc),
            timeframe=Timeframe.H1,
        )

        data = {"EURUSD": sample_bars}

        result = await optimizer.optimize(
            MeanReversionStrategy,
            param_grid,
            data,
            config,
            metric="sharpe_ratio",
        )

        assert "best_params" in result
        assert "windows" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])