from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import polars as pl

from src.strategy.backtest.engine import BacktestResult, Trade


@dataclass
class PerformanceMetrics:
    """Comprehensive performance metrics."""

    # Returns
    total_return: float = 0.0
    total_return_pct: float = 0.0
    annual_return: float = 0.0
    monthly_return_avg: float = 0.0
    monthly_return_std: float = 0.0

    # Risk-adjusted returns
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    sterling_ratio: float = 0.0
    burke_ratio: float = 0.0
    omega_ratio: float = 0.0
    kappa_ratio: float = 0.0

    # Drawdown
    max_drawdown: float = 0.0
    max_drawdown_pct: float = 0.0
    avg_drawdown: float = 0.0
    avg_drawdown_duration: float = 0.0  # days
    max_drawdown_duration: float = 0.0  # days
    current_drawdown: float = 0.0
    ulcer_index: float = 0.0
    pain_index: float = 0.0
    pain_ratio: float = 0.0

    # Risk
    volatility_annual: float = 0.0
    downside_volatility: float = 0.0
    var_95: float = 0.0
    var_99: float = 0.0
    cvar_95: float = 0.0
    cvar_99: float = 0.0
    skewness: float = 0.0
    kurtosis: float = 0.0
    tail_ratio: float = 0.0

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
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_bars_held: float = 0.0
    avg_trade_duration: float = 0.0  # seconds

    # Advanced
    recovery_factor: float = 0.0
    payoff_ratio: float = 0.0
    profit_to_max_dd: float = 0.0
    k_ratio: float = 0.0
    r_squared: float = 0.0

    # Benchmark comparison
    alpha: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0
    treynor_ratio: float = 0.0
    correlation: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}

    @classmethod
    def from_backtest_result(cls, result: BacktestResult, benchmark_returns: np.ndarray = None) -> PerformanceMetrics:
        """Create metrics from backtest result."""
        metrics = cls()

        # Basic returns
        metrics.total_return = result.total_return
        metrics.total_return_pct = result.total_return_pct
        metrics.annual_return = result.annual_return

        # Risk-adjusted
        metrics.sharpe_ratio = result.sharpe_ratio
        metrics.sortino_ratio = result.sortino_ratio
        metrics.calmar_ratio = result.calmar_ratio
        metrics.sterling_ratio = result.sterling_ratio
        metrics.recovery_factor = result.recovery_factor
        metrics.payoff_ratio = result.payoff_ratio
        metrics.profit_to_max_dd = result.profit_to_max_dd
        metrics.ulcer_index = result.ulcer_index

        # Drawdown
        metrics.max_drawdown = result.max_drawdown
        metrics.max_drawdown_pct = result.max_drawdown_pct
        metrics.current_drawdown = result.current_drawdown

        # Trade stats
        metrics.total_trades = result.total_trades
        metrics.winning_trades = result.winning_trades
        metrics.losing_trades = result.losing_trades
        metrics.win_rate = result.win_rate
        metrics.profit_factor = result.profit_factor
        metrics.expectancy = result.expectancy
        metrics.avg_win = result.avg_win
        metrics.avg_loss = result.avg_loss
        metrics.largest_win = result.largest_win
        metrics.largest_loss = result.largest_loss
        metrics.avg_bars_held = result.avg_bars_held
        metrics.avg_trade_duration = result.avg_trade_duration.total_seconds()

        return metrics


def calculate_advanced_metrics(
    equity_curve: list[tuple],
    trades: list[Trade],
    benchmark_returns: np.ndarray = None,
    risk_free_rate: float = 0.02,
) -> PerformanceMetrics:
    """Calculate comprehensive performance metrics."""

    if not equity_curve or len(equity_curve) < 2:
        return PerformanceMetrics()

    timestamps = [t for t, _ in equity_curve]
    equities = [float(e) for _, e in equity_curve]

    equity_array = np.array(equities)
    returns = np.diff(equity_array) / equity_array[:-1]
    returns = returns[~np.isnan(returns)]

    if len(returns) == 0:
        return PerformanceMetrics()

    metrics = PerformanceMetrics()

    # --- Returns ---
    metrics.total_return = (equity_array[-1] - equity_array[0]) / equity_array[0]
    metrics.total_return_pct = metrics.total_return * 100

    # Annualized return
    days = (timestamps[-1] - timestamps[0]).days
    years = max(days / 365.25, 1/365.25)
    metrics.annual_return = (1 + metrics.total_return) ** (1 / years) - 1

    # Monthly returns
    monthly_returns = []
    for i in range(1, len(equity_curve)):
        prev_date, prev_eq = equity_curve[i - 1]
        curr_date, curr_eq = equity_curve[i]
        if prev_date.month != curr_date.month or prev_date.year != curr_date.year:
            monthly_returns.append((curr_eq - prev_eq) / prev_eq)

    if monthly_returns:
        metrics.monthly_return_avg = np.mean(monthly_returns) * 100
        metrics.monthly_return_std = np.std(monthly_returns) * 100

    # --- Risk-Adjusted Returns ---
    if np.std(returns) > 0:
        excess_returns = returns - risk_free_rate / 252
        metrics.sharpe_ratio = np.mean(excess_returns) / np.std(returns) * np.sqrt(252)

    # Sortino
    downside_returns = returns[returns < 0]
    if len(downside_returns) > 0 and np.std(downside_returns) > 0:
        metrics.sortino_ratio = np.mean(excess_returns) / np.std(downside_returns) * np.sqrt(252)

    # --- Drawdown ---
    peak = np.maximum.accumulate(equity_array)
    drawdown = (peak - equity_array) / peak
    drawdown_pct = drawdown * 100

    metrics.max_drawdown = float(np.max(peak - equity_array))
    metrics.max_drawdown_pct = float(np.max(drawdown_pct))
    metrics.current_drawdown = float(drawdown_pct[-1])

    # Drawdown periods
    in_drawdown = drawdown > 0
    dd_periods = []
    current_period = 0
    for is_dd in in_drawdown:
        if is_dd:
            current_period += 1
        elif current_period > 0:
            dd_periods.append(current_period)
            current_period = 0
    if current_period > 0:
        dd_periods.append(current_period)

    if dd_periods:
        metrics.avg_drawdown_duration = np.mean(dd_periods)
        metrics.max_drawdown_duration = np.max(dd_periods)

    # Average drawdown
    dd_values = drawdown_pct[drawdown_pct > 0]
    if len(dd_values) > 0:
        metrics.avg_drawdown = float(np.mean(dd_values))

    # Ulcer Index
    metrics.ulcer_index = float(np.sqrt(np.mean(drawdown_pct ** 2)))

    # Pain Index
    metrics.pain_index = float(np.mean(drawdown_pct)) if len(drawdown_pct) > 0 else 0
    metrics.pain_ratio = metrics.annual_return / metrics.pain_index if metrics.pain_index > 0 else 0

    # Calmar
    if metrics.max_drawdown_pct > 0:
        metrics.calmar_ratio = metrics.annual_return / (metrics.max_drawdown_pct / 100)

    # Sterling
    if metrics.avg_drawdown > 0:
        metrics.sterling_ratio = metrics.annual_return / (metrics.avg_drawdown / 100)

    # Burke
    if len(dd_periods) > 0:
        metrics.burke_ratio = metrics.annual_return / np.sqrt(np.sum(np.array(dd_periods) ** 2))

    # --- Risk ---
    metrics.volatility_annual = float(np.std(returns) * np.sqrt(252)) * 100
    metrics.downside_volatility = float(np.std(downside_returns) * np.sqrt(252)) * 100 if len(downside_returns) > 0 else 0

    # VaR
    metrics.var_95 = float(np.percentile(returns, 5)) * 100
    metrics.var_99 = float(np.percentile(returns, 1)) * 100

    # CVaR (Expected Shortfall)
    var_95_threshold = np.percentile(returns, 5)
    var_99_threshold = np.percentile(returns, 1)
    metrics.cvar_95 = float(np.mean(returns[returns <= var_95_threshold])) * 100
    metrics.cvar_99 = float(np.mean(returns[returns <= var_99_threshold])) * 100

    # Skewness & Kurtosis
    from scipy import stats
    metrics.skewness = float(stats.skew(returns))
    metrics.kurtosis = float(stats.kurtosis(returns))

    # Tail Ratio
    p95 = np.percentile(returns, 95)
    p5 = np.percentile(returns, 5)
    if p5 != 0:
        metrics.tail_ratio = p95 / abs(p5)

    # Omega Ratio
    threshold = 0
    gains = returns[returns > threshold]
    losses = returns[returns <= threshold]
    if len(losses) > 0 and np.sum(losses) != 0:
        metrics.omega_ratio = np.sum(gains) / abs(np.sum(losses))

    # Kappa Ratio
    if metrics.var_95 != 0:
        metrics.kappa_ratio = metrics.annual_return / abs(metrics.var_95 / 100)

    # --- Trade Statistics ---
    if trades:
        metrics.total_trades = len(trades)
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl < 0]

        metrics.winning_trades = len(wins)
        metrics.losing_trades = len(losses)
        metrics.win_rate = len(wins) / len(trades) if trades else 0

        win_pnls = [float(t.net_pnl) for t in wins]
        loss_pnls = [float(t.net_pnl) for t in losses]

        metrics.avg_win = float(np.mean(win_pnls)) if win_pnls else 0
        metrics.avg_loss = float(np.mean(loss_pnls)) if loss_pnls else 0
        metrics.largest_win = float(np.max(win_pnls)) if win_pnls else 0
        metrics.largest_loss = float(np.min(loss_pnls)) if loss_pnls else 0

        gross_profit = sum(win_pnls) if win_pnls else 0
        gross_loss = abs(sum(loss_pnls)) if loss_pnls else 0
        metrics.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Expectancy
        metrics.expectancy = (metrics.win_rate * metrics.avg_win + (1 - metrics.win_rate) * metrics.avg_loss)

        # Payoff ratio
        metrics.payoff_ratio = metrics.avg_win / abs(metrics.avg_loss) if metrics.avg_loss != 0 else 0

        # Consecutive wins/losses
        max_consec_wins = 0
        max_consec_losses = 0
        current_wins = 0
        current_losses = 0

        for t in trades:
            if t.net_pnl > 0:
                current_wins += 1
                current_losses = 0
                max_consec_wins = max(max_consec_wins, current_wins)
            else:
                current_losses += 1
                current_wins = 0
                max_consec_losses = max(max_consec_losses, current_losses)

        metrics.max_consecutive_wins = max_consec_wins
        metrics.max_consecutive_losses = max_consec_losses

        # Avg trade duration
        durations = [t.duration.total_seconds() for t in trades]
        metrics.avg_trade_duration = float(np.mean(durations)) if durations else 0

    # --- Advanced Metrics ---
    metrics.recovery_factor = metrics.total_return / (metrics.max_drawdown / equity_array[0]) if metrics.max_drawdown > 0 else 0
    metrics.profit_to_max_dd = metrics.total_return * equity_array[0] / metrics.max_drawdown if metrics.max_drawdown > 0 else 0

    # K-Ratio (requires linear regression on equity curve)
    if len(equity_curve) > 10:
        x = np.arange(len(equity_array))
        log_equity = np.log(equity_array / equity_array[0])
        slope, intercept = np.polyfit(x, log_equity, 1)
        residuals = log_equity - (slope * x + intercept)
        se = np.std(residuals) / np.sqrt(np.sum((x - np.mean(x)) ** 2))
        if se > 0:
            metrics.k_ratio = slope / se

    # R-squared
    if len(equity_curve) > 10:
        x = np.arange(len(equity_array))
        log_equity = np.log(equity_array / equity_array[0])
        slope, intercept = np.polyfit(x, log_equity, 1)
        predicted = slope * x + intercept
        ss_res = np.sum((log_equity - predicted) ** 2)
        ss_tot = np.sum((log_equity - np.mean(log_equity)) ** 2)
        if ss_tot > 0:
            metrics.r_squared = 1 - ss_res / ss_tot

    # --- Benchmark Comparison ---
    if benchmark_returns is not None and len(benchmark_returns) == len(returns):
        # Align returns
        min_len = min(len(returns), len(benchmark_returns))
        strat_ret = returns[:min_len]
        bench_ret = benchmark_returns[:min_len]

        # Beta
        cov = np.cov(strat_ret, bench_ret)[0, 1]
        bench_var = np.var(bench_ret)
        if bench_var > 0:
            metrics.beta = cov / bench_var

        # Alpha
        bench_annual = np.mean(bench_ret) * 252
        metrics.alpha = metrics.annual_return - risk_free_rate - metrics.beta * (bench_annual - risk_free_rate)

        # Correlation
        if np.std(strat_ret) > 0 and np.std(bench_ret) > 0:
            metrics.correlation = np.corrcoef(strat_ret, bench_ret)[0, 1]

        # Information Ratio
        active_ret = strat_ret - bench_ret
        if np.std(active_ret) > 0:
            metrics.information_ratio = np.mean(active_ret) / np.std(active_ret) * np.sqrt(252)

        # Treynor Ratio
        if metrics.beta != 0:
            metrics.treynor_ratio = (metrics.annual_return - risk_free_rate) / metrics.beta

    return metrics


def generate_tear_sheet(metrics: PerformanceMetrics, result: BacktestResult = None) -> str:
    """Generate a formatted tear sheet string."""
    lines = [
        "=" * 60,
        "PERFORMANCE TEAR SHEET",
        "=" * 60,
        "",
        "RETURNS",
        "-" * 20,
        f"  Total Return:           {metrics.total_return_pct:>8.2f}%",
        f"  Annual Return:          {metrics.annual_return * 100:>8.2f}%",
        f"  Monthly Avg Return:     {metrics.monthly_return_avg:>8.2f}%",
        f"  Monthly Std Return:     {metrics.monthly_return_std:>8.2f}%",
        "",
        "RISK-ADJUSTED RETURNS",
        "-" * 20,
        f"  Sharpe Ratio:           {metrics.sharpe_ratio:>8.2f}",
        f"  Sortino Ratio:          {metrics.sortino_ratio:>8.2f}",
        f"  Calmar Ratio:           {metrics.calmar_ratio:>8.2f}",
        f"  Sterling Ratio:         {metrics.sterling_ratio:>8.2f}",
        f"  Burke Ratio:            {metrics.burke_ratio:>8.2f}",
        f"  Omega Ratio:            {metrics.omega_ratio:>8.2f}",
        f"  Kappa Ratio:            {metrics.kappa_ratio:>8.2f}",
        "",
        "DRAWDOWN",
        "-" * 20,
        f"  Max Drawdown:           {metrics.max_drawdown_pct:>8.2f}%",
        f"  Current Drawdown:       {metrics.current_drawdown:>8.2f}%",
        f"  Avg Drawdown:           {metrics.avg_drawdown:>8.2f}%",
        f"  Max DD Duration:        {metrics.max_drawdown_duration:>8.0f} bars",
        f"  Avg DD Duration:        {metrics.avg_drawdown_duration:>8.1f} bars",
        f"  Ulcer Index:            {metrics.ulcer_index:>8.2f}",
        f"  Pain Index:             {metrics.pain_index:>8.2f}",
        "",
        "RISK",
        "-" * 20,
        f"  Annual Volatility:      {metrics.volatility_annual:>8.2f}%",
        f"  Downside Volatility:    {metrics.downside_volatility:>8.2f}%",
        f"  VaR (95%):              {metrics.var_95:>8.2f}%",
        f"  VaR (99%):              {metrics.var_99:>8.2f}%",
        f"  CVaR (95%):             {metrics.cvar_95:>8.2f}%",
        f"  CVaR (99%):             {metrics.cvar_99:>8.2f}%",
        f"  Skewness:               {metrics.skewness:>8.2f}",
        f"  Kurtosis:               {metrics.kurtosis:>8.2f}",
        f"  Tail Ratio:             {metrics.tail_ratio:>8.2f}",
        "",
        "TRADE STATISTICS",
        "-" * 20,
        f"  Total Trades:           {metrics.total_trades:>8d}",
        f"  Winning Trades:         {metrics.winning_trades:>8d}",
        f"  Losing Trades:          {metrics.losing_trades:>8d}",
        f"  Win Rate:               {metrics.win_rate * 100:>7.2f}%",
        f"  Profit Factor:          {metrics.profit_factor:>8.2f}",
        f"  Expectancy:             {metrics.expectancy:>8.2f}",
        f"  Avg Win:                {metrics.avg_win:>8.2f}",
        f"  Avg Loss:               {metrics.avg_loss:>8.2f}",
        f"  Largest Win:            {metrics.largest_win:>8.2f}",
        f"  Largest Loss:           {metrics.largest_loss:>8.2f}",
        f"  Max Consec Wins:        {metrics.max_consecutive_wins:>8d}",
        f"  Max Consec Losses:      {metrics.max_consecutive_losses:>8d}",
        f"  Payoff Ratio:           {metrics.payoff_ratio:>8.2f}",
        f"  Avg Trade Duration:     {metrics.avg_trade_duration / 3600:>7.1f} hrs",
        "",
        "ADVANCED",
        "-" * 20,
        f"  Recovery Factor:        {metrics.recovery_factor:>8.2f}",
        f"  Profit/MaxDD:           {metrics.profit_to_max_dd:>8.2f}",
        f"  K-Ratio:                {metrics.k_ratio:>8.2f}",
        f"  R-Squared:              {metrics.r_squared:>8.4f}",
        "",
    ]

    if metrics.alpha != 0 or metrics.beta != 0:
        lines.extend([
            "BENCHMARK COMPARISON",
            "-" * 20,
            f"  Alpha:                  {metrics.alpha * 100:>8.2f}%",
            f"  Beta:                   {metrics.beta:>8.2f}",
            f"  Correlation:            {metrics.correlation:>8.2f}",
            f"  Information Ratio:      {metrics.information_ratio:>8.2f}",
            f"  Treynor Ratio:          {metrics.treynor_ratio:>8.2f}",
            "",
        ])

    lines.append("=" * 60)

    return "\n".join(lines)


def compare_strategies(results: dict[str, BacktestResult]) -> pl.DataFrame:
    """Compare multiple strategy backtest results."""
    rows = []

    for name, result in results.items():
        metrics = calculate_advanced_metrics(
            result.equity_curve,
            result.trades,
        )

        rows.append({
            "Strategy": name,
            "Total Return %": f"{metrics.total_return_pct:.2f}",
            "Annual Return %": f"{metrics.annual_return * 100:.2f}",
            "Sharpe": f"{metrics.sharpe_ratio:.2f}",
            "Sortino": f"{metrics.sortino_ratio:.2f}",
            "Calmar": f"{metrics.calmar_ratio:.2f}",
            "Max DD %": f"{metrics.max_drawdown_pct:.2f}",
            "Win Rate %": f"{metrics.win_rate * 100:.1f}",
            "Profit Factor": f"{metrics.profit_factor:.2f}",
            "Total Trades": metrics.total_trades,
            "Avg Win": f"{metrics.avg_win:.2f}",
            "Avg Loss": f"{metrics.avg_loss:.2f}",
            "Expectancy": f"{metrics.expectancy:.2f}",
        })

    return pl.DataFrame(rows)