#!/usr/bin/env python3
"""
Live Paper Trading Script using MetaTrader 5 (MT5) Demo Account
Connects to MT5, receives real-time tick data, and executes a simple moving average crossover strategy.
"""

import asyncio
import signal
import sys
from datetime import UTC, datetime
from decimal import Decimal
from typing import Dict, List
import os
import glob

import MetaTrader5 as mt5
from loguru import logger

# Add the project root to the path so we can import our modules
sys.path.append(".")

from src.data.models import Order, OrderSide, OrderType, PositionSide
from src.execution.brokers.mt5_broker import MT5BrokerAdapter
from src.execution.position_manager import PositionManager
from src.infra.config.settings import settings


class MovingAverageCrossStrategy:
    """Simple moving average crossover strategy for demonstration."""

    def __init__(self, symbol: str, fast_period: int = 10, slow_period: int = 20):
        self.symbol = symbol
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.prices: List[float] = []
        self.fast_ma: float = 0.0
        self.slow_ma: float = 0.0
        self.position: PositionSide = PositionSide.FLAT  # Track our desired position

    def update_price(self, price: float) -> PositionSide:
        """Update price history and calculate moving averages.
        Returns the desired position (LONG, SHORT, or FLAT)."""
        self.prices.append(price)
        if len(self.prices) > self.slow_period:
            self.prices.pop(0)

        if len(self.prices) < self.slow_period:
            return self.position  # Not enough data yet

        # Calculate moving averages
        self.fast_ma = sum(self.prices[-self.fast_period:]) / self.fast_period
        self.slow_ma = sum(self.prices[-self.slow_period:]) / self.slow_period

        # Generate signal
        if self.fast_ma > self.slow_ma and self.position != PositionSide.LONG:
            return PositionSide.LONG
        elif self.fast_ma < self.slow_ma and self.position != PositionSide.SHORT:
            return PositionSide.SHORT
        else:
            return self.position  # Hold current position

    def get_signal(self) -> PositionSide:
        """Get current signal without updating."""
        return self.position


def find_mt5_terminal() -> str | None:
    """
    Attempt to locate the MetaTrader 5 terminal64.exe executable in common installation locations.
    Returns the directory containing terminal64.exe if found, otherwise None.
    """
    # Common installation paths
    program_files = [
        r"C:\Program Files\MetaTrader 5",
        r"C:\Program Files (x86)\MetaTrader 5"
    ]
    
    # User-specific paths (AppData)
    local_app_data = os.getenv('LOCALAPPDATA')
    app_data = os.getenv('APPDATA')
    user_paths = []
    if local_app_data:
        user_paths.append(os.path.join(local_app_data, 'MetaQuotes', 'Terminal'))
    if app_data:
        user_paths.append(os.path.join(app_data, 'MetaQuotes', 'Terminal'))
    
    all_paths = program_files + user_paths
    
    # Check program files directories (direct executable)
    for path in program_files:
        terminal_exe = os.path.join(path, 'terminal64.exe')
        if os.path.isfile(terminal_exe):
            return path  # Return the directory containing terminal64.exe
    
    # Check user directories (need to find the latest broker folder)
    for user_path in user_paths:
        if not os.path.isdir(user_path):
            continue
        # Look for subdirectories (broker folders) containing terminal64.exe
        try:
            broker_dirs = [d for d in os.listdir(user_path) 
                          if os.path.isdir(os.path.join(user_path, d))]
            # Sort by modification time to get the most recent
            broker_dirs.sort(key=lambda d: os.path.getmtime(os.path.join(user_path, d)), reverse=True)
            for broker_dir in broker_dirs:
                terminal_exe = os.path.join(user_path, broker_dir, 'terminal64.exe')
                if os.path.isfile(terminal_exe):
                    return os.path.join(user_path, broker_dir)  # Return the broker-specific directory
        except (PermissionError, FileNotFoundError):
            continue
    
    return None


async def main():
    """Main function to run the live paper trading bot."""
    # Setup logging
    logger.remove()
    logger.add(sys.stdout, format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}", level="INFO")
    logger.add("logs/paper_trading_{time:YYYY-MM-DD}.log", rotation="1 day", retention="7 days", level="DEBUG")

    logger.info("Starting Live Paper Trading Bot with MT5")

    # Load MT5 credentials from environment/settings
    mt5_login = settings.mt5_login
    mt5_password = settings.mt5_password
    mt5_server = settings.mt5_server
    mt5_path = settings.mt5_path

    # If MT5 path not set, try to find it automatically
    if not mt5_path:
        logger.info("MT5_PATH not set in environment, attempting to auto-detect MT5 installation...")
        auto_path = find_mt5_terminal()
        if auto_path:
            mt5_path = auto_path
            logger.info(f"Auto-detected MT5 installation at: {mt5_path}")
        else:
            logger.warning("Could not auto-detect MT5 installation. Please install MetaTrader 5 or set MT5_PATH in .env")

    if not all([mt5_login, mt5_password, mt5_server]):
        logger.error("MT5 credentials not found in environment variables. Please set MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in .env")
        sys.exit(1)

    logger.info(f"Connecting to MT5: {mt5_login}@{mt5_server}")
    if mt5_path:
        logger.info(f"Using MT5 path: {mt5_path}")

    # Initialize components
    broker = MT5BrokerAdapter()
    # Override the path if we found one
    if mt5_path:
        broker._path = mt5_path
    position_manager = PositionManager()
    strategy = MovingAverageCrossStrategy(symbol="EURUSD", fast_period=10, slow_period=20)

    # Connect to MT5
    try:
        await broker.connect()
        logger.info("Successfully connected to MT5")
    except Exception as e:
        logger.error(f"Failed to connect to MT5: {e}")
        logger.error("Please ensure:")
        logger.error("1. MetaTrader 5 is installed")
        logger.error("2. You have a valid demo account")
        logger.error("3. The MT5 terminal is running and logged in")
        logger.error("4. If using a custom path, set MT5_PATH in .env to the terminal directory")
        sys.exit(1)

    # Get account info
    try:
        account_info = await broker.get_account_info()
        logger.info(f"Account: {account_info.login}, Balance: {account_info.balance}, Equity: {account_info.equity}")
    except Exception as e:
        logger.error(f"Failed to get account info: {e}")

    # Symbol information
    symbol_info = mt5.symbol_info("EURUSD")
    if not symbol_info:
        logger.error("Failed to get symbol info for EURUSD")
        await broker.disconnect()
        sys.exit(1)

    if not symbol_info.visible:
        logger.info("EURUSD is not visible in MarketWatch, adding it...")
        if not mt5.symbol_select("EURUSD", True):
            logger.error("Failed to select EURUSD in MarketWatch")
            await broker.disconnect()
            sys.exit(1)

    # Trading parameters
    lot_size = 0.01  # Micro lot for paper trading
    max_positions = 1

    # Signal to track last signal to avoid duplicate orders
    last_signal = PositionSide.FLAT

    # Graceful shutdown handling
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.info("Received shutdown signal")
        shutdown_event.set()

    # Register signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    # Main trading loop
    logger.info("Starting main trading loop...")
    try:
        while not shutdown_event.is_set():
            # Get latest tick
            tick = mt5.symbol_info_tick("EURUSD")
            if not tick:
                logger.warning("No tick data received, retrying...")
                await asyncio.sleep(1)
                continue

            # Use mid-price for simplicity
            price = (tick.bid + tick.ask) / 2
            logger.debug(f"Received tick: Bid={tick.bid}, Ask={tick.ask}, Mid={price:.5f}")

            # Update strategy and get signal
            desired_position = strategy.update_price(price)

            # Log trading info
            logger.info(f"Price: {price:.5f} | Fast MA: {strategy.fast_ma:.5f} | Slow MA: {strategy.slow_ma:.5f} | Signal: {desired_position.name}")

            # Check current position from position manager
            current_positions = position_manager.get_open_positions()
            eurusd_position = None
            for pos in current_positions:
                if pos.symbol == "EURUSD":
                    eurusd_position = pos
                    break

            current_position_side = PositionSide.FLAT
            if eurusd_position:
                current_position_side = PositionSide.LONG if eurusd_position.direction.name == "LONG" else PositionSide.SHORT

            logger.info(f"Current position: {current_position_side.name} (Volume: {eurusd_position.volume if eurusd_position else 0})")

            # Determine if we need to trade
            if desired_position != current_position_side and desired_position != PositionSide.FLAT:
                # We need to open a position in the desired direction
                # First, close any existing opposite position
                if current_position_side != PositionSide.FLAT and current_position_side != desired_position:
                    logger.info(f"Closing existing {current_position_side.name} position")
                    close_order = Order(
                        symbol="EURUSD",
                        order_type=OrderType.MARKET,
                        side=OrderSide.SELL if current_position_side == PositionSide.LONG else OrderSide.BUY,
                        volume=eurusd_position.volume if eurusd_position else Decimal(lot_size),
                        price=Decimal(str(tick.bid if current_position_side == PositionSide.LONG else tick.ask)),
                        client_order_id=f"close_{int(datetime.now(UTC).timestamp())}",
                    )
                    try:
                        result = await broker.place_order(close_order)
                        logger.info(f"Close order result: {result.status} - {result.comment}")
                        # Wait a bit for the order to fill
                        await asyncio.sleep(2)
                    except Exception as e:
                        logger.error(f"Error placing close order: {e}")

                # Open new position
                order_side = OrderSide.BUY if desired_position == PositionSide.LONG else OrderSide.SELL
                order_price = Decimal(str(tick.ask if order_side == OrderSide.BUY else tick.bid))
                open_order = Order(
                    symbol="EURUSD",
                    order_type=OrderType.MARKET,
                    side=order_side,
                    volume=Decimal(lot_size),
                    price=order_price,
                    client_order_id=f"open_{int(datetime.now(UTC).timestamp())}",
                )
                logger.info(f"Opening {desired_position.name} position: {order_side.name} {lot_size} lots at {order_price}")
                try:
                    result = await broker.place_order(open_order)
                    logger.info(f"Open order result: {result.status} - {result.comment}")
                    if result.status.name == "FILLED":
                        # Update our internal position tracking (position manager will be updated via events in a real system)
                        # For simplicity, we'll just log and rely on position manager updates from separate task
                        pass
                except Exception as e:
                    logger.error(f"Error placing open order: {e}")

                last_signal = desired_position
                await asyncio.sleep(5)  # Wait after trading to avoid overtrading

            elif desired_position == PositionSide.FLAT and current_position_side != PositionSide.FLAT:
                # Close position if signal goes flat
                logger.info("Signal flattened, closing position")
                close_order = Order(
                    symbol="EURUSD",
                    order_type=OrderType.MARKET,
                    side=OrderSide.SELL if current_position_side == PositionSide.LONG else OrderSide.BUY,
                    volume=eurusd_position.volume if eurusd_position else Decimal(lot_size),
                    price=Decimal(str(tick.bid if current_position_side == PositionSide.LONG else tick.ask)),
                    client_order_id=f"close_flat_{int(datetime.now(UTC).timestamp())}",
                )
                try:
                    result = await broker.place_order(close_order)
                    logger.info(f"Close order result: {result.status} - {result.comment}")
                except Exception as e:
                    logger.error(f"Error placing close order: {e}")
                await asyncio.sleep(5)

            # Update position manager with current MT5 positions (simplified - in reality we'd use events)
            # For this demo, we'll periodically refresh positions from MT5
            await asyncio.sleep(1)  # Main loop delay

    except Exception as e:
        logger.exception(f"Error in main loop: {e}")
    finally:
        logger.info("Shutting down...")
        await broker.disconnect()
        logger.info("Disconnected from MT5")
        logger.info("Paper trading bot stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        sys.exit(0)
EOF