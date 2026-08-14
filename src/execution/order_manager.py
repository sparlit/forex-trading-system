import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID, uuid4

from loguru import logger

from src.data.models import (
    Direction,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
    PositionSide,
    SignalType,
)
from src.execution.position_manager import PositionManager
from src.strategy.base.strategy import StrategyRegistry


class BrokerType(str, Enum):
    MT5 = "mt5"
    CCXT = "ccxt"
    CTRADER = "ctrader"
    IBKR = "ibkr"
    SIMULATION = "simulation"


class ExecutionAlgorithm(str, Enum):
    MARKET = "market"
    TWAP = "twap"
    VWAP = "vwap"
    ICEBERG = "iceberg"
    ADAPTIVE = "adaptive"
    POV = "pov"  # Percentage of Volume
    IMPLEMENTATION_SHORTFALL = "implementation_shortfall"


class ExecutionConfig:
    """Configuration for order execution."""

    def __init__(
        self,
        algorithm: str = "ADAPTIVE",
        max_slippage_bps: int = 5,
        partial_fill_timeout: int = 30,
        max_order_age: int = 300,
        retry_attempts: int = 3,
        retry_delay: int = 1,
        use_smart_routing: bool = True,
        min_order_size: float = 0.01,
        max_order_size: float = 100.0,
        twap_duration_minutes: int = 30,
        vwap_participation_rate: float = 0.1,
        iceberg_display_size: float = 0.1,
        adaptive_urgency: str = "normal",
    ):
        self.algorithm = algorithm
        self.max_slippage_bps = max_slippage_bps
        self.partial_fill_timeout = partial_fill_timeout
        self.max_order_age = max_order_age
        self.retry_attempts = retry_attempts
        self.retry_delay = retry_delay
        self.use_smart_routing = use_smart_routing
        self.min_order_size = min_order_size
        self.max_order_size = max_order_size
        self.twap_duration_minutes = twap_duration_minutes
        self.vwap_participation_rate = vwap_participation_rate
        self.iceberg_display_size = iceberg_display_size
        self.adaptive_urgency = adaptive_urgency


class BrokerAdapter:
    """Abstract base class for broker adapters."""

    def __init__(self, broker_type: str):
        self.broker_type = broker_type
        self._connected = False
        self._account_info: dict = {}

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Connect to broker."""
        raise NotImplementedError("Subclass must implement connect()")

    async def disconnect(self) -> None:
        """Disconnect from broker."""
        raise NotImplementedError("Subclass must implement disconnect()")

    async def place_order(self, order: Order) -> Order:
        """Place order with broker."""
        # Pre‑trade validation – raise if the order violates any limit
        try:
            from src.risk.pre_trade import get_pre_trade_validator
            validator = get_pre_trade_validator()
            validator.validate(
                order,
                account_balance=Decimal(100000),
                account_free_margin=Decimal(100000),
            )
        except Exception as exc:
            logger.warning(f"Pre‑trade validation failed: {exc}")
            raise
        raise NotImplementedError("Subclass must implement place_order()")

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order."""
        raise NotImplementedError("Subclass must implement cancel_order()")

    async def modify_order(self, order_id: str, new_price: Decimal | None = None, new_volume: Decimal | None = None) -> bool:
        """Modify order."""
        raise NotImplementedError("Subclass must implement modify_order()")

    async def get_order_status(self, order_id: str) -> Order | None:
        """Get order status."""
        raise NotImplementedError("Subclass must implement get_order_status()")

    async def get_open_orders(self) -> list[Order]:
        """Get all open orders."""
        raise NotImplementedError("Subclass must implement get_open_orders()")

    async def get_positions(self) -> list[any]:
        """Get current positions."""
        raise NotImplementedError("Subclass must implement get_positions()")

    async def get_account_info(self) -> dict:
        """Get account info (balance, equity, margin)."""
        raise NotImplementedError("Subclass must implement get_account_info()")

    async def get_symbol_info(self, symbol: str) -> dict | None:
        """Get symbol specifications."""
        raise NotImplementedError("Subclass must implement get_symbol_info()")

    async def health_check(self) -> bool:
        """Check broker connection health."""
        raise NotImplementedError("Subclass must implement health_check()")


class OrderManager:
    """Manages order lifecycle."""

    def __init__(self):
        self._orders: dict[UUID, Order] = {}
        self._client_order_map: dict[str, UUID] = {}  # client_order_id -> order_id
        self._broker_order_map: dict[str, UUID] = {}  # broker_order_id -> order_id

    def create_order(
        self,
        strategy_id: str,
        signal_id: UUID,
        symbol: str,
        symbol_id: int,
        broker: str,
        order_type: OrderType,
        side: OrderSide,
        volume: Decimal,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> Order:
        """Create new order."""
        order = Order(
            client_order_id=client_order_id or f"{strategy_id}_{uuid4().hex[:8]}",
            strategy_id=strategy_id,
            signal_id=signal_id,
            symbol_id=symbol_id,
            symbol=symbol,
            broker=broker,
            order_type=order_type,
            side=side,
            volume=volume,
            price=price,
            stop_price=stop_price,
            status=OrderStatus.PENDING,
        )

        self._orders[order.order_id] = order
        self._client_order_map[order.client_order_id] = order.order_id

        return order

    def get_order(self, order_id: UUID) -> Order | None:
        return self._orders.get(order_id)

    def get_order_by_client_id(self, client_order_id: str) -> Order | None:
        order_id = self._client_order_map.get(client_order_id)
        if order_id:
            return self._orders.get(order_id)
        return None

    def get_order_by_broker_id(self, broker_order_id: str) -> Order | None:
        order_id = self._broker_order_map.get(broker_order_id)
        if order_id:
            return self._orders.get(order_id)
        return None

    def update_order(self, order: Order) -> None:
        """Update order in manager."""
        self._orders[order.order_id] = order
        if order.broker_order_id:
            self._broker_order_map[order.broker_order_id] = order.order_id

    def get_strategy_orders(self, strategy_id: str) -> list[Order]:
        return [o for o in self._orders.values() if o.strategy_id == strategy_id]

    def get_symbol_orders(self, symbol: str) -> list[Order]:
        return [o for o in self._orders.values() if o.symbol == symbol]

    def get_active_orders(self) -> list[Order]:
        return [o for o in self._orders.values() if o.is_active]

    def remove_order(self, order_id: UUID) -> bool:
        if order_id in self._orders:
            order = self._orders[order_id]
            self._client_order_map.pop(order.client_order_id, None)
            if order.broker_order_id:
                self._broker_order_map.pop(order.broker_order_id, None)
            del self._orders[order_id]
            return True
        return False


class SmartOrderRouter:
    """Routes orders to best broker/exchange."""

    def __init__(self, brokers: dict[str, BrokerAdapter]):
        self.brokers = brokers

    async def route_order(self, order: Order) -> str:
        """Determine best broker for order."""
        # For now, just return the order's broker
        return order.broker

    async def split_order(self, order: Order, num_slices: int | None = None) -> list[Order]:
        """Split large order into smaller slices."""
        if not num_slices:
            return [order]
        slice_volume = order.volume / num_slices
        slices = []
        for i in range(num_slices):
            slice_order = Order(
                client_order_id=f"{order.client_order_id}_slice_{i}",
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
            slices.append(slice_order)
        return slices


class ExecutionEngine:
    """Main execution engine coordinating order routing and management."""

    def __init__(self, config: ExecutionConfig = None):
        self.config = config or ExecutionConfig()
        self.brokers: dict[str, BrokerAdapter] = {}
        self.order_manager = OrderManager()
        self.position_manager = PositionManager()
        self.router = SmartOrderRouter(self.brokers)
        self._running = False
        self._strategy_registry = StrategyRegistry()

    def register_broker(self, broker: BrokerAdapter) -> None:
        """Register a broker adapter."""
        self.brokers[broker.broker_type] = broker
        self.router = SmartOrderRouter(self.brokers)

    async def connect_all(self) -> None:
        """Connect to all registered brokers."""
        for broker in self.brokers.values():
            try:
                await broker.connect()
            except Exception as e:
                logger.error(f"Failed to connect to {broker.broker_type}: {e}")

    async def disconnect_all(self) -> None:
        """Disconnect from all brokers."""
        for broker in self.brokers.values():
            try:
                await broker.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting from {broker.broker_type}: {e}")

    async def execute_signal(self, signal) -> list[Order]:
        """Execute a trading signal."""
        orders = []

        # Get strategy from registry
        strategy = self._strategy_registry.get(strategy_id=signal.strategy_id)
        if not strategy:
            logger.warning(f"Strategy not found: {signal.strategy_id}")
            return orders

        # Create order from signal
        order = self.order_manager.create_order(
            strategy_id=signal.strategy_id,
            signal_id=signal.signal_id,
            symbol=signal.symbol,
            symbol_id=0,  # Would look up from symbol
            broker=strategy.broker or "mt5",
            order_type=OrderType.MARKET if signal.order_type == "market" else OrderType.LIMIT,
            side=OrderSide.BUY if signal.direction == Direction.LONG else OrderSide.SELL,
            volume=signal.position_size or Decimal("0.01"),
            price=signal.entry_price,
            stop_price=signal.stop_loss,
        )

        # Store order
        created_order = self.order_manager.create_order(
            strategy_id=order.strategy_id,
            signal_id=order.signal_id,
            symbol=order.symbol,
            symbol_id=order.symbol_id,
            broker=order.broker,
            order_type=order.order_type,
            side=order.side,
            volume=order.volume,
            price=order.price,
            stop_price=order.stop_price,
            client_order_id=order.client_order_id,
        )
        orders.append(created_order)

        # For paper trading, update position immediately
        if strategy.is_paper:
            side = (
                PositionSide.LONG
                if created_order.side == OrderSide.BUY
                else PositionSide.SHORT
            )
            volume = created_order.volume
            price = (
                created_order.price
                if created_order.price
                else signal.entry_price
                or Decimal(0)
            )  # Fallback to signal entry price or zero

            if signal.signal_type == SignalType.ENTRY_LONG:
                # Open position
                self.position_manager.open_position(
                    strategy_id=strategy.strategy_id,
                    symbol=signal.symbol,
                    side=side,
                    volume=volume,
                    entry_price=price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                )
            elif signal.signal_type == SignalType.EXIT_LONG:
                # Close position
                self.position_manager.close_position_by_symbol_strategy(
                    strategy_id=strategy.strategy_id,
                    symbol=signal.symbol,
                    price=price,
                    commission=Decimal(0),
                )

        # In a live system, we would send the order to the broker via the router
        # For now, we just return the created order
        return orders

    async def monitor_orders(self) -> None:
        """Monitor active orders for fills, timeouts."""
        self._running = True
        while self._running:
            try:
                active_orders = self.order_manager.get_active_orders()
                for order in active_orders:
                    broker = self.brokers.get(order.broker)
                    if broker:
                        # Check order status
                        updated = await broker.get_order_status(order.broker_order_id or "")
                        if updated:
                            self.order_manager.update_order(updated)

                            # Check for timeout
                            if order.submitted_at:
                                age = (
                                    datetime.now(UTC) - order.submitted_at
                                ).total_seconds()
                                if age > self.config.max_order_age:
                                    await self.cancel_order(order.order_id)

            except Exception as e:
                logger.error(f"Order monitoring error: {e}")
                await asyncio.sleep(5)

            await asyncio.sleep(1)

    async def cancel_order(self, order_id: UUID) -> bool:
        """Cancel an order."""
        order = self.order_manager.get_order(order_id)
        if not order or not order.is_active:
            return False

        broker = self.brokers.get(order.broker)
        if broker:
            success = await broker.cancel_order(order.broker_order_id or "")
            if success:
                order.status = OrderStatus.CANCELLED
                order.cancelled_at = datetime.now(UTC)
                self.order_manager.update_order(order)
            return success
        return False

    def stop_monitoring(self) -> None:
        self._running = False

    def get_positions(
        self, strategy_id: str | None = None, symbol: str | None = None, open_only: bool = True
    ) -> list[dict]:
        """Get positions as dictionaries for API."""
        positions = self.position_manager.get_positions(
            strategy_id=strategy_id, symbol=symbol, open_only=open_only
        )
        return [
            {
                "position_id": str(p.position_id),
                "strategy_id": p.strategy_id,
                "symbol": p.symbol,
                "side": p.side.value,
                "volume": float(p.volume),
                "entry_price": float(p.entry_price),
                "current_price": float(p.current_price),
                "unrealized_pnl": float(p.unrealized_pnl),
                "realized_pnl": float(p.realized_pnl),
                "stop_loss": float(p.stop_loss) if p.stop_loss else None,
                "take_profit": float(p.take_profit) if p.take_profit else None,
                "opened_at": p.opened_at.isoformat(),
                "updated_at": p.updated_at.isoformat(),
                "is_open": p.is_open,
            }
            for p in positions
        ]


# Global execution engine instance
execution_engine = ExecutionEngine()