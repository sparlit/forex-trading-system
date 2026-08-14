"""Test basic imports and configurations."""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_settings_import():
    """Test settings can be imported."""
    from src.infra.config.settings import Direction, Environment, Timeframe, settings

    assert settings.app_name == "forex-trading-system"
    assert settings.environment == Environment.DEVELOPMENT
    assert Timeframe.H1.value == "1h"
    assert Direction.LONG.value == "long"


def test_data_models_import():
    """Test data models can be imported."""
    from src.data.models import (
        AssetClass,
        BrokerType,
        DataSource,
        Direction,
        OrderSide,
        OrderStatus,
        OrderType,
        SignalType,
        Timeframe,
    )

    # Test enums
    assert Timeframe.M1.value == "1m"
    assert DataSource.MT5.value == "mt5"
    assert Direction.SHORT.value == "short"
    assert OrderType.LIMIT.value == "limit"
    assert OrderSide.BUY.value == "buy"
    assert OrderStatus.PENDING.value == "pending"
    assert BrokerType.CCXT.value == "ccxt"
    assert AssetClass.FOREX.value == "forex"
    assert SignalType.ENTRY.value == "entry"


def test_strategy_base_import():
    """Test strategy base classes."""
    from src.strategy.base.signal import SignalStrength
    from src.strategy.base.strategy import StrategyState

    assert StrategyState.ACTIVE.value == "active"
    assert SignalStrength.from_float(0.8) == SignalStrength.VERY_STRONG


def test_risk_import():
    """Test risk module."""
    from src.risk import (
        CircuitBreakerType,
        PositionSizingMethod,
    )

    assert PositionSizingMethod.KELLY.value == "kelly"
    assert CircuitBreakerType.DAILY_LOSS.value == "daily_loss"


def test_execution_import():
    """Test execution module."""
    from src.execution import (
        ExecutionAlgorithm,
        OrderStatus,
    )

    assert ExecutionAlgorithm.TWAP.value == "twap"
    assert OrderStatus.FILLED.value == "filled"


def test_technical_indicators():
    """Test technical indicators."""
    import polars as pl

    from src.strategy.technical.indicators import TechnicalIndicators

    # Create sample data
    df = pl.DataFrame({
        "timestamp": [1, 2, 3, 4, 5],
        "open": [1.0, 1.1, 1.05, 1.15, 1.1],
        "high": [1.1, 1.15, 1.1, 1.2, 1.15],
        "low": [0.95, 1.05, 1.0, 1.1, 1.05],
        "close": [1.05, 1.1, 1.08, 1.18, 1.12],
        "volume": [1000, 1100, 900, 1200, 1000],
    })

    # Test SMA
    result = TechnicalIndicators.add_all_indicators_polars(df)
    assert "sma_10" in result.columns
    assert "rsi_14" in result.columns


def test_config_loading():
    """Test configuration loading."""
    from src.infra.config.settings import settings

    # Check required settings exist
    assert hasattr(settings, 'mt5_enabled')
    assert hasattr(settings, 'ccxt_enabled')
    assert hasattr(settings, 'risk_max_drawdown')
    assert hasattr(settings, 'execution_default_algorithm')


if __name__ == "__main__":
    test_settings_import()
    test_data_models_import()
    test_strategy_base_import()
    test_risk_import()
    test_execution_import()
    test_technical_indicators()
    test_config_loading()
    print("All tests passed!")