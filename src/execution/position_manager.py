from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4


class PositionSide(str, Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


@dataclass
class Position:
    position_id: UUID = field(default_factory=uuid4)
    strategy_id: str = ""
    symbol: str = ""
    side: PositionSide = PositionSide.FLAT
    volume: Decimal = Decimal(0)
    entry_price: Decimal = Decimal(0)
    current_price: Decimal = Decimal(0)
    unrealized_pnl: Decimal = Decimal(0)
    realized_pnl: Decimal = Decimal(0)
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    opened_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    is_open: bool = True

    def update_price(self, price: Decimal) -> None:
        """Update current price and unrealized P&L."""
        self.current_price = price
        if self.side == PositionSide.LONG:
            self.unrealized_pnl = (price - self.entry_price) * self.volume
        elif self.side == PositionSide.SHORT:
            self.unrealized_pnl = (self.entry_price - price) * self.volume
        self.updated_at = datetime.now(UTC)

    def close(self, price: Decimal, commission: Decimal = Decimal(0)) -> None:
        """Close the position and realize P&L."""
        self.update_price(price)
        if self.side == PositionSide.LONG:
            self.realized_pnl = (price - self.entry_price) * self.volume - commission
        elif self.side == PositionSide.SHORT:
            self.realized_pnl = (self.entry_price - price) * self.volume - commission
        self.unrealized_pnl = Decimal(0)
        self.current_price = price
        self.side = PositionSide.FLAT
        self.is_open = False
        self.updated_at = datetime.now(UTC)


class PositionManager:
    """Manages open and closed positions."""

    def __init__(self):
        self._positions: dict[UUID, Position] = {}
        self._symbol_strategy_map: dict[str, dict[str, UUID]] = {}  # symbol -> strategy_id -> position_id

    def get_position(self, position_id: UUID) -> Position | None:
        return self._positions.get(position_id)

    def get_positions(self, strategy_id: str | None = None, symbol: str | None = None, open_only: bool = True) -> list[Position]:
        positions = list(self._positions.values())
        if strategy_id:
            positions = [p for p in positions if p.strategy_id == strategy_id]
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        if open_only:
            positions = [p for p in positions if p.is_open]
        return positions

    def open_position(
        self,
        strategy_id: str,
        symbol: str,
        side: PositionSide,
        volume: Decimal,
        entry_price: Decimal,
        stop_loss: Decimal | None = None,
        take_profit: Decimal | None = None,
    ) -> Position:
        """Open a new position."""
        position = Position(
            strategy_id=strategy_id,
            symbol=symbol,
            side=side,
            volume=volume,
            entry_price=entry_price,
            current_price=entry_price,  # Initial price is entry price
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        self._positions[position.position_id] = position

        # Update index
        if symbol not in self._symbol_strategy_map:
            self._symbol_strategy_map[symbol] = {}
        self._symbol_strategy_map[symbol][strategy_id] = position.position_id

        return position

    def close_position(self, position_id: UUID, price: Decimal, commission: Decimal = Decimal(0)) -> Position | None:
        """Close a position by ID."""
        position = self._positions.get(position_id)
        if position and position.is_open:
            position.close(price, commission)
            return position
        return None

    def close_position_by_symbol_strategy(self, symbol: str, strategy_id: str, price: Decimal, commission: Decimal = Decimal(0)) -> Position | None:
        """Close the open position for a given symbol and strategy."""
        if symbol in self._symbol_strategy_map and strategy_id in self._symbol_strategy_map[symbol]:
            position_id = self._symbol_strategy_map[symbol][strategy_id]
            return self.close_position(position_id, price, commission)
        return None

    def update_position_price(self, symbol: str, strategy_id: str, price: Decimal) -> None:
        """Update the current price for a position."""
        if symbol in self._symbol_strategy_map and strategy_id in self._symbol_strategy_map[symbol]:
            position_id = self._symbol_strategy_map[symbol][strategy_id]
            position = self._positions.get(position_id)
            if position and position.is_open:
                position.update_price(price)

    def get_open_position(self, strategy_id: str, symbol: str) -> Position | None:
        """Get open position for a strategy and symbol."""
        for position in self._positions.values():
            if (position.strategy_id == strategy_id and
                position.symbol == symbol and
                position.is_open):
                return position
        return None