"""
Elite Autonomous Quantum Trading System - Walk-Forward Backtesting Engine
Genetic Algorithm Optimization, Rolling Windows, Dynamic Slippage & Fees
"""

from __future__ import annotations

import logging
import random
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class OptimizationMetric(Enum):
    SHARPE_RATIO = "sharpe_ratio"
    SORTINO_RATIO = "sortino_ratio"
    CALMAR_RATIO = "calmar_ratio"
    TOTAL_RETURN = "total_return"
    MAX_DRAWDOWN = "max_drawdown"
    WIN_RATE = "win_rate"
    PROFIT_FACTOR = "profit_factor"
    EXPECTANCY = "expectancy"


@dataclass
class BacktestConfig:
    """Backtest configuration."""
    start_date: datetime = field(default_factory=lambda: datetime.now(UTC) - timedelta(days=365))
    end_date: datetime = field(default_factory=lambda: datetime.now(UTC))
    initial_capital: float = 100000
    commission_per_trade: float = 0.0001  # 1 basis point
    slippage_bps: float = 0.5  # 0.5 basis points
    max_position_size: float = 1.0  # 100% of capital
    margin_requirement: float = 0.1  # 10% margin
    risk_free_rate: float = 0.02
    benchmark_symbol: str = "SPY"
    
    # Walk-forward settings
    train_window_days: int = 252  # 1 year
    test_window_days: int = 63    # 1 quarter
    step_size_days: int = 21      # 1 month
    
    # Genetic algorithm settings
    population_size: int = 50
    generations: int = 100
    mutation_rate: float = 0.1
    crossover_rate: float = 0.7
    elite_size: int = 5
    
    # Parameter bounds for optimization
    param_bounds: dict[str, tuple[float, float]] = field(default_factory=dict)


@dataclass
class StrategyParameters:
    """Strategy parameter set for optimization."""
    params: dict[str, float]
    fitness: float = 0.0
    metrics: dict[str, float] = field(default_factory=dict)
    generation: int = 0
    individual_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    
    def mutate(self, bounds: dict[str, tuple[float, float]], rate: float = 0.1) -> StrategyParameters:
        """Create mutated copy."""
        new_params = self.params.copy()
        for key, (min_val, max_val) in bounds.items():
            if key in new_params and random.random() < rate:
                # Gaussian mutation
                current = new_params[key]
                sigma = (max_val - min_val) * 0.1
                new_val = current + random.gauss(0, sigma)
                new_params[key] = max(min_val, min(max_val, new_val))
        
        return StrategyParameters(params=new_params, generation=self.generation + 1)
    
    @staticmethod
    def crossover(parent1: StrategyParameters, parent2: StrategyParameters, 
                  bounds: dict[str, tuple[float, float]], rate: float = 0.7) -> tuple[StrategyParameters, StrategyParameters]:
        """Create two children via crossover."""
        if random.random() > rate:
            return parent1, parent2
        
        child1_params = {}
        child2_params = {}
        
        for key in parent1.params:
            if key in parent2.params and random.random() < 0.5:
                child1_params[key] = parent1.params[key]
                child2_params[key] = parent2.params[key]
            else:
                child1_params[key] = parent2.params.get(key, parent1.params[key])
                child2_params[key] = parent1.params.get(key, parent2.params[key])
        
        gen = max(parent1.generation, parent2.generation) + 1
        return (
            StrategyParameters(params=child1_params, generation=gen),
            StrategyParameters(params=child2_params, generation=gen)
        )


@dataclass
class BacktestResult:
    """Complete backtest result."""
    strategy_name: str
    parameters: dict[str, float]
    start_date: datetime
    end_date: datetime
    
    # Performance metrics
    total_return: float = 0.0
    annualized_return: float = 0.0
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    
    # Trade statistics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    largest_win: float = 0.0
    largest_loss: float = 0.0
    
    # Risk metrics
    volatility: float = 0.0
    downside_volatility: float = 0.0
    var_95: float = 0.0
    var_99: float = 0.0
    
    # Equity curve
    equity_curve: list[float] = field(default_factory=list)
    daily_returns: list[float] = field(default_factory=list)
    drawdown_curve: list[float] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)
    
    # Trade log
    trades: list[dict[str, Any]] = field(default_factory=list)
    
    # Walk-forward specific
    oos_metrics: dict[str, float] = field(default_factory=dict)  # Out-of-sample
    is_metrics: dict[str, float] = field(default_factory=dict)   # In-sample


@dataclass
class WalkForwardResult:
    """Walk-forward analysis result."""
    windows: list[BacktestResult] = field(default_factory=list)
    aggregated_metrics: dict[str, float] = field(default_factory=dict)
    parameter_stability: dict[str, float] = field(default_factory=dict)
    robustness_score: float = 0.0


class WalkForwardBacktester:
    """
    Walk-Forward Backtesting Engine with Genetic Algorithm Optimization.
    
    Features:
    - Rolling window walk-forward analysis
    - Genetic algorithm for parameter optimization
    - Dynamic slippage and commission modeling
    - Out-of-sample validation
    - Parameter stability analysis
    - Robustness scoring
    """
    
    def __init__(self, config: BacktestConfig | None = None):
        self.config = config or BacktestConfig()
        self.market_data: dict[str, pd.DataFrame] = {}
        self.strategy_func: Any = None
        self.results: list[BacktestResult] = []
        
        logger.info("WalkForwardBacktester initialized")
    
    def load_data(self, symbol: str, data: pd.DataFrame):
        """Load market data for symbol."""
        # Ensure required columns
        required = ['open', 'high', 'low', 'close', 'volume']
        if not all(col in data.columns for col in required):
            raise ValueError(f"Data must contain columns: {required}")
        
        # Ensure datetime index
        if not isinstance(data.index, pd.DatetimeIndex):
            if 'timestamp' in data.columns:
                data.index = pd.to_datetime(data['timestamp'])
            else:
                raise ValueError("Data must have datetime index or 'timestamp' column")
        
        data = data.sort_index()
        self.market_data[symbol] = data
        logger.info(f"Loaded {len(data)} bars for {symbol}")
    
    def set_strategy(self, strategy_func: callable):
        """Set strategy function to test.
        
        Strategy function signature:
        def strategy(data: pd.DataFrame, params: dict) -> pd.Series:
            # Returns signal series: 1=long, -1=short, 0=flat
            return signals
        """
        self.strategy_func = strategy_func
    
    async def run_walk_forward(self, strategy_name: str) -> WalkForwardResult:
        """Run complete walk-forward analysis."""
        if self.strategy_func is None:
            raise ValueError("Strategy function not set")
        
        # Get primary symbol data
        primary_symbol = list(self.market_data.keys())[0]
        data = self.market_data[primary_symbol]
        
        # Filter by date range
        mask = (data.index >= self.config.start_date) & (data.index <= self.config.end_date)
        data = data[mask]
        
        if len(data) < self.config.train_window_days + self.config.test_window_days:
            raise ValueError("Insufficient data for walk-forward windows")
        
        windows = []
        current_start = self.config.start_date
        
        window_num = 0
        while True:
            train_end = current_start + timedelta(days=self.config.train_window_days)
            test_end = train_end + timedelta(days=self.config.test_window_days)
            
            if test_end > self.config.end_date:
                break
            
            window_num += 1
            logger.info(f"Walk-forward window {window_num}: "
                       f"Train {current_start.date()} to {train_end.date()}, "
                       f"Test {train_end.date()} to {test_end.date()}")
            
            # Split data
            train_mask = (data.index >= current_start) & (data.index < train_end)
            test_mask = (data.index >= train_end) & (data.index < test_end)
            
            train_data = data[train_mask]
            test_data = data[test_mask]
            
            if len(train_data) < 50 or len(test_data) < 10:
                logger.warning(f"Insufficient data in window {window_num}, skipping")
                current_start += timedelta(days=self.config.step_size_days)
                continue
            
            # Optimize on training data
            best_params = await self._genetic_optimize(
                strategy_name, train_data, primary_symbol
            )
            
            # Test on out-of-sample data
            oos_result = self._run_backtest(
                strategy_name, best_params, test_data, primary_symbol,
                train_end, test_end
            )
            oos_result.is_metrics = self._extract_metrics(
                self._run_backtest(strategy_name, best_params, train_data, primary_symbol,
                                 current_start, train_end)
            )
            
            windows.append(oos_result)
            
            # Move to next window
            current_start += timedelta(days=self.config.step_size_days)
        
        # Aggregate results
        wf_result = WalkForwardResult(windows=windows)
        wf_result.aggregated_metrics = self._aggregate_metrics(windows)
        wf_result.parameter_stability = self._analyze_parameter_stability(windows)
        wf_result.robustness_score = self._calculate_robustness(windows)
        
        logger.info(f"Walk-forward complete: {len(windows)} windows, "
                   f"Robustness: {wf_result.robustness_score:.3f}")
        
        return wf_result
    
    async def _genetic_optimize(
        self, 
        strategy_name: str, 
        train_data: pd.DataFrame,
        symbol: str
    ) -> dict[str, float]:
        """Genetic algorithm optimization on training data."""
        bounds = self.config.param_bounds
        
        if not bounds:
            # Default bounds for common parameters
            bounds = {
                'fast_period': (5, 50),
                'slow_period': (20, 200),
                'signal_period': (5, 50),
                'threshold': (0.001, 0.05),
                'stop_loss': (0.01, 0.1),
                'take_profit': (0.01, 0.2),
            }
        
        # Initialize population
        population = []
        for _ in range(self.config.population_size):
            params = {}
            for key, (min_val, max_val) in bounds.items():
                if isinstance(min_val, int) or (isinstance(min_val, float) and min_val == int(min_val)):
                    params[key] = float(random.randint(int(min_val), int(max_val)))
                else:
                    params[key] = random.uniform(min_val, max_val)
            population.append(StrategyParameters(params=params))
        
        best_overall = None
        best_fitness = -float('inf')
        
        for generation in range(self.config.generations):
            # Evaluate fitness
            for individual in population:
                if individual.fitness == 0:  # Not evaluated yet
                    result = self._run_backtest(
                        strategy_name, individual.params, train_data, symbol,
                        train_data.index[0], train_data.index[-1]
                    )
                    individual.metrics = self._extract_metrics(result)
                    individual.fitness = self._calculate_fitness(individual.metrics)
                    
                    if individual.fitness > best_fitness:
                        best_fitness = individual.fitness
                        best_overall = individual
            
            # Sort by fitness
            population.sort(key=lambda x: x.fitness, reverse=True)
            
            # Elitism
            new_population = population[:self.config.elite_size]
            
            # Generate offspring
            while len(new_population) < self.config.population_size:
                # Tournament selection
                parent1 = self._tournament_select(population)
                parent2 = self._tournament_select(population)
                
                # Crossover
                child1, child2 = StrategyParameters.crossover(
                    parent1, parent2, bounds, self.config.crossover_rate
                )
                
                # Mutation
                child1 = child1.mutate(bounds, self.config.mutation_rate)
                child2 = child2.mutate(bounds, self.config.mutation_rate)
                
                new_population.extend([child1, child2])
            
            population = new_population[:self.config.population_size]
            
            if generation % 20 == 0:
                logger.debug(f"Generation {generation}: Best fitness = {best_fitness:.4f}")
        
        logger.info(f"Optimization complete: Best fitness = {best_fitness:.4f}")
        return best_overall.params if best_overall else {}
    
    def _tournament_select(self, population: list[StrategyParameters], tournament_size: int = 3) -> StrategyParameters:
        """Tournament selection."""
        contestants = random.sample(population, min(tournament_size, len(population)))
        return max(contestants, key=lambda x: x.fitness)
    
    def _calculate_fitness(self, metrics: dict[str, float]) -> float:
        """Calculate fitness from metrics."""
        # Multi-objective fitness
        sharpe = metrics.get('sharpe_ratio', 0)
        max_dd = abs(metrics.get('max_drawdown', 1))
        win_rate = metrics.get('win_rate', 0)
        profit_factor = metrics.get('profit_factor', 0)
        total_trades = metrics.get('total_trades', 0)
        
        # Penalize low trade count
        trade_penalty = min(1.0, total_trades / 30)
        
        # Composite fitness
        fitness = (
            sharpe * 0.4 +
            (1 - max_dd) * 0.3 +
            win_rate * 0.15 +
            min(profit_factor, 3) / 3 * 0.15
        ) * trade_penalty
        
        return fitness
    
    def _run_backtest(
        self,
        strategy_name: str,
        params: dict[str, float],
        data: pd.DataFrame,
        symbol: str,
        start_date: datetime,
        end_date: datetime
    ) -> BacktestResult:
        """Run single backtest."""
        # Generate signals
        signals = self.strategy_func(data, params)
        
        # Ensure signals aligned with data
        signals = signals.reindex(data.index).fillna(0)
        
        # Calculate positions (shift signals by 1 to avoid lookahead)
        positions = signals.shift(1).fillna(0)
        
        # Calculate returns
        returns = data['close'].pct_change().fillna(0)
        strategy_returns = positions * returns
        
        # Apply transaction costs
        trades = positions.diff().abs()
        transaction_costs = trades * (self.config.commission_per_trade + self.config.slippage_bps / 10000)
        net_returns = strategy_returns - transaction_costs
        
        # Equity curve
        equity = (1 + net_returns).cumprod() * self.config.initial_capital
        
        # Calculate metrics
        result = BacktestResult(
            strategy_name=strategy_name,
            parameters=params,
            start_date=start_date,
            end_date=end_date,
            equity_curve=equity.tolist(),
            daily_returns=net_returns.tolist(),
            timestamps=data.index.tolist()
        )
        
        # Performance metrics
        total_days = (end_date - start_date).days
        years = total_days / 365.25
        
        result.total_return = (equity.iloc[-1] / self.config.initial_capital) - 1
        result.annualized_return = (1 + result.total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # Sharpe
        if net_returns.std() > 0:
            excess_returns = net_returns - self.config.risk_free_rate / 252
            result.sharpe_ratio = excess_returns.mean() / net_returns.std() * np.sqrt(252)
        
        # Sortino
        downside_returns = net_returns[net_returns < 0]
        if len(downside_returns) > 0 and downside_returns.std() > 0:
            result.sortino_ratio = (net_returns.mean() - self.config.risk_free_rate / 252) / downside_returns.std() * np.sqrt(252)
        
        # Drawdown
        rolling_max = equity.expanding().max()
        drawdown = (equity - rolling_max) / rolling_max
        result.max_drawdown = drawdown.min()
        result.drawdown_curve = drawdown.tolist()
        
        # Max drawdown duration
        dd_periods = (drawdown < 0).astype(int)
        dd_groups = (dd_periods != dd_periods.shift()).cumsum()
        dd_durations = dd_periods.groupby(dd_groups).sum()
        result.max_drawdown_duration = dd_durations.max() if len(dd_durations) > 0 else 0
        
        # Calmar
        if result.max_drawdown != 0:
            result.calmar_ratio = result.annualized_return / abs(result.max_drawdown)
        
        # Trade statistics
        position_changes = positions.diff().fillna(0)
        trade_entries = position_changes[position_changes != 0]
        result.total_trades = len(trade_entries)
        
        if result.total_trades > 0:
            # Simplified trade PnL calculation
            trade_returns = net_returns[position_changes != 0]
            winning = trade_returns[trade_returns > 0]
            losing = trade_returns[trade_returns < 0]
            
            result.winning_trades = len(winning)
            result.losing_trades = len(losing)
            result.win_rate = result.winning_trades / result.total_trades if result.total_trades > 0 else 0
            
            if len(winning) > 0:
                result.avg_win = winning.mean()
                result.largest_win = winning.max()
            if len(losing) > 0:
                result.avg_loss = losing.mean()
                result.largest_loss = losing.min()
            
            if result.avg_loss != 0:
                result.profit_factor = abs(result.avg_win * result.winning_trades / (result.avg_loss * result.losing_trades))
            
            result.expectancy = (result.win_rate * result.avg_win) - ((1 - result.win_rate) * abs(result.avg_loss))
        
        # Risk metrics
        result.volatility = net_returns.std() * np.sqrt(252)
        result.downside_volatility = downside_returns.std() * np.sqrt(252) if len(downside_returns) > 0 else 0
        
        if len(net_returns) > 0:
            result.var_95 = np.percentile(net_returns, 5)
            result.var_99 = np.percentile(net_returns, 1)
        
        # Trade log
        for idx, change in trade_entries.items():
            result.trades.append({
                'timestamp': idx,
                'symbol': symbol,
                'side': 'buy' if change > 0 else 'sell',
                'price': data.loc[idx, 'close'],
                'size': abs(change),
                'pnl': net_returns.loc[idx] * self.config.initial_capital
            })
        
        return result
    
    def _extract_metrics(self, result: BacktestResult) -> dict[str, float]:
        """Extract metrics dict from result."""
        return {
            'total_return': result.total_return,
            'annualized_return': result.annualized_return,
            'sharpe_ratio': result.sharpe_ratio,
            'sortino_ratio': result.sortino_ratio,
            'calmar_ratio': result.calmar_ratio,
            'max_drawdown': result.max_drawdown,
            'max_drawdown_duration': result.max_drawdown_duration,
            'total_trades': result.total_trades,
            'win_rate': result.win_rate,
            'profit_factor': result.profit_factor,
            'expectancy': result.expectancy,
            'avg_win': result.avg_win,
            'avg_loss': result.avg_loss,
            'volatility': result.volatility,
            'downside_volatility': result.downside_volatility,
            'var_95': result.var_95,
            'var_99': result.var_99,
        }
    
    def _aggregate_metrics(self, windows: list[BacktestResult]) -> dict[str, float]:
        """Aggregate metrics across walk-forward windows."""
        if not windows:
            return {}
        
        metrics = defaultdict(list)
        for w in windows:
            m = self._extract_metrics(w)
            for k, v in m.items():
                metrics[k].append(v)
        
        aggregated = {}
        for k, v in metrics.items():
            aggregated[f'{k}_mean'] = np.mean(v)
            aggregated[f'{k}_std'] = np.std(v)
            aggregated[f'{k}_min'] = np.min(v)
            aggregated[f'{k}_max'] = np.max(v)
            aggregated[f'{k}_median'] = np.median(v)
        
        # Consistency metrics
        aggregated['sharpe_consistency'] = sum(1 for w in windows if w.sharpe_ratio > 1) / len(windows)
        aggregated['positive_windows'] = sum(1 for w in windows if w.total_return > 0) / len(windows)
        
        return aggregated
    
    def _analyze_parameter_stability(self, windows: list[BacktestResult]) -> dict[str, float]:
        """Analyze parameter stability across windows."""
        if len(windows) < 2:
            return {}
        
        param_stability = {}
        all_params = set()
        for w in windows:
            all_params.update(w.parameters.keys())
        
        for param in all_params:
            values = [w.parameters.get(param, 0) for w in windows]
            if len(values) > 1 and np.mean(values) != 0:
                cv = np.std(values) / abs(np.mean(values))  # Coefficient of variation
                param_stability[param] = 1 / (1 + cv)  # Higher = more stable
            else:
                param_stability[param] = 1.0
        
        return param_stability
    
    def _calculate_robustness(self, windows: list[BacktestResult]) -> float:
        """Calculate overall robustness score (0-1)."""
        if not windows:
            return 0.0
        
        scores = []
        
        # Consistency of positive returns
        pos_rate = sum(1 for w in windows if w.total_return > 0) / len(windows)
        scores.append(pos_rate)
        
        # Sharpe consistency
        sharpe_cons = sum(1 for w in windows if w.sharpe_ratio > 0.5) / len(windows)
        scores.append(sharpe_cons)
        
        # Drawdown control
        dd_control = sum(1 for w in windows if w.max_drawdown > -0.2) / len(windows)
        scores.append(dd_control)
        
        # Win rate consistency
        wr_cons = sum(1 for w in windows if w.win_rate > 0.4) / len(windows)
        scores.append(wr_cons)
        
        return np.mean(scores)


# Example strategy functions
def ema_crossover_strategy(data: pd.DataFrame, params: dict) -> pd.Series:
    """EMA Crossover strategy."""
    fast = int(params.get('fast_period', 20))
    slow = int(params.get('slow_period', 50))
    
    ema_fast = data['close'].ewm(span=fast).mean()
    ema_slow = data['close'].ewm(span=slow).mean()
    
    signals = pd.Series(0, index=data.index)
    signals[ema_fast > ema_slow] = 1
    signals[ema_fast < ema_slow] = -1
    
    return signals


def bollinger_rsi_strategy(data: pd.DataFrame, params: dict) -> pd.Series:
    """Bollinger Bands + RSI mean reversion."""
    period = int(params.get('period', 20))
    std_dev = params.get('std_dev', 2.0)
    rsi_period = int(params.get('rsi_period', 14))
    rsi_oversold = params.get('rsi_oversold', 30)
    rsi_overbought = params.get('rsi_overbought', 70)
    
    # Bollinger Bands
    sma = data['close'].rolling(period).mean()
    std = data['close'].rolling(period).std()
    upper = sma + std_dev * std
    lower = sma - std_dev * std
    
    # RSI
    delta = data['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(rsi_period).mean()
    loss = -delta.where(delta < 0, 0).rolling(rsi_period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    signals = pd.Series(0, index=data.index)
    # Long: price below lower band AND RSI oversold
    signals[(data['close'] < lower) & (rsi < rsi_oversold)] = 1
    # Short: price above upper band AND RSI overbought
    signals[(data['close'] > upper) & (rsi > rsi_overbought)] = -1
    
    return signals


def donchian_breakout_strategy(data: pd.DataFrame, params: dict) -> pd.Series:
    """Donchian Channel Breakout (Turtle System)."""
    period = int(params.get('period', 20))
    exit_period = int(params.get('exit_period', 10))
    atr_period = int(params.get('atr_period', 14))
    atr_mult = params.get('atr_multiplier', 2.0)
    filter_ema = int(params.get('filter_ema', 200))
    
    upper = data['high'].rolling(period).max()
    lower = data['low'].rolling(period).min()
    exit_upper = data['high'].rolling(exit_period).max()
    exit_lower = data['low'].rolling(exit_period).min()
    
    trend_ema = data['close'].ewm(span=filter_ema).mean()
    
    signals = pd.Series(0, index=data.index)
    position = 0
    
    for i in range(len(data)):
        if position == 0:
            # Long entry
            if data['close'].iloc[i] > upper.iloc[i] and data['close'].iloc[i] > trend_ema.iloc[i]:
                position = 1
            # Short entry
            elif data['close'].iloc[i] < lower.iloc[i] and data['close'].iloc[i] < trend_ema.iloc[i]:
                position = -1
        elif position == 1:
            # Exit long
            if data['close'].iloc[i] < exit_lower.iloc[i]:
                position = 0
        elif position == -1:
            # Exit short
            if data['close'].iloc[i] > exit_upper.iloc[i]:
                position = 0
        
        signals.iloc[i] = position
    
    return signals


# Global instance
backtester = WalkForwardBacktester()


async def get_backtester(config: BacktestConfig | None = None) -> WalkForwardBacktester:
    """Get or create global backtester."""
    global backtester
    if config:
        backtester = WalkForwardBacktester(config)
    return backtester