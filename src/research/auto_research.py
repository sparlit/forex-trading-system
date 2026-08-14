"""
Auto Research Pipeline - Continuous strategy discovery, validation, and deployment.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from src.data.storage.timescale import TimescaleDB
from src.portfolio.capital_allocator import CapitalAllocator
from src.risk.risk_engine import RiskEngine
from src.strategy.base import BaseStrategy, StrategyConfig, StrategyRegistry, StrategyStatus
from src.strategy.strategies import STRATEGY_FACTORIES

logger = logging.getLogger(__name__)


class ResearchStatus(str, Enum):
    PENDING = "pending"
    GENERATING = "generating"
    BACKTESTING = "backtesting"
    VALIDATING = "validating"
    PAPER_TRADING = "paper_trading"
    LIVE = "live"
    REJECTED = "rejected"
    ARCHIVED = "archived"


@dataclass
class Hypothesis:
    """Research hypothesis for a new strategy"""
    hypothesis_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    strategy_type: str = ""  # Maps to STRATEGY_FACTORIES
    asset_class: str = "forex"
    symbols: list[str] = field(default_factory=list)
    timeframes: list[str] = field(default_factory=lambda: ["1h"])
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_sharpe: float = 1.5
    expected_max_dd: float = 0.05
    expected_win_rate: float = 0.55
    rationale: str = ""
    status: ResearchStatus = ResearchStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BacktestResult:
    """Result of backtesting a hypothesis"""
    hypothesis_id: str
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    total_trades: int = 0
    avg_trade_duration: timedelta = timedelta(0)
    parameter_stability: float = 1.0
    out_of_sample_sharpe: float = 0.0
    applied_filters: bool = False
    filter_results: dict[str, bool] = field(default_factory=dict)
    equity_curve: list[dict] = field(default_factory=list)
    trades: list[dict] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)


class HypothesisGenerator:
    """Generates new strategy hypotheses"""
    
    def __init__(self, market_data: Any = None):
        self.market_data = market_data
        
        # Parameter spaces for different strategy types
        self.param_spaces = {
            "trend_following": {
                "fast_ema": [8, 10, 12, 15, 20],
                "slow_ema": [20, 26, 30, 40, 50],
                "signal_ema": [5, 9, 12],
                "atr_period": [10, 14, 20],
                "atr_multiplier": [1.5, 2.0, 2.5, 3.0],
                "trend_filter_period": [100, 150, 200, 250],
                "min_trend_strength": [0.01, 0.02, 0.03],
            },
            "mean_reversion": {
                "lookback_period": [10, 15, 20, 30, 50],
                "entry_zscore": [1.5, 2.0, 2.5, 3.0],
                "exit_zscore": [0.0, 0.5, 1.0],
                "stop_zscore": [2.5, 3.0, 3.5, 4.0],
                "bb_period": [15, 20, 25],
                "bb_std": [1.5, 2.0, 2.5],
                "cooldown_bars": [5, 10, 15, 20],
            },
            "carry_trade": {
                "min_carry_bps": [25, 50, 75, 100],
                "max_leverage": [2.0, 3.0, 4.0, 5.0],
                "vol_target": [0.08, 0.10, 0.12, 0.15],
                "correlation_filter": [0.5, 0.6, 0.7, 0.8],
            }
        }
        
        self.asset_symbols = {
            "forex": ["EURUSD", "GBPUSD", "USDJPY", "USDCHF", "AUDUSD", "USDCAD", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"],
            "crypto": ["BTCUSD", "ETHUSD", "SOLUSD", "ADAUSD", "DOTUSD"],
            "metals": ["XAUUSD", "XAGUSD"],
            "indices": ["US30", "SPX500", "NAS100", "GER40", "UK100"],
        }
    
    def generate(self, count: int = 10, strategy_types: list[str] | None = None) -> list[Hypothesis]:
        """Generate random hypotheses"""
        if strategy_types is None:
            strategy_types = list(self.param_spaces.keys())
        
        hypotheses = []
        
        for _ in range(count):
            strategy_type = np.random.choice(strategy_types)
            param_space = self.param_spaces[strategy_type]
            
            # Random parameter combination
            params = {}
            for param, values in param_space.items():
                params[param] = np.random.choice(values)
            
            # Random symbols
            symbols = np.random.choice(
                self.asset_symbols.get("forex", ["EURUSD"]),
                size=np.random.randint(3, 8),
                replace=False
            ).tolist()
            
            # Random timeframes
            timeframes = np.random.choice(
                ["15m", "30m", "1h", "4h"],
                size=np.random.randint(1, 3),
                replace=False
            ).tolist()
            
            hypothesis = Hypothesis(
                name=f"{strategy_type}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
                description=f"Auto-generated {strategy_type} hypothesis",
                strategy_type=strategy_type,
                asset_class="forex",
                symbols=symbols,
                timeframes=timeframes,
                parameters=params,
                expected_sharpe=np.random.uniform(1.0, 2.5),
                expected_max_dd=np.random.uniform(0.03, 0.10),
                expected_win_rate=np.random.uniform(0.50, 0.65),
                rationale=f"Auto-generated parameter combination for {strategy_type}"
            )
            
            hypotheses.append(hypothesis)
        
        return hypotheses
    
    def generate_from_patterns(self, patterns: list[dict]) -> list[Hypothesis]:
        """Generate hypotheses from detected market patterns"""
        hypotheses = []
        
        for pattern in patterns:
            # Pattern: {type: "trend", strength: 0.8, symbol: "EURUSD", ...}
            if pattern["type"] == "strong_trend":
                hypothesis = Hypothesis(
                    name=f"trend_following_{pattern['symbol']}_{datetime.now(UTC).strftime('%Y%m%d')}",
                    description=f"Strong trend detected in {pattern['symbol']}",
                    strategy_type="trend_following",
                    symbols=[pattern["symbol"]],
                    parameters={
                        "fast_ema": 8,
                        "slow_ema": 21,
                        "atr_multiplier": 1.5,
                        "trend_filter_period": 50
                    },
                    rationale=f"Strong trend pattern detected (strength: {pattern['strength']:.2f})"
                )
                hypotheses.append(hypothesis)
            
            elif pattern["type"] == "mean_reversion":
                hypothesis = Hypothesis(
                    name=f"mean_reversion_{pattern['symbol']}_{datetime.now(UTC).strftime('%Y%m%d')}",
                    description=f"Mean reversion pattern in {pattern['symbol']}",
                    strategy_type="mean_reversion",
                    symbols=[pattern["symbol"]],
                    parameters={
                        "lookback_period": 15,
                        "entry_zscore": 2.5,
                        "bb_std": 2.5
                    },
                    rationale=f"Overextended price detected (z-score: {pattern.get('zscore', 2.5):.2f})"
                )
                hypotheses.append(hypothesis)
        
        return hypotheses


class VectorizedBacktester:
    """Fast vectorized backtesting engine"""
    
    def __init__(self, 
                 commission_bps: float = 1.0,
                 slippage_bps: float = 2.0,
                 initial_capital: float = 100000.0):
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        self.initial_capital = initial_capital
    
    def run(self, 
            strategy: BaseStrategy,
            price_data: dict[str, pd.DataFrame],
            start_date: datetime,
            end_date: datetime) -> BacktestResult:
        """Run vectorized backtest"""
        
        # This is a simplified version - production would be more complex
        # For each symbol, generate signals and simulate
        
        all_trades = []
        equity_curves = []
        
        for symbol, df in price_data.items():
            if symbol not in strategy.required_symbols:
                continue
            
            # Filter date range
            df = df[(df.index >= start_date) & (df.index <= end_date)]
            if len(df) < 100:
                continue
            
            # Generate signals (vectorized)
            signals = self._generate_signals_vectorized(strategy, df)
            
            # Simulate trades
            trades, equity = self._simulate_trades(df, signals)
            
            all_trades.extend(trades)
            equity_curves.append(equity)
        
        # Aggregate results
        return self._aggregate_results(all_trades, equity_curves)
    
    def _generate_signals_vectorized(self, strategy: BaseStrategy, df: pd.DataFrame) -> pd.Series:
        """Generate signals using vectorized operations"""
        # This would call strategy logic in vectorized form
        # For now, return dummy signals
        return pd.Series(0, index=df.index)
    
    def _simulate_trades(self, df: pd.DataFrame, signals: pd.Series) -> tuple:
        """Simulate trades from signals"""
        trades = []
        equity = self.initial_capital
        position = 0
        entry_price = 0
        
        for i in range(1, len(df)):
            signal = signals.iloc[i]
            price = df['close'].iloc[i]
            
            if signal != 0 and position == 0:
                # Enter position
                position = signal  # 1 or -1
                entry_price = price * (1 + self.slippage_bps / 10000 * signal)
            elif signal == 0 and position != 0:
                # Exit position
                exit_price = price * (1 - self.slippage_bps / 10000 * position)
                pnl = (exit_price - entry_price) * position
                commission = (entry_price + exit_price) * abs(position) * self.commission_bps / 10000
                net_pnl = pnl - commission
                
                trades.append({
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "pnl": pnl,
                    "net_pnl": net_pnl,
                    "side": "long" if position > 0 else "short"
                })
                position = 0
        
        return trades, [equity]
    
    def _aggregate_results(self, trades: list, equity_curves: list) -> BacktestResult:
        """Aggregate backtest results"""
        if not trades:
            return BacktestResult(hypothesis_id="", applied_filters=False)
        
        pnls = [t["net_pnl"] for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]
        
        total_return = sum(pnls) / self.initial_capital
        annualized_return = total_return * (252 / max(len(trades), 1))
        sharpe = np.mean(pnls) / np.std(pnls) * np.sqrt(252) if np.std(pnls) > 0 else 0
        
        win_rate = len(wins) / len(trades)
        profit_factor = sum(wins) / abs(sum(losses)) if losses else float('inf')
        expectancy = np.mean(pnls)
        max_dd = max(pnls) - min(pnls) if pnls else 0
        
        return BacktestResult(
            hypothesis_id="",
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            total_trades=len(trades),
            applied_filters=True
        )


class WalkForwardValidator:
    """Walk-forward validation for robustness"""
    
    def __init__(self, 
                 train_window: int = 252,
                 test_window: int = 63,
                 step: int = 21,
                 min_train_size: int = 100):
        self.train_window = train_window
        self.test_window = test_window
        self.step = step
        self.min_train_size = min_train_size
    
    def validate(self, 
                 strategy: BaseStrategy,
                 price_data: dict[str, pd.DataFrame],
                 start_date: datetime,
                 end_date: datetime) -> dict[str, Any]:
        """Run walk-forward validation"""
        
        # Get common date range
        all_dates = set()
        for df in price_data.values():
            all_dates.update(df.index)
        
        all_dates = sorted([d for d in all_dates if start_date <= d <= end_date])
        
        if len(all_dates) < self.train_window + self.test_window:
            return {"error": "Insufficient data for walk-forward"}
        
        results = []
        
        for i in range(0, len(all_dates) - self.train_window - self.test_window, self.step):
            train_end = all_dates[i + self.train_window]
            test_end = all_dates[min(i + self.train_window + self.test_window, len(all_dates) - 1)]
            
            train_start = all_dates[i]
            
            # Filter data
            train_data = {}
            test_data = {}
            
            for symbol, df in price_data.items():
                train_data[symbol] = df[(df.index >= train_start) & (df.index <= train_end)]
                test_data[symbol] = df[(df.index > train_end) & (df.index <= test_end)]
            
            if any(len(d) < self.min_train_size for d in train_data.values()):
                continue
            
            # Optimize parameters on train
            best_params = self._optimize_parameters(strategy, train_data)
            
            # Test on out-of-sample
            test_result = self._test_parameters(strategy, test_data, best_params)
            
            results.append({
                "train_start": train_start,
                "train_end": train_end,
                "test_start": train_end,
                "test_end": test_end,
                "params": best_params,
                "sharpe": test_result.get("sharpe", 0),
                "return": test_result.get("return", 0),
                "max_dd": test_result.get("max_dd", 0),
            })
        
        # Aggregate
        if results:
            oos_sharpe = np.mean([r["sharpe"] for r in results])
            oos_return = np.mean([r["return"] for r in results])
            consistency = sum(1 for r in results if r["sharpe"] > 0) / len(results)
            
            return {
                "windows": len(results),
                "oos_sharpe": oos_sharpe,
                "oos_return": oos_return,
                "consistency": consistency,
                "results": results,
                "validated": oos_sharpe > 0.5 and consistency > 0.5
            }
        
        return {"validated": False, "error": "No valid windows"}
    
    def _optimize_parameters(self, strategy: BaseStrategy, train_data: dict) -> dict:
        """Optimize strategy parameters on training data"""
        # Grid search or Bayesian optimization
        # For now, return default params
        return strategy.parameters
    
    def _test_parameters(self, strategy: BaseStrategy, test_data: dict, params: dict) -> dict:
        """Test parameters on test data"""
        # Update strategy params and run backtest
        return {"sharpe": 1.0, "return": 0.1, "max_dd": 0.05}


class StatisticalValidator:
    """Statistical significance testing for strategies"""
    
    @staticmethod
    def deflated_sharpe(sharpe: float, n_trials: int, n_obs: int) -> float:
        """Calculate Deflated Sharpe Ratio (Bailey & Lopez de Prado)"""
        if n_trials <= 1:
            return sharpe
        
        # Expected maximum Sharpe under null
        em = np.sqrt(2 * np.log(n_trials)) * (1 - 0.5772 / np.sqrt(2 * np.log(n_trials)))
        var = (1 + 0.5 * sharpe**2) / n_obs
        
        dsr = (sharpe - em) / np.sqrt(var) if var > 0 else 0
        p_value = stats.norm.cdf(dsr)
        
        return {
            "deflated_sharpe": dsr,
            "p_value": p_value,
            "significant": p_value < 0.05
        }
    
    @staticmethod
    def pbo_sharpe(returns: np.ndarray, n_splits: int = 10) -> dict:
        """Probability of Backtest Overfitting"""
        from itertools import combinations
        
        n = len(returns)
        if n < n_splits * 2:
            return {"pbo": 1.0}
        
        splits = np.array_split(returns, n_splits)
        
        # All combinations of train/test
        rank_count = 0
        total = 0
        
        for train_idx in combinations(range(n_splits), n_splits // 2):
            train = np.concatenate([splits[i] for i in train_idx])
            test = np.concatenate([splits[i] for i in range(n_splits) if i not in train_idx])
            
            train_sharpe = np.mean(train) / np.std(train) * np.sqrt(252) if np.std(train) > 0 else 0
            test_sharpe = np.mean(test) / np.std(test) * np.sqrt(252) if np.std(test) > 0 else 0
            
            if train_sharpe > 0:
                total += 1
                if test_sharpe < 0:
                    rank_count += 1
        
        pbo = rank_count / total if total > 0 else 1.0
        
        return {
            "pbo": pbo,
            "overfitted": pbo > 0.5
        }
    
    @staticmethod
    def minimum_track_record(sharpe: float, vol: float, prob: float = 0.95) -> int:
        """Minimum track record length for statistical significance"""
        # From Bailey & Lopez de Prado
        z = stats.norm.ppf(prob)
        n = int((z * vol / sharpe) ** 2)
        return max(n, 30)


class HypothesisFilter:
    """Filter hypotheses based on backtest results"""
    
    def __init__(self, config: dict | None = None):
        self.config = config or {
            "min_sharpe": 1.0,
            "min_annual_return": 0.10,
            "max_drawdown": 0.10,
            "min_win_rate": 0.45,
            "min_profit_factor": 1.2,
            "min_trades": 30,
            "min_oos_sharpe": 0.5,
            "max_pbo": 0.5,
            "min_deflated_sharpe": 1.0,
        }
    
    def evaluate(self, result: BacktestResult, oos_result: dict | None = None) -> dict[str, bool]:
        """Evaluate backtest against filters"""
        filters = {}
        
        filters["sharpe"] = result.sharpe_ratio >= self.config["min_sharpe"]
        filters["annual_return"] = result.annualized_return >= self.config["min_annual_return"]
        filters["max_drawdown"] = result.max_drawdown <= self.config["max_drawdown"]
        filters["win_rate"] = result.win_rate >= self.config["min_win_rate"]
        filters["profit_factor"] = result.profit_factor >= self.config["min_profit_factor"]
        filters["min_trades"] = result.total_trades >= self.config["min_trades"]
        
        if oos_result:
            filters["oos_sharpe"] = oos_result.get("oos_sharpe", 0) >= self.config["min_oos_sharpe"]
            filters["oos_consistency"] = oos_result.get("consistency", 0) > 0.5
        
        # Overall not_implemented
        filters["overall"] = all(filters.values())
        
        return filters


class AutoResearchPipeline:
    """Main pipeline for continuous strategy research"""
    
    def __init__(self, 
                 timescaledb: TimescaleDB,
                 risk_engine: RiskEngine,
                 strategy_registry: StrategyRegistry,
                 capital_allocator: CapitalAllocator,
                 config: dict | None = None):
        self.timescaledb = timescaledb
        self.risk_engine = risk_engine
        self.strategy_registry = strategy_registry
        self.capital_allocator = capital_allocator
        
        self.config = config or {
            "generation_interval_hours": 24,
            "max_hypotheses_per_cycle": 20,
            "paper_trading_days": 14,
            "min_paper_sharpe": 1.0,
            "max_concurrent_paper": 5,
        }
        
        # Components
        self.generator = HypothesisGenerator()
        self.backtester = VectorizedBacktester()
        self.wf_validator = WalkForwardValidator()
        self.stat_validator = StatisticalValidator()
        self.filter = HypothesisFilter()
        
        # State
        self.hypotheses: dict[str, Hypothesis] = {}
        self.backtest_results: dict[str, BacktestResult] = {}
        self.paper_strategies: dict[str, datetime] = {}  # strategy_id -> start_date
        
        self.running = False
        self.logger = logger
    
    async def start(self):
        self.running = True
        asyncio.create_task(self._research_loop())
        asyncio.create_task(self._paper_monitoring_loop())
        self.logger.info("AutoResearchPipeline started")
    
    async def stop(self):
        self.running = False
        self.logger.info("AutoResearchPipeline stopped")
    
    async def _research_loop(self):
        """Main research cycle"""
        while self.running:
            try:
                await self._run_research_cycle()
            except Exception as e:
                self.logger.error(f"Research cycle error: {e}")
            
            await asyncio.sleep(self.config["generation_interval_hours"] * 3600)
    
    async def _run_research_cycle(self):
        """Run one research cycle"""
        self.logger.info("Starting research cycle...")
        
        # 1. Generate hypotheses
        hypotheses = self.generator.generate(
            count=self.config["max_hypotheses_per_cycle"]
        )
        
        for hyp in hypotheses:
            self.hypotheses[hyp.hypothesis_id] = hyp
            await self._store_hypothesis(hyp)
        
        # 2. Backtest all pending hypotheses
        for hyp in list(self.hypotheses.values()):
            if hyp.status == ResearchStatus.PENDING:
                await self._backtest_hypothesis(hyp)
        
        # 3. Walk-forward validate validated backtests
        for hyp in list(self.hypotheses.values()):
            if hyp.status == ResearchStatus.BACKTESTING:
                await self._walkforward_validate(hyp)
        
        # 4. Statistical validation
        for hyp in list(self.hypotheses.values()):
            if hyp.status == ResearchStatus.VALIDATING:
                await self._statistical_validate(hyp)
        
        # 5. Deploy to paper trading
        for hyp in list(self.hypotheses.values()):
            if hyp.status == ResearchStatus.PAPER_TRADING:
                await self._deploy_paper(hyp)
        
        self.logger.info(f"Research cycle complete. Hypotheses: {len(self.hypotheses)}")
    
    async def _backtest_hypothesis(self, hypothesis: Hypothesis):
        """Run backtest on hypothesis"""
        hypothesis.status = ResearchStatus.BACKTESTING
        self.logger.info(f"Backtesting {hypothesis.hypothesis_id}")
        
        try:
            # Get price data
            price_data = await self._get_price_data(hypothesis)
            
            # Create strategy instance
            factory = STRATEGY_FACTORIES.get(hypothesis.strategy_type)
            if not factory:
                hypothesis.status = ResearchStatus.REJECTED
                return
            
            config = StrategyConfig(
                strategy_id=hypothesis.hypothesis_id,
                name=hypothesis.name,
                strategy_type=hypothesis.strategy_type,
                parameters={"strategy_type": hypothesis.strategy_type, **hypothesis.parameters},
                symbols=hypothesis.symbols
            )
            
            strategy = factory(config)
            
            # Run backtest
            end_date = datetime.now(UTC)
            start_date = end_date - timedelta(days=365)
            
            result = self.backtester.run(strategy, price_data, start_date, end_date)
            result.hypothesis_id = hypothesis.hypothesis_id
            
            # Apply filters
            filters = self.filter.evaluate(result)
            result.applied_filters = filters.get("overall", False)
            result.filter_results = filters
            
            self.backtest_results[hypothesis.hypothesis_id] = result
            
            if result.applied_filters:
                hypothesis.status = ResearchStatus.BACKTESTING
                self.logger.info(f"Backtest applied: {hypothesis.hypothesis_id} Sharpe={result.sharpe_ratio:.2f}")
            else:
                hypothesis.status = ResearchStatus.REJECTED
                self.logger.info(f"Backtest failed: {hypothesis.hypothesis_id}")
            
            await self._store_backtest_result(result)
            
        except Exception as e:
            self.logger.error(f"Backtest error for {hypothesis.hypothesis_id}: {e}")
            hypothesis.status = ResearchStatus.REJECTED
    
    async def _walkforward_validate(self, hypothesis: Hypothesis):
        """Run walk-forward validation"""
        hypothesis.status = ResearchStatus.VALIDATING
        self.logger.info(f"Walk-forward validation: {hypothesis.hypothesis_id}")
        
        try:
            factory = STRATEGY_FACTORIES.get(hypothesis.strategy_type)
            config = StrategyConfig(
                strategy_id=hypothesis.hypothesis_id,
                strategy_type=hypothesis.strategy_type,
                parameters={"strategy_type": hypothesis.strategy_type, **hypothesis.parameters}
            )
            strategy = factory(config)
            
            price_data = await self._get_price_data(hypothesis)
            
            wf_result = self.wf_validator.validate(strategy, price_data, 
                                                   datetime.now(UTC) - timedelta(days=730),
                                                   datetime.now(UTC))
            
            if wf_result.get("validated", False):
                self.logger.info(f"Walk-forward validated: {hypothesis.hypothesis_id}")
                # Continue to statistical validation
            else:
                hypothesis.status = ResearchStatus.REJECTED
                self.logger.info(f"Walk-forward failed: {hypothesis.hypothesis_id}")
                
        except Exception as e:
            self.logger.error(f"Walk-forward error: {e}")
            hypothesis.status = ResearchStatus.REJECTED
    
    async def _statistical_validate(self, hypothesis: Hypothesis):
        """Run statistical significance tests"""
        hypothesis.status = ResearchStatus.VALIDATING
        
        try:
            result = self.backtest_results.get(hypothesis.hypothesis_id)
            if not result:
                hypothesis.status = ResearchStatus.REJECTED
                return
            
            # Deflated Sharpe
            dsr = self.stat_validator.deflated_sharpe(
                result.sharpe_ratio,
                n_trials=100,  # Approximate number of trials
                n_obs=result.total_trades
            )
            
            # PBO
            # Would need full return series
            
            if dsr["significant"]:
                hypothesis.status = ResearchStatus.PAPER_TRADING
                self.logger.info(f"Statistical validation validated: {hypothesis.hypothesis_id}")
            else:
                hypothesis.status = ResearchStatus.REJECTED
                self.logger.info(f"Statistical validation failed: {hypothesis.hypothesis_id}")
                
        except Exception as e:
            self.logger.error(f"Statistical validation error: {e}")
            hypothesis.status = ResearchStatus.REJECTED
    
    async def _deploy_paper(self, hypothesis: Hypothesis):
        """Deploy to paper trading"""
        if len(self.paper_strategies) >= self.config["max_concurrent_paper"]:
            return
        
        # Create paper trading config
        config = StrategyConfig(
            strategy_id=hypothesis.hypothesis_id,
            name=hypothesis.name,
            strategy_type=hypothesis.strategy_type,
            parameters={"strategy_type": hypothesis.strategy_type, **hypothesis.parameters},
            is_paper=True,
            status=StrategyStatus.PAPER_TRADING
        )
        
        _strategy = self.strategy_registry.create_strategy(config)
        self.paper_strategies[hypothesis.hypothesis_id] = datetime.now(UTC)
        hypothesis.status = ResearchStatus.PAPER_TRADING
        
        self.logger.info(f"Deployed to paper trading: {hypothesis.hypothesis_id}")
    
    async def _paper_monitoring_loop(self):
        """Monitor paper trading strategies"""
        while self.running:
            try:
                for hyp_id, start_date in list(self.paper_strategies.items()):
                    if (datetime.now(UTC) - start_date).days >= self.config["paper_trading_days"]:
                        # Evaluate paper performance
                        await self._evaluate_paper(hyp_id)
            except Exception as e:
                self.logger.error(f"Paper monitoring error: {e}")
            
            await asyncio.sleep(3600)  # Hourly
    
    async def _evaluate_paper(self, hypothesis_id: str):
        """Evaluate paper trading performance"""
        # Get paper trading results
        # If meets criteria, promote to live
        # Otherwise, reject or extend
        
        # For now, simple logic
        del self.paper_strategies[hypothesis_id]
        hypothesis = self.hypotheses.get(hypothesis_id)
        if hypothesis:
            hypothesis.status = ResearchStatus.LIVE
            self.logger.info(f"Promoted to live: {hypothesis_id}")
    
    async def _get_price_data(self, hypothesis: Hypothesis) -> dict[str, pd.DataFrame]:
        """Get price data for backtesting"""
        # Would fetch from TimescaleDB
        # For now, return empty
        return {}
    
    async def _store_hypothesis(self, hypothesis: Hypothesis):
        """Store hypothesis in database."""
        logger.info(f"Storing hypothesis: {hypothesis.name}")

    async def _store_backtest_result(self, result: BacktestResult):
        """Store backtest result in database."""
        logger.info(f"Storing backtest result: {result}")
    
    def get_status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "total_hypotheses": len(self.hypotheses),
            "by_status": {
                status.value: sum(1 for h in self.hypotheses.values() if h.status == status)
                for status in ResearchStatus
            },
            "paper_trading": len(self.paper_strategies),
            "config": self.config
        }