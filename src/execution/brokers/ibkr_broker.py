"""
Interactive Brokers (IBKR) Broker Adapter
==========================================

Interactive Brokers API adapter for order execution via IBKR TWS/Gateway API.

Requirements:
- ib_insync library (pip install ib_insync)
- TWS or IB Gateway running
- API connections enabled in TWS/Gateway settings
- API port configured (default 7497 for TWS paper, 7496 for TWS live, 4001/4002 for Gateway)

Documentation: https://ib-insync.readthedocs.io/
IBKR API: https://interactivebrokers.github.io/tws-api/
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from ib_insync import (
    IB,
    Contract,
    Forex,
    Future,
    LimitOrder,
    MarketOrder,
    Option,
    Stock,
    StopLimitOrder,
    StopOrder,
    Trade,
)
from ib_insync import (
    Order as IBOrder,
)
from ib_insync import (
    Position as IBPosition,
)
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

IBKR_ORDER_TYPE_MAP = {
    OrderType.MARKET: "MKT",
    OrderType.LIMIT: "LMT",
    OrderType.STOP: "STP",
    OrderType.STOP_LIMIT: "STP LMT",
}

IBKR_ORDER_SIDE_MAP = {
    OrderSide.BUY: "BUY",
    OrderSide.SELL: "SELL",
}

IBKR_ORDER_STATUS_MAP = {
    "PendingSubmit": OrderStatus.PENDING,
    "PreSubmitted": OrderStatus.PENDING,
    "Submitted": OrderStatus.SUBMITTED,
    "PartiallyFilled": OrderStatus.PARTIAL,
    "Filled": OrderStatus.FILLED,
    "Cancelled": OrderStatus.CANCELLED,
    "CancelledByUser": OrderStatus.CANCELLED,
    "Rejected": OrderStatus.REJECTED,
    "Expired": OrderStatus.EXPIRED,
    "PendingCancel": OrderStatus.CANCELLED,
}

class IBKRAdapter(BrokerAdapter):
    """Interactive Brokers (IBKR) broker adapter using ib_insync."""
    
    # Maps are defined as module-level constants (IBKR_*)

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 7497,  # 7497=paper TWS, 7496=live TWS, 4001=paper gateway, 4002=live gateway
        client_id: int = 1,
        readonly: bool = False,
        account: str | None = None,
    ):
        super().__init__(BrokerType.IBKR)
        
        self._host = host
        self._port = port
        self._client_id = client_id
        self._readonly = readonly
        self._account = account or settings.ibkr_account

        self._ib: IB | None = None
        self._connected = False
        self._account_id: str | None = None
        self._contracts: dict[str, Contract] = {}
        self._pending_orders: dict[int, Order] = {}

    @property
    def broker_type(self) -> BrokerType:
        return BrokerType.IBKR

    @broker_type.setter
    def broker_type(self, value: BrokerType) -> None:
        # Allow base class to set broker_type
        self._broker_type = value

    @property
    def is_connected(self) -> bool:
        return self._connected and self._ib is not None and self._ib.isConnected()

    async def connect(self) -> None:
        """Connect to IBKR TWS/Gateway."""
        try:
            self._ib = IB()
            
            # Connect to TWS/Gateway
            await self._ib.connectAsync(
                host=self._host,
                port=self._port,
                clientId=self._client_id,
                readonly=self._readonly,
                timeout=30,
            )
            
            # Get managed accounts
            accounts = self._ib.managedAccounts()
            if not accounts:
                raise ConnectionError("No managed accounts found")
            
            self._account_id = self._account or accounts[0]
            logger.info(f"IBKR connected: account={self._account_id}")
            
            # Sync existing orders/positions
            await self._ib.reqAllOpenOrdersAsync()
            await self._ib.reqPositionsAsync()
            
            self._connected = True
            logger.info("IBKR adapter connected successfully")
            
        except Exception as e:
            logger.error(f"IBKR connection failed: {e}")
            raise ConnectionError(f"IBKR connection failed: {e}")
    
    async def disconnect(self) -> None:
        """Disconnect from IBKR."""
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
        self._connected = False
        logger.info("IBKR adapter disconnected")
    
    def _create_contract(self, symbol: str, sec_type: str = "STK") -> Contract:
        """Create IB contract from symbol."""
        cache_key = f"{symbol}:{sec_type}"
        if cache_key in self._contracts:
            return self._contracts[cache_key]
        
        # Parse symbol (e.g., "EURUSD" -> Forex, "AAPL" -> Stock)
        if sec_type == "STK" or (sec_type == "STK" and "." not in symbol and len(symbol) <= 5):
            contract = Stock(symbol, "SMART", "USD")
        elif sec_type == "CASH" or (len(symbol) == 6 and symbol.isalpha()):
            # Forex pair like EURUSD
            base = symbol[:3]
            quote = symbol[3:]
            contract = Forex(base, quote)
        elif sec_type == "FUT":
            # Future format: ES202412
            contract = Future(symbol, "GLOBEX", "USD")
        elif sec_type == "OPT":
            # Option parsing would be more complex
            contract = Option(symbol, "SMART", "USD")
        else:
            contract = Stock(symbol, "SMART", "USD")
        
        # Qualify contract
        qualified = self._ib.qualifyContracts(contract)
        if qualified:
            contract = qualified[0]
            self._contracts[f"{symbol}:{sec_type}"] = contract
        
        return contract
    
    def _create_order(self, order: Order) -> IBOrder:
        """Create IB order from our Order model."""
        order_type = IBKR_ORDER_TYPE_MAP.get(order.order_type, "MKT")
        side = IBKR_ORDER_SIDE_MAP.get(order.side, "BUY")
        
        if order_type == "MKT":
            ib_order = MarketOrder(side, float(order.volume))
        elif order_type == "LMT":
            if not order.price:
                raise ValueError("Limit order requires price")
            ib_order = LimitOrder(side, float(order.volume), float(order.price))
        elif order_type == "STP":
            if not order.stop_price:
                raise ValueError("Stop order requires stop price")
            ib_order = StopOrder(side, float(order.volume), float(order.stop_price))
        elif order_type == "STP LMT":
            if not order.price or not order.stop_price:
                raise ValueError("Stop-limit order requires price and stop price")
            ib_order = StopLimitOrder(side, float(order.volume), float(order.price), float(order.stop_price))
        else:
            ib_order = MarketOrder(side, float(order.volume))
        
        # Common order settings
        ib_order.tif = "GTC"
        ib_order.outsideRth = True  # Allow extended hours
        ib_order.clientId = f"CLIENT_{order.client_order_id}"
        
        # Stop loss and take profit as bracket orders would need parent order
        # For simplicity, we handle SL/TP as separate orders
        
        return ib_order
    
    async def place_order(self, order: Order) -> Order:
        """Place order via IBKR."""
        if not self.is_connected:
            raise ConnectionError("Not connected to IBKR")
        
        contract = self._create_contract(order.symbol)
        ib_order = self._create_order(order)
        
        try:
            # Place order
            _trade = self._ib.placeOrder(contract, ib_order)
            
            # Wait for order to be acknowledged
            await asyncio.sleep(0.5)
            
            # Update order with broker info
            order.broker_order_id = str(_trade.order.orderId)
            order.status = IBKR_ORDER_STATUS_MAP.get(_trade.orderStatus.status, OrderStatus.SUBMITTED)
            order.submitted_at = datetime.now(UTC)
            order.filled_volume = Decimal(str(_trade.filled))
            order.avg_fill_price = Decimal(str(_trade.orderStatus.avgFillPrice)) if _trade.orderStatus.avgFillPrice > 0 else None
            
            if _trade.orderStatus.status == "Filled":
                order.status = OrderStatus.FILLED
                order.filled_at = datetime.now(UTC)
                order.filled_volume = Decimal(str(_trade.filled))
                order.avg_fill_price = Decimal(str(_trade.orderStatus.avgFillPrice))
                # Commission info available in trade.fills
            
            # Track for updates
            self._pending_orders[_trade.order.orderId] = order
            
            logger.info(f"IBKR order placed: {order.client_order_id} -> {order.broker_order_id}")
            return order
            
        except Exception as e:
            logger.error(f"IBKR order placement failed: {e}")
            order.status = OrderStatus.REJECTED
            order.comment = str(e)
            return order
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order via IBKR."""
        if not self.is_connected:
            return False
        
        try:
            order_id_int = int(order_id)
            _trade = self._ib.cancelOrder(order_id_int)
            await asyncio.sleep(0.5)
            return True
        except Exception as e:
            logger.error(f"IBKR cancel order failed: {e}")
            return False
    
    async def modify_order(
        self,
        order_id: str,
        new_price: Decimal | None = None,
        new_volume: Decimal | None = None,
        new_sl: Decimal | None = None,
        new_tp: Decimal | None = None,
    ) -> bool:
        """Modify order via IBKR."""
        if not self.is_connected:
            return False
        
        try:
            order_id_int = int(order_id)
            
            # Get current order
            trades = self._ib.trades()
            _trade = next((t for t in trades if t.order.orderId == order_id_int), None)
            if not _trade:
                return False
            
            # Modify order
            if new_price is not None:
                _trade.order.lmtPrice = float(new_price)
            if new_volume is not None:
                _trade.order.totalQuantity = float(new_volume)
            
            self._ib.placeOrder(_trade.contract, _trade.order)
            await asyncio.sleep(0.5)
            return True
            
        except Exception as e:
            logger.error(f"IBKR modify order failed: {e}")
            return False
    
    async def get_order_status(self, order_id: str) -> Order | None:
        """Get order status from IBKR."""
        if not self.is_connected:
            return None
        
        try:
            order_id_int = int(order_id)
            
            # Check pending orders
            for trade in self._ib.trades():
                if trade.order.orderId == order_id_int:
                    return self._convert_ib_trade(trade)
            
            # Check completed orders
            for trade in self._ib.trades():
                if trade.order.orderId == order_id_int:
                    return self._convert_ib_trade(trade)
            
            return None
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return None
    
    async def get_open_orders(self) -> list[Order]:
        """Get all open orders."""
        if not self.is_connected:
            return []
        
        try:
            orders = []
            for trade in self._ib.trades():
                if trade.orderStatus.status not in ["Filled", "Cancelled", "Rejected", "Expired"]:
                    orders.append(self._convert_ib_trade(trade))
            return orders
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return []
    
    async def get_positions(self) -> list[Position]:
        """Get current positions."""
        if not self.is_connected:
            return []

        try:
            positions: list[Position] = []
            for pos in self._ib.positions():
                if pos.position != 0:
                    positions.append(
                        Position(
                            position_id=UUID(int=0),
                            symbol=pos.contract.symbol,
                            broker=BrokerType.IBKR,
                            broker_position_id=str(pos.contract.conId),
                            direction=Direction.LONG if pos.position > 0 else Direction.SHORT,
                            volume=Decimal(str(abs(pos.position))),
                            entry_price=Decimal(str(pos.avgCost)),
                            current_price=Decimal(str(pos.marketPrice)),
                            unrealized_pnl=Decimal(str(pos.unrealizedPNL)),
                            stop_loss=Decimal(0),
                            take_profit=Decimal(0),
                            is_open=True,
                        )
                    )
            return positions
        except Exception as e:
            logger.error(f"Error getting IBKR positions: {e}")
            return []
    
    async def get_account_info(self) -> dict[str, Any]:
        """Get account info."""
        if not self.is_connected:
            return {}
        
        try:
            account = self._ib.accountSummary()
            summary = {item.tag: item.value for item in account if item.account == self._account_id}

            return {
                "account": self._account_id,
                "balance": Decimal(summary.get("TotalCashValue", "0")),
                "equity": Decimal(summary.get("NetLiquidation", "0")),
                "margin": Decimal(summary.get("InitMarginReq", "0")),
                "free_margin": Decimal(summary.get("AvailableFunds", "0")),
                "margin_level": Decimal(summary.get("MaintMarginReq", "0")),
                "currency": "USD",
                "profit": Decimal(summary.get("UnrealizedPnL", "0")),
            }
        except Exception as e:
            logger.error(f"Error getting IBKR account info: {e}")
            return {}
    
    async def get_symbol_info(self, symbol: str) -> dict[str, Any] | None:
        """Get symbol info."""
        try:
            contract = self._create_contract(symbol)
            details = self._ib.reqContractDetails(contract)
            if not details:
                return None

            d = details[0]
            return {
                "symbol": d.contract.symbol,
                "sec_type": d.contract.secType,
                "exchange": d.contract.exchange,
                "currency": d.contract.currency,
                "min_tick": d.minTick,
                "trading_hours": d.tradingHours,
                "liquid_hours": d.liquidHours,
            }
        except Exception as e:
            logger.error(f"Error getting IBKR symbol info: {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check IBKR connection health."""
        if not self._ib or not self._ib.isConnected():
            return False
        try:
            # Quick check
            await self._ib.reqCurrentTimeAsync()
            return True
        except Exception as e:
            logger.error(f"IBKR health check failed: {e}")
            return False
    
    def _convert_ib_trade(self, trade: Trade) -> Order:
        """Convert IB trade to our Order model."""
        status = IBKR_ORDER_STATUS_MAP.get(trade.orderStatus.status, OrderStatus.PENDING)
        
        # Map side
        side = OrderSide.BUY if trade.order.action == "BUY" else OrderSide.SELL
        
        # Map order type
        order_type_map = {v: k for k, v in IBKR_ORDER_TYPE_MAP.items()}
        order_type = order_type_map.get(trade.order.orderType, OrderType.MARKET)
        
        return Order(
            order_id=UUID(int=trade.order.orderId),
            broker_order_id=str(trade.order.orderId),
            client_order_id=trade.order.clientId,
            symbol=trade.contract.symbol,
            order_type=order_type,
            side=side,
            volume=Decimal(str(trade.order.totalQuantity)),
            price=Decimal(str(trade.order.lmtPrice)) if trade.order.lmtPrice > 0 else None,
            stop_price=Decimal(str(trade.order.auxPrice)) if trade.order.auxPrice > 0 else None,
            status=status,
            filled_volume=Decimal(str(trade.filled)),
            avg_fill_price=Decimal(str(trade.orderStatus.avgFillPrice)) if trade.orderStatus.avgFillPrice > 0 else None,
            commission=Decimal(str(trade.commissionReport.commission)) if trade.commissionReport else Decimal(0),
            submitted_at=datetime.fromtimestamp(trade.log[0].time, tz=UTC) if trade.log else None,
            filled_at=datetime.now(UTC) if trade.orderStatus.status == "Filled" else None,
            comment=trade.orderStatus.whyHeld,
        )
    
    def _convert_ib_position(self, pos: IBPosition) -> Position:
        """Convert IB position to our Position model."""
        direction = Direction.LONG if pos.position > 0 else Direction.SHORT
        
        return Position(
            position_id=UUID(int=pos.contract.conId),
            symbol=pos.contract.symbol,
            symbol_id=pos.contract.conId,
            broker=BrokerType.IBKR,
            broker_position_id=str(pos.account),
            direction=direction,
            volume=Decimal(str(abs(pos.position))),
            entry_price=Decimal(str(pos.avgCost)),
            current_price=Decimal(str(pos.marketPrice)),
            unrealized_pnl=Decimal(str(pos.unrealizedPNL)),
            realized_pnl=Decimal(str(pos.realizedPNL)),
            stop_loss=None,  # Not directly available
            take_profit=None,
            swap=Decimal(0),
            commission=Decimal(0),
            margin_used=Decimal(0),
            opened_at=datetime.now(UTC),  # Not directly available
            is_open=True,
        )


class IBKROrderManager:
    """High-level order management for IBKR."""
    
    def __init__(self, adapter: IBKRAdapter):
        self.adapter = adapter
    
    async def place_market_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: Decimal,
        sl: Decimal | None = None,
        tp: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> Order:
        """Place a market order."""
        order = Order(
            order_id=UUID(int=int(time.time() * 1000000)),
            client_order_id=client_order_id or f"MKT_{int(time.time())}",
            symbol=symbol,
            order_type=OrderType.MARKET,
            side=side,
            volume=volume,
            stop_price=sl,
        )
        return await self.adapter.place_order(order)
    
    async def place_limit_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: Decimal,
        price: Decimal,
        sl: Decimal | None = None,
        tp: Decimal | None = None,
        client_order_id: str | None = None,
    ) -> Order:
        """Place a limit order."""
        order = Order(
            order_id=UUID(int=int(time.time() * 1000000)),
            client_order_id=client_order_id or f"LMT_{int(time.time())}",
            symbol=symbol,
            order_type=OrderType.LIMIT,
            side=side,
            volume=volume,
            price=price,
            stop_price=sl,
        )
        return await self.adapter.place_order(order)
    
    async def place_stop_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: Decimal,
        stop_price: Decimal,
        client_order_id: str | None = None,
    ) -> Order:
        """Place a stop order."""
        order = Order(
            order_id=UUID(int=int(time.time() * 1000000)),
            client_order_id=client_order_id or f"STP_{int(time.time())}",
            symbol=symbol,
            order_type=OrderType.STOP,
            side=side,
            volume=volume,
            stop_price=stop_price,
        )
        return await self.adapter.place_order(order)
    
    async def place_bracket_order(
        self,
        symbol: str,
        side: OrderSide,
        volume: Decimal,
        entry_price: Decimal | None,
        stop_loss: Decimal,
        take_profit: Decimal,
        client_order_id: str | None = None,
    ) -> list[Order]:
        """Place bracket order (entry + SL + TP)."""
        orders = []
        
        # Entry order
        if entry_price:
            entry_order = Order(
                order_id=UUID(int=int(time.time() * 1000000)),
                client_order_id=f"{client_order_id}_entry",
                symbol=symbol,
                order_type=OrderType.LIMIT,
                side=side,
                volume=volume,
                price=entry_price,
            )
        else:
            entry_order = Order(
                order_id=UUID(int=int(time.time() * 1000000)),
                client_order_id=f"{client_order_id}_entry",
                symbol=symbol,
                order_type=OrderType.MARKET,
                side=side,
                volume=volume,
            )
        
        entry_result = await self.adapter.place_order(entry_order)
        orders.append(entry_result)
        
        # SL and TP as separate orders (IBKR handles brackets differently)
        # For production, use IB's native bracket orders
        # This is simplified
        return orders
    
    async def close_position(self, symbol: str) -> bool:
        """Close position for symbol."""
        positions = await self.adapter.get_positions()
        for pos in positions:
            if pos.symbol == symbol:
                side = OrderSide.SELL if pos.direction == Direction.LONG else OrderSide.BUY
                order = Order(
                    order_id=UUID(int=int(time.time() * 1000000)),
                    client_order_id=f"CLOSE_{symbol}_{int(time.time())}",
                    symbol=symbol,
                    order_type=OrderType.MARKET,
                    side=side,
                    volume=pos.volume,
                )
                await self.adapter.place_order(order)
                return True
        return False
    
    async def set_stop_loss(self, order_id: str, sl: Decimal) -> bool:
        """Set stop loss for position."""
        # For IBKR, SL is typically part of bracket or separate order
        return await self.adapter.modify_order(order_id, new_sl=sl)
    
    async def set_take_profit(self, order_id: str, tp: Decimal) -> bool:
        """Set take profit for position."""
        return await self.adapter.modify_order(order_id, new_tp=tp)


# Example usage
if __name__ == "__main__":
    import time
    
    async def example():
        adapter = IBKRAdapter(
            host="127.0.0.1",
            port=7497,  # Paper trading port
            client_id=1,
        )
        
        try:
            await adapter.connect()
            
            # Get account info
            account = await adapter.get_account_info()
            logger.info(f"Account: {account}")
            
            # Get positions
            positions = await adapter.get_positions()
            logger.info(f"Positions: {positions}")
            
            # Place a market order
            order = await adapter.place_order(Order(
                symbol="AAPL",
                order_type=OrderType.MARKET,
                side=OrderSide.BUY,
                volume=Decimal(10),
            ))
            logger.info(f"Order placed: {order.broker_order_id}")
            
        finally:
            await adapter.disconnect()
    
    asyncio.run(example())