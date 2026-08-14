from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import ccxt.async_support as ccxt
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

CCXT_ORDER_TYPE_MAP = {
    OrderType.MARKET: "market",
    OrderType.LIMIT: "limit",
    OrderType.STOP: "stop",
    OrderType.STOP_LIMIT: "stop_limit",
}

CCXT_ORDER_SIDE_MAP = {
    OrderSide.BUY: "buy",
    OrderSide.SELL: "sell",
}

CCXT_ORDER_STATUS_MAP = {
    "open": OrderStatus.SUBMITTED,
    "closed": OrderStatus.FILLED,
    "canceled": OrderStatus.CANCELLED,
    "rejected": OrderStatus.REJECTED,
    "expired": OrderStatus.EXPIRED,
    "pending": OrderStatus.PENDING,
}

class CCXTBrokerAdapter(BrokerAdapter):
    """CCXT broker adapter for crypto exchange order execution."""

    # class-level now empty; maps are module-level constants

    def __init__(self, exchanges: list[str] | None = None, api_keys: dict | None = None):
        super().__init__(BrokerType.CCXT)
        self.exchange_names = exchanges or settings.ccxt_exchanges
        self.api_keys = api_keys or settings.ccxt_api_keys
        self._exchanges: dict[str, ccxt.Exchange] = {}
        self._markets_loaded = False

    async def connect(self) -> None:
        """Initialize all exchange connections."""
        for exchange_name in self.exchange_names:
            try:
                exchange_class = getattr(ccxt, exchange_name)
                config = {
                    "enableRateLimit": settings.ccxt_enable_rate_limit,
                    "rateLimit": settings.ccxt_rate_limit,
                    "timeout": settings.ccxt_timeout,
                    "options": settings.ccxt_options.get(exchange_name, {}),
                }

                if exchange_name in self.api_keys:
                    config.update(self.api_keys[exchange_name])

                exchange = exchange_class(config)
                await exchange.load_markets()
                self._exchanges[exchange_name] = exchange
                logger.info(f"CCXT exchange connected: {exchange_name}")

            except Exception as e:
                logger.error(f"Failed to connect to {exchange_name}: {e}")

        if not self._exchanges:
            raise ConnectionError("No CCXT exchanges connected")

        self._markets_loaded = True
        self._connected = True

    async def disconnect(self) -> None:
        """Close all exchange connections."""
        for exchange in self._exchanges.values():
            try:
                await exchange.close()
            except Exception as e:
                logger.error(f"Error closing exchange: {e}")
        self._exchanges.clear()
        self._connected = False
        logger.info("All CCXT exchanges disconnected")

    def _get_exchange_for_symbol(self, symbol: str) -> tuple[str, ccxt.Exchange]:
        """Find which exchange has this symbol."""
        for exch_name, exch in self._exchanges.items():
            if symbol in exch.markets:
                return exch_name, exch

        # Default to first exchange
        first_exch = next(iter(self._exchanges.items()))
        return first_exch

    async def place_order(self, order: Order) -> Order:
        """Place order on exchange."""
        exch_name, exchange = self._get_exchange_for_symbol(order.symbol)

        try:
            # Prepare order parameters
            params = {
                "clientOrderId": order.client_order_id,
            }

            # Handle stop orders
            if order.order_type == OrderType.STOP:
                params["stopPrice"] = float(order.stop_price)
            elif order.order_type == OrderType.STOP_LIMIT:
                params["stopPrice"] = float(order.stop_price)
                params["price"] = float(order.price)

            ccxt_order = await exchange.create_order(
                symbol=order.symbol,
                type=CCXT_ORDER_TYPE_MAP.get(order.order_type, "market"),
                side=CCXT_ORDER_SIDE_MAP.get(order.side, "buy"),
                amount=float(order.volume),
                price=float(order.price) if order.price else None,
                params=params,
            )

            # Update order with exchange response
            order.broker_order_id = ccxt_order.get("id", "")
            order.status = CCXT_ORDER_STATUS_MAP.get(ccxt_order.get("status", "open"), OrderStatus.SUBMITTED)
            order.filled_volume = Decimal(str(ccxt_order.get("filled", 0)))
            order.avg_fill_price = Decimal(str(ccxt_order.get("average", 0))) if ccxt_order.get("average") else None
            order.submitted_at = datetime.now(UTC)

            if order.status == OrderStatus.FILLED:
                order.filled_at = datetime.now(UTC)
                order.commission = Decimal(str(ccxt_order.get("fee", {}).get("cost", 0))) if ccxt_order.get("fee") else Decimal(0)

            logger.info(f"CCXT order placed: {order.client_order_id} -> {order.broker_order_id} on {exch_name}")

            return order

        except Exception as e:
            logger.error(f"CCXT order placement failed: {e}")
            order.status = OrderStatus.REJECTED
            order.comment = str(e)
            return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order on exchange."""
        # Need to know which exchange - would need to track this
        for exchange in self._exchanges.values():
            try:
                result = await exchange.cancel_order(order_id)
                return result.get("status") == "canceled"
            except Exception as e:
                logger.error(f"Exception occurred: {e}")
                continue
        return False

    async def modify_order(self, order_id: str, new_price: Decimal | None = None, new_volume: Decimal | None = None, new_sl: Decimal | None = None, new_tp: Decimal | None = None) -> bool:
        """Modify order on exchange (cancel and replace)."""
        # Most exchanges don't support modify, need to cancel and replace
        success = await self.cancel_order(order_id)
        if not success:
            return False

        # Would need to create new order with updated params
        # This is a simplified implementation
        return True

    async def get_order_status(self, order_id: str) -> Order | None:
        """Get order status from exchange."""
        for exchange in self._exchanges.values():
            try:
                ccxt_order = await exchange.fetch_order(order_id)
                if ccxt_order:
                    return self._map_ccxt_order(ccxt_order)
            except Exception as e:
                logger.error(f"Exception occurred: {e}")
                continue
        return None

    async def get_open_orders(self) -> list[Order]:
        """Get all open orders from all exchanges."""
        all_orders = []
        for exch_name, exchange in self._exchanges.items():
            try:
                orders = await exchange.fetch_open_orders()
                for ccxt_order in orders:
                    all_orders.append(self._convert_ccxt_order(ccxt_order, exch_name))
            except Exception as e:
                logger.error(f"Error fetching open orders from {exch_name}: {e}")
        return all_orders

    async def get_positions(self) -> list[Position]:
        """Get current positions from all exchanges."""
        all_positions = []
        for exch_name, exchange in self._exchanges.items():
            try:
                # For spot, check balances
                # For futures, fetch positions
                if hasattr(exchange, 'fetch_positions'):
                    positions = await exchange.fetch_positions()
                    for pos in positions:
                        if pos.get("contracts", 0) > 0:
                            all_positions.append(self._convert_ccxt_position(pos, exch_name))
            except Exception as e:
                logger.error(f"Error fetching positions from {exch_name}: {e}")
        return all_positions

    async def get_account_info(self) -> dict[str, Any]:
        """Get account info from all exchanges."""
        accounts = {}
        for exch_name, exchange in self._exchanges.items():
            try:
                balance = await exchange.fetch_balance()
                accounts[exch_name] = {
                    "balance": balance,
                    "free": balance.get("free", {}),
                    "used": balance.get("used", {}),
                    "total": balance.get("total", {}),
                }
            except Exception as e:
                logger.error(f"Error fetching balance from {exch_name}: {e}")
        return accounts

    async def get_symbol_info(self, symbol: str) -> dict[str, Any] | None:
        """Get symbol info from exchange."""
        _exch_name, exchange = self._get_exchange_for_symbol(symbol)
        if symbol in exchange.markets:
            market = exchange.markets[symbol]
            return {
                "symbol": market["symbol"],
                "base": market["base"],
                "quote": market["quote"],
                "precision": market["precision"],
                "limits": market["limits"],
                "type": market["type"],
                "spot": market.get("spot", False),
                "future": market.get("future", False),
                "swap": market.get("swap", False),
            }
        return None

    async def health_check(self) -> bool:
        """Check exchange connections."""
        for exchange in self._exchanges.values():
            try:
                await exchange.fetch_time()
            except Exception as e:
                logger.error(f"Health check failed for exchange: {e}")
                return False
        return True

    def _convert_ccxt_order(self, ccxt_order: dict, exchange_name: str) -> Order:
        """Convert CCXT order to our Order model."""
        status = CCXT_ORDER_STATUS_MAP.get(ccxt_order.get("status", "open"), OrderStatus.PENDING)

        side = OrderSide.BUY if ccxt_order.get("side") == "buy" else OrderSide.SELL

        order_type_str = ccxt_order.get("type", "market")
        if order_type_str == "market":
            order_type = OrderType.MARKET
        elif order_type_str == "limit":
            order_type = OrderType.LIMIT
        elif order_type_str in ["stop", "stop_loss"]:
            order_type = OrderType.STOP
        elif order_type_str in ["stop_limit", "take_profit_limit"]:
            order_type = OrderType.STOP_LIMIT
        else:
            order_type = OrderType.MARKET

        return Order(
            order_id=UUID(int=hash(ccxt_order.get("id", "")) % (2**64)),
            broker_order_id=ccxt_order.get("id", ""),
            client_order_id=ccxt_order.get("clientOrderId", ""),
            symbol=ccxt_order.get("symbol", ""),
            symbol_id=0,
            broker=BrokerType.CCXT,
            order_type=order_type,
            side=side,
            volume=Decimal(str(ccxt_order.get("amount", 0))),
            price=Decimal(str(ccxt_order.get("price", 0))) if ccxt_order.get("price") else None,
            stop_price=Decimal(str(ccxt_order.get("stopPrice", 0))) if ccxt_order.get("stopPrice") else None,
            status=status,
            filled_volume=Decimal(str(ccxt_order.get("filled", 0))),
            avg_fill_price=Decimal(str(ccxt_order.get("average", 0))) if ccxt_order.get("average") else None,
            commission=Decimal(str(ccxt_order.get("fee", {}).get("cost", 0))) if ccxt_order.get("fee") else Decimal(0),
            submitted_at=datetime.fromtimestamp(ccxt_order["timestamp"] / 1000, tz=UTC) if ccxt_order.get("timestamp") else None,
            filled_at=datetime.fromtimestamp(ccxt_order["lastTradeTimestamp"] / 1000, tz=UTC) if ccxt_order.get("lastTradeTimestamp") else None,
        )

    def _convert_ccxt_position(self, ccxt_pos: dict, exchange_name: str) -> Position:
        """Convert CCXT position to our Position model."""
        contracts = ccxt_pos.get("contracts", 0)
        if contracts == 0:
            return None

        direction = Direction.LONG if contracts > 0 else Direction.SHORT

        return Position(
            position_id=UUID(int=hash(ccxt_pos.get("symbol", "") + exchange_name) % (2**64)),
            symbol=ccxt_pos.get("symbol", ""),
            symbol_id=0,
            broker=BrokerType.CCXT,
            broker_position_id=f"{exchange_name}:{ccxt_pos.get('symbol', '')}",
            direction=direction,
            volume=Decimal(str(abs(contracts))),
            entry_price=Decimal(str(ccxt_pos.get("entryPrice", 0))),
            current_price=Decimal(str(ccxt_pos.get("markPrice", 0))),
            unrealized_pnl=Decimal(str(ccxt_pos.get("unrealizedPnl", 0))),
            realized_pnl=Decimal(str(ccxt_pos.get("realizedPnl", 0))),
            stop_loss=Decimal(str(ccxt_pos.get("stopLoss", 0))) if ccxt_pos.get("stopLoss") else None,
            take_profit=Decimal(str(ccxt_pos.get("takeProfit", 0))) if ccxt_pos.get("takeProfit") else None,
            margin_used=Decimal(str(ccxt_pos.get("initialMargin", 0))),
            opened_at=datetime.fromtimestamp(ccxt_pos["timestamp"] / 1000, tz=UTC) if ccxt_pos.get("timestamp") else datetime.now(UTC),
            is_open=True,
        )