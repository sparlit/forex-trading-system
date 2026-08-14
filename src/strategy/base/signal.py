from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from src.data.models import Direction, SignalType, Timeframe


class SignalStrength(str, Enum):
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    VERY_STRONG = "very_strong"

    @classmethod
    def from_float(cls, value: float) -> SignalStrength:
        if value >= 0.8:
            return cls.VERY_STRONG
        elif value >= 0.6:
            return cls.STRONG
        elif value >= 0.4:
            return cls.MODERATE
        else:
            return cls.WEAK


@dataclass(slots=True)
class Signal:
    """Trading signal with full metadata."""
    signal_id: UUID = field(default_factory=uuid4)
    strategy_id: str = ""
    strategy_name: str = ""
    symbol: str = ""
    symbol_id: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    signal_type: SignalType = SignalType.ENTRY_LONG
    direction: Direction = Direction.FLAT
    strength: float = 0.0  # 0.0 to 1.0
    strength_category: SignalStrength = SignalStrength.WEAK
    entry_price: Decimal | None = None
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    position_size: Decimal | None = None
    risk_reward_ratio: float | None = None
    confidence: float = 0.0  # Model confidence 0.0 to 1.0
    timeframe: Timeframe = Timeframe.H1
    metadata: dict[str, Any] = field(default_factory=dict)
    expires_at: datetime | None = None
    is_executed: bool = False
    executed_at: datetime | None = None
    execution_price: Decimal | None = None
    execution_order_id: UUID | None = None

    def __post_init__(self):
        self.strength_category = SignalStrength.from_float(self.strength)

    @property
    def is_valid(self) -> bool:
        """Check if signal is valid for execution."""
        if self.direction == Direction.FLAT:
            return False
        if self.strength < 0.1:
            return False
        if self.confidence < 0.1:
            return False
        return not (self.expires_at and datetime.now(UTC) > self.expires_at)

    @property
    def risk_pips(self) -> Decimal | None:
        """Calculate risk in pips."""
        if self.entry_price and self.stop_loss:
            return abs(self.entry_price - self.stop_loss)
        return None

    @property
    def reward_pips(self) -> Decimal | None:
        """Calculate reward in pips."""
        if self.entry_price and self.take_profit:
            return abs(self.take_profit - self.entry_price)
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "signal_id": str(self.signal_id),
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "symbol": self.symbol,
            "symbol_id": self.symbol_id,
            "timestamp": self.timestamp.isoformat(),
            "signal_type": self.signal_type.value,
            "direction": self.direction.value,
            "strength": self.strength,
            "strength_category": self.strength_category.value,
            "entry_price": float(self.entry_price) if self.entry_price else None,
            "stop_loss": float(self.stop_loss) if self.stop_loss else None,
            "take_profit": float(self.take_profit) if self.take_profit else None,
            "position_size": float(self.position_size) if self.position_size else None,
            "risk_reward_ratio": self.risk_reward_ratio,
            "confidence": self.confidence,
            "timeframe": self.timeframe.value,
            "metadata": self.metadata,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "is_executed": self.is_executed,
            "executed_at": self.executed_at.isoformat() if self.executed_at else None,
            "execution_price": float(self.execution_price) if self.execution_price else None,
            "execution_order_id": str(self.execution_order_id) if self.execution_order_id else None,
        }

    @classmethod
    def create_entry(
        cls,
        strategy_id: str,
        strategy_name: str,
        symbol: str,
        direction: Direction,
        entry_price: Decimal,
        stop_loss: Decimal,
        take_profit: Decimal,
        strength: float = 0.5,
        confidence: float = 0.5,
        timeframe: Timeframe = Timeframe.H1,
        position_size: Decimal | None = None,
        metadata: dict[str, Any] | None = None,
        expires_seconds: int = 300,
    ) -> Signal:
        """Factory method to create entry signal."""
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        rr_ratio = float(reward / risk) if risk > 0 else None

        return cls(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            symbol=symbol,
            signal_type=SignalType.ENTRY_LONG,
            direction=direction,
            strength=strength,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            position_size=position_size,
            risk_reward_ratio=rr_ratio,
            timeframe=timeframe,
            metadata=metadata or {},
            expires_at=datetime.now(UTC).replace(second=0, microsecond=0) +
                       __import__('datetime').timedelta(seconds=expires_seconds),
        )

    @classmethod
    def create_exit(
        cls,
        strategy_id: str,
        strategy_name: str,
        symbol: str,
        direction: Direction,
        strength: float = 0.5,
        confidence: float = 0.5,
        timeframe: Timeframe = Timeframe.H1,
        metadata: dict[str, Any] | None = None,
    ) -> Signal:
        """Factory method to create exit signal."""
        return cls(
            strategy_id=strategy_id,
            strategy_name=strategy_name,
            symbol=symbol,
            signal_type=SignalType.EXIT_LONG,
            direction=direction,
            strength=strength,
            confidence=confidence,
            timeframe=timeframe,
            metadata=metadata or {},
        )