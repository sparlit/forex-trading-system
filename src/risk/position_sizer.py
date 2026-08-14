from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

import numpy as np
from loguru import logger

from src.data.models import Direction, Position, Symbol

if TYPE_CHECKING:
    from src.strategy.base.signal import Signal


class PositionSizingMethod(str, Enum):
    FIXED = "fixed"
    PERCENT_EQUITY = "percent_equity"
    KELLY = "kelly"
    VOLATILITY_TARGET = "volatility_target"
    RISK_PARITY = "risk_parity"
    ATR_BASED = "atr_based"
    MAX_DRAWDOWN = "max_drawdown"


@dataclass
class PositionSizingConfig:
    method: PositionSizingMethod = PositionSizingMethod.VOLATILITY_TARGET
    risk_per_trade: float = 0.02  # 2% risk per trade
    max_position_pct: float = 0.10  # Max 10% of equity per position
    max_sector_exposure: float = 0.30  # Max 30% per sector
    max_total_exposure: float = 1.0  # Max 100% total exposure
    kelly_fraction: float = 0.5  # Half-Kelly
    target_volatility: float = 0.15  # 15% annual target volatility
    atr_multiplier: float = 2.0  # ATR multiplier for stop
    min_position_size: float = 0.01
    max_position_size: float = 100.0
    max_leverage: float = 10.0


@dataclass
class PositionSizeResult:
    size: Decimal
    risk_amount: Decimal
    stop_loss: Decimal
    take_profit: Decimal | None = None
    risk_reward_ratio: float | None = None
    method_used: PositionSizingMethod = PositionSizingMethod.FIXED
    metadata: dict = field(default_factory=dict)


class PositionSizer:
    """Advanced position sizing with multiple methods."""

    def __init__(self, config: PositionSizingConfig = None):
        self.config = config or PositionSizingConfig()

    def calculate_position_size(
        self,
        signal: Signal,
        symbol: Symbol,
        equity: Decimal,
        current_positions: dict[str, Position],
        account_balance: Decimal,
        free_margin: Decimal,
        symbol_multiplier: dict[str, Decimal] | None = None,
    ) -> PositionSizeResult:
        """Calculate optimal position size based on configured method.
        Applies a first‑trade override (0.01 lots) and optional pyramiding multiplier.
        """

        # Determine base size using the selected method
        if self.config.method == PositionSizingMethod.FIXED:
            result = self._fixed_size(signal, symbol, equity)
        elif self.config.method == PositionSizingMethod.PERCENT_EQUITY:
            result = self._percent_equity(signal, symbol, equity)
        elif self.config.method == PositionSizingMethod.KELLY:
            result = self._kelly_criterion(signal, symbol, equity)
        elif self.config.method == PositionSizingMethod.VOLATILITY_TARGET:
            result = self._volatility_target(signal, symbol, equity)
        elif self.config.method == PositionSizingMethod.RISK_PARITY:
            result = self._risk_parity(signal, symbol, equity, current_positions)
        elif self.config.method == PositionSizingMethod.ATR_BASED:
            result = self._atr_based(signal, symbol, equity)
        elif self.config.method == PositionSizingMethod.MAX_DRAWDOWN:
            result = self._max_drawdown_control(signal, symbol, equity, current_positions)
        else:
            result = self._fixed_size(signal, symbol, equity)

        # First‑trade enforcement: if this symbol has not been traded yet in this session,
        # enforce the minimum lot size (0.01).
        if not hasattr(self, "_first_trade_done"):
            self._first_trade_done = set()
        if symbol.symbol not in self._first_trade_done:
            result.size = Decimal(str(self.config.min_position_size))
            self._first_trade_done.add(symbol.symbol)

        # Pyramiding: if all existing positions for this symbol are profitable,
        # automatically increase size by a multiplier (default 2×) unless overridden.
        profitable = True
        for pos in current_positions.values():
            if pos.symbol == symbol.symbol and getattr(pos, "unrealized_pnl", Decimal(0)) < 0:
                profitable = False
                break
        if profitable:
            mult = Decimal('2.0')
            if symbol_multiplier and symbol.symbol in symbol_multiplier:
                mult = Decimal(symbol_multiplier[symbol.symbol])
            size = result.size * mult
            size = min(size, Decimal(str(self.config.max_position_size)))
            size = max(size, Decimal(str(self.config.min_position_size)))
            size = symbol.normalize_volume(size)
            result.size = size

        return result

    def _fixed_size(self, signal: Signal, symbol: Symbol, equity: Decimal) -> PositionSizeResult:
        """Fixed position size."""
        size = Decimal(str(self.config.min_position_size))
        max_pos_size = Decimal(str(self.config.max_position_size))
        size = min(size, max_pos_size)
        size = min(size, symbol.max_volume)
        min_pos_size = Decimal(str(self.config.min_position_size))
        size = max(size, min_pos_size)
        size = symbol.normalize_volume(size)

        risk_amount = equity * Decimal(str(self.config.risk_per_trade))

        return PositionSizeResult(
            size=size,
            risk_amount=risk_amount,
            stop_loss=signal.stop_loss or Decimal(0),
            take_profit=signal.take_profit,
            method_used=PositionSizingMethod.FIXED,
        )

    def _percent_equity(self, signal: Signal, symbol: Symbol, equity: Decimal) -> PositionSizeResult:
        """Position size as percentage of equity."""
        max_size_value = equity * Decimal(str(self.config.max_position_pct))

        # Calculate size based on stop loss distance
        if signal.entry_price and signal.stop_loss:
            risk_per_unit = abs(signal.entry_price - signal.stop_loss)
            if risk_per_unit > 0:
                size = max_size_value / risk_per_unit
            else:
                size = Decimal(str(self.config.min_position_size))
        else:
            size = Decimal(str(self.config.min_position_size))

        # Apply constraints
        size = min(size, self.config.max_position_size)
        size = min(size, symbol.max_volume)
        size = max(size, symbol.min_volume)
        size = symbol.normalize_volume(size)

        risk_amount = equity * Decimal(str(self.config.risk_per_trade))

        return PositionSizeResult(
            size=size,
            risk_amount=risk_amount,
            stop_loss=signal.stop_loss or Decimal(0),
            take_profit=signal.take_profit,
            method_used=PositionSizingMethod.PERCENT_EQUITY,
        )

    def _kelly_criterion(self, signal: Signal, symbol: Symbol, equity: Decimal) -> PositionSizeResult:
        """Kelly criterion position sizing."""
        # Estimate win rate and win/loss ratio from signal metadata
        metadata = signal.metadata
        win_rate = metadata.get("win_rate", 0.55)
        avg_win = metadata.get("avg_win", 1.5)
        avg_loss = metadata.get("avg_loss", 1.0)

        if avg_loss > 0:
            kelly_f = (win_rate * avg_win - (1 - win_rate) * avg_loss) / avg_win
            kelly_f = max(0, kelly_f)  # No negative Kelly
            kelly_f *= self.config.kelly_fraction  # Half-Kelly
        else:
            kelly_f = self.config.risk_per_trade

        # Cap Kelly fraction
        kelly_f = min(kelly_f, self.config.max_position_pct)

        size_value = equity * Decimal(str(kelly_f))

        # Convert to position size
        if signal.entry_price and signal.stop_loss:
            risk_per_unit = abs(signal.entry_price - signal.stop_loss)
            if risk_per_unit > 0:
                size = size_value / risk_per_unit
            else:
                size = Decimal(str(self.config.min_position_size))
        else:
            size = Decimal(str(self.config.min_position_size))

        size = min(size, self.config.max_position_size)
        size = min(size, symbol.max_volume)
        size = max(size, symbol.min_volume)
        size = symbol.normalize_volume(size)

        risk_amount = equity * Decimal(str(kelly_f))

        return PositionSizeResult(
            size=size,
            risk_amount=risk_amount,
            stop_loss=signal.stop_loss or Decimal(0),
            take_profit=signal.take_profit,
            method_used=PositionSizingMethod.KELLY,
            metadata={"kelly_fraction": kelly_f, "win_rate": win_rate},
        )

    def _volatility_target(self, signal: Signal, symbol: Symbol, equity: Decimal) -> PositionSizeResult:
        """Volatility targeting position sizing."""
        # Get volatility estimate from signal metadata or use default
        metadata = signal.metadata
        volatility = metadata.get("volatility", 0.15)  # Annual volatility
        atr = metadata.get("atr", float(signal.entry_price) * 0.001 if signal.entry_price else 0.001)

        # Target daily volatility
        daily_target_vol = Decimal(str(self.config.target_volatility / np.sqrt(252)))
        current_daily_vol = Decimal(str(volatility / np.sqrt(252)))

        if current_daily_vol > 0:
            vol_scalar = daily_target_vol / current_daily_vol
        else:
            vol_scalar = Decimal("1.0")

        # Base risk
        base_risk = equity * Decimal(str(self.config.risk_per_trade))
        adjusted_risk = base_risk * vol_scalar

        # Calculate size from ATR
        if signal.entry_price and atr > 0:
            risk_per_unit = Decimal(str(atr * self.config.atr_multiplier))
            size = adjusted_risk / risk_per_unit
        else:
            size = Decimal(str(self.config.min_position_size))

        # Apply constraints
        max_pos_size = Decimal(str(self.config.max_position_size))
        min_pos_size = Decimal(str(self.config.min_position_size))
        size = min(size, max_pos_size)
        size = min(size, symbol.max_volume)
        size = max(size, min_pos_size)
        size = symbol.normalize_volume(size)

        # Recalculate actual stop loss based on ATR
        if signal.entry_price:
            atr_decimal = Decimal(str(atr))
            if signal.direction.value == "long":
                stop_loss = signal.entry_price - atr_decimal * Decimal(str(self.config.atr_multiplier))
            else:
                stop_loss = signal.entry_price + atr_decimal * Decimal(str(self.config.atr_multiplier))
        else:
            stop_loss = signal.stop_loss or Decimal(0)

        return PositionSizeResult(
            size=size,
            risk_amount=adjusted_risk,
            stop_loss=stop_loss,
            take_profit=signal.take_profit,
            method_used=PositionSizingMethod.VOLATILITY_TARGET,
            metadata={"vol_scalar": float(vol_scalar), "atr": atr},
        )

    def _risk_parity(
        self,
        signal: Signal,
        symbol: Symbol,
        equity: Decimal,
        current_positions: dict[str, Position],
    ) -> PositionSizeResult:
        """Risk parity position sizing - equal risk contribution."""
        # Calculate current portfolio risk
        total_risk = Decimal(0)
        position_risks = {}

        for pos in current_positions.values():
            if pos.stop_loss and pos.entry_price:
                risk = abs(pos.entry_price - pos.stop_loss) * pos.volume
                position_risks[pos.symbol] = risk
                total_risk += risk

        # Target risk per position
        len(current_positions) + 1
        target_risk_per_position = equity * Decimal(str(self.config.risk_per_trade))

        # If we have existing positions, adjust for risk parity
        if position_risks:
            avg_risk = total_risk / len(position_risks)
            # Scale new position to match average risk
            risk_amount = avg_risk
        else:
            risk_amount = target_risk_per_position

        # Calculate size
        if signal.entry_price and signal.stop_loss:
            risk_per_unit = abs(signal.entry_price - signal.stop_loss)
            if risk_per_unit > 0:
                size = risk_amount / risk_per_unit
            else:
                size = Decimal(str(self.config.min_position_size))
        else:
            size = Decimal(str(self.config.min_position_size))

        size = min(size, self.config.max_position_size)
        size = min(size, symbol.max_volume)
        size = max(size, symbol.min_volume)
        size = symbol.normalize_volume(size)

        return PositionSizeResult(
            size=size,
            risk_amount=risk_amount,
            stop_loss=signal.stop_loss or Decimal(0),
            take_profit=signal.take_profit,
            method_used=PositionSizingMethod.RISK_PARITY,
            metadata={"target_risk_per_position": float(target_risk_per_position)},
        )

    def _atr_based(self, signal: Signal, symbol: Symbol, equity: Decimal) -> PositionSizeResult:
        """ATR-based position sizing."""
        atr = signal.metadata.get("atr", float(signal.entry_price) * 0.001 if signal.entry_price else 0.001)

        if signal.entry_price and atr > 0:
            # Stop loss at ATR multiple
            atr_decimal = Decimal(str(atr * self.config.atr_multiplier))

            if signal.direction == Direction.LONG:
                stop_loss = signal.entry_price - atr_decimal
            else:
                stop_loss = signal.entry_price + atr_decimal

            risk_per_unit = atr_decimal
            risk_amount = equity * Decimal(str(self.config.risk_per_trade))
            size = risk_amount / risk_per_unit if risk_per_unit > 0 else Decimal(str(self.config.min_position_size))

            # Take profit at 2:1 reward:risk
            if signal.direction == Direction.LONG:
                take_profit = signal.entry_price + atr_decimal * Decimal(2)
            else:
                take_profit = signal.entry_price - atr_decimal * Decimal(2)
        else:
            stop_loss = signal.stop_loss or Decimal(0)
            take_profit = signal.take_profit
            size = Decimal(str(self.config.min_position_size))
            risk_amount = equity * Decimal(str(self.config.risk_per_trade))

        size = min(size, self.config.max_position_size)
        size = min(size, symbol.max_volume)
        size = max(size, symbol.min_volume)
        size = symbol.normalize_volume(size)

        return PositionSizeResult(
            size=size,
            risk_amount=risk_amount,
            stop_loss=stop_loss,
            take_profit=take_profit,
            risk_reward_ratio=2.0,
            method_used=PositionSizingMethod.ATR_BASED,
            metadata={"atr": atr, "atr_multiplier": self.config.atr_multiplier},
        )

    def _max_drawdown_control(
        self,
        signal: Signal,
        symbol: Symbol,
        equity: Decimal,
        current_positions: dict[str, Position],
    ) -> PositionSizeResult:
        """Position sizing with max drawdown control."""
        # Calculate current drawdown
        peak_equity = equity  # In practice, track peak equity
        current_drawdown = (peak_equity - equity) / peak_equity if peak_equity > 0 else Decimal(0)

        # Reduce position size as drawdown increases
        dd_factor = Decimal("1.0") - Decimal(str(current_drawdown)) / Decimal(str(self.config.max_position_pct))
        dd_factor = max(Decimal("0.1"), min(Decimal("1.0"), dd_factor))  # Floor at 10%

        base_result = self._percent_equity(signal, symbol, equity)
        base_result.size = symbol.normalize_volume(base_result.size * dd_factor)
        base_result.risk_amount = base_result.risk_amount * dd_factor
        base_result.method_used = PositionSizingMethod.MAX_DRAWDOWN
        base_result.metadata["drawdown_factor"] = float(dd_factor)
        base_result.metadata["current_drawdown"] = float(current_drawdown)

        return base_result

    def validate_position(
        self,
        result: PositionSizeResult,
        signal: Signal,
        symbol: Symbol,
        equity: Decimal,
        current_positions: dict[str, Position],
    ) -> tuple[bool, str | None]:
        """Validate position size against risk limits."""

        # Check minimum size
        if result.size < symbol.min_volume:
            return False, f"Position size {result.size} below minimum {symbol.min_volume}"

        # Check maximum size
        if result.size > symbol.max_volume:
            return False, f"Position size {result.size} above maximum {symbol.max_volume}"

        # Check max position value
        if signal.entry_price:
            position_value = result.size * signal.entry_price
            max_value = equity * Decimal(str(self.config.max_position_pct))
            if position_value > max_value:
                return False, f"Position value {position_value} exceeds max {max_value}"

        # Check total exposure
        total_exposure = Decimal(0)
        for pos in current_positions.values():
            if pos.current_price > 0:
                total_exposure += pos.volume * pos.current_price

        if signal.entry_price:
            new_exposure = total_exposure + (result.size * signal.entry_price)
            max_exposure = equity * Decimal(str(self.config.max_total_exposure))
            if new_exposure > max_exposure:
                return False, f"Total exposure {new_exposure} would exceed max {max_exposure}"

        # Check sector exposure
        # Sector exposure check skipped due to lack of sector data in Symbol model
        if not hasattr(self, '_sector_warning_logged'):
            logger.warning("Sector exposure check skipped: sector data not available")
            self._sector_warning_logged = True

        # Check leverage
        if signal.entry_price:
            margin_required = (result.size * signal.entry_price) / Decimal(str(symbol.margin_rate))
            if margin_required > equity * Decimal(str(self.config.max_leverage)):
                return False, f"Margin required {margin_required} exceeds max leverage"

        return True, None


# Global position sizer
position_sizer = PositionSizer()