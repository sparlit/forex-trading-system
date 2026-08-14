"""Strategy package exports – lightweight imports for core functionality.

We only import heavy ML modules (`ml.models`, `ml.strategies`) if the optional
dependencies (`torch`, `sklearn`, `pyarrow`, etc.) can be loaded. This prevents
Windows‑specific access‑violation crashes when the test suite imports `src`
solely for backtesting utilities.
"""

from __future__ import annotations

# Core backtest / technical modules – always safe to import
from src.strategy.backtest.engine import (
    BacktestConfig,
    BacktestMode,
    BacktestResult,
    EventDrivenBacktestEngine,
    MonteCarloSimulator,
    Trade,
    VectorizedBacktestEngine,
    WalkForwardOptimizer,
)
from src.strategy.backtest.metrics import (
    PerformanceMetrics,
    calculate_advanced_metrics,
    compare_strategies,
    generate_tear_sheet,
)
from src.strategy.base.signal import Signal, SignalStrength, SignalType

# Base strategy infrastructure
from src.strategy.base.strategy import (
    Strategy,
    StrategyConfig,
    StrategyRegistry,
    StrategyState,
    strategy_registry,
)

# Technical indicators – lightweight
from src.strategy.technical.indicators import (
    CandlestickPatterns,
    MarketRegime,
    TechnicalIndicators,
)

# Optional heavy ML imports – guarded
try:
    from src.strategy.ml.gnn_strategy import (
        GNNStrategy,
        create_gnn_strategy,
    )
    from src.strategy.ml.meta_learning_strategy import (
        MetaLearningStrategy,
        create_meta_learning_strategy,
    )
    from src.strategy.ml.models import (
        FeatureEngineer,
        LSTMModel,
        MLModelTrainer,
        ModelConfig,
        OnlineLearner,
        TransformerModel,
    )
    from src.strategy.ml.strategies import (
        BreakoutStrategy,
        EnsembleStrategy,
        MeanReversionStrategy,
        TrendFollowingStrategy,
    )
    from src.strategy.ml.transformer_strategy import (
        TransformerStrategy,
        create_transformer_strategy,
    )
except Exception:  # pragma: no cover – missing optional deps
    FeatureEngineer = LSTMModel = MLModelTrainer = ModelConfig = OnlineLearner = TransformerModel = None  # type: ignore
    BreakoutStrategy = EnsembleStrategy = MeanReversionStrategy = TrendFollowingStrategy = None  # type: ignore
    TransformerStrategy = GNNStrategy = MetaLearningStrategy = None  # type: ignore
    create_transformer_strategy = create_gnn_strategy = create_meta_learning_strategy = None  # type: ignore

# Runner
from src.strategy.runner import run_strategy_worker

__all__ = [
    # Backtest
    "BacktestConfig",
    "BacktestMode",
    "BacktestResult",
    # ML Strategies
    "BreakoutStrategy",
    # Technical Indicators
    "CandlestickPatterns",
    "EnsembleStrategy",
    "EventDrivenBacktestEngine",
    # ML Models
    "FeatureEngineer",
    "GNNStrategy",
    "LSTMModel",
    "MLModelTrainer",
    "MarketRegime",
    "MeanReversionStrategy",
    "MetaLearningStrategy",
    "ModelConfig",
    "MonteCarloSimulator",
    "OnlineLearner",
    # Metrics
    "PerformanceMetrics",
    # Signals
    "Signal",
    "SignalStrength",
    "SignalType",
    # Base Strategy
    "Strategy",
    "StrategyConfig",
    "StrategyRegistry",
    "StrategyState",
    "TechnicalIndicators",
    "Trade",
    "TransformerModel",
    "TransformerStrategy",
    "TrendFollowingStrategy",
    "VectorizedBacktestEngine",
    "WalkForwardOptimizer",
    "calculate_advanced_metrics",
    "compare_strategies",
    "create_gnn_strategy",
    "create_meta_learning_strategy",
    # Factory functions
    "create_transformer_strategy",
    "generate_tear_sheet",
    # Runner
    "run_strategy_worker",
    "strategy_registry",
]
