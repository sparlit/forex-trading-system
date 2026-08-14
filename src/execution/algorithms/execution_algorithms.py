from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from loguru import logger

from src.execution.order_manager import (
    ExecutionAlgorithm,
    ExecutionConfig,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)


@dataclass
class AlgorithmState:
    """State for execution algorithm."""
    order_id: UUID
    symbol: str
    side: OrderSide
    total_volume: Decimal
    filled_volume: Decimal = Decimal(0)
    slices: list[dict] = field(default_factory=list)
    start_time: datetime = field(default_factory=lambda: datetime.now(UTC))
    end_time: datetime | None = None
    is_complete: bool = False
    metadata: dict = field(default_factory=dict)


class BaseAlgorithm(ABC):
    """Base class for execution algorithms."""

    def __init__(self, config: ExecutionConfig):
        self.config = config
        self._states: dict[UUID, AlgorithmState] = {}
        self._callbacks: list[Callable[[Order], Awaitable[None]]] = []

    def register_callback(self, callback: Callable[[Order], Awaitable[None]]) -> None:
        """Register callback for slice orders."""
        self._callbacks.append(callback)

    async def _emit_slice(self, slice_order: Order) -> None:
        """Emit slice order to callbacks."""
        for callback in self._callbacks:
            try:
                await callback(slice_order)
            except Exception:
                logger.exception("Algorithm callback error")

    @abstractmethod
    async def start(self, order: Order) -> AlgorithmState:
        """Start algorithm for an order."""

    @abstractmethod
    async def on_fill(self, state: AlgorithmState, fill_volume: Decimal, fill_price: Decimal) -> None:
        """Handle fill notification."""

    @abstractmethod
    async def on_slice_fill(self, state: AlgorithmState, slice_order: Order) -> None:
        """Handle slice fill."""

    async def cancel(self, order_id: UUID) -> bool:
        """Cancel algorithm."""
        if order_id in self._states:
            state = self._states[order_id]
            state.is_complete = True
            return True
        return False


class TWAPAlgorithm(BaseAlgorithm):
    """Time-Weighted Average Price execution algorithm."""

    async def start(self, order: Order) -> AlgorithmState:
        """Start TWAP execution."""
        duration = timedelta(minutes=self.config.twap_duration_minutes)
        end_time = datetime.now(UTC) + duration

        # Calculate number of slices
        num_slices = max(1, int(duration.total_seconds() / 60))  # 1 slice per minute
        slice_volume = order.volume / num_slices

        state = AlgorithmState(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            total_volume=order.volume,
            end_time=end_time,
            metadata={
                "num_slices": num_slices,
                "slice_volume": float(slice_volume),
                "interval_seconds": 60,
            }
        )

        self._states[order.order_id] = state

        # Schedule slices
        asyncio.create_task(self._run_twap(state, order, num_slices, slice_volume))

        return state

    async def _run_twap(self, state: AlgorithmState, order: Order, num_slices: int, slice_volume: Decimal) -> None:
        """Run TWAP slicing."""
        interval = state.metadata["interval_seconds"]

        for i in range(num_slices):
            if state.is_complete:
                break

            # Check if we should continue
            remaining = state.total_volume - state.filled_volume
            if remaining <= Decimal("0.001"):
                break

            # Adjust final slice volume
            current_slice = min(slice_volume, remaining)

            slice_order = Order(
                client_order_id=f"{order.client_order_id}_twap_{i}",
                strategy_id=order.strategy_id,
                signal_id=order.signal_id,
                symbol_id=order.symbol_id,
                symbol=order.symbol,
                broker=order.broker,
                order_type=OrderType.MARKET,
                side=order.side,
                volume=current_slice,
                price=order.price,
                stop_price=order.stop_price,
                status=OrderStatus.PENDING,
            )

            state.slices.append({
                "slice_id": i,
                "order_id": slice_order.order_id,
                "volume": float(current_slice),
                "scheduled_time": (datetime.now(UTC) + timedelta(seconds=i * interval)).isoformat(),
            })

            await self._emit_slice(slice_order)

            # Wait for interval (except last slice)
            if i < num_slices - 1:
                await asyncio.sleep(interval)

        state.is_complete = True

    async def on_fill(self, state: AlgorithmState, fill_volume: Decimal, fill_price: Decimal) -> None:
        state.filled_volume += fill_volume
        if state.filled_volume >= state.total_volume:
            state.is_complete = True

    async def on_slice_fill(self, state: AlgorithmState, slice_order: Order) -> None:
        # Update filled volume from slice
        state.filled_volume += slice_order.volume
        # Submit next slice if not complete
        if not state.is_complete and state.filled_volume < state.total_volume:
            await self._submit_next_slice(state, slice_order.symbol)


class VWAPAlgorithm(BaseAlgorithm):
    """Volume-Weighted Average Price execution algorithm."""

    async def start(self, order: Order) -> AlgorithmState:
        """Start VWAP execution."""
        # VWAP uses historical volume profile to schedule orders
        # For now, use simple time-based with volume participation rate
        duration = timedelta(minutes=self.config.twap_duration_minutes)
        end_time = datetime.now(UTC) + duration

        state = AlgorithmState(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            total_volume=order.volume,
            end_time=end_time,
            metadata={
                "participation_rate": self.config.vwap_participation_rate,
                "profile": {},  # Would load historical volume profile
            }
        )

        self._states[order.order_id] = state

        # Run VWAP
        asyncio.create_task(self._run_vwap(state, order))

        return state

    async def _run_vwap(self, state: AlgorithmState, order: Order) -> None:
        """Run VWAP execution based on volume profile."""
        participation_rate = state.metadata["participation_rate"]

        # Simplified: use 1-minute intervals, adjust size by recent volume
        interval = 60
        max_slices = int((state.end_time - datetime.now(UTC)).total_seconds() / interval)

        for i in range(max_slices):
            if state.is_complete:
                break

            remaining = state.total_volume - state.filled_volume
            if remaining <= Decimal("0.001"):
                break

            # In production, would get real-time volume and adjust
            # For now, use fixed participation
            slice_volume = remaining * Decimal(str(participation_rate))
            slice_volume = max(slice_volume, Decimal(str(self.config.min_order_size)))
            slice_volume = min(slice_volume, remaining)

            slice_order = Order(
                client_order_id=f"{order.client_order_id}_vwap_{i}",
                strategy_id=order.strategy_id,
                signal_id=order.signal_id,
                symbol_id=order.symbol_id,
                symbol=order.symbol,
                broker=order.broker,
                order_type=OrderType.MARKET,
                side=order.side,
                volume=slice_volume,
                price=order.price,
                stop_price=order.stop_price,
                status=OrderStatus.PENDING,
            )

            state.slices.append({
                "slice_id": i,
                "order_id": slice_order.order_id,
                "volume": float(slice_volume),
            })

            await self._emit_slice(slice_order)

            await asyncio.sleep(interval)

        state.is_complete = True

    async def on_fill(self, state: AlgorithmState, fill_volume: Decimal, fill_price: Decimal) -> None:
        state.filled_volume += fill_volume
        if state.filled_volume >= state.total_volume:
            state.is_complete = True

    async def on_slice_fill(self, state: AlgorithmState, slice_order: Order) -> None:
        # Update filled volume from slice
        state.filled_volume += slice_order.volume
        # Submit next slice if not complete
        if not state.is_complete and state.filled_volume < state.total_volume:
            await self._submit_next_slice(state, slice_order.symbol)


class IcebergAlgorithm(BaseAlgorithm):
    """Iceberg order execution algorithm - shows only small portion."""

    async def start(self, order: Order) -> AlgorithmState:
        """Start Iceberg execution."""
        display_size = order.volume * Decimal(str(self.config.iceberg_display_size))
        display_size = max(display_size, Decimal(str(self.config.min_order_size)))

        state = AlgorithmState(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            total_volume=order.volume,
            metadata={
                "display_size": float(display_size),
                "remaining_hidden": float(order.volume - display_size),
            }
        )

        self._states[order.order_id] = state

        # Submit first visible slice
        await self._submit_next_slice(state, order, display_size)

        return state

    async def _submit_next_slice(self, state: AlgorithmState, order: Order, display_size: Decimal) -> None:
        """Submit next visible slice."""
        remaining = state.total_volume - state.filled_volume
        if remaining <= Decimal("0.001"):
            state.is_complete = True
            return

        slice_volume = min(display_size, remaining)

        slice_order = Order(
            client_order_id=f"{order.client_order_id}_iceberg_{len(state.slices)}",
            strategy_id=order.strategy_id,
            signal_id=order.signal_id,
            symbol_id=order.symbol_id,
            symbol=order.symbol,
            broker=order.broker,
            order_type=order.order_type,
            side=order.side,
            volume=slice_volume,
            price=order.price,
            stop_price=order.stop_price,
            status=OrderStatus.PENDING,
        )

        state.slices.append({
            "slice_id": len(state.slices),
            "order_id": slice_order.order_id,
            "volume": float(slice_volume),
        })

        await self._emit_slice(slice_order)

    async def on_fill(self, state: AlgorithmState, fill_volume: Decimal, fill_price: Decimal) -> None:
        state.filled_volume += fill_volume

        # Submit next slice if current one filled
        remaining = state.total_volume - state.filled_volume
        display_size = Decimal(str(state.metadata["display_size"]))

        if remaining > Decimal("0.001"):
            await self._submit_next_slice(state, None, display_size)
        else:
            state.is_complete = True

    async def on_slice_fill(self, state: AlgorithmState, slice_order: Order) -> None:
        # Iceberg submits next slice when current fills
        if not state.is_complete:
            remaining = state.total_volume - state.filled_volume
            if remaining > Decimal('0.001'):
                display_size = Decimal(str(state.metadata['display_size']))
                await self._submit_next_slice(state, slice_order.symbol, display_size)


class AdaptiveAlgorithm(BaseAlgorithm):
    """Adaptive execution algorithm - adjusts based on market conditions."""

    def __init__(self, config: ExecutionConfig):
        super().__init__(config)
        self._urgency_profiles = {
            "low": {"participation": 0.05, "max_slippage": 2, "interval": 120},
            "normal": {"participation": 0.1, "max_slippage": 5, "interval": 60},
            "high": {"participation": 0.2, "max_slippage": 10, "interval": 30},
        }

    async def start(self, order: Order) -> AlgorithmState:
        """Start adaptive execution."""
        urgency = self.config.adaptive_urgency
        profile = self._urgency_profiles.get(urgency, self._urgency_profiles["normal"])

        duration = timedelta(minutes=self.config.twap_duration_minutes)
        end_time = datetime.now(UTC) + duration

        state = AlgorithmState(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            total_volume=order.volume,
            end_time=end_time,
            metadata={
                "urgency": urgency,
                "profile": profile,
                "current_spread": 0.0,
                "current_volatility": 0.0,
            }
        )

        self._states[order.order_id] = state

        asyncio.create_task(self._run_adaptive(state, order, profile))

        return state

    async def _run_adaptive(self, state: AlgorithmState, order: Order, profile: dict) -> None:
        """Run adaptive execution with dynamic adjustments."""
        interval = profile["interval"]
        participation = profile["participation"]

        while not state.is_complete:
            remaining = state.total_volume - state.filled_volume
            if remaining <= Decimal("0.001"):
                break

            # Check time remaining
            time_left = (state.end_time - datetime.now(UTC)).total_seconds()
            if time_left <= 0:
                # Aggressive completion
                participation = min(participation * 2, 0.5)

            # Adjust for market conditions (would get real data)
            # If spread widening, reduce participation
            # If volatility high, reduce participation

            slice_volume = remaining * Decimal(str(participation))
            slice_volume = max(slice_volume, Decimal(str(self.config.min_order_size)))
            slice_volume = min(slice_volume, remaining)

            slice_order = Order(
                client_order_id=f"{order.client_order_id}_adaptive_{len(state.slices)}",
                strategy_id=order.strategy_id,
                signal_id=order.signal_id,
                symbol_id=order.symbol_id,
                symbol=order.symbol,
                broker=order.broker,
                order_type=OrderType.MARKET,
                side=order.side,
                volume=slice_volume,
                price=order.price,
                stop_price=order.stop_price,
                status=OrderStatus.PENDING,
            )

            state.slices.append({
                "slice_id": len(state.slices),
                "order_id": slice_order.order_id,
                "volume": float(slice_volume),
                "participation": participation,
            })

            await self._emit_slice(slice_order)

            await asyncio.sleep(interval)

        state.is_complete = True

    async def on_fill(self, state: AlgorithmState, fill_volume: Decimal, fill_price: Decimal) -> None:
        state.filled_volume += fill_volume
        if state.filled_volume >= state.total_volume:
            state.is_complete = True

    async def on_slice_fill(self, state: AlgorithmState, slice_order: Order) -> None:
        # Update filled volume from slice
        state.filled_volume += slice_order.volume
        # Submit next slice if not complete
        if not state.is_complete and state.filled_volume < state.total_volume:
            await self._submit_next_slice(state, slice_order.symbol)


class POVAlgorithm(BaseAlgorithm):
    """Percentage of Volume algorithm."""

    async def start(self, order: Order) -> AlgorithmState:
        """Start POV execution."""
        duration = timedelta(minutes=self.config.twap_duration_minutes)
        end_time = datetime.now(UTC) + duration

        state = AlgorithmState(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            total_volume=order.volume,
            end_time=end_time,
            metadata={
                "target_pov": self.config.vwap_participation_rate,
            }
        )

        self._states[order.order_id] = state

        asyncio.create_task(self._run_pov(state, order))

        return state

    async def _run_pov(self, state: AlgorithmState, order: Order) -> None:
        """Run POV - would need real-time market volume."""
        # Simplified implementation
        interval = 30
        target_pov = state.metadata["target_pov"]

        while not state.is_complete:
            remaining = state.total_volume - state.filled_volume
            if remaining <= Decimal("0.001"):
                break

            time_left = (state.end_time - datetime.now(UTC)).total_seconds()
            if time_left <= 0:
                break

            # In production, get real market volume for last interval
            # For now, use fixed size
            slice_volume = remaining * Decimal(str(target_pov))
            slice_volume = max(slice_volume, Decimal(str(self.config.min_order_size)))
            slice_volume = min(slice_volume, remaining)

            slice_order = Order(
                client_order_id=f"{order.client_order_id}_pov_{len(state.slices)}",
                strategy_id=order.strategy_id,
                signal_id=order.signal_id,
                symbol_id=order.symbol_id,
                symbol=order.symbol,
                broker=order.broker,
                order_type=OrderType.MARKET,
                side=order.side,
                volume=slice_volume,
                price=order.price,
                stop_price=order.stop_price,
                status=OrderStatus.PENDING,
            )

            state.slices.append({
                "slice_id": len(state.slices),
                "order_id": slice_order.order_id,
                "volume": float(slice_volume),
            })

            await self._emit_slice(slice_order)

            await asyncio.sleep(interval)

        state.is_complete = True

    async def on_fill(self, state: AlgorithmState, fill_volume: Decimal, fill_price: Decimal) -> None:
        state.filled_volume += fill_volume
        if state.filled_volume >= state.total_volume:
            state.is_complete = True

    async def on_slice_fill(self, state: AlgorithmState, slice_order: Order) -> None:
        # Update filled volume from slice
        state.filled_volume += slice_order.volume
        # Submit next slice if not complete
        if not state.is_complete and state.filled_volume < state.total_volume:
            await self._submit_next_slice(state, slice_order.symbol)


class ImplementationShortfallAlgorithm(BaseAlgorithm):
    """Implementation Shortfall (Arrival Price) algorithm."""

    async def start(self, order: Order) -> AlgorithmState:
        """Start IS execution."""
        # Implementation Shortfall tries to minimize (execution price - arrival price)
        arrival_price = order.price or Decimal(0)

        state = AlgorithmState(
            order_id=order.order_id,
            symbol=order.symbol,
            side=order.side,
            total_volume=order.volume,
            metadata={
                "arrival_price": float(arrival_price),
                "risk_aversion": 0.5,  # Would be calibrated
            }
        )

        self._states[order.order_id] = state

        asyncio.create_task(self._run_is(state, order))

        return state

    async def _run_is(self, state: AlgorithmState, order: Order) -> None:
        """Run Implementation Shortfall - simplified."""
        # This is a complex algorithm requiring:
        # - Volatility forecast
        # - Market impact model
        # - Temporary vs permanent impact
        # - Risk aversion parameter
        # For now, use adaptive with arrival price tracking
        await AdaptiveAlgorithm(self.config)._run_adaptive(state, order)

    async def on_fill(self, state: AlgorithmState, fill_volume: Decimal, fill_price: Decimal) -> None:
        state.filled_volume += fill_volume
        # Track implementation shortfall
        arrival = Decimal(str(state.metadata.get("arrival_price", 0)))
        if arrival > 0:
            shortfall = (fill_price - arrival) / arrival if state.side == OrderSide.BUY else (arrival - fill_price) / arrival
            state.metadata["implementation_shortfall"] = float(shortfall)

        if state.filled_volume >= state.total_volume:
            state.is_complete = True

    async def on_slice_fill(self, state: AlgorithmState, slice_order: Order) -> None:
        # Update filled volume from slice
        state.filled_volume += slice_order.volume
        # Submit next slice if not complete
        if not state.is_complete and state.filled_volume < state.total_volume:
            await self._submit_next_slice(state, slice_order.symbol)


# Algorithm factory
ALGORITHM_REGISTRY = {
    ExecutionAlgorithm.TWAP: TWAPAlgorithm,
    ExecutionAlgorithm.VWAP: VWAPAlgorithm,
    ExecutionAlgorithm.ICEBERG: IcebergAlgorithm,
    ExecutionAlgorithm.ADAPTIVE: AdaptiveAlgorithm,
    ExecutionAlgorithm.POV: POVAlgorithm,
    ExecutionAlgorithm.IMPLEMENTATION_SHORTFALL: ImplementationShortfallAlgorithm,
}


def create_algorithm(algorithm: ExecutionAlgorithm, config: ExecutionConfig) -> BaseAlgorithm:
    """Create algorithm instance."""
    algo_class = ALGORITHM_REGISTRY.get(algorithm)
    if not algo_class:
        raise ValueError(f"Unknown algorithm: {algorithm}")
    return algo_class(config)