from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import MetaTrader5 as mt5
from loguru import logger

from src.data.models import Direction, Position
from src.execution.order_manager import (
    BrokerAdapter,
    BrokerType,
    Order,
    OrderSide,
    OrderStatus,
    OrderType,
)
from src.infra.config.settings import settings

MT5_ORDER_TYPE_MAP = {
    (OrderType.MARKET, OrderSide.BUY): mt5.ORDER_TYPE_BUY,
    (OrderType.MARKET, OrderSide.SELL): mt5.ORDER_TYPE_SELL,
    (OrderType.LIMIT, OrderSide.BUY): mt5.ORDER_TYPE_BUY_LIMIT,
    (OrderType.LIMIT, OrderSide.SELL): mt5.ORDER_TYPE_SELL_LIMIT,
    (OrderType.STOP, OrderSide.BUY): mt5.ORDER_TYPE_BUY_STOP,
    (OrderType.STOP, OrderSide.SELL): mt5.ORDER_TYPE_SELL_STOP,
    (OrderType.STOP_LIMIT, OrderSide.BUY): mt5.ORDER_TYPE_BUY_STOP_LIMIT,
    (OrderType.STOP_LIMIT, OrderSide.SELL): mt5.ORDER_TYPE_SELL_STOP_LIMIT,
}

MT5_ORDER_STATUS_MAP = {
    mt5.ORDER_STATE_STARTED: OrderStatus.PENDING,
    mt5.ORDER_STATE_PLACED: OrderStatus.SUBMITTED,
    mt5.ORDER_STATE_PARTIAL: OrderStatus.PARTIAL,
    mt5.ORDER_STATE_FILLED: OrderStatus.FILLED,
    mt5.ORDER_STATE_CANCELED: OrderStatus.CANCELLED,
    mt5.ORDER_STATE_REJECTED: OrderStatus.REJECTED,
    mt5.ORDER_STATE_EXPIRED: OrderStatus.EXPIRED,
}

class MT5BrokerAdapter(BrokerAdapter):
    """MetaTrader 5 broker adapter for order execution."""

    # Maps are defined as module-level constants (MT5_*)

    def __init__(self):
        super().__init__(BrokerType.MT5)
        self._login = settings.mt5_login
        self._password = settings.mt5_password
        self._server = settings.mt5_server
        self._path = settings.mt5_path
        self._timeout = settings.mt5_timeout
        self._portable = settings.mt5_portable

    async def connect(self) -> None:
        """Initialize MT5 connection."""
        loop = asyncio.get_event_loop()
        initialized = await loop.run_in_executor(
            None,
            lambda: mt5.initialize(
                login=self._login,
                password=self._password,
                server=self._server,
                path=self._path,
                timeout=self._timeout,
                portable=self._portable,
            )
        )

        if not initialized:
            error = mt5.last_error()
            raise ConnectionError(f"MT5 initialization failed: {error}")

        # Wait for connection
        for _ in range(30):
            terminal_info = await loop.run_in_executor(None, mt5.terminal_info)
            if terminal_info and terminal_info.connected:
                break
            await asyncio.sleep(1)
        else:
            raise ConnectionError("MT5 terminal not connected after 30 seconds")

        self._connected = True
        self._account_info = await self.get_account_info()
        logger.info(f"MT5 broker connected: {self._login} @ {self._server}")

    async def disconnect(self) -> None:
        """Shutdown MT5 connection."""
        await asyncio.get_event_loop().run_in_executor(None, mt5.shutdown)
        self._connected = False
        logger.info("MT5 broker disconnected")

    async def place_order(self, order: Order) -> Order:
        """Place order with MT5."""
        loop = asyncio.get_event_loop()

        # Prepare order request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": float(order.volume),
            "type": MT5_ORDER_TYPE_MAP.get((order.order_type, order.side), mt5.ORDER_TYPE_BUY),
            "price": float(order.price) if order.price else 0.0,
            "sl": float(order.stop_price) if order.stop_price else 0.0,
            "tp": 0.0,  # Will be set via modify if needed
            "deviation": 10,
            "magic": 123456,
            "comment": order.client_order_id[:31],
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        # Send order
        result = await loop.run_in_executor(None, mt5.order_send, request)

        if result is None:
            error = mt5.last_error()
            order.status = OrderStatus.REJECTED
            order.comment = f"MT5 Error: {error}"
            return order

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            order.status = OrderStatus.REJECTED
            order.comment = f"MT5 Retcode: {result.retcode}, {result.comment}"
            return order

        # Update order with broker info
        order.broker_order_id = str(result.order)
        order.status = OrderStatus.FILLED
        order.filled_volume = Decimal(str(result.volume))
        order.avg_fill_price = Decimal(str(result.price))
        order.submitted_at = datetime.now(UTC)
        order.filled_at = datetime.now(UTC)
        order.commission = Decimal(str(result.commission)) if hasattr(result, 'commission') else Decimal(0)

        logger.info(f"MT5 order filled: {order.client_order_id} -> {order.broker_order_id}, volume={order.filled_volume}, price={order.avg_fill_price}")

        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order in MT5."""
        loop = asyncio.get_event_loop()

        request = {
            "action": mt5.TRADE_ACTION_REMOVE,
            "order": int(order_id),
        }

        result = await loop.run_in_executor(None, mt5.order_send, request)

        if result is None:
            return False

        return result.retcode == mt5.TRADE_RETCODE_DONE

    async def modify_order(self, order_id: str, new_price: Decimal | None = None, new_volume: Decimal | None = None, new_sl: Decimal | None = None, new_tp: Decimal | None = None) -> bool:
        """Modify order in MT5."""
        loop = asyncio.get_event_loop()

        # Get current order
        orders = await loop.run_in_executor(None, lambda: mt5.orders_get(ticket=int(order_id)))
        if not orders:
            return False

        order = orders[0]

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "order": int(order_id),
            "symbol": order.symbol,
            "price": float(new_price) if new_price else order.price_open,
            "sl": float(new_sl) if new_sl else order.sl,
            "tp": float(new_tp) if new_tp else order.tp,
        }

        result = await loop.run_in_executor(None, mt5.order_send, request)

        if result is None:
            return False

        return result.retcode == mt5.TRADE_RETCODE_DONE

    async def get_order_status(self, order_id: str) -> Order | None:
        """Get order status from MT5."""
        loop = asyncio.get_event_loop()

        # Check orders
        orders = await loop.run_in_executor(None, lambda: mt5.orders_get(ticket=int(order_id)))
        if orders:
            order = orders[0]
            return self._convert_mt5_order(order)

        # Check history (filled orders)
        from_date = datetime.now(UTC).replace(day=1)
        deals = await loop.run_in_executor(
            None,
            lambda: mt5.history_deals_get(from_date, datetime.now(UTC))
        )

        if deals:
            for deal in deals:
                if deal.order == int(order_id):
                    # Convert deal to order status
                    return Order(
                        order_id=UUID(int=deal.order),
                        broker_order_id=str(deal.order),
                        status=OrderStatus.FILLED,
                        filled_volume=Decimal(str(deal.volume)),
                        avg_fill_price=Decimal(str(deal.price)),
                        filled_at=datetime.fromtimestamp(deal.time, tz=UTC),
                    )

        return None

    async def get_open_orders(self) -> list[Order]:
        """Get all open orders from MT5."""
        loop = asyncio.get_event_loop()
        orders = await loop.run_in_executor(None, mt5.orders_get)

        if not orders:
            return []

        result = []
        for order in orders:
            result.append(self._convert_mt5_order(order))

        return result

    async def get_positions(self) -> list[Position]:
        """Get current positions from MT5."""
        loop = asyncio.get_event_loop()
        positions = await loop.run_in_executor(None, mt5.positions_get)

        if not positions:
            return []

        result = []
        for pos in positions:
            result.append(self._convert_mt5_position(pos))

        return result

    async def get_account_info(self) -> dict[str, Any]:
        """Get account info from MT5."""
        loop = asyncio.get_event_loop()
        account = await loop.run_in_executor(None, mt5.account_info)

        if not account:
            return {}

        return {
            "login": account.login,
            "balance": Decimal(str(account.balance)),
            "equity": Decimal(str(account.equity)),
            "margin": Decimal(str(account.margin)),
            "free_margin": Decimal(str(account.margin_free)),
            "margin_level": Decimal(str(account.margin_level)) if account.margin_level > 0 else Decimal(0),
            "currency": account.currency,
            "leverage": account.leverage,
            "profit": Decimal(str(account.profit)),
        }

    async def get_symbol_info(self, symbol: str) -> dict[str, Any] | None:
        """Get symbol info from MT5."""
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(None, mt5.symbol_info, symbol)

        if not info:
            return None

        return {
            "symbol": info.name,
            "bid": Decimal(str(info.bid)),
            "ask": Decimal(str(info.ask)),
            "spread": info.spread,
            "digits": info.digits,
            "contract_size": Decimal(str(info.trade_contract_size)),
            "tick_size": Decimal(str(info.trade_tick_size)),
            "tick_value": Decimal(str(info.trade_tick_value)),
            "volume_min": Decimal(str(info.volume_min)),
            "volume_max": Decimal(str(info.volume_max)),
            "volume_step": Decimal(str(info.volume_step)),
            "swap_long": Decimal(str(info.swap_long)),
            "swap_short": Decimal(str(info.swap_short)),
            "margin_initial": Decimal(str(info.margin_initial)),
            "currency_base": info.currency_base,
            "currency_profit": info.currency_profit,
            "currency_margin": info.currency_margin,
        }

    async def health_check(self) -> bool:
        """Check MT5 connection health."""
        try:
            loop = asyncio.get_event_loop()
            terminal_info = await loop.run_in_executor(None, mt5.terminal_info)
            return terminal_info is not None and terminal_info.connected
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return False

    def _convert_mt5_order(self, mt5_order) -> Order:
        """Convert MT5 order to our Order model."""
        # Map side
        if mt5_order.type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_BUY_STOP_LIMIT]:
            side = OrderSide.BUY
        else:
            side = OrderSide.SELL

        # Map order type
        if mt5_order.type in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL]:
            order_type = OrderType.MARKET
        elif mt5_order.type in [mt5.ORDER_TYPE_BUY_LIMIT, mt5.ORDER_TYPE_SELL_LIMIT]:
            order_type = OrderType.LIMIT
        elif mt5_order.type in [mt5.ORDER_TYPE_BUY_STOP, mt5.ORDER_TYPE_SELL_STOP]:
            order_type = OrderType.STOP
        else:
            order_type = OrderType.STOP_LIMIT

        status = MT5_ORDER_STATUS_MAP.get(mt5_order.state, OrderStatus.PENDING)

        return Order(
            order_id=UUID(int=mt5_order.ticket),
            broker_order_id=str(mt5_order.ticket),
            symbol=mt5_order.symbol,
            symbol_id=0,  # Would need mapping
            broker=BrokerType.MT5,
            order_type=order_type,
            side=side,
            volume=Decimal(str(mt5_order.volume_current)),
            price=Decimal(str(mt5_order.price_open)) if mt5_order.price_open > 0 else None,
            stop_price=Decimal(str(mt5_order.sl)) if mt5_order.sl > 0 else None,
            status=status,
            filled_volume=Decimal(str(mt5_order.volume_current - mt5_order.volume_initial)) if mt5_order.volume_initial > 0 else Decimal(0),
            comment=mt5_order.comment,
        )

    def _convert_mt5_position(self, mt5_pos) -> Position:
        """Convert MT5 position to our Position model."""
        direction = Direction.LONG if mt5_pos.type == mt5.POSITION_TYPE_BUY else Direction.SHORT

        return Position(
            position_id=UUID(int=mt5_pos.ticket),
            symbol=mt5_pos.symbol,
            symbol_id=0,
            broker=BrokerType.MT5,
            broker_position_id=str(mt5_pos.ticket),
            direction=direction,
            volume=Decimal(str(mt5_pos.volume)),
            entry_price=Decimal(str(mt5_pos.price_open)),
            current_price=Decimal(str(mt5_pos.price_current)),
            unrealized_pnl=Decimal(str(mt5_pos.profit)),
            realized_pnl=Decimal(0),
            stop_loss=Decimal(str(mt5_pos.sl)) if mt5_pos.sl > 0 else None,
            take_profit=Decimal(str(mt5_pos.tp)) if mt5_pos.tp > 0 else None,
            swap=Decimal(str(mt5_pos.swap)),
            commission=Decimal(str(mt5_pos.commission)),
            margin_used=Decimal(str(mt5_pos.margin)),
            opened_at=datetime.fromtimestamp(mt5_pos.time, tz=UTC),
            is_open=True,
        )