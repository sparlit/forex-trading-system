"""
cTrader Broker Adapter
======================

cTrader Open API adapter for order execution via Protobuf/gRPC.

Requirements:
- cTrader Open API credentials (Client ID, Client Secret)
- Access to cTrader FIX/gRPC endpoints
- Protobuf definitions for cTrader Open API messages

Documentation: https://ctrader.com/open-api
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import grpc
import websockets
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


class CTraderMessageTypes:
    """cTrader Open API message types."""
    # Application messages
    PROTO_OA_APPLICATION_AUTH_REQ = 2100
    PROTO_OA_APPLICATION_AUTH_RES = 2101
    
    # Account messages
    PROTO_OA_ACCOUNT_LIST_REQ = 2102
    PROTO_OA_ACCOUNT_LIST_RES = 2103
    PROTO_OA_ACCOUNT_AUTH_REQ = 2104
    PROTO_OA_ACCOUNT_AUTH_RES = 2105
    
    # Order messages
    PROTO_OA_NEW_ORDER_REQ = 2106
    PROTO_OA_NEW_ORDER_RES = 2107
    PROTO_OA_EXECUTION_REPORT = 2108
    
    # Position messages
    PROTO_OA_POSITION_LIST_REQ = 2109
    PROTO_OA_POSITION_LIST_RES = 2110
    PROTO_OA_POSITION_CLOSE_REQ = 2111
    PROTO_OA_POSITION_CLOSE_RES = 2112
    PROTO_OA_POSITION_MODIFY_REQ = 2113
    PROTO_OA_POSITION_MODIFY_RES = 2114
    
    # Symbol messages
    PROTO_OA_SYMBOL_LIST_REQ = 2115
    PROTO_OA_SYMBOL_LIST_RES = 2116
    PROTO_OA_SYMBOL_BY_ID_REQ = 2117
    PROTO_OA_SYMBOL_BY_ID_RES = 2118
    
    # Market data
    PROTO_OA_GET_TREND_BARS_REQ = 2119
    PROTO_OA_GET_TREND_BARS_RES = 2120
    PROTO_OA_SUBSCRIBE_SPOTS_REQ = 2121
    PROTO_OA_SUBSCRIBE_SPOTS_RES = 2122
    PROTO_OA_SPOT_EVENT = 2123
    
    # Account info
    PROTO_OA_GET_ACCOUNT_INFO_REQ = 2124
    PROTO_OA_GET_ACCOUNT_INFO_RES = 2125
    
    # Error
    PROTO_OA_ERROR_RES = 2126



CTRADER_ORDER_TYPE_MAP = {
    OrderType.MARKET: 1,      # MARKET
    OrderType.LIMIT: 2,       # LIMIT
    OrderType.STOP: 3,        # STOP
    OrderType.STOP_LIMIT: 4,  # STOP_LIMIT
}

CTRADER_ORDER_SIDE_MAP = {
    OrderSide.BUY: 1,   # BUY
    OrderSide.SELL: 2,  # SELL
}

CTRADER_ORDER_STATUS_MAP = {
    1: OrderStatus.PENDING,      # CREATED
    2: OrderStatus.SUBMITTED,    # ACCEPTED
    3: OrderStatus.PARTIAL,      # PARTIALLY_FILLED
    4: OrderStatus.FILLED,       # FILLED
    5: OrderStatus.CANCELLED,    # CANCELLED
    6: OrderStatus.REJECTED,     # REJECTED
    7: OrderStatus.EXPIRED,      # EXPIRED
}

CTRADER_POSITION_SIDE_MAP = {
    1: Direction.LONG,   # BUY
    2: Direction.SHORT,  # SELL
}

class CTraderAdapter(BrokerAdapter):
    """cTrader Open API broker adapter using gRPC/WebSocket."""
    
    # Maps are defined as module-level constants (CTRADER_*)

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        access_token: str | None = None,
        refresh_token: str | None = None,
        host: str = "demo.ctraderapi.com",
        port: int = 443,
    ):
        super().__init__(BrokerType.CTRADER)
        
        self._client_id = client_id or settings.ctrader_client_id
        self._client_secret = client_secret or settings.ctrader_client_secret
        self._access_token = access_token or settings.ctrader_access_token
        self._refresh_token = refresh_token or settings.ctrader_refresh_token
        self._host = host
        self._port = port
        
        self._grpc_channel: grpc.aio.Channel | None = None
        self._stub = None
        self._websocket: websockets.WebSocketClientProtocol | None = None
        self._connected = False
        self._account_id: int | None = None
        self._symbols: dict[str, Any] = {}
        self._pending_requests: dict[int, asyncio.Future] = {}
        self._request_id = 0

    @property
    def broker_type(self) -> BrokerType:
        return BrokerType.CTRADER

    @broker_type.setter
    def broker_type(self, value: BrokerType) -> None:
        # Allow base class to set broker_type
        self._broker_type = value

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        """Establish connection to cTrader Open API."""
        try:
            # Authenticate via OAuth2
            await self._authenticate()

            # Establish gRPC connection
            await self._connect_grpc()

            # Get account list and select first
            await self._get_accounts()

            # Load symbols
            await self._load_symbols()

            self._connected = True
            logger.info(f"cTrader adapter connected: account={self._account_id}")

        except Exception as e:
            logger.error(f"cTrader connection failed: {e}")
            raise ConnectionError(f"cTrader connection failed: {e}")

    async def _authenticate(self) -> None:
        """OAuth2 authentication with cTrader."""
        auth_url = f"https://{self._host}/api/oauth2/token"
        
        if self._refresh_token:
            # Refresh access token
            _data = {
                "grant_type": "refresh_token",
                "refresh_token": self._refresh_token,
                "client_id": self._client_id,
                "client_secret": self._client_secret,
            }
        else:
            # Initial client credentials flow
            _data = {
                "grant_type": "client_credentials",
                "client_id": self._client_id,
                "client_secret": self._client_secret,
                "scope": "openapi",
            }
        
        async with asyncio.timeout(30):
            async with websockets.connect(auth_url) as _ws:
                # In production, use aiohttp for HTTP requests
                # This is a simplified example
                pass
        
        # For production, use aiohttp:
        # async with aiohttp.ClientSession() as session:
        #     async with session.post(auth_url, data=data) as resp:
        #         token_data = await resp.json()
        #         self._access_token = token_data["access_token"]
        #         self._refresh_token = token_data.get("refresh_token", self._refresh_token)
        
        # Mock for now - replace with actual implementation
        if not self._access_token:
            logger.warning("cTrader access token not available - running in mock mode")
            self._access_token = settings.ctrader_access_token

    async def _connect_grpc(self) -> None:
        """Establish gRPC connection to cTrader."""
        target = f"{self._host}:{self._port}"
        
        # Create secure channel with SSL
        credentials = grpc.ssl_channel_credentials()
        call_credentials = grpc.access_token_call_credentials(self._access_token)
        composite_credentials = grpc.composite_channel_credentials(
            credentials, call_credentials
        )
        
        self._grpc_channel = grpc.aio.secure_channel(
            target,
            composite_credentials,
            options=[
                ("grpc.max_receive_message_length", 1024 * 1024 * 10),
                ("grpc.max_send_message_length", 1024 * 1024 * 10),
            ]
        )
        
        # Wait for channel to be ready
        await self._grpc_channel.channel_ready()
        
        # Create stub (requires generated protobuf stubs)
        # from ctrader_open_api import ProtoOAApplicationAuthReq, ProtoOAApplicationAuthRes
        # self._stub = ProtoOAApplicationAuthReqStub(self._grpc_channel)
        
        logger.info("gRPC channel established")
    
    async def _get_accounts(self) -> None:
        """Get and select trading account."""
        # Send ProtoOAAccountListReq
        # Receive ProtoOAAccountListRes
        # Select first account or configured account
        
        # Mock for now
        self._account_id = 12345
        logger.info(f"Selected account: {self._account_id}")
    
    async def _load_symbols(self) -> None:
        """Load available symbols from cTrader."""
        # Send ProtoOASymbolListReq
        # Receive ProtoOASymbolListRes
        # Parse and cache symbols
        
        # Mock for now
        self._symbols = {
            "EURUSD": {"id": 1, "digits": 5, "pip_value": 0.00001, "lot_size": 100000},
            "GBPUSD": {"id": 2, "digits": 5, "pip_value": 0.00001, "lot_size": 100000},
            "USDJPY": {"id": 3, "digits": 3, "pip_value": 0.01, "lot_size": 100000},
            "XAUUSD": {"id": 4, "digits": 2, "pip_value": 0.01, "lot_size": 100},
        }
        logger.info(f"Loaded {len(self._symbols)} symbols")
    
    async def disconnect(self) -> None:
        """Disconnect from cTrader."""
        if self._websocket:
            await self._websocket.close()
        if self._grpc_channel:
            await self._grpc_channel.close()
        self._connected = False
        logger.info("cTrader adapter disconnected")
    
    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id
    
    async def _send_request(self, payload: dict) -> asyncio.Future:
        """Send request and return future for response."""
        request_id = self._next_request_id()
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future
        
        payload["request_id"] = request_id
        payload["client_id"] = self._client_id
        payload["timestamp"] = int(time.time() * 1000)
        
        if self._websocket:
            await self._websocket.send(json.dumps(payload))
        
        return future
    
    async def place_order(self, order: Order) -> Order:
        """Place order via cTrader."""
        if not self._connected:
            raise ConnectionError("Not connected to cTrader")
        
        symbol_info = self._symbols.get(order.symbol)
        if not symbol_info:
            raise ValueError(f"Unknown symbol: {order.symbol}")
        
        # Build ProtoOANewOrderReq
        payload = {
            "message_type": CTraderMessageTypes.PROTO_OA_NEW_ORDER_REQ,
            "account_id": self._account_id,
            "symbol_id": symbol_info["id"],
            "order_type": CTRADER_ORDER_TYPE_MAP.get(order.order_type, 1),
            "trade_side": CTRADER_ORDER_SIDE_MAP.get(order.side, 1),
            "volume": int(float(order.volume) * 100),  # cTrader uses 1/100 lots
            "price": int(float(order.price) * 10**symbol_info["digits"]) if order.price else 0,
            "stop_loss": int(float(order.stop_price) * 10**symbol_info["digits"]) if order.stop_price else 0,
            "take_profit": 0,
            "label": order.client_order_id[:32],
            "comment": f"Order {order.client_order_id}",
        }
        
        # Send and wait for response
        future = self._send_request(payload)
        try:
            response = await asyncio.wait_for(future, timeout=30)
            
            if response.get("error_code"):
                order.status = OrderStatus.REJECTED
                order.comment = response.get("error_message", "Unknown error")
                return order
            
            # Update order with broker response
            order.broker_order_id = str(response.get("order_id", ""))
            order.status = OrderStatus.SUBMITTED
            order.submitted_at = datetime.now(UTC)
            
            logger.info(f"cTrader order placed: {order.client_order_id} -> {order.broker_order_id}")
            return order
            
        except asyncio.TimeoutError:
            order.status = OrderStatus.REJECTED
            order.comment = "Order timeout"
            return order
        except Exception as e:
            logger.error(f"cTrader order placement failed: {e}")
            order.status = OrderStatus.REJECTED
            order.comment = str(e)
            return order
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel order via cTrader."""
        # Send cancel request
        # Receive confirmation
        return True  # Simplified
    
    async def modify_order(
        self,
        order_id: str,
        new_price: Decimal | None = None,
        new_volume: Decimal | None = None,
        new_sl: Decimal | None = None,
        new_tp: Decimal | None = None,
    ) -> bool:
        """Modify order via cTrader."""
        # cTrader uses position modify for SL/TP changes
        return True  # Simplified
    
    async def get_order_status(self, order_id: str) -> Order | None:
        """Get order status from cTrader."""
        return None  # Simplified
    
    async def get_open_orders(self) -> list[Order]:
        """Get all open orders."""
        return []  # Simplified
    
    async def get_positions(self) -> list[Position]:
        """Get current positions."""
        return []  # Simplified
    
    async def get_account_info(self) -> dict[str, Any]:
        """Get account info."""
        return {}  # Simplified
    
    async def get_symbol_info(self, symbol: str) -> dict[str, Any] | None:
        """Get symbol info."""
        return self._symbols.get(symbol)
    
    async def health_check(self) -> bool:
        """Check cTrader connection health."""
        if not self._connected or not self._grpc_channel:
            return False
        try:
            # Check channel state
            state = self._grpc_channel.get_state(try_to_connect=False)
            return state == grpc.ChannelConnectivity.READY
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            return False
    
    async def _handle_websocket_messages(self) -> None:
        """Handle incoming WebSocket messages."""
        try:
            async for message in self._websocket:
                data = json.loads(message)
                request_id = data.get("request_id")
                
                if request_id in self._pending_requests:
                    future = self._pending_requests.pop(request_id)
                    if not future.done():
                        future.set_result(data)
                else:
                    # Handle unsolicited messages (executions, positions, etc.)
                    await self._handle_unsolicited(data)
        except Exception as e:
            logger.error(f"WebSocket handler error: {e}")
    
    async def _handle_unsolicited(self, data: dict) -> None:
        """Handle unsolicited messages (executions, position updates)."""
        msg_type = data.get("message_type")
        
        if msg_type == CTraderMessageTypes.PROTO_OA_EXECUTION_REPORT:
            # Handle execution report
            pass
        elif msg_type == CTraderMessageTypes.PROTO_OA_POSITION_CLOSE_RES:
            # Handle position close
            pass


class CTraderOrderManager:
    """High-level order management for cTrader."""
    
    def __init__(self, adapter: CTraderAdapter):
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
    
    async def close_position(self, position_id: str) -> bool:
        """Close a position."""
        return await self.adapter.cancel_order(position_id)
    
    async def set_stop_loss(self, position_id: str, sl: Decimal) -> bool:
        """Set stop loss for position."""
        return await self.adapter.modify_order(position_id, new_sl=sl)
    
    async def set_take_profit(self, position_id: str, tp: Decimal) -> bool:
        """Set take profit for position."""
        return await self.adapter.modify_order(position_id, new_tp=tp)


# Example usage
if __name__ == "__main__":
    async def example():
        adapter = CTraderAdapter(
            client_id="your_client_id",
            client_secret="your_client_secret",
        )
        
        try:
            await adapter.connect()
            
            # Place a market order
            order = await adapter.place_order(Order(
                symbol="EURUSD",
                order_type=OrderType.MARKET,
                side=OrderSide.BUY,
                volume=Decimal("0.1"),
            ))
            
            logger.info(f"Order placed: {order.broker_order_id}")
            
        finally:
            await adapter.disconnect()
    
    asyncio.run(example())