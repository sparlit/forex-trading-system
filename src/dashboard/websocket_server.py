"""
Elite Autonomous Quantum Trading System - WebSocket Server
Real-time data streaming for dashboard updates.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


class DashboardWebSocketServer:
    """WebSocket server for real-time dashboard updates."""
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8765):
        self.host = host
        self.port = port
        self.clients: set[WebSocketServerProtocol] = set()
        self.server = None
        self.running = False
        self.latest_data: dict[str, Any] = {}
        
    async def start(self):
        """Start the WebSocket server."""
        self.server = await websockets.serve(
            self._handle_client,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10,
        )
        self.running = True
        logger.info(f"🌐 WebSocket server started on ws://{self.host}:{self.port}")
        
        # Start broadcast loop
        asyncio.create_task(self._broadcast_loop())
    
    async def stop(self):
        """Stop the WebSocket server."""
        self.running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        logger.info("🌐 WebSocket server stopped")
    
    async def _handle_client(self, websocket: WebSocketServerProtocol):
        """Handle new client connection."""
        self.clients.add(websocket)
        client_ip = websocket.remote_address[0] if websocket.remote_address else "unknown"
        logger.info(f"📱 Dashboard client connected: {client_ip} (total: {len(self.clients)})")
        
        try:
            # Send initial data
            if self.latest_data:
                await websocket.send(json.dumps({
                    "type": "init",
                    "data": self.latest_data,
                    "timestamp": datetime.now(UTC).isoformat(),
                }))
            
            # Keep connection alive
            async for message in websocket:
                try:
                    msg = json.loads(message)
                    await self._handle_message(websocket, msg)
                except json.JSONDecodeError:
                    raise NotImplementedError("Not implemented")
                    
        except websockets.exceptions.ConnectionClosed:
            raise NotImplementedError("Not implemented")
        except Exception as e:
            logger.error(f"WebSocket client error: {e}")
        finally:
            self.clients.discard(websocket)
            logger.info(f"📱 Dashboard client disconnected: {client_ip} (total: {len(self.clients)})")
    
    async def _handle_message(self, websocket: WebSocketServerProtocol, msg: dict):
        """Handle incoming message from client."""
        msg_type = msg.get("type")
        
        if msg_type == "ping":
            await websocket.send(json.dumps({"type": "pong", "timestamp": datetime.now(UTC).isoformat()}))
        elif msg_type == "subscribe":
            # Client can subscribe to specific data streams
            raise NotImplementedError("Not implemented")
        elif msg_type == "command":
            # Handle commands from dashboard
            raise NotImplementedError("Not implemented")
    
    async def _broadcast_loop(self):
        """Periodically broadcast updates to all clients."""
        while self.running:
            if self.clients and self.latest_data:
                message = json.dumps({
                    "type": "update",
                    "data": self.latest_data,
                    "timestamp": datetime.now(UTC).isoformat(),
                })
                
                # Send to all connected clients
                disconnected = set()
                for client in self.clients:
                    try:
                        await client.send(message)
                    except websockets.exceptions.ConnectionClosed:
                        disconnected.add(client)
                    except Exception:
                        disconnected.add(client)
                
                # Clean up disconnected clients
                self.clients -= disconnected
            
            await asyncio.sleep(0.5)  # 2 Hz update rate
    
    def update_data(self, data: dict[str, Any]):
        """Update the latest data to broadcast."""
        self.latest_data.update(data)
    
    def broadcast_event(self, event_type: str, event_data: dict):
        """Broadcast a specific event."""
        if self.clients:
            message = json.dumps({
                "type": "event",
                "event_type": event_type,
                "data": event_data,
                "timestamp": datetime.now(UTC).isoformat(),
            })
            
            for client in self.clients:
                try:
                    asyncio.create_task(client.send(message))
                except Exception:
                    logging.getLogger(__name__).exception('Suppressed exception')


# Global WebSocket server instance
ws_server: DashboardWebSocketServer | None = None


async def get_ws_server(host: str = "0.0.0.0", port: int = 8765) -> DashboardWebSocketServer:
    """Get or create global WebSocket server."""
    global ws_server
    if ws_server is None:
        ws_server = DashboardWebSocketServer(host, port)
        await ws_server.start()
    return ws_server