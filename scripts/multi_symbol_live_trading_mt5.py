#!/usr/bin/env python3
"""
Multi-symbol live paper trading script for MetaTrader 5.
This script connects to MT5, subscribes to tick data for multiple symbols,
and runs a simple moving average crossover strategy for each symbol.
It can run in simulation mode (no actual orders) or live trading mode.
"""

import MetaTrader5 as mt5
import time
import logging
import os
from datetime import datetime
from typing import Dict
import sys
import numpy as np

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
SIMULATE_TRADING = os.getenv("SIMULATE_TRADING", "0") == "1"

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/multi_symbol_live_trading.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("multi_symbol_live_trading")


class MovingAverageCrossover:
    """Simple Moving Average Crossover strategy."""

    def __init__(self, symbol: str, fast_period: int = 10, slow_period: int = 20, lot_size: float = 0.01):
        self.symbol = symbol
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.lot_size = lot_size
        self.prices = []  # Store recent prices for MA calculation
        self.position = 0  # 0: no position, 1: long, -1: short
        self.ticket = None  # MT5 ticket for the open position
        self.symbol_info = None  # Cache symbol info

    def _get_symbol_info(self):
        """Get and cache symbol info."""
        if self.symbol_info is None:
            self.symbol_info = mt5.symbol_info(self.symbol)
            if self.symbol_info is None:
                logger.error(f"Failed to get symbol info for {self.symbol}")
                return False
            # Ensure symbol is selected in MarketWatch
            if not mt5.symbol_select(self.symbol, True):
                logger.error(f"Failed to select symbol {self.symbol}")
                return False
        return True

    def update_price(self, price: float) -> None:
        """Update price history and calculate moving averages."""
        self.prices.append(price)
        # Keep only the necessary number of prices
        if len(self.prices) > self.slow_period:
            self.prices.pop(0)

    def get_signal(self) -> int:
        """
        Generate trading signal based on MA crossover.
        Returns: 1 (buy), -1 (sell), 0 (hold)
        """
        if len(self.prices) < self.slow_period:
            return 0  # Not enough data

        # Calculate moving averages
        ma_fast = np.mean(self.prices[-self.fast_period:])
        ma_slow = np.mean(self.prices[-self.slow_period:])

        # Generate signal
        if ma_fast > ma_slow and self.position <= 0:
            return 1  # Buy signal
        elif ma_fast < ma_slow and self.position >= 0:
            return -1  # Sell signal
        else:
            return 0  # Hold

    def _calculate_lot_size(self) -> float:
        """Calculate a valid lot size based on symbol constraints."""
        if not self._get_symbol_info():
            return 0.01  # fallback

        # Ensure lot size is within min/max and step
        lot = max(self.symbol_info.volume_min, min(self.lot_size, self.symbol_info.volume_max))
        # Adjust to step size
        step = self.symbol_info.volume_step
        lot = round(lot / step) * step
        # Ensure it's not less than min after rounding
        lot = max(lot, self.symbol_info.volume_min)
        return lot

    def execute_trade(self, signal: int) -> None:
        """Execute trade based on signal."""
        if signal == 0:
            return

        # Get symbol info for lot size and pricing
        if not self._get_symbol_info():
            return

        # Get current market price
        tick = mt5.symbol_info_tick(self.symbol)
        if not tick:
            logger.error(f"Failed to get tick for {self.symbol}")
            return

        # Calculate valid lot size
        lot = self._calculate_lot_size()
        if lot <= 0:
            logger.error(f"Invalid lot size calculated for {self.symbol}")
            return

        # Determine order type and price
        if signal == 1 and self.position <= 0:  # Buy signal
            action = mt5.TRADE_ACTION_DEAL
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
            # Close existing short position if any
            if self.position == -1:
                self.close_position()
        elif signal == -1 and self.position >= 0:  # Sell signal
            action = mt5.TRADE_ACTION_DEAL
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
            # Close existing long position if any
            if self.position == 1:
                self.close_position()
        else:
            return  # No action needed

        if SIMULATE_TRADING:
            logger.info(f"[SIMULATION] Would place order: {self.symbol} {'BUY' if signal == 1 else 'SELL'} {lot} lots at {price}")
            # In simulation, we still set the ticket and position for tracking
            self.ticket = 0  # fake ticket
            self.position = signal
            return

        # Prepare trade request
        request = {
            "action": action,
            "symbol": self.symbol,
            "volume": lot,
            "type": order_type,
            "price": price,
            "deviation": 50,  # Increased deviation to allow for slippage
            "magic": 123456,
            "comment": "Python script MA cross",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,  # Allow partial fill or return
        }

        # Send trade request with retry on requote
        max_retries = 3
        for attempt in range(max_retries):
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                self.ticket = result.order
                self.position = signal
                logger.info(f"Order placed: {self.symbol} {'BUY' if signal == 1 else 'SELL'} {lot} lots at {price}")
                return
            elif result.retcode == mt5.TRADE_RETCODE_REQUOTE:
                # Requote - try again with the new price
                logger.warning(f"Requote for {self.symbol}, retrying... ({attempt+1}/{max_retries})")
                # Update price from a new tick
                time.sleep(0.1)
                tick = mt5.symbol_info_tick(self.symbol)
                if not tick:
                    logger.error(f"Failed to get tick for {self.symbol} on requote retry")
                    break
                if signal == 1 and self.position <= 0:
                    price = tick.ask
                elif signal == -1 and self.position >= 0:
                    price = tick.bid
                request["price"] = price
            else:
                logger.error(f"Order failed for {self.symbol}, retcode={result.retcode}, comment={result.comment}")
                break

    def close_position(self) -> None:
        """Close the current position."""
        if self.ticket is None:
            return

        if SIMULATE_TRADING:
            logger.info(f"[SIMULATION] Would close position for ticket {self.ticket} ({self.symbol})")
            self.ticket = None
            self.position = 0
            return

        # Get position details
        positions = mt5.positions_get(ticket=self.ticket)
        if not positions:
            logger.warning(f"No position found for ticket {self.ticket}")
            self.ticket = None
            self.position = 0
            return

        pos = positions[0]
        # Determine close type and price
        if pos.type == mt5.POSITION_TYPE_BUY:
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(self.symbol).bid
        else:  # POSITION_TYPE_SELL
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(self.symbol).ask

        # Close request
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "position": self.ticket,
            "symbol": self.symbol,
            "volume": pos.volume,
            "type": order_type,
            "price": price,
            "deviation": 50,
            "magic": 123456,
            "comment": "Python script close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_RETURN,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Position close failed for {self.symbol}, retcode={result.retcode}, comment={result.comment}")
            return

        logger.info(f"Position closed: {self.symbol} at {price}")
        self.ticket = None
        self.position = 0


def initialize_mt5() -> bool:
    """Initialize MT5 connection."""
    if not mt5.initialize():
        logger.error("MT5 initialize() failed")
        mt5.shutdown()
        return False

    # Login if credentials are provided
    login_str = os.getenv("MT5_LOGIN")
    password = os.getenv("MT5_PASSWORD")
    server = os.getenv("MT5_SERVER")

    if login_str and password and server:
        try:
            login = int(login_str)
        except ValueError:
            logger.error(f"MT5_LOGIN must be an integer, got: {login_str}")
            mt5.shutdown()
            return False

        if not mt5.login(login, password=password, server=server):
            logger.error(f"MT5 login failed: {mt5.last_error()}")
            mt5.shutdown()
            return False
        logger.info(f"MT5 logged in: account {login}, server {server}")
    else:
        logger.warning("MT5 login credentials not provided, using current terminal")

    return True


def main():
    """Main function to run multi-symbol live trading."""
    # Symbols to trade
    symbols = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"]  # Add or remove as needed

    # Initialize MT5
    if not initialize_mt5():
        return

    # Show account info
    account_info = mt5.account_info()
    if account_info:
        logger.info(f"Account: {account_info.login}, Balance: {account_info.balance}, Equity: {account_info.equity}")

    # Create strategy instances
    strategies: Dict[str, MovingAverageCrossover] = {}
    for symbol in symbols:
        strategies[symbol] = MovingAverageCrossover(symbol)

    # Track last tick time to avoid processing the same tick multiple times
    last_tick_time: Dict[str, int] = {symbol: 0 for symbol in symbols}

    mode = "SIMULATION" if SIMULATE_TRADING else "LIVE"
    logger.info(f"Starting multi-symbol live trading in {mode} mode...")

    try:
        while True:
            for symbol in symbols:
                # Get latest tick
                tick = mt5.symbol_info_tick(symbol)
                if not tick:
                    continue

                # Check if we have a new tick
                if tick.time == last_tick_time[symbol]:
                    continue
                last_tick_time[symbol] = tick.time

                # Use bid price for simplicity (or you can use mid-price)
                price = (tick.bid + tick.ask) / 2

                # Update strategy
                strategy = strategies[symbol]
                strategy.update_price(price)

                # Get signal and execute trade
                signal = strategy.get_signal()
                if signal != 0:
                    logger.info(f"{symbol}: Price={price:.5f}, Signal={'BUY' if signal==1 else 'SELL'}")
                    strategy.execute_trade(signal)
                else:
                    # Log occasionally to show we're alive
                    if tick.time % 60 == 0:  # Log once per minute
                        logger.debug(f"{symbol}: Price={price:.5f}, Holding, MA Fast/SMA not ready or no crossover")

            # Sleep briefly to avoid high CPU usage
            time.sleep(0.1)

    except KeyboardInterrupt:
        logger.info("Received interrupt signal, shutting down...")
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
    finally:
        # Close all positions before exiting
        logger.info("Closing all open positions...")
        for symbol, strategy in strategies.items():
            if strategy.position != 0:
                strategy.close_position()

        # Shutdown MT5
        mt5.shutdown()
        logger.info("MT5 shutdown complete.")


if __name__ == "__main__":
    # Create logs directory if it doesn't exist
    os.makedirs("logs", exist_ok=True)
    main()