"""

MT5 EA Bridge Server
=====================

Receives real-time data from MT5 EA and provides command interface.
Supports both ZeroMQ (low latency) and HTTP (fallback) transports.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from loguru import logger


def _utc_now() -> datetime:
    return datetime.now(UTC)


try:
    import zmq
    import zmq.asyncio
    ZMQ_AVAILABLE = True
except ImportError:
    ZMQ_AVAILABLE = False
    logger.warning("ZeroMQ not available, using HTTP only")

try:
    import uvicorn
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    FASTAPI_AVAILABLE = True
except ImportError:
    FASTAPI_AVAILABLE = False
    logger.warning("FastAPI not available")


@dataclass(slots=True)
class MarketData:
    """Market data from EA."""
    symbol: str
    bid: float
    ask: float
    last: float
    volume: int
    time: int
    time_msc: int
    flags: int
    volume_real: float
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(slots=True)
class AccountInfo:
    """Account info from EA."""
    login: int
    balance: float
    equity: float
    profit: float
    margin: float
    free_margin: float
    margin_level: float
    leverage: int
    currency: str
    name: str
    server: str
    trade_allowed: bool
    trade_expert: bool
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(slots=True)
class PositionData:
    """Position data from EA."""
    ticket: int
    symbol: str
    type: str  # "buy" or "sell"
    volume: float
    price_open: float
    price_current: float
    sl: float
    tp: float
    profit: float
    swap: float
    commission: float
    magic: int
    comment: str
    time_open: int
    time_update: int
    timestamp: datetime = field(default_factory=_utc_now)


@dataclass(slots=True)
class TradeEvent:
    """Trade event from EA."""
    trans_type: int
    order_type: int
    symbol: str
    volume: float
    price: float
    sl: float
    tp: float
    magic: int
    comment: str
    result_retcode: int
    result_deal: int
    result_order: int
    result_volume: float
    result_price: float
    result_comment: str
    timestamp: datetime = field(default_factory=_utc_now)


class EABridge:
    """
    Bridge server for MT5 EA communication.
    
    Handles:
    - Market data ingestion (ticks, Level 2)
    - Account info updates
    - Position tracking
    - Trade event notifications
    - Command dispatch to EA
    """
    
    def __init__(
        self,
        zmq_port: int = 5555,
        http_port: int = 8000,
        host: str = "0.0.0.0",
    ):
        self.zmq_port = zmq_port
        self.http_port = http_port
        self.host = host
        
        # State
        self._running = False
        self._zmq_context = None
        self._zmq_socket = None
        self._http_app = None
        self._http_server = None
        
        # Data storage
        self.latest_market_data: dict[str, MarketData] = {}
        self.latest_account_info: AccountInfo | None = None
        self.latest_positions: dict[int, PositionData] = {}
        self.trade_events: list[TradeEvent] = []
        
        # Connected EAs
        self.connected_eas: dict[str, dict] = {}
        
        # Callbacks
        self.on_market_data: Callable[[MarketData], None] | None = None
        self.on_account_info: Callable[[AccountInfo], None] | None = None
        self.on_positions: Callable[[dict[int, PositionData]], None] | None = None
        self.on_trade_event: Callable[[TradeEvent], None] | None = None
        self.on_ea_connected: Callable[[str, dict], None] | None = None
        self.on_ea_disconnected: Callable[[str], None] | None = None
        
        # Command queue for sending to EA
        self._command_queue: asyncio.Queue = asyncio.Queue()
        
        logger.info(f"EABridge initialized: ZMQ={zmq_port}, HTTP={http_port}")
    
    async def start(self) -> None:
        """Start the bridge server."""
        self._running = True
        
        # Start ZeroMQ if available
        if ZMQ_AVAILABLE:
            await self._start_zmq()
        
        # Start HTTP server
        if FASTAPI_AVAILABLE:
            await self._start_http()
        
        # Start command processor
        asyncio.create_task(self._process_commands())
        
        logger.info("EA Bridge started")
    
    async def stop(self) -> None:
        """Stop the bridge server."""
        self._running = False
        
        if self._zmq_socket:
            self._zmq_socket.close()
        if self._zmq_context:
            self._zmq_context.term()
        
        if self._http_server:
            self._http_server.should_exit = True
        
        logger.info("EA Bridge stopped")
    
    async def _start_zmq(self) -> None:
        """Start ZeroMQ subscriber socket."""
        self._zmq_context = zmq.asyncio.Context()
        self._zmq_socket = self._zmq_context.socket(zmq.SUB)
        self._zmq_socket.bind(f"tcp://{self.host}:{self.zmq_port}")
        self._zmq_socket.setsockopt(zmq.SUBSCRIBE, b"")
        
        # Start receiver task
        asyncio.create_task(self._zmq_receiver())
        logger.info(f"ZeroMQ listener started on tcp://{self.host}:{self.zmq_port}")
    
    async def _zmq_receiver(self) -> None:
        """Receive messages from ZeroMQ."""
        while self._running:
            try:
                message = await self._zmq_socket.recv_string()
                await self._handle_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"ZeroMQ receive error: {e}")
                await asyncio.sleep(1)
    
    async def _start_http(self) -> None:
        """Start HTTP server with FastAPI."""
        self._http_app = FastAPI(title="MT5 EA Bridge", version="1.0.0")
        self._setup_http_routes()
        
        config = uvicorn.Config(
            self._http_app,
            host=self.host,
            port=self.http_port,
            log_level="info",
        )
        self._http_server = uvicorn.Server(config)
        
        # Run in background
        asyncio.create_task(self._http_server.serve())
        logger.info(f"HTTP server started on http://{self.host}:{self.http_port}")
    
    def _setup_http_routes(self) -> None:
        """Setup HTTP routes."""
        from fastapi import Request
        
        @self._http_app.get("/health")
        async def health():
            return {
                "status": "ok",
                "connected_eas": len(self.connected_eas),
                "market_data_symbols": len(self.latest_market_data),
                "positions": len(self.latest_positions),
            }
        
        @self._http_app.post("/api/v1/ea/data")
        async def receive_data(request: Request):
            data = await request.json()
            await self._handle_message(json.dumps(data))
            return {"status": "ok"}
        
        @self._http_app.get("/api/v1/ea/commands")
        async def get_commands():
            commands = []
            while not self._command_queue.empty():
                try:
                    cmd = self._command_queue.get_nowait()
                    commands.append(cmd)
                except asyncio.QueueEmpty:
                    break
            return commands
        
        @self._http_app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            ea_id = f"ws_{id(websocket)}"
            self.connected_eas[ea_id] = {
                "type": "websocket",
                "connected_at": datetime.now(UTC),
                "websocket": websocket,
            }
            if self.on_ea_connected:
                self.on_ea_connected(ea_id, self.connected_eas[ea_id])
            
            try:
                while True:
                    data = await websocket.receive_text()
                    await self._handle_message(data)
                    
                    # Send any pending commands
                    while not self._command_queue.empty():
                        cmd = await self._command_queue.get()
                        await websocket.send_text(json.dumps(cmd))
                        
            except WebSocketDisconnect:
                logger.info(f"WebSocket client {ea_id} disconnected")
            finally:
                del self.connected_eas[ea_id]
                if self.on_ea_disconnected:
                    self.on_ea_disconnected(ea_id)
    
    async def _handle_message(self, message: str) -> None:
        """Handle incoming message from EA."""
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            
            if msg_type == "market_data":
                await self._handle_market_data(data)
            elif msg_type == "account_info":
                await self._handle_account_info(data)
            elif msg_type == "positions":
                await self._handle_positions(data)
            elif msg_type == "trade_event":
                await self._handle_trade_event(data)
            elif msg_type == "heartbeat":
                await self._handle_heartbeat(data)
            else:
                logger.warning(f"Unknown message type: {msg_type}")
                
        except json.JSONDecodeError:
            logger.error("Invalid JSON received")
        except Exception as e:
            logger.error(f"Error handling message: {e}")
    
    async def _handle_market_data(self, data: dict) -> None:
        """Handle market data update."""
        md = MarketData(
            symbol=data["symbol"],
            bid=data["bid"],
            ask=data["ask"],
            last=data["last"],
            volume=data["volume"],
            time=data["time"],
            time_msc=data["time_msc"],
            flags=data["flags"],
            volume_real=data["volume_real"],
        )
        
        self.latest_market_data[md.symbol] = md
        
        if self.on_market_data:
            self.on_market_data(md)
    
    async def _handle_account_info(self, data: dict) -> None:
        """Handle account info update."""
        ai = AccountInfo(
            login=data["login"],
            balance=data["balance"],
            equity=data["equity"],
            profit=data["profit"],
            margin=data["margin"],
            free_margin=data["free_margin"],
            margin_level=data["margin_level"],
            leverage=data["leverage"],
            currency=data["currency"],
            name=data["name"],
            server=data["server"],
            trade_allowed=data["trade_allowed"],
            trade_expert=data["trade_expert"],
        )
        
        self.latest_account_info = ai
        
        if self.on_account_info:
            self.on_account_info(ai)
    
    async def _handle_positions(self, data: dict) -> None:
        """Handle positions update."""
        positions = {}
        for pos_data in data.get("positions", []):
            pos = PositionData(
                ticket=pos_data["ticket"],
                symbol=pos_data["symbol"],
                type=pos_data["type"],
                volume=pos_data["volume"],
                price_open=pos_data["price_open"],
                price_current=pos_data["price_current"],
                sl=pos_data["sl"],
                tp=pos_data["tp"],
                profit=pos_data["profit"],
                swap=pos_data["swap"],
                commission=pos_data["commission"],
                magic=pos_data["magic"],
                comment=pos_data["comment"],
                time_open=pos_data["time_open"],
                time_update=pos_data["time_update"],
            )
            positions[pos.ticket] = pos
        
        self.latest_positions = positions
        
        if self.on_positions:
            self.on_positions(positions)
    
    async def _handle_trade_event(self, data: dict) -> None:
        """Handle trade event."""
        event = TradeEvent(
            trans_type=data["trans_type"],
            order_type=data["order_type"],
            symbol=data["symbol"],
            volume=data["volume"],
            price=data["price"],
            sl=data["sl"],
            tp=data["tp"],
            magic=data["magic"],
            comment=data["comment"],
            result_retcode=data["result_retcode"],
            result_deal=data["result_deal"],
            result_order=data["result_order"],
            result_volume=data["result_volume"],
            result_price=data["result_price"],
            result_comment=data["result_comment"],
        )
        
        self.trade_events.append(event)
        # Keep only last 1000 events
        if len(self.trade_events) > 1000:
            self.trade_events = self.trade_events[-500:]
        
        if self.on_trade_event:
            self.on_trade_event(event)
    
    async def _handle_heartbeat(self, data: dict) -> None:
        """Handle EA heartbeat."""
        ea_id = f"ea_{data.get('account', 'unknown')}"
        if ea_id not in self.connected_eas:
            self.connected_eas[ea_id] = {
                "type": "zmq",
                "connected_at": datetime.now(UTC),
                "account": data.get("account"),
                "version": data.get("ea_version"),
            }
            if self.on_ea_connected:
                self.on_ea_connected(ea_id, self.connected_eas[ea_id])
        
        self.connected_eas[ea_id]["last_heartbeat"] = datetime.now(UTC)
        self.connected_eas[ea_id]["connected"] = data.get("connected", True)
    
    async def _process_commands(self) -> None:
        """Process command queue."""
        while self._running:
            try:
                # Commands are pulled by EA via HTTP/WebSocket
                # This is where we'd push commands if using push model
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Command processor error: {e}")
    
    def send_command(self, command: dict) -> None:
        """Queue a command to be sent to EA."""
        self._command_queue.put_nowait(command)
    
    def send_order(
        self,
        symbol: str,
        action: str,  # "buy", "sell", "close"
        volume: float,
        price: float = 0,
        sl: float = 0,
        tp: float = 0,
        comment: str = "",
        magic: int = 123456,
    ) -> None:
        """Send order command to EA."""
        order_type_map = {
            "buy": 0,      # ORDER_TYPE_BUY
            "sell": 1,     # ORDER_TYPE_SELL
            "buy_limit": 2,
            "sell_limit": 3,
            "buy_stop": 4,
            "sell_stop": 5,
        }
        
        command = {
            "type": "order",
            "symbol": symbol,
            "action": action,
            "order_type": order_type_map.get(action.lower(), 0),
            "volume": volume,
            "price": price,
            "sl": sl,
            "tp": tp,
            "comment": comment,
            "magic": magic,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        
        self.send_command(command)
        logger.info(f"Queued order: {symbol} {action} {volume} lots")
    
    def send_close_position(self, ticket: int) -> None:
        """Send close position command."""
        command = {
            "type": "close_position",
            "ticket": ticket,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.send_command(command)
    
    def send_modify_position(self, ticket: int, sl: float, tp: float) -> None:
        """Send modify position command."""
        command = {
            "type": "modify_position",
            "ticket": ticket,
            "sl": sl,
            "tp": tp,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        self.send_command(command)
    
    def get_latest_market_data(self, symbol: str) -> MarketData | None:
        """Get latest market data for symbol."""
        return self.latest_market_data.get(symbol)
    
    def get_all_market_data(self) -> dict[str, MarketData]:
        """Get all latest market data."""
        return self.latest_market_data.copy()
    
    def get_account_info(self) -> AccountInfo | None:
        """Get latest account info."""
        return self.latest_account_info
    
    def get_positions(self) -> dict[int, PositionData]:
        """Get current positions."""
        return self.latest_positions.copy()
    
    def get_status(self) -> dict[str, Any]:
        """Get bridge status."""
        return {
            "running": self._running,
            "connected_eas": len(self.connected_eas),
            "market_data_symbols": len(self.latest_market_data),
            "positions": len(self.latest_positions),
            "trade_events": len(self.trade_events),
            "zmq_available": ZMQ_AVAILABLE,
            "http_available": FASTAPI_AVAILABLE,
        }


async def create_ea_bridge(
    zmq_port: int = 5555,
    http_port: int = 8000,
    host: str = "0.0.0.0",
) -> EABridge:
    """Create and start EA bridge."""
    bridge = EABridge(zmq_port=zmq_port, http_port=http_port, host=host)
    await bridge.start()
    return bridge
