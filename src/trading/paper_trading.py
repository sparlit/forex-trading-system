"""
Paper Trading System - Full simulation for strategy validation.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import pandas as pd
from loguru import logger

from src.data.models import Order, OrderStatus, OrderType, Portfolio, Position
from src.data.storage.timescale import TimescaleDB
from src.risk.risk_engine import RiskEngine
from src.strategy.base import StrategyManager

logger = logging.getLogger(__name__)


class PaperTradingMode(str, Enum):
    SIMULATED = "simulated"      # Pure simulation with historical data
    REALTIME = "realtime"        # Real-time simulation with live data
    BACKTEST = "backtest"        # Backtest mode


@dataclass
class PaperAccount:
    """Paper trading account state"""
    account_id: str
    initial_balance: float
    balance: float
    equity: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    margin_used: float = 0.0
    free_margin: float = 0.0
    margin_level: float = 0.0
    currency: str = "USD"
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PaperPosition:
    """Paper trading position"""
    position_id: str
    account_id: str
    symbol: str
    strategy_id: str
    side: str  # "long" or "short"
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    swap: float = 0.0
    commission: float = 0.0
    margin_used: float = 0.0
    opened_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    is_open: bool = True


@dataclass
class PaperOrder:
    """Paper trading order"""
    order_id: str
    account_id: str
    symbol: str
    strategy_id: str
    side: str  # "buy" or "sell"
    order_type: str
    quantity: float
    price: float = 0.0
    stop_price: float = 0.0
    status: str = "pending"
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    commission: float = 0.0
    created_at: datetime = field(default_factory=datetime.utcnow)
    filled_at: datetime | None = None
    cancelled_at: datetime | None = None
    parent_order_id: str | None = None


class PaperTradingEngine:
    """Paper trading execution engine"""
    
    def __init__(self, 
                 config: PaperTradingMode = PaperTradingMode.REALTIME,
                 initial_balance: float = 100000.0,
                 commission_bps: float = 1.0,
                 slippage_bps: float = 2.0):
        self.mode = config
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        
        # Account
        self.account = PaperAccount(
            account_id=f"paper_{uuid.uuid4().hex[:8]}",
            initial_balance=initial_balance,
            balance=initial_balance,
            equity=initial_balance
        )
        
        # State
        self.positions: dict[str, PaperPosition] = {}
        self.orders: dict[str, PaperOrder] = {}
        self.fills: list = []
        
        # Market data cache
        self.price_cache: dict[str, float] = {}
        self.bid_cache: dict[str, float] = {}
        self.ask_cache: dict[str, float] = {}
        
        # Metrics
        self.total_trades = 0
        self.winning_trades = 0
        self.losing_trades = 0
        
        logger.info(f"PaperTradingEngine initialized: {self.account.account_id}, Balance: ${initial_balance:,.2f}")
    
    def update_market_price(self, symbol: str, bid: float, ask: float):
        """Update market price for simulation"""
        self.bid_cache[symbol] = bid
        self.ask_cache[symbol] = ask
        mid = (bid + ask) / 2
        self.price_cache[symbol] = mid
        
        # Update position PnL
        for pos in self.positions.values():
            if pos.symbol == symbol:
                pos.current_price = mid
                if pos.side == "long":
                    pos.unrealized_pnl = (mid - pos.entry_price) * pos.quantity
                else:
                    pos.unrealized_pnl = (pos.entry_price - mid) * pos.quantity
        
        self._update_account()
    
    def _update_account(self):
        """Update account equity and margin"""
        self.account.unrealized_pnl = sum(p.unrealized_pnl for p in self.positions.values())
        self.account.equity = self.account.balance + self.account.unrealized_pnl
        self.account.free_margin = self.account.equity - self.account.margin_used
        self.account.margin_level = (self.account.equity / self.account.margin_used * 100) if self.account.margin_used > 0 else 0
        self.account.updated_at = datetime.now(UTC)
    
    def submit_order(self, order: Order) -> PaperOrder:
        """Submit order to paper engine"""
        paper_order = PaperOrder(
            order_id=order.order_id or str(uuid.uuid4()),
            account_id=self.account.account_id,
            symbol=order.symbol,
            strategy_id=order.strategy_id,
            side=order.side.value,
            order_type=order.order_type.value,
            quantity=order.quantity,
            price=order.price,
            stop_price=order.stop_price
        )
        
        self.orders[paper_order.order_id] = paper_order
        logger.info(f"Paper order submitted: {paper_order.order_id} {paper_order.side} {paper_order.quantity} {paper_order.symbol}")
        
        # Process immediately for market orders
        if order.order_type == OrderType.MARKET:
            self._process_market_order(paper_order)
        
        return paper_order
    
    def _process_market_order(self, order: PaperOrder):
        """Process market order immediately"""
        bid = self.bid_cache.get(order.symbol, 0)
        ask = self.ask_cache.get(order.symbol, 0)
        
        if bid == 0 or ask == 0:
            order.status = OrderStatus.REJECTED.value
            logger.warning(f"Order {order.order_id} rejected: no market price")
            return
        
        # Apply slippage
        if order.side == "buy":
            fill_price = ask * (1 + self.slippage_bps / 10000)
        else:
            fill_price = bid * (1 - self.slippage_bps / 10000)
        
        commission = fill_price * order.quantity * (self.commission_bps / 10000)
        
        # Create fill
        fill = {
            "fill_id": str(uuid.uuid4()),
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "price": fill_price,
            "commission": commission,
            "timestamp": datetime.now(UTC)
        }
        self.fills.append(fill)
        
        # Update order
        order.status = OrderStatus.FILLED.value
        order.filled_quantity = order.quantity
        order.avg_fill_price = fill_price
        order.commission = commission
        order.filled_at = datetime.now(UTC)
        
        # Create/update position
        self._update_position_from_fill(fill)
        
        self.total_trades += 1
        logger.info(f"Market order filled: {order.order_id} @ {fill_price:.5f}")
    
    def _process_limit_order(self, order: PaperOrder):
        """Process limit order - check if fillable"""
        current_price = self.price_cache.get(order.symbol, 0)
        if current_price == 0:
            return
        
        if order.side == "buy" and current_price <= order.price:
            fill_price = min(current_price, order.price)
        elif order.side == "sell" and current_price >= order.price:
            fill_price = max(current_price, order.price)
        else:
            return  # Not fillable
        
        commission = fill_price * order.quantity * (self.commission_bps / 10000)
        
        fill = {
            "fill_id": str(uuid.uuid4()),
            "order_id": order.order_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "price": fill_price,
            "commission": commission,
            "timestamp": datetime.now(UTC)
        }
        self.fills.append(fill)
        
        order.status = OrderStatus.FILLED.value
        order.filled_quantity = order.quantity
        order.avg_fill_price = fill_price
        order.commission = commission
        order.filled_at = datetime.now(UTC)
        
        self._update_position_from_fill(fill)
        self.total_trades += 1
        logger.info(f"Limit order filled: {order.order_id} @ {fill_price:.5f}")
    
    def _update_position_from_fill(self, fill: dict):
        """Update or create position from fill"""
        symbol = fill["symbol"]
        side = "long" if fill["side"] == "buy" else "short"
        quantity = fill["quantity"]
        price = fill["price"]
        
        # Find existing position
        existing = None
        for pos in self.positions.values():
            if pos.symbol == symbol and pos.side == side and pos.is_open:
                existing = pos
                break
        
        if existing:
            # Average entry price
            total_qty = existing.quantity + quantity
            existing.entry_price = (existing.entry_price * existing.quantity + price * quantity) / total_qty
            existing.quantity = total_qty
            existing.unrealized_pnl = 0  # Will be recalculated
            existing.commission += fill["commission"]
        else:
            # New position
            position = PaperPosition(
                position_id=str(uuid.uuid4()),
                account_id=self.account.account_id,
                symbol=symbol,
                strategy_id="",  # Would come from order
                side=side,
                quantity=quantity,
                entry_price=price,
                current_price=price,
                commission=fill["commission"],
                stop_loss=0,
                take_profit=0
            )
            self.positions[position.position_id] = position
        
        self._update_account()
    
    def close_position(self, position_id: str, price: float | None = None) -> bool:
        """Close a position"""
        if position_id not in self.positions:
            return False
        
        position = self.positions[position_id]
        if not position.is_open:
            return False
        
        close_price = price or self.price_cache.get(position.symbol, position.current_price)
        
        if position.side == "long":
            pnl = (close_price - position.entry_price) * position.quantity
        else:
            pnl = (position.entry_price - close_price) * position.quantity
        
        pnl -= position.commission  # Subtract accumulated commission
        
        # Realize PnL
        position.realized_pnl = pnl
        position.unrealized_pnl = 0
        position.is_open = False
        position.updated_at = datetime.now(UTC)
        
        # Update account
        self.account.balance += position.quantity * close_price
        self.account.realized_pnl += pnl
        
        if pnl > 0:
            self.winning_trades += 1
        else:
            self.losing_trades += 1
        
        self._update_account()
        logger.info(f"Position closed: {position_id} PnL: ${pnl:.2f}")
        return True
    
    def check_stop_take_profit(self):
        """Check stop loss and take profit levels"""
        for pos_id, position in list(self.positions.items()):
            if not position.is_open:
                continue
            
            current = self.price_cache.get(position.symbol, position.current_price)
            
            if position.side == "long":
                if position.stop_loss > 0 and current <= position.stop_loss:
                    self.close_position(pos_id, position.stop_loss)
                    logger.info(f"Stop loss hit: {pos_id} @ {position.stop_loss}")
                elif position.take_profit > 0 and current >= position.take_profit:
                    self.close_position(pos_id, position.take_profit)
                    logger.info(f"Take profit hit: {pos_id} @ {position.take_profit}")
            else:
                if position.stop_loss > 0 and current >= position.stop_loss:
                    self.close_position(pos_id, position.stop_loss)
                    logger.info(f"Stop loss hit: {pos_id} @ {position.stop_loss}")
                elif position.take_profit > 0 and current <= position.take_profit:
                    self.close_position(pos_id, position.take_profit)
                    logger.info(f"Take profit hit: {pos_id} @ {position.take_profit}")
    
    def get_account_summary(self) -> dict:
        return {
            "account_id": self.account.account_id,
            "balance": self.account.balance,
            "equity": self.account.equity,
            "unrealized_pnl": self.account.unrealized_pnl,
            "realized_pnl": self.account.realized_pnl,
            "margin_used": self.account.margin_used,
            "free_margin": self.account.free_margin,
            "margin_level": self.account.margin_level,
            "open_positions": len([p for p in self.positions.values() if p.is_open]),
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.winning_trades / self.total_trades if self.total_trades > 0 else 0
        }
    
    def get_positions(self) -> list[dict]:
        return [
            {
                "position_id": p.position_id,
                "symbol": p.symbol,
                "side": p.side,
                "quantity": p.quantity,
                "entry_price": p.entry_price,
                "current_price": p.current_price,
                "unrealized_pnl": p.unrealized_pnl,
                "realized_pnl": p.realized_pnl,
                "is_open": p.is_open,
                "opened_at": p.opened_at.isoformat()
            }
            for p in self.positions.values()
        ]
    
    def get_orders(self) -> list[dict]:
        return [
            {
                "order_id": o.order_id,
                "symbol": o.symbol,
                "side": o.side,
                "type": o.order_type,
                "quantity": o.quantity,
                "price": o.price,
                "status": o.status,
                "filled": o.filled_quantity,
                "avg_fill_price": o.avg_fill_price
            }
            for o in self.orders.values()
        ]


class PaperTradingService:
    """Paper trading service with backtesting support"""
    
    def __init__(self, 
                 timescaledb: TimescaleDB,
                 risk_engine: RiskEngine,
                 strategy_manager: StrategyManager,
                 mode: PaperTradingMode = PaperTradingMode.REALTIME,
                 initial_balance: float = 100000.0):
        self.engine = PaperTradingEngine(mode, initial_balance)
        self.timescaledb = timescaledb
        self.risk_engine = risk_engine
        self.strategy_manager = strategy_manager
        self.mode = mode
        
        self.running = False
        self.logger = logger
    
    async def start(self):
        self.running = True
        asyncio.create_task(self._trading_loop())
        asyncio.create_task(self._risk_loop())
        logger.info("PaperTradingService started")
    
    async def stop(self):
        self.running = False
        logger.info("PaperTradingService stopped")
    
    async def _trading_loop(self):
        while self.running:
            try:
                # Update market prices from live data
                await self._update_market_data()
                
                # Check stops/TPS
                self.engine.check_stop_take_profit()
                
                # Generate signals from strategies
                await self._generate_signals()
                
            except Exception as e:
                self.logger.error(f"Trading loop error: {e}")
            
            await asyncio.sleep(1)  # 1 second loop
    
    async def _risk_loop(self):
        while self.running:
            try:
                # Run risk checks
                alerts, _actions = await self.risk_engine.run_risk_checks(
                    portfolio=self._get_portfolio()
                )
                
                # Process risk alerts
                for alert in alerts:
                    self.logger.warning(f"Risk alert: {alert.message}")
                    
            except Exception as e:
                self.logger.error(f"Risk loop error: {e}")
            
            await asyncio.sleep(30)
    
    async def _update_market_data(self):
        """Update market prices from live data source."""
        # Fetch latest prices for all tracked symbols
        for symbol in list(self.engine.positions.keys()):
            try:
                # Would use data connector to fetch latest price
                logger.debug(f"Market data update for {symbol} (stub)")
            except Exception as e:
                logger.error(f"Failed to update market data for {symbol}: {e}")

    async def _generate_signals(self):
        """Generate signals from strategy manager."""
        # Would get market data and process through strategies
        try:
            for strategy_id in self.strategies:
                logger.debug(f"Generating signals for strategy {strategy_id} (stub)")
        except Exception as e:
            logger.error(f"Failed to generate signals: {e}")
    
    def _get_portfolio(self) -> Portfolio:
        """Convert paper account to Portfolio model"""
        positions = []
        for pos in self.engine.positions.values():
            if pos.is_open:
                positions.append(Position(
                    position_id=pos.position_id,
                    symbol=pos.symbol,
                    strategy_id=pos.strategy_id,
                    side=pos.side,
                    quantity=pos.quantity,
                    entry_price=pos.entry_price,
                    current_price=pos.current_price,
                    unrealized_pnl=pos.unrealized_pnl,
                    realized_pnl=pos.realized_pnl,
                    is_open=pos.is_open
                ))
        
        return Portfolio(
            account_id=self.engine.account.account_id,
            balance=self.engine.account.balance,
            equity=self.engine.account.equity,
            unrealized_pnl=self.engine.account.unrealized_pnl,
            realized_pnl=self.engine.account.realized_pnl,
            positions=positions
        )
    
    def get_status(self) -> dict[str, Any]:
        return {
            "mode": self.mode.value,
            "running": self.running,
            "account": self.engine.get_account_summary(),
            "positions": self.engine.get_positions(),
            "orders": self.engine.get_orders()
        }


class BacktestEngine:
    """Vectorized backtesting engine"""
    
    def __init__(self, 
                 initial_capital: float = 100000.0,
                 commission_bps: float = 1.0,
                 slippage_bps: float = 2.0):
        self.initial_capital = initial_capital
        self.commission_bps = commission_bps
        self.slippage_bps = slippage_bps
        
        self.results: dict = {}
    
    def run_backtest(self, 
                     strategy, 
                     price_data: dict[str, pd.DataFrame],
                     start_date: str,
                     end_date: str) -> dict:
        """Run vectorized backtest"""
        
        # Align all data to common timeline
        # Generate signals
        # Simulate trades
        # Calculate metrics
        
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe_ratio": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "total_trades": 0,
            "equity_curve": [],
            "trades": []
        }
    
    def _vectorized_simulation(self, signals: pd.DataFrame, prices: pd.DataFrame) -> dict:
        """Fast vectorized portfolio simulation."""
        if signals.empty or prices.empty:
            return {
                "equity_curve": pd.Series(dtype=float),
                "trades": [],
                "total_pnl": 0.0,
                "sharpe": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
            }

        # Merge signals with prices on timestamp
        pnl_series = pd.Series(0.0, index=prices.index)
        trades = []
        position = 0
        entry_price = 0.0

        for _, signal in signals.iterrows():
            ts = signal.get("timestamp")
            side = signal.get("side", "")
            price = prices.loc[ts, "close"] if ts in prices.index else None
            if price is None:
                continue

            if side == "BUY" and position <= 0:
                position = 1
                entry_price = float(price)
            elif side == "SELL" and position >= 0:
                if position > 0:
                    trade_pnl = float(price) - entry_price
                    trades.append({"pnl": trade_pnl, "entry": entry_price, "exit": float(price)})
                position = -1
                entry_price = float(price)

        equity = pnl_series.cumsum()
        wins = [t for t in trades if t["pnl"] > 0]
        return {
            "equity_curve": equity,
            "trades": trades,
            "total_pnl": float(equity.iloc[-1]) if len(equity) > 0 else 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "win_rate": len(wins) / len(trades) if trades else 0.0,
        }
    
    def walk_forward_analysis(self, 
                              strategy, 
                              price_data: dict[str, pd.DataFrame],
                              train_window: int = 252,
                              test_window: int = 63,
                              step: int = 21) -> list[dict]:
        """Walk-forward optimization"""
        results = []
        
        # Walk forward through time
        # Train on window, test on next window
        # Step forward
        
        return results