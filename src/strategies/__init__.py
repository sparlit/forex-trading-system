"""
Elite Autonomous Quantum Trading System - Strategies Package
"""

from .comprehensive_strategies import (
    REGIME_STRATEGY_WEIGHTS,
    SESSION_STRATEGY_PREFERENCES,
    STRATEGY_REGISTRY,
    SYMBOL_STRATEGY_MAP,
    AutoStrategySelector,
    AutoStyleSelector,
    DonchianBreakoutStrategy,
    StrategyCategory,
    StrategyFactory,
    StrategyMetadata,
    TradingStyle,
    register_strategy,
)

# Import part 2 strategies
from .comprehensive_strategies_part2 import (
    BollingerRSIStrategy,
    CarryTradeStrategy,
    EMACrossoverStrategy,
    FundingRateArbStrategy,
    MACDMomentumStrategy,
)

# Import part 3 strategies
from .comprehensive_strategies_part3 import (
    ICTSMCStrategy,
    MarketMakingStrategy,
    NewsStraddleStrategy,
    OrderFlowVolumeProfileStrategy,
    PairsTradingStrategy,
)

# Import part 4 strategies
from .comprehensive_strategies_part4 import (
    CentralBankNewsStraddleStrategy,
    CentralBankPegBreakStrategy,
    CrossExchangeFundingArbStrategy,
    CryptoDerivativesBasisStrategy,
    CryptoMEVArbitrageStrategy,
    DarkPoolAbsorptionStrategy,
    HighFrequencyMarketMakingStrategy,
    ICTSmartMoneyConceptsStrategy,
    IntermarketAnalysisStrategy,
    StatisticalArbitrageStrategy,
    SystematicMomentumCTAStrategy,
    TimeOfDayStructuralArbStrategy,
)

__all__ = [
    "REGIME_STRATEGY_WEIGHTS",
    "SESSION_STRATEGY_PREFERENCES",
    "STRATEGY_REGISTRY",
    "SYMBOL_STRATEGY_MAP",
    "AutoStrategySelector",
    "AutoStyleSelector",
    "BollingerRSIStrategy",
    "CarryTradeStrategy",
    "CentralBankNewsStraddleStrategy",
    "CentralBankPegBreakStrategy",
    "CrossExchangeFundingArbStrategy",
    "CryptoDerivativesBasisStrategy",
    "CryptoMEVArbitrageStrategy",
    "DarkPoolAbsorptionStrategy",
    "DonchianBreakoutStrategy",
    "EMACrossoverStrategy",
    "FundingRateArbStrategy",
    "HighFrequencyMarketMakingStrategy",
    "ICTSMCStrategy",
    "ICTSmartMoneyConceptsStrategy",
    "IntermarketAnalysisStrategy",
    "MACDMomentumStrategy",
    "MarketMakingStrategy",
    "NewsStraddleStrategy",
    "OrderFlowVolumeProfileStrategy",
    "PairsTradingStrategy",
    "StatisticalArbitrageStrategy",
    "StrategyCategory",
    "StrategyFactory",
    "StrategyMetadata",
    "SystematicMomentumCTAStrategy",
    "TimeOfDayStructuralArbStrategy",
    "TradingStyle",
    "register_strategy",
]
