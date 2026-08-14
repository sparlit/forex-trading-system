from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

import numpy as np
import polars as pl
from loguru import logger

from src.data.models import AssetClass, Bar, Symbol, Timeframe
from src.risk.position_sizer import PositionSizer, PositionSizingConfig
from src.strategy.base.signal import Direction, Signal, SignalType
from src.strategy.base.strategy import Strategy, StrategyConfig


class BacktestMode(str, Enum):
    VECTORIZED = "vectorized"      # Fast, uses Polars/NumPy
    EVENT_DRIVEN = "event_driven"  # Realistic, simulates tick-by-tick


@dataclass
class BacktestConfig:
    """Configuration for backtesting."""
    mode: BacktestMode = BacktestMode.VECTORIZED
    initial_capital: Decimal = Decimal(100000)
    commission_per_lot: Decimal = Decimal("7.0")
    spread_bps: int = 10
    slippage_bps: int = 2
    max_positions: int = 20
    allow_short: bool = True
    margin_requirement: float = 0.01
    position_sizing: PositionSizingConfig = field(default_factory=PositionSizingConfig)
    start_date: datetime = None
    end_date: datetime = None
    symbols: list[str] = field(default_factory=list)
    timeframe: Timeframe = Timeframe.H1
    data_source: str = "mt5"


@dataclass
class Trade:
    """Represents a completed trade."""
    trade_id: UUID = field(default_factory=uuid4)
    strategy_id: str = ""
    symbol: str = ""
    direction: Direction = Direction.FLAT
    entry_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    exit_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    entry_price: Decimal = Decimal(0)
    exit_price: Decimal = Decimal(0)
    volume: Decimal = Decimal(0)
    pnl: Decimal = Decimal(0)
    commission: Decimal = Decimal(0)
    swap: Decimal = Decimal(0)
    net_pnl: Decimal = Decimal(0)
    return_pct: float = 0.0
    duration: timedelta = field(default_factory=timedelta)
    max_favorable: Decimal = Decimal(0)
    max_adverse: Decimal = Decimal(0)
    exit_reason: str = ""  # "tp", "sl", "signal", "eod", "manual"


@dataclass
class BacktestResult:
    """Complete backtest results."""
    config: BacktestConfig
    strategy_id: str
    start_date: datetime
    end_date: datetime
    initial_capital: Decimal
    final_equity: Decimal
    total_return: float
    total_return_pct: float
    annual_return: float

    # Risk metrics
    max_drawdown: float
    max_drawdown_pct: float
    current_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    var_95: float
    var_99: float

    # Trade statistics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    expectancy: float
    avg_win: float
    avg_loss: float
    largest_win: float
    largest_loss: float
    avg_trade_duration: timedelta
    avg_bars_held: float

    # Equity curve
    equity_curve: list[tuple[datetime, Decimal]] = field(default_factory=list)
    daily_returns: list[tuple[datetime, float]] = field(default_factory=list)
    trades: list[Trade] = field(default_factory=list)

    # Monthly returns
    monthly_returns: dict[str, float] = field(default_factory=dict)

    # Additional metrics
    recovery_factor: float = 0.0
    payoff_ratio: float = 0.0
    profit_to_max_dd: float = 0.0
    ulcer_index: float = 0.0
    sterling_ratio: float = 0.0

    metadata: dict[str, Any] = field(default_factory=dict)


class VectorizedBacktestEngine:
    """Fast vectorized backtesting using Polars."""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.position_sizer = PositionSizer(config.position_sizing)

    async def run(
        self,
        strategy: Strategy,
        data: dict[str, pl.DataFrame],  # symbol -> DataFrame
    ) -> BacktestResult:
        """Run vectorized backtest."""

        # Prepare data
        prepared_data = self._prepare_data(data)

        # Initialize state
        equity = self.config.initial_capital
        positions: dict[str, dict] = {}  # symbol -> position dict
        trades: list[Trade] = []
        equity_curve = [(self.config.start_date, equity)]

        # Get all timestamps
        all_timestamps = sorted(set().union(*[set(df["timestamp"].to_list()) for df in prepared_data.values()]))

        for timestamp in all_timestamps:
            # Update equity with current positions
            equity = self._update_equity(equity, positions, prepared_data, timestamp)
            equity_curve.append((timestamp, equity))

            # Process each symbol
            for symbol, df in prepared_data.items():
                # Get bar for this timestamp
                bar_rows = df.filter(pl.col("timestamp") == timestamp)
                if len(bar_rows) == 0:
                    continue

                bar = bar_rows.row(0, named=True)
                bar_obj = self._row_to_bar(bar, symbol)

                # Check exit conditions for existing positions
                if symbol in positions:
                    exit_trade = self._check_exit(positions[symbol], bar_obj, timestamp)
                    if exit_trade:
                        trades.append(exit_trade)
                        equity += exit_trade.net_pnl
                        del positions[symbol]

                # Generate signals
                signals = await strategy.on_bar(bar_obj)

                # Process entry signals
                for signal in signals:
                    if signal.signal_type in (SignalType.ENTRY_LONG, SignalType.ENTRY_SHORT) and symbol not in positions:
                        if len(positions) >= self.config.max_positions:
                            continue

                        trade = self._enter_position(signal, bar_obj, equity, timestamp)
                        if trade:
                            positions[signal.symbol] = trade

        # Close remaining positions at end
        final_timestamp = all_timestamps[-1] if all_timestamps else self.config.end_date
        for symbol, pos in positions.items():
            df = prepared_data.get(symbol)
            if df is not None:
                last_bar = df.tail(1).row(0, named=True)
                bar_obj = self._row_to_bar(last_bar, symbol)
                exit_trade = self._force_exit(pos, bar_obj, final_timestamp, "eod")
                trades.append(exit_trade)
                equity += exit_trade.net_pnl

        # Calculate metrics
        return self._calculate_metrics(
            strategy.config.strategy_id,
            equity_curve,
            trades,
            self.config.initial_capital,
            equity,
        )

    def _prepare_data(self, data: dict[str, pl.DataFrame]) -> dict[str, pl.DataFrame]:
        """Prepare data with indicators."""
        prepared = {}
        for symbol, df in data.items():
            # Filter date range
            if self.config.start_date:
                df = df.filter(pl.col("timestamp") >= self.config.start_date)
            if self.config.end_date:
                df = df.filter(pl.col("timestamp") <= self.config.end_date)

            # Add indicators
            from src.strategy.technical.indicators import TechnicalIndicators
            df = TechnicalIndicators.add_all_indicators_polars(df)

            prepared[symbol] = df.sort("timestamp")

        return prepared

    def _row_to_bar(self, row: dict, symbol: str) -> Bar:
        """Convert row to Bar object."""
        return Bar(
            symbol_id=0,
            symbol=symbol,
            timestamp=row["timestamp"],
            timeframe=self.config.timeframe,
            open=Decimal(str(row["open"])),
            high=Decimal(str(row["high"])),
            low=Decimal(str(row["low"])),
            close=Decimal(str(row["close"])),
            volume=Decimal(str(row["volume"])),
            spread=Decimal(str(row.get("spread", 0))),
        )

    def _enter_position(self, signal: Signal, bar: Bar, equity: Decimal, timestamp: datetime) -> dict | None:
        """Enter a new position."""
        # Create mock symbol for sizing
        symbol = Symbol(
            symbol_id=0,
            symbol=signal.symbol,
            base_currency="",
            quote_currency="",
            asset_class=AssetClass.FOREX,  # placeholder
            contract_size=Decimal(1),
            tick_size=Decimal("0.00001"),
            min_volume=Decimal("0.01"),
            max_volume=Decimal(100),
            volume_step=Decimal("0.01"),
            margin_rate=Decimal(str(self.config.margin_requirement)),
        )

        # Calculate position size
        sizing = self.position_sizer.calculate_position_size(
            signal=signal,
            symbol=symbol,
            equity=equity,
            current_positions={},
            account_balance=equity,
            free_margin=equity,
        )

        if not sizing.size or sizing.size <= 0:
            return None

        # Calculate costs
        entry_price = signal.entry_price or bar.close
        commission = sizing.size * self.config.commission_per_lot
        spread_cost = sizing.size * entry_price * Decimal(str(self.config.spread_bps / 10000))
        slippage_cost = sizing.size * entry_price * Decimal(str(self.config.slippage_bps / 10000))

        return {
            "symbol": signal.symbol,
            "direction": signal.direction,
            "entry_time": timestamp,
            "entry_price": entry_price,
            "volume": sizing.size,
            "stop_loss": signal.stop_loss,
            "take_profit": signal.take_profit,
            "commission": commission,
            "spread_cost": spread_cost,
            "slippage_cost": slippage_cost,
            "max_favorable": Decimal(0),
            "max_adverse": Decimal(0),
        }

    def _check_exit(self, position: dict, bar: Bar, timestamp: datetime) -> Trade | None:
        """Check if position should be exited."""
        exit_price = None
        exit_reason = ""

        direction = position["direction"]
        entry_price = position["entry_price"]
        stop_loss = position["stop_loss"]
        take_profit = position["take_profit"]

        # Update max favorable/adverse
        if direction == Direction.LONG:
            favorable = bar.high - entry_price
            adverse = entry_price - bar.low
        else:
            favorable = entry_price - bar.low
            adverse = bar.high - entry_price

        position["max_favorable"] = max(position["max_favorable"], Decimal(str(favorable)))
        position["max_adverse"] = max(position["max_adverse"], Decimal(str(adverse)))

        # Check stop loss
        if stop_loss:
            if direction == Direction.LONG and bar.low <= stop_loss or direction == Direction.SHORT and bar.high >= stop_loss:
                exit_price = stop_loss
                exit_reason = "sl"

        # Check take profit
        if not exit_price and take_profit:
            if direction == Direction.LONG and bar.high >= take_profit or direction == Direction.SHORT and bar.low <= take_profit:
                exit_price = take_profit
                exit_reason = "tp"

        if exit_price:
            return self._create_trade(position, exit_price, timestamp, exit_reason)

        return None

    def _force_exit(self, position: dict, bar: Bar, timestamp: datetime, reason: str) -> Trade:
        """Force exit position."""
        exit_price = bar.close
        return self._create_trade(position, exit_price, timestamp, reason)

    def _create_trade(self, position: dict, exit_price: Decimal, timestamp: datetime, reason: str) -> Trade:
        """Create trade record."""
        direction = position["direction"]
        entry_price = position["entry_price"]
        volume = position["volume"]

        # Calculate P&L
        if direction == Direction.LONG:
            gross_pnl = (exit_price - entry_price) * volume
        else:
            gross_pnl = (entry_price - exit_price) * volume

        commission = position["commission"] + (volume * self.config.commission_per_lot)  # Exit commission
        swap = position.get("swap", Decimal(0))
        spread_cost = position["spread_cost"] + position["slippage_cost"]

        net_pnl = gross_pnl - commission - swap - spread_cost
        return_pct = float(net_pnl / (entry_price * volume)) if entry_price * volume > 0 else 0.0

        return Trade(
            strategy_id="",  # Would be set by caller
            symbol=position["symbol"],
            direction=direction,
            entry_time=position["entry_time"],
            exit_time=timestamp,
            entry_price=entry_price,
            exit_price=exit_price,
            volume=volume,
            pnl=gross_pnl,
            commission=commission,
            swap=swap,
            net_pnl=net_pnl,
            return_pct=return_pct,
            duration=timestamp - position["entry_time"],
            max_favorable=position["max_favorable"],
            max_adverse=position["max_adverse"],
            exit_reason=reason,
        )

    def _update_equity(self, equity: Decimal, positions: dict, data: dict, timestamp: datetime) -> Decimal:
        """Update equity with unrealized P&L."""
        # In vectorized mode, equity only changes on realized trades
        # Unrealized is tracked separately
        return equity

    def _calculate_metrics(
        self,
        strategy_id: str,
        equity_curve: list[tuple[datetime, Decimal]],
        trades: list[Trade],
        initial_capital: Decimal,
        final_equity: Decimal,
    ) -> BacktestResult:
        """Calculate performance metrics."""

        if not equity_curve:
            equity_curve = [(self.config.start_date, initial_capital), (self.config.end_date, final_equity)]

        # Convert to arrays
        [t for t, _ in equity_curve]
        equities = [float(e) for _, e in equity_curve]

        # Returns
        equity_array = np.array(equities)
        returns = np.diff(equity_array) / equity_array[:-1]
        returns = returns[~np.isnan(returns)]

        # Total return
        total_return = float(final_equity - initial_capital)
        total_return_pct = total_return / float(initial_capital) * 100

        # Annual return
        days = (self.config.end_date - self.config.start_date).days if self.config.start_date and self.config.end_date else 365
        annual_return = (1 + total_return_pct / 100) ** (365 / days) - 1 if days > 0 else 0

        # Drawdown
        peak = np.maximum.accumulate(equity_array)
        drawdown = (peak - equity_array) / peak
        max_drawdown_pct = float(np.max(drawdown)) * 100
        max_drawdown = float(np.max(peak - equity_array))
        current_drawdown = float(drawdown[-1]) * 100

        # Risk metrics
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe_ratio = float(np.mean(returns) / np.std(returns) * np.sqrt(252))
            downside_returns = returns[returns < 0]
            if len(downside_returns) > 0 and np.std(downside_returns) > 0:
                sortino_ratio = float(np.mean(returns) / np.std(downside_returns) * np.sqrt(252))
            else:
                sortino_ratio = 0
        else:
            sharpe_ratio = 0
            sortino_ratio = 0

        calmar_ratio = annual_return / (max_drawdown_pct / 100) if max_drawdown_pct > 0 else 0

        # VaR
        var_95 = float(np.percentile(returns, 5)) * 100 if len(returns) > 0 else 0
        var_99 = float(np.percentile(returns, 1)) * 100 if len(returns) > 0 else 0

        # Trade statistics
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t.net_pnl > 0])
        losing_trades = len([t for t in trades if t.net_pnl < 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        wins = [float(t.net_pnl) for t in trades if t.net_pnl > 0]
        losses = [float(t.net_pnl) for t in trades if t.net_pnl < 0]

        avg_win = float(np.mean(wins)) if wins else 0
        avg_loss = float(np.mean(losses)) if losses else 0
        largest_win = float(np.max(wins)) if wins else 0
        largest_loss = float(np.min(losses)) if losses else 0

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
        expectancy = (win_rate * avg_win + (1 - win_rate) * avg_loss) if total_trades > 0 else 0

        avg_duration = sum(t.duration.total_seconds() for t in trades) / total_trades if total_trades > 0 else 0
        avg_bars_held = avg_duration / (self.config.timeframe.to_seconds()) if self.config.timeframe.to_seconds() > 0 else 0

        # Monthly returns
        monthly_returns = {}
        for i in range(1, len(equity_curve)):
            prev_date, prev_eq = equity_curve[i - 1]
            curr_date, curr_eq = equity_curve[i]
            if prev_date.month != curr_date.month or prev_date.year != curr_date.year:
                month_key = f"{prev_date.year}-{prev_date.month:02d}"
                monthly_returns[month_key] = float((curr_eq - prev_eq) / prev_eq * 100)

        # Additional metrics
        recovery_factor = total_return / max_drawdown if max_drawdown > 0 else 0
        payoff_ratio = avg_win / abs(avg_loss) if avg_loss != 0 else 0
        profit_to_max_dd = total_return / max_drawdown if max_drawdown > 0 else 0

        # Ulcer Index
        ulcer_index = float(np.sqrt(np.mean(drawdown ** 2))) * 100

        # Sterling Ratio
        sterling_ratio = annual_return / (ulcer_index / 100) if ulcer_index > 0 else 0

        return BacktestResult(
            config=self.config,
            strategy_id=strategy_id,
            start_date=self.config.start_date,
            end_date=self.config.end_date,
            initial_capital=initial_capital,
            final_equity=final_equity,
            total_return=total_return,
            total_return_pct=total_return_pct,
            annual_return=annual_return * 100,
            max_drawdown=max_drawdown,
            max_drawdown_pct=max_drawdown_pct,
            current_drawdown=current_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            var_95=var_95,
            var_99=var_99,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=expectancy,
            avg_win=avg_win,
            avg_loss=avg_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            avg_trade_duration=timedelta(seconds=avg_duration),
            avg_bars_held=avg_bars_held,
            equity_curve=equity_curve,
            daily_returns=[],  # Would compute from equity curve
            trades=trades,
            monthly_returns=monthly_returns,
            recovery_factor=recovery_factor,
            payoff_ratio=payoff_ratio,
            profit_to_max_dd=profit_to_max_dd,
            ulcer_index=ulcer_index,
            sterling_ratio=sterling_ratio,
        )


class EventDrivenBacktestEngine:
    """Event-driven backtesting for realistic simulation."""

    def __init__(self, config: BacktestConfig):
        self.config = config
        self.position_sizer = PositionSizer(config.position_sizing)

    async def run(
        self,
        strategy: Strategy,
        data: dict[str, list[Bar]],  # symbol -> list of bars
    ) -> BacktestResult:
        """Run event-driven backtest with tick simulation."""
        # This would simulate tick-by-tick using tick data
        # For now, fall back to vectorized
        vectorized = VectorizedBacktestEngine(self.config)

        # Convert bars to DataFrames
        dfs = {}
        for symbol, bars in data.items():
            dfs[symbol] = pl.DataFrame({
                "timestamp": [b.timestamp for b in bars],
                "open": [float(b.open) for b in bars],
                "high": [float(b.high) for b in bars],
                "low": [float(b.low) for b in bars],
                "close": [float(b.close) for b in bars],
                "volume": [float(b.volume) for b in bars],
                "spread": [float(b.spread) for b in bars],
            })

        return await vectorized.run(strategy, dfs)


class WalkForwardOptimizer:
    """Walk-forward optimization for strategy parameters."""

    def __init__(
        self,
        train_window: int = 252,  # Trading days
        test_window: int = 63,    # Trading days
        step_size: int = 21,      # Step forward
        min_train_size: int = 100,
    ):
        self.train_window = train_window
        self.test_window = test_window
        self.step_size = step_size
        self.min_train_size = min_train_size

    async def optimize(
        self,
        strategy_class: type,
        param_grid: dict[str, list[Any]],
        data: dict[str, pl.DataFrame],
        config: BacktestConfig,
        metric: str = "sharpe_ratio",
    ) -> dict[str, Any]:
        """Run walk-forward optimization."""

        # Get date range from data
        all_dates = sorted(set().union(*[set(df["timestamp"].to_list()) for df in data.values()]))

        if len(all_dates) < self.train_window + self.test_window:
            logger.warning("Insufficient data for walk-forward optimization")
            return {}

        results = []
        best_params = None
        best_score = -float("inf")

        # Walk forward
        for i in range(0, len(all_dates) - self.train_window - self.test_window + 1, self.step_size):
            train_start = all_dates[i]
            train_end = all_dates[i + self.train_window - 1]
            test_start = all_dates[i + self.train_window]
            test_end = all_dates[min(i + self.train_window + self.test_window - 1, len(all_dates) - 1)]

            # Skip if test window too small
            if (test_end - test_start).days < self.min_train_size:
                continue

            # Update config for this window
            window_config = BacktestConfig(
                **{**config.__dict__, "start_date": train_start, "end_date": test_end}
            )

            # Grid search on training period
            train_results = await self._grid_search(
                strategy_class, param_grid, data, window_config, metric, train_start, train_end
            )

            if not train_results:
                continue

            # Select best params from training
            best_train = max(train_results, key=lambda x: x["score"])
            params = best_train["params"]

            # Test on out-of-sample period
            test_config = BacktestConfig(
                **{**config.__dict__, "start_date": test_start, "end_date": test_end}
            )

            test_result = await self._test_params(
                strategy_class, params, data, test_config, metric
            )

            if test_result:
                results.append({
                    "train_start": train_start,
                    "train_end": train_end,
                    "test_start": test_start,
                    "test_end": test_end,
                    "params": params,
                    "train_score": best_train["score"],
                    "test_score": test_result["score"],
                    "test_result": test_result["result"],
                })

                if test_result["score"] > best_score:
                    best_score = test_result["score"]
                    best_params = params

        return {
            "windows": results,
            "best_params": best_params,
            "best_score": best_score,
            "avg_test_score": np.mean([r["test_score"] for r in results]) if results else 0,
            "consistency": sum(1 for r in results if r["test_score"] > 0) / len(results) if results else 0,
        }

    async def _grid_search(
        self,
        strategy_class: type,
        param_grid: dict[str, list[Any]],
        data: dict[str, pl.DataFrame],
        config: BacktestConfig,
        metric: str,
        train_start: datetime,
        train_end: datetime,
    ) -> list[dict]:
        """Grid search over parameter space."""
        import itertools

        # Generate parameter combinations
        keys = list(param_grid.keys())
        values = list(param_grid.values())
        combinations = list(itertools.product(*values))

        results = []

        for combo in combinations:
            params = dict(zip(keys, combo))

            # Create strategy with params
            strategy_config = StrategyConfig(
                strategy_id=f"wfo_{hash(str(params))}",
                name=strategy_class.__name__,
                parameters=params,
            )
            strategy = strategy_class(strategy_config)
            await strategy.initialize()

            # Run backtest on training period
            train_config = BacktestConfig(
                **{**config.__dict__, "start_date": train_start, "end_date": train_end}
            )

            engine = VectorizedBacktestEngine(train_config)
            result = await engine.run(strategy, data)

            # Extract metric
            score = getattr(result, metric, 0)

            results.append({
                "params": params,
                "score": score,
                "result": result,
            })

        return results

    async def _test_params(
        self,
        strategy_class: type,
        params: dict[str, Any],
        data: dict[str, pl.DataFrame],
        config: BacktestConfig,
        metric: str,
    ) -> dict | None:
        """Test parameters on out-of-sample data."""
        strategy_config = StrategyConfig(
            strategy_id=f"wfo_test_{hash(str(params))}",
            name=strategy_class.__name__,
            parameters=params,
        )
        strategy = strategy_class(strategy_config)
        await strategy.initialize()

        engine = VectorizedBacktestEngine(config)
        result = await engine.run(strategy, data)

        score = getattr(result, metric, 0)

        return {
            "params": params,
            "score": score,
            "result": result,
        }


class MonteCarloSimulator:
    """Monte Carlo simulation for backtest validation."""

    def __init__(self, num_simulations: int = 1000):
        self.num_simulations = num_simulations

    def simulate(
        self,
        trades: list[Trade],
        initial_capital: Decimal,
        num_simulations: int | None = None,
    ) -> dict[str, Any]:
        """Run Monte Carlo simulation on trade results."""
        num_simulations = num_simulations or self.num_simulations

        if not trades:
            return {}

        # Extract trade returns
        returns = [float(t.return_pct) for t in trades]

        simulation_results = []

        for _ in range(num_simulations):
            # Bootstrap sample
            sampled_returns = np.random.choice(returns, size=len(returns), replace=True)

            # Simulate equity curve
            equity = float(initial_capital)
            equity_curve = [equity]

            for ret in sampled_returns:
                equity *= (1 + ret / 100)
                equity_curve.append(equity)

            # Calculate metrics
            total_return = (equity - float(initial_capital)) / float(initial_capital) * 100

            equity_array = np.array(equity_curve)
            peak = np.maximum.accumulate(equity_array)
            drawdown = (peak - equity_array) / peak
            max_dd = float(np.max(drawdown)) * 100

            simulation_results.append({
                "final_equity": equity,
                "total_return": total_return,
                "max_drawdown": max_dd,
            })

        # Aggregate results
        final_equities = [r["final_equity"] for r in simulation_results]
        total_returns = [r["total_return"] for r in simulation_results]
        max_drawdowns = [r["max_drawdown"] for r in simulation_results]

        return {
            "num_simulations": num_simulations,
            "mean_final_equity": float(np.mean(final_equities)),
            "median_final_equity": float(np.median(final_equities)),
            "std_final_equity": float(np.std(final_equities)),
            "percentile_5": float(np.percentile(final_equities, 5)),
            "percentile_95": float(np.percentile(final_equities, 95)),
            "mean_return": float(np.mean(total_returns)),
            "median_return": float(np.median(total_returns)),
            "prob_profit": sum(1 for r in total_returns if r > 0) / num_simulations,
            "prob_loss": sum(1 for r in total_returns if r < 0) / num_simulations,
            "mean_max_dd": float(np.mean(max_drawdowns)),
            "max_max_dd": float(np.max(max_drawdowns)),
            "percentile_95_max_dd": float(np.percentile(max_drawdowns, 95)),
            "ruin_probability": sum(1 for eq in final_equities if eq < float(initial_capital) * 0.5) / num_simulations,
        }