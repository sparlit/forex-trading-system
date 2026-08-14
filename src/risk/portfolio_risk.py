from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import numpy as np

from src.data.models import Position, Symbol


@dataclass
class RiskLimits:
    """Portfolio risk limits."""
    max_portfolio_risk: float = 0.02  # 2% per trade
    max_drawdown: float = 0.10  # 10% max drawdown
    max_correlation: float = 0.7  # Max position correlation
    max_leverage: float = 10.0
    var_confidence: float = 0.99
    var_horizon_days: int = 1
    max_position_size_pct: float = 0.10
    max_sector_exposure: float = 0.30
    stop_out_level: float = 0.50
    margin_call_level: float = 0.80
    daily_loss_limit: float = 0.05
    weekly_loss_limit: float = 0.10
    monthly_loss_limit: float = 0.20


@dataclass
class PortfolioRiskMetrics:
    """Current portfolio risk metrics."""
    total_equity: Decimal
    total_margin_used: Decimal
    free_margin: Decimal
    margin_level: float
    total_unrealized_pnl: Decimal
    total_realized_pnl: Decimal
    daily_pnl: Decimal
    weekly_pnl: Decimal
    monthly_pnl: Decimal
    current_drawdown: float
    max_drawdown: float
    portfolio_var_95: Decimal
    portfolio_var_99: Decimal
    portfolio_es_95: Decimal
    portfolio_es_99: Decimal
    max_correlation: float
    sector_exposures: dict[str, float]
    leverage: float
    open_positions: int
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


class PortfolioRiskManager:
    """Portfolio-level risk management."""

    def __init__(self, limits: RiskLimits = None):
        self.limits = limits or RiskLimits()
        self._equity_curve: list[tuple[datetime, Decimal]] = []
        self._daily_pnl_history: list[tuple[datetime, Decimal]] = []
        self._position_history: list[Position] = []
        self._correlation_matrix: np.ndarray | None = None
        self._symbol_list: list[str] = []

    def update_equity(self, equity: Decimal, timestamp: datetime | None = None) -> None:
        """Update equity curve."""
        timestamp = timestamp or datetime.now(UTC)
        self._equity_curve.append((timestamp, equity))

        # Keep last 2 years
        cutoff = timestamp - timedelta(days=730)
        self._equity_curve = [(t, e) for t, e in self._equity_curve if t > cutoff]

    def update_daily_pnl(self, pnl: Decimal, date: datetime | None = None) -> None:
        """Update daily P&L history."""
        date = date or datetime.now(UTC).date()
        self._daily_pnl_history.append((datetime.combine(date, datetime.min.time().replace(tzinfo=UTC)), pnl))

        # Keep last 2 years
        cutoff = datetime.now(UTC) - timedelta(days=730)
        self._daily_pnl_history = [(t, p) for t, p in self._daily_pnl_history if t > cutoff]

    def calculate_drawdown(self, equity: Decimal) -> tuple[float, float]:
        """Calculate current and max drawdown."""
        if not self._equity_curve:
            return 0.0, 0.0

        peak = max(e for _, e in self._equity_curve)
        current_dd = float((peak - equity) / peak) if peak > 0 else 0.0

        # Max drawdown from peak
        max_dd = 0.0
        running_peak = Decimal(0)
        for _, e in self._equity_curve:
            running_peak = max(running_peak, e)
            dd = float((running_peak - e) / running_peak) if running_peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        return current_dd, max_dd

    def calculate_var(
        self,
        positions: dict[str, Position],
        symbols: dict[str, Symbol],
        confidence: float = 0.99,
        horizon_days: int = 1,
    ) -> tuple[Decimal, Decimal]:
        """Calculate Value at Risk and Expected Shortfall."""
        if not positions:
            return Decimal(0), Decimal(0)

        # Get returns for each position - fetch from historical data
        returns_data = {}
        for symbol in positions:
            if symbol in symbols:
                # In practice, fetch historical returns from data service
                # For now, use zero returns as placeholder - real implementation would query DB
                returns_data[symbol] = np.zeros(252)

        if not returns_data:
            return Decimal(0), Decimal(0)

        # Portfolio returns (equal weighted for simplicity)
        symbols_list = list(returns_data.keys())
        n = len(symbols_list)
        weights = np.ones(n) / n

        # Calculate portfolio returns
        portfolio_returns = np.zeros(252)
        for i, sym in enumerate(symbols_list):
            portfolio_returns += weights[i] * returns_data[sym]

        # VaR
        var_percentile = np.percentile(portfolio_returns, (1 - confidence) * 100)
        var = Decimal(str(abs(var_percentile) * float(sum(p.volume * p.current_price for p in positions.values()))))

        # Expected Shortfall (CVaR)
        es_returns = portfolio_returns[portfolio_returns <= var_percentile]
        es = Decimal(str(abs(np.mean(es_returns)) * float(sum(p.volume * p.current_price for p in positions.values()))))

        return var, es

    def calculate_correlation_matrix(self, positions: dict[str, Position]) -> np.ndarray:
        """Calculate correlation matrix of positions."""
        symbols = list(positions.keys())
        n = len(symbols)

        if n < 2:
            return np.eye(1)

        # In practice, use historical returns
        # For now, return identity with some correlation
        corr = np.eye(n)
        for i in range(n):
            for j in range(i + 1, n):
                # Estimate correlation based on asset class
                corr[i, j] = corr[j, i] = 0.3  # Placeholder

        self._correlation_matrix = corr
        self._symbol_list = symbols
        return corr

    def check_correlation_limit(self, positions: dict[str, Position]) -> tuple[bool, str | None]:
        """Check if any positions exceed correlation limit."""
        if len(positions) < 2:
            return True, None

        corr = self.calculate_correlation_matrix(positions)
        symbols = self._symbol_list

        for i in range(len(symbols)):
            for j in range(i + 1, len(symbols)):
                if corr[i, j] > self.limits.max_correlation:
                    return False, f"Correlation between {symbols[i]} and {symbols[j]} is {corr[i, j]:.2f}, exceeds limit {self.limits.max_correlation}"

        return True, None

    def check_sector_exposure(
        self,
        positions: dict[str, Position],
        symbols: dict[str, Symbol],
    ) -> tuple[bool, dict[str, float]]:
        """Check sector exposure limits."""
        sector_exposure = defaultdict(Decimal)
        total_exposure = Decimal(0)

        for pos in positions.values():
            if pos.symbol in symbols:
                sym = symbols[pos.symbol]
                sector = sym.sector or sym.asset_class.value
                exposure = pos.volume * pos.current_price
                sector_exposure[sector] += exposure
                total_exposure += exposure

        sector_pct = {}
        for sector, exposure in sector_exposure.items():
            pct = float(exposure / total_exposure) if total_exposure > 0 else 0.0
            sector_pct[sector] = pct
            if pct > self.limits.max_sector_exposure:
                return False, sector_pct

        return True, sector_pct

    def check_leverage(self, equity: Decimal, margin_used: Decimal) -> tuple[bool, float]:
        """Check leverage limits."""
        leverage = float(margin_used / equity) if equity > 0 else 0.0
        return leverage <= self.limits.max_leverage, leverage

    def check_margin_level(self, equity: Decimal, margin_used: Decimal) -> tuple[bool, float, str]:
        """Check margin level and return status."""
        margin_level = float(equity / margin_used * 100) if margin_used > 0 else float("inf")

        if margin_level <= self.limits.stop_out_level * 100:
            return False, margin_level, "STOP_OUT"
        elif margin_level <= self.limits.margin_call_level * 100:
            return True, margin_level, "MARGIN_CALL"
        else:
            return True, margin_level, "OK"

    def check_loss_limits(self) -> tuple[bool, dict[str, float]]:
        """Check daily/weekly/monthly loss limits."""
        now = datetime.now(UTC)
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        daily_loss = sum(
            float(pnl) for dt, pnl in self._daily_pnl_history
            if dt.date() == today and pnl < 0
        )
        weekly_loss = sum(
            float(pnl) for dt, pnl in self._daily_pnl_history
            if dt.date() >= week_start and pnl < 0
        )
        monthly_loss = sum(
            float(pnl) for dt, pnl in self._daily_pnl_history
            if dt.date() >= month_start and pnl < 0
        )

        limits = {
            "daily": abs(daily_loss),
            "weekly": abs(weekly_loss),
            "monthly": abs(monthly_loss),
        }

        if daily_loss > self.limits.daily_loss_limit:
            return False, limits
        if weekly_loss > self.limits.weekly_loss_limit:
            return False, limits
        if monthly_loss > self.limits.monthly_loss_limit:
            return False, limits

        return True, limits

    def get_risk_metrics(
        self,
        equity: Decimal,
        balance: Decimal,
        positions: dict[str, Position],
        symbols: dict[str, Symbol],
        margin_used: Decimal,
    ) -> PortfolioRiskMetrics:
        """Get comprehensive risk metrics."""
        current_dd, max_dd = self.calculate_drawdown(equity)
        var_99, es_99 = self.calculate_var(positions, symbols, 0.99, self.limits.var_horizon_days)
        var_95, es_95 = self.calculate_var(positions, symbols, 0.95, self.limits.var_horizon_days)

        # Daily/weekly/monthly P&L
        now = datetime.now(UTC)
        today = now.date()
        week_start = today - timedelta(days=today.weekday())
        month_start = today.replace(day=1)

        daily_pnl = sum(pnl for dt, pnl in self._daily_pnl_history if dt.date() == today)
        weekly_pnl = sum(pnl for dt, pnl in self._daily_pnl_history if dt.date() >= week_start)
        monthly_pnl = sum(pnl for dt, pnl in self._daily_pnl_history if dt.date() >= month_start)

        total_unrealized = sum(p.unrealized_pnl for p in positions.values())
        total_realized = sum(p.realized_pnl for p in positions.values())

        # Sector exposures
        sector_exposure = defaultdict(Decimal)
        total_exposure = Decimal(0)
        for pos in positions.values():
            if pos.symbol in symbols:
                sym = symbols[pos.symbol]
                sector = sym.sector or sym.asset_class.value
                exposure = pos.volume * pos.current_price
                sector_exposure[sector] += exposure
                total_exposure += exposure

        sector_pct = {
            sector: float(exp / total_exposure) if total_exposure > 0 else 0.0
            for sector, exp in sector_exposure.items()
        }

        free_margin = equity - margin_used
        margin_level = float(equity / margin_used * 100) if margin_used > 0 else float("inf")
        leverage = float(margin_used / equity) if equity > 0 else 0.0

        return PortfolioRiskMetrics(
            total_equity=equity,
            total_margin_used=margin_used,
            free_margin=free_margin,
            margin_level=margin_level,
            total_unrealized_pnl=total_unrealized,
            total_realized_pnl=total_realized,
            daily_pnl=daily_pnl,
            weekly_pnl=weekly_pnl,
            monthly_pnl=monthly_pnl,
            current_drawdown=current_dd,
            max_drawdown=max_dd,
            portfolio_var_95=var_95,
            portfolio_var_99=var_99,
            portfolio_es_95=es_95,
            portfolio_es_99=es_99,
            max_correlation=np.max(self._correlation_matrix) if self._correlation_matrix is not None else 0.0,
            sector_exposures=sector_pct,
            leverage=leverage,
            open_positions=len(positions),
        )

    def validate_new_position(
        self,
        signal,
        symbol: Symbol,
        position_size: Decimal,
        equity: Decimal,
        positions: dict[str, Position],
        symbols: dict[str, Symbol],
        margin_used: Decimal,
    ) -> tuple[bool, list[str]]:
        """Validate if new position passes all risk checks."""
        errors = []

        # Create hypothetical position
        hypothetical_positions = dict(positions)
        hypothetical_positions[signal.symbol] = Position(
            symbol=signal.symbol,
            volume=position_size,
            entry_price=signal.entry_price or Decimal(0),
            current_price=signal.entry_price or Decimal(0),
            direction=signal.direction,
        )

        # Check correlation
        corr_ok, corr_msg = self.check_correlation_limit(hypothetical_positions)
        if not corr_ok:
            errors.append(corr_msg)

        # Check sector exposure
        sector_ok, sector_pct = self.check_sector_exposure(hypothetical_positions, symbols)
        if not sector_ok:
            for sector, pct in sector_pct.items():
                if pct > self.limits.max_sector_exposure:
                    errors.append(f"Sector {sector} exposure {pct:.1%} exceeds limit {self.limits.max_sector_exposure:.1%}")

        # Check leverage
        new_margin = margin_used + (position_size * (signal.entry_price or Decimal(0)) / Decimal(str(symbol.margin_rate)))
        lev_ok, leverage = self.check_leverage(equity, new_margin)
        if not lev_ok:
            errors.append(f"Leverage {leverage:.1f}x exceeds limit {self.limits.max_leverage:.1f}x")

        # Check margin level
        margin_ok, margin_level, status = self.check_margin_level(equity, new_margin)
        if not margin_ok:
            errors.append(f"Margin level {margin_level:.1f}% would trigger {status}")

        # Check loss limits
        loss_ok, loss_limits = self.check_loss_limits()
        if not loss_ok:
            errors.append(f"Loss limits exceeded: {loss_limits}")

        return len(errors) == 0, errors


# Global risk manager
portfolio_risk_manager = PortfolioRiskManager()